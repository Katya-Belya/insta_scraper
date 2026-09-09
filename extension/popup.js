// Key used to remember the reviewed result in chrome.storage.local.
const STORAGE_KEY = "flyerResult";

// The three states a review can be in.
//
// "pending"  - nobody has reviewed this flyer yet
// "accepted" - the user confirmed the date the pipeline read
// "edited"   - the user replaced the date the pipeline read
const REVIEW_PENDING = "pending";
const REVIEW_ACCEPTED = "accepted";
const REVIEW_EDITED = "edited";

// Where the local Python extractor listens.
//
// Started with `python -m src.server`, which binds this exact port on the
// loopback interface. manifest.json grants the popup access to it.
const EXTRACTOR_URL = "http://127.0.0.1:8756/extract";

// The header the extractor reads the flyer's name from. The body is the image
// bytes and nothing else.
const FILENAME_HEADER = "X-Flyer-Filename";

// File types the pipeline can read. Kept in step with IMAGE_EXTENSIONS in
// src/pipeline.py, which is what the extractor itself checks against.
const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];

// Every message the popup can show about the flyer itself, as opposed to the
// review of it. Exactly one of these is on screen at any time.
//
// The tone decides the colour: plain for the states that are just progress,
// red for the ones the user has to do something about.
const STATES = {
  idle: {
    text: "Select a flyer to extract its event date.",
    tone: "",
  },
  processing: {
    text: "Reading the flyer...",
    tone: "is-working",
  },
  success: {
    text: "Found an event date. Review it below.",
    tone: "is-success",
  },
  noDateFound: {
    text: "No date was readable on this flyer. Use Edit to enter it.",
    tone: "is-error",
  },
  // The states a flyer can fail in name the file they are about. Nothing was
  // extracted from it, so it is not the flyer shown below, and saying which
  // file failed is the only way to tell the two apart.
  invalidFile: {
    text: (filename) =>
      `${filename} is not an image. Choose a JPG, JPEG, PNG, or WEBP.`,
    tone: "is-error",
  },
  connectionError: {
    text: "Cannot reach the extractor. Start it with: python -m src.server",
    tone: "is-error",
  },
  extractionError: {
    text: (filename) => `${filename} could not be read. Try another image.`,
    tone: "is-error",
  },
};

// The result of the most recent command-line pipeline run, if one has written
// extension/latest_result.js.
//
// The popup no longer depends on that file - a flyer selected here is
// extracted on demand instead - but a run that wrote it still opens the popup
// on its result, so the command-line workflow keeps working.
const latestPipelineResult = window.flyerResult ?? null;

// What the pipeline made of the flyer currently on screen ("ok",
// "no_date_found", "invalid_date").
//
// Deliberately not part of the reviewed result below: it belongs to the
// pipeline, a review never changes it, and the stored record holds only what
// the review is about. It is null when the popup restored a review from
// storage without having run the flyer through the pipeline in this session.
let pipelineStatus = latestPipelineResult ? latestPipelineResult.status : null;

// The canonical reviewed result the popup maintains.
//
// It is the single object that describes the flyer *after* review, and it is
// exactly what gets written to chrome.storage.local:
//
//     {
//       filename:          "august_happy_hour.jpg",
//       originalEventDate: "2027-08-04",  // what the pipeline read
//       eventDate:         "2027-08-05",  // what the review settled on
//       needsReview:       true,          // pipeline's "a human should look"
//       reviewStatus:      "edited"       // what the user did about it
//     }
//
// originalEventDate is never changed once the result is created, so the date
// the pipeline read stays available even after the user corrects it.
//
// null means there is nothing to review yet: no flyer has been selected and
// storage held no earlier review.
let reviewedResult = null;

// How many flyers have been selected so far.
//
// Reading a flyer takes a moment, and nothing stops the user from selecting
// another one while the first is still being read. Each extraction remembers
// its own number and gives up if a later one has started, so an earlier
// answer arriving late cannot replace a newer flyer's result.
let selectionCount = 0;

// Build a fresh, unreviewed result from the pipeline output.
function createReviewedResult(pipelineResult) {
  return {
    filename: pipelineResult.filename,
    originalEventDate: pipelineResult.eventDate,
    eventDate: pipelineResult.eventDate,
    needsReview: pipelineResult.needsReview,
    reviewStatus: REVIEW_PENDING,
  };
}

// Turn whatever chrome.storage.local gave us back into a canonical result.
//
// A stored review is only reused when it belongs to the flyer that is
// currently loaded. A newer pipeline run writes a different flyer, which has
// not been reviewed yet.
//
// Fields missing from the stored value fall back to the pipeline result, so a
// record written by an older version of the popup still produces all four
// review fields.
function restoreReviewedResult(pipelineResult, storedResult) {
  const freshResult = createReviewedResult(pipelineResult);

  if (!storedResult || storedResult.filename !== pipelineResult.filename) {
    return freshResult;
  }

  return {
    filename: freshResult.filename,
    originalEventDate:
      storedResult.originalEventDate ?? freshResult.originalEventDate,
    eventDate: storedResult.eventDate ?? freshResult.eventDate,
    needsReview: storedResult.needsReview ?? freshResult.needsReview,
    reviewStatus: storedResult.reviewStatus ?? freshResult.reviewStatus,
  };
}

// Turn a stored record into a canonical result when there is no pipeline
// result to check it against.
//
// This is the ordinary case now: the popup is opened, no flyer has been
// selected in this session, and the review from last time is what should be
// on screen. Missing fields fall back to values that describe an unreviewed
// flyer, so a record from an older popup version still opens.
function restoreStoredResult(storedResult) {
  return {
    filename: storedResult.filename,
    originalEventDate: storedResult.originalEventDate ?? null,
    eventDate: storedResult.eventDate ?? null,
    needsReview: storedResult.needsReview ?? false,
    reviewStatus: storedResult.reviewStatus ?? REVIEW_PENDING,
  };
}

// Show one of the STATES above.
//
// `filename` is only used by the states whose message names the file that
// failed.
function setState(stateName, filename) {
  const state = STATES[stateName];
  const element = document.getElementById("state-message");

  element.textContent =
    typeof state.text === "function" ? state.text(filename) : state.text;
  element.className = state.tone;
}

// Name the flyer the popup is currently about.
//
// This is the flyer of the result on screen, so that a file which failed to
// extract - and left the previous result in place - cannot look as though the
// date below belongs to it. While a flyer is being read it is the selection
// itself, because it is about to become that result.
function showFlyerName(filename) {
  document.getElementById("filename").textContent = filename ?? "";
}

// Switch the event date between the read-only span and the edit field.
function setEditing(editing) {
  document.getElementById("event-date").hidden = editing;
  document.getElementById("event-date-input").hidden = !editing;
  document.getElementById("edit").hidden = editing;
  document.getElementById("save").hidden = !editing;

  // Accept only applies to a result nobody has settled yet.
  //
  // Accepting a result while its date is still being edited would store the
  // old date, so Accept waits until the edit is saved. Once the review has
  // settled - "accepted", or "edited" with a date the user chose - there is
  // nothing left to accept, and accepting anyway would relabel a corrected
  // date as if it were the one the pipeline read.
  document.getElementById("accept").disabled =
    editing || reviewedResult.reviewStatus !== REVIEW_PENDING;
}

// Display the reviewed result in the popup.
function renderResult(result) {
  showFlyerName(result.filename);

  // The review section only means something once there is a result.
  document.getElementById("result").hidden = false;

  document.getElementById("needs-review").textContent =
    result.needsReview ? "Yes" : "No";

  // A flyer with no readable date has no event date to show yet.
  document.getElementById("event-date").textContent = result.eventDate ?? "";

  // The date the pipeline read is only worth showing once the review replaced
  // it with something else.
  const dateWasChanged = result.originalEventDate !== result.eventDate;
  document.getElementById("original-event-date-row").hidden = !dateWasChanged;
  document.getElementById("original-event-date").textContent =
    result.originalEventDate ?? "";

  // What the pipeline made of the flyer, which the review never changes.
  // A review restored from storage alone has no pipeline status to show, so
  // the row is hidden rather than left blank.
  document.getElementById("status-row").hidden = pipelineStatus === null;
  document.getElementById("status").textContent = pipelineStatus ?? "";

  document.getElementById("review-status").textContent = result.reviewStatus;

  // Showing a result always leaves the date read-only; editing starts only
  // when the user asks for it.
  setEditing(false);

  // Show the accepted state: there is nothing left to accept, so the
  // Accept button is switched off (by setEditing) and the popup says so.
  const accepted = result.reviewStatus === REVIEW_ACCEPTED;
  document.getElementById("message").textContent = accepted ? "Accepted!" : "";
}

// Show the popup with no flyer to review: the whole review section stays
// hidden and the only thing on offer is Select Flyer.
function renderIdle() {
  showFlyerName(null);
  document.getElementById("result").hidden = true;
  setState("idle");
}

// Write the canonical reviewed result to chrome.storage.local and redraw the
// popup.
function saveResult(onSaved) {
  chrome.storage.local.set({ [STORAGE_KEY]: reviewedResult }, () => {
    renderResult(reviewedResult);

    if (onSaved) {
      onSaved();
    }
  });
}

// chrome.storage.local is asynchronous, so the popup is filled in once the
// stored value comes back.
chrome.storage.local.get(STORAGE_KEY, (stored) => {
  const storedResult = stored[STORAGE_KEY];

  if (latestPipelineResult) {
    // A command-line run left a result here, so the popup opens on it.
    reviewedResult = restoreReviewedResult(latestPipelineResult, storedResult);
  } else if (storedResult && storedResult.filename) {
    // Nothing new was extracted, so the last review is what to show.
    reviewedResult = restoreStoredResult(storedResult);
  }

  if (reviewedResult === null) {
    renderIdle();
    return;
  }

  renderResult(reviewedResult);
  setState(reviewedResult.eventDate ? "success" : "noDateFound");
});

// The reviewed result is built once chrome.storage.local answers, so a click
// that lands before then has nothing to review yet.
function reviewIsReady() {
  return reviewedResult !== null;
}

// Whether the pipeline is able to read this file at all.
//
// The file input already filters by image type, but a user can defeat that
// filter in the file dialog, so the choice is checked here as well - and the
// extractor checks it a third time, because it is what actually opens the
// file.
function isSupportedImage(file) {
  if (file.type) {
    return file.type.startsWith("image/");
  }

  // Some systems report no MIME type. Fall back to the extension.
  const name = file.name.toLowerCase();
  return IMAGE_EXTENSIONS.some((extension) => name.endsWith(extension));
}

// Send one flyer to the local extractor and review whatever comes back.
//
// Nothing that fails here disturbs the reviewed result already on screen: it
// is replaced only once the extractor has actually returned a result for the
// new flyer.
async function extractFlyer(file) {
  // This selection supersedes any extraction still in flight.
  const selection = (selectionCount += 1);
  const isCurrentSelection = () => selection === selectionCount;

  // Put the popup back on the flyer the reviewed result is about. Every early
  // return below leaves that result untouched, so the name has to match it
  // rather than the file that failed - which the failure message names.
  const restoreFlyerName = () =>
    showFlyerName(reviewedResult ? reviewedResult.filename : null);

  if (!isSupportedImage(file)) {
    restoreFlyerName();
    setState("invalidFile", file.name);
    return;
  }

  // The flyer is on its way to becoming the result, so it is what the popup
  // is about while it is being read.
  showFlyerName(file.name);
  setState("processing");

  let response;

  try {
    response = await fetch(EXTRACTOR_URL, {
      method: "POST",
      headers: {
        [FILENAME_HEADER]: encodeURIComponent(file.name),
        "Content-Type": file.type || "application/octet-stream",
      },
      body: file,
    });
  } catch (error) {
    if (!isCurrentSelection()) {
      return;
    }

    // fetch only rejects when the request never got an answer, which here
    // means the extractor is not running.
    restoreFlyerName();
    setState("connectionError");
    return;
  }

  if (!response.ok) {
    const failure = await response.json().catch(() => ({}));

    if (!isCurrentSelection()) {
      return;
    }

    // The extractor rejects a file the pipeline cannot read for the same
    // reason the popup does, so it produces the same state.
    restoreFlyerName();
    setState(
      failure.error === "unsupported_file_type"
        ? "invalidFile"
        : "extractionError",
      file.name
    );
    return;
  }

  const pipelineResult = await response.json();

  if (!isCurrentSelection()) {
    return;
  }

  // A new extraction replaces the reviewed result: this is a different flyer,
  // and nobody has reviewed it yet.
  pipelineStatus = pipelineResult.status;
  reviewedResult = createReviewedResult(pipelineResult);

  saveResult(() => {
    setState(reviewedResult.eventDate ? "success" : "noDateFound");
  });
}

// Selecting a file is what starts an extraction.
document.getElementById("file-input").addEventListener("change", (event) => {
  const input = event?.target ?? document.getElementById("file-input");
  const file = input.files && input.files[0];

  if (!file) {
    return;
  }

  extractFlyer(file);
});

// Find the Accept button and respond when the user clicks it.
document.getElementById("accept").addEventListener("click", () => {
  if (!reviewIsReady()) {
    return;
  }

  // Accepting keeps the date the pipeline read, so only the review state
  // changes.
  reviewedResult.reviewStatus = REVIEW_ACCEPTED;

  // Persist the accepted result so it stays accepted after the popup closes.
  saveResult();
});

// The Edit button makes the displayed date editable.
document.getElementById("edit").addEventListener("click", () => {
  if (!reviewIsReady()) {
    return;
  }

  const input = document.getElementById("event-date-input");

  // Start from the date that is on screen so the user can correct it.
  input.value = reviewedResult.eventDate ?? "";

  setEditing(true);
  document.getElementById("message").textContent = "";
  input.focus();
});

// The Save button keeps the corrected date.
document.getElementById("save").addEventListener("click", () => {
  const correctedDate = document.getElementById("event-date-input").value.trim();

  // An empty field would wipe the date, so the edit stays open instead.
  if (!correctedDate) {
    document.getElementById("message").textContent = "Enter an event date.";
    return;
  }

  // Only the reviewed date moves: originalEventDate still holds what the
  // pipeline read.
  reviewedResult.eventDate = correctedDate;
  reviewedResult.reviewStatus = REVIEW_EDITED;

  // Persist the corrected result so the new date is shown the next time the
  // popup is opened.
  saveResult(() => {
    document.getElementById("message").textContent = "Saved!";
  });
});
document.getElementById("export").addEventListener("click", () => {
  if (!reviewIsReady()) {
    document.getElementById("message").textContent =
      "No reviewed result is ready.";
    return;
  }

  const ics = window.generateReviewedEventsIcs([reviewedResult]);

  if (!ics) {
    document.getElementById("message").textContent =
      reviewedResult.reviewStatus === REVIEW_PENDING
        ? "Accept or edit the result before exporting."
        : "The reviewed result has no valid event date.";
    return;
  }

  const blob = new Blob([ics], {
    type: "text/calendar;charset=utf-8",
  });
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = downloadUrl;
  link.download = "reviewed_events.ics";
  link.click();

  URL.revokeObjectURL(downloadUrl);

  document.getElementById("message").textContent =
    "Calendar file downloaded!";
});
