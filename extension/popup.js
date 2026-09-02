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

// The real result written by the pipeline into latest_result.js.
//
// This object describes what OCR found and is never modified here: the review
// is kept separately so a pipeline value (such as its own status) can never be
// overwritten by something the user did in the popup.
const flyerResult = window.flyerResult;

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
let reviewedResult = null;

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

// Switch the event date between the read-only span and the edit field.
function setEditing(editing) {
  document.getElementById("event-date").hidden = editing;
  document.getElementById("event-date-input").hidden = !editing;
  document.getElementById("edit").hidden = editing;
  document.getElementById("save").hidden = !editing;

  // Accepting a result while its date is still being edited would store the
  // old date, so Accept waits until the edit is saved.
  document.getElementById("accept").disabled =
    editing || reviewedResult.reviewStatus === REVIEW_ACCEPTED;
}

// Display the reviewed result in the popup.
function renderResult(result) {
  document.getElementById("filename").textContent = result.filename;

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
  document.getElementById("status").textContent = flyerResult.status;

  document.getElementById("review-status").textContent = result.reviewStatus;

  // Showing a result always leaves the date read-only; editing starts only
  // when the user asks for it.
  setEditing(false);

  // Show the accepted state: there is nothing left to accept, so the
  // Accept button is switched off (by setEditing) and the popup says so.
  const accepted = result.reviewStatus === REVIEW_ACCEPTED;
  document.getElementById("message").textContent = accepted ? "Accepted!" : "";
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
  reviewedResult = restoreReviewedResult(flyerResult, stored[STORAGE_KEY]);

  renderResult(reviewedResult);
});

// The reviewed result is built once chrome.storage.local answers, so a click
// that lands before then has nothing to review yet.
function reviewIsReady() {
  return reviewedResult !== null;
}

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
