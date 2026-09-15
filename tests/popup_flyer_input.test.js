/*
 * Tests for the extension's flyer input (extension/popup.js).
 *
 * Run with:
 *
 *     node tests/popup_flyer_input.test.js
 *
 * These cover the half of the V1 workflow that happens before a review: the
 * Select Flyer control, the message sent to the Python native host, and each
 * state the popup can end up in. What the user then does with the result is
 * covered in tests/popup_review.test.js.
 *
 * The stub popup these run against lives in tests/popup_harness.js. The
 * native host is stubbed there, so no host registration and no OCR install is
 * needed.
 */

const assert = require("assert");

const {
  PIPELINE_RESULT,
  assertRecord,
  base64Of,
  createRunner,
  fakeFile,
  flush,
  hostFailure,
  hostResult,
  openPopup,
} = require("./popup_harness");

const { test, report } = createRunner();

// The messages the popup shows for each state, quoted here so a change to the
// wording has to be deliberate.
const IDLE = "Select a flyer to extract its event date.";
const PROCESSING = "Reading the flyer...";
const SUCCESS = "Found an event date. Review it below.";
const NO_DATE_FOUND =
  "No date was readable on this flyer. Use Edit to enter it.";
const CONNECTION_ERROR =
  "Cannot reach the extractor. Reinstall the native host and reload.";

// The failure messages name the file they are about, because that file is not
// the flyer the result on screen belongs to.
const invalidFile = (filename) =>
  `${filename} is not an image. Choose a JPG, JPEG, PNG, or WEBP.`;
const extractionError = (filename) =>
  `${filename} could not be read. Try another image.`;

// A native host Chrome can launch, which answers with `result`.
function hostReturning(result) {
  return () => hostResult(result);
}

test("a popup with no flyer opens idle", () => {
  // No command-line run has written latest_result.js and nothing has been
  // reviewed before, so there is nothing to show yet.
  const popup = openPopup(null, {});

  assert.strictEqual(popup.elements["state-message"].textContent, IDLE);
  assert.strictEqual(popup.elements["filename"].textContent, "");

  // Nothing to review means the whole review section stays out of the way.
  assert.strictEqual(popup.elements["result"].hidden, true);
  assert.strictEqual(popup.stored(), undefined);
});

test("an idle popup still reopens the last reviewed result", () => {
  const stored = {
    flyerResult: {
      filename: "august_happy_hour.jpg",
      originalEventDate: "2027-08-04",
      eventDate: "2027-08-05",
      needsReview: true,
      reviewStatus: "edited",
    },
  };

  const popup = openPopup(null, stored);

  assert.strictEqual(popup.elements["result"].hidden, false);
  assert.strictEqual(
    popup.elements["filename"].textContent,
    "august_happy_hour.jpg"
  );
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-08-05");
  assert.strictEqual(
    popup.elements["original-event-date"].textContent,
    "2027-08-04"
  );
  assert.strictEqual(popup.elements["review-status"].textContent, "edited");

  // The pipeline never ran in this session, so there is no pipeline status to
  // show and the row is hidden rather than left blank.
  assert.strictEqual(popup.elements["status-row"].hidden, true);
  assert.strictEqual(popup.elements["status"].textContent, "");

  // The review is settled, so it stays settled across reopening.
  assert.strictEqual(popup.elements["accept"].disabled, true);
});

test("selecting a flyer sends it to the native host", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: hostReturning(PIPELINE_RESULT),
  });

  const file = fakeFile("cherry_blossom_market.jpeg");
  await popup.selectFlyer(file);

  assert.strictEqual(popup.messages.length, 1);

  const { hostName, message } = popup.messages[0];

  // The host name has to match the one in the registered host manifest, or
  // Chrome has nothing to launch.
  assert.strictEqual(hostName, "com.flyer_extractor.host");

  // A Native Messaging message is JSON, so the image travels base64-encoded
  // alongside the name the pipeline will give the result.
  assert.deepStrictEqual(JSON.parse(JSON.stringify(message)), {
    type: "extract",
    filename: "cherry_blossom_market.jpeg",
    imageBase64: base64Of(file),
  });
});

test("a filename JSON can carry travels unchanged", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: hostReturning(PIPELINE_RESULT),
  });

  // The HTTP transport had to percent-encode this, because a header cannot
  // carry it. A JSON message can, so the host sees the name the user chose.
  await popup.selectFlyer(fakeFile("café night.png", { type: "image/png" }));

  assert.strictEqual(popup.messages[0].message.filename, "café night.png");
});

test("the selected filename is shown while the flyer is read", async () => {
  const seen = [];

  const popup = openPopup(null, {}, {
    respondToHost: () => {
      // Captured mid-request: this is what the popup looks like while the
      // host is working.
      seen.push({
        state: popup.elements["state-message"].textContent,
        tone: popup.elements["state-message"].className,
        filename: popup.elements["filename"].textContent,
      });

      return hostResult(PIPELINE_RESULT);
    },
  });

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  assert.deepStrictEqual(seen, [
    {
      state: PROCESSING,
      tone: "is-working",
      filename: "cherry_blossom_market.jpeg",
    },
  ]);
});

test("a successful extraction is stored as a pending review", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: hostReturning(PIPELINE_RESULT),
  });

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  assert.strictEqual(popup.elements["state-message"].textContent, SUCCESS);
  assert.strictEqual(popup.elements["state-message"].className, "is-success");

  // The extracted result becomes the canonical reviewed result, unreviewed.
  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-27",
    needsReview: false,
    reviewStatus: "pending",
  });

  assert.strictEqual(popup.elements["result"].hidden, false);
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(popup.elements["review-status"].textContent, "pending");
  assert.strictEqual(popup.elements["status"].textContent, "ok");
  assert.strictEqual(popup.elements["status-row"].hidden, false);

  // A pending result is exactly what Accept is for.
  assert.strictEqual(popup.elements["accept"].disabled, false);
});

test("an extracted flyer can be accepted and exported", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: hostReturning(PIPELINE_RESULT),
  });

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  popup.elements["accept"].click();

  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-27",
    needsReview: false,
    reviewStatus: "accepted",
  });

  popup.elements["export"].click();

  assert.strictEqual(popup.downloads.length, 1);
  assert.strictEqual(popup.downloads[0].filename, "reviewed_events.ics");
});

test("a flyer with no readable date says so and can still be edited", async () => {
  const noDateFound = {
    filename: "mystery.jpeg",
    eventDate: null,
    status: "no_date_found",
    needsReview: true,
  };

  const popup = openPopup(null, {}, {
    respondToHost: hostReturning(noDateFound),
  });

  await popup.selectFlyer(fakeFile("mystery.jpeg"));

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    NO_DATE_FOUND
  );
  assert.strictEqual(popup.elements["state-message"].className, "is-error");

  // The flyer was read, so it is reviewable: a missing date shows as blank
  // and the user can supply one.
  assert.strictEqual(popup.elements["event-date"].textContent, "");
  assert.strictEqual(popup.elements["needs-review"].textContent, "Yes");
  assert.strictEqual(popup.elements["status"].textContent, "no_date_found");

  popup.elements["edit"].click();
  popup.elements["event-date-input"].value = "2027-09-01";
  popup.elements["save"].click();

  assertRecord(popup.stored(), {
    filename: "mystery.jpeg",
    originalEventDate: null,
    eventDate: "2027-09-01",
    needsReview: true,
    reviewStatus: "edited",
  });
});

test("a file that is not an image is refused before it is sent", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: hostReturning(PIPELINE_RESULT),
  });

  await popup.selectFlyer(
    fakeFile("event_notes.pdf", { type: "application/pdf" })
  );

  // The message is where the refused file is named.
  assert.strictEqual(
    popup.elements["state-message"].textContent,
    invalidFile("event_notes.pdf")
  );
  assert.strictEqual(popup.elements["state-message"].className, "is-error");

  // Nothing was sent, so nothing was extracted.
  assert.strictEqual(popup.messages.length, 0);
  assert.strictEqual(popup.stored(), undefined);

  // Nothing was extracted, so there is still no flyer to show.
  assert.strictEqual(popup.elements["filename"].textContent, "");
  assert.strictEqual(popup.elements["result"].hidden, true);
});

test("a file with no reported type is judged by its extension", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: hostReturning(PIPELINE_RESULT),
  });

  // Some systems report no MIME type at all.
  await popup.selectFlyer(fakeFile("flyer.WEBP", { type: "" }));
  assert.strictEqual(popup.messages.length, 1);

  await popup.selectFlyer(fakeFile("flyer.txt", { type: "" }));
  assert.strictEqual(popup.messages.length, 1, "the text file was not sent");
  assert.strictEqual(
    popup.elements["state-message"].textContent,
    invalidFile("flyer.txt")
  );
});

test("a host Chrome cannot launch is reported as such", async () => {
  // The default stub host is one Chrome cannot find, which is what an
  // unregistered or misregistered host manifest looks like from the popup.
  const popup = openPopup(null, {});

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    CONNECTION_ERROR
  );
  assert.strictEqual(popup.elements["state-message"].className, "is-error");
  assert.strictEqual(popup.stored(), undefined);
});

test("an extractor error is reported without losing the review", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: () =>
      hostFailure("extraction_failed", "TesseractNotFoundError"),
  });

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    extractionError("cherry_blossom_market.jpeg")
  );
  assert.strictEqual(popup.stored(), undefined);
});

test("a host with no pipeline behind it is reported as unreachable", async () => {
  // The host launched, but the interpreter Chrome ran it with has none of the
  // project's requirements. That is not a problem with the flyer, so the
  // popup points at the host rather than telling the user to try another
  // image.
  const popup = openPopup(null, {}, {
    respondToHost: () =>
      hostFailure("pipeline_unavailable", "No module named 'PIL'"),
  });

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    CONNECTION_ERROR
  );
  assert.strictEqual(popup.stored(), undefined);
});

test("a file the host refuses shows the invalid-file state", async () => {
  const popup = openPopup(null, {}, {
    respondToHost: () =>
      hostFailure("unsupported_file_type", "not a supported image"),
  });

  // The popup's own check passes on the MIME type, so this is the host having
  // the last word about what the pipeline can read.
  await popup.selectFlyer(fakeFile("flyer.gif", { type: "image/gif" }));

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    invalidFile("flyer.gif")
  );
});

test("a failed extraction leaves the previous reviewed result alone", async () => {
  const stored = {
    flyerResult: {
      filename: "august_happy_hour.jpg",
      originalEventDate: "2027-08-04",
      eventDate: "2027-08-05",
      needsReview: true,
      reviewStatus: "edited",
    },
  };

  const popup = openPopup(null, stored);

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    CONNECTION_ERROR
  );

  // The reviewed result survives a failed extraction untouched: it is
  // replaced only when a new one actually succeeds.
  assertRecord(popup.stored(), stored.flyerResult);
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-08-05");
  assert.strictEqual(popup.elements["review-status"].textContent, "edited");

  // The flyer named above the result is still the one the result is about,
  // so the failed selection cannot look as though it has that date.
  assert.strictEqual(
    popup.elements["filename"].textContent,
    "august_happy_hour.jpg"
  );
});

test("a new extraction replaces a settled review", async () => {
  const stored = {
    flyerResult: {
      filename: "august_happy_hour.jpg",
      originalEventDate: "2027-08-04",
      eventDate: "2027-08-05",
      needsReview: true,
      reviewStatus: "edited",
    },
  };

  const popup = openPopup(null, stored, {
    respondToHost: hostReturning(PIPELINE_RESULT),
  });

  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  // A different flyer nobody has reviewed, so none of the old review carries
  // over into it.
  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-27",
    needsReview: false,
    reviewStatus: "pending",
  });

  assert.strictEqual(popup.elements["accept"].disabled, false);
  assert.strictEqual(popup.elements["original-event-date-row"].hidden, true);
});

test("a second selection wins over one still being read", async () => {
  const slowFlyer = {
    filename: "slow.jpeg",
    eventDate: "2027-01-01",
    status: "ok",
    needsReview: false,
  };

  // The first flyer's answer is held back until the test releases it.
  let releaseFirst;
  const firstAnswer = new Promise((resolve) => {
    releaseFirst = () => resolve(hostResult(slowFlyer));
  });

  let messageCount = 0;

  const popup = openPopup(null, {}, {
    respondToHost: () => {
      messageCount += 1;
      return messageCount === 1 ? firstAnswer : hostResult(PIPELINE_RESULT);
    },
  });

  // Selecting the second flyer while the first is still being read.
  await popup.selectFlyer(fakeFile("slow.jpeg"));
  await popup.selectFlyer(fakeFile("cherry_blossom_market.jpeg"));

  assert.strictEqual(messageCount, 2);

  // The first answer arrives late, after the second flyer was already shown.
  releaseFirst();
  await flush();

  // The flyer the user selected last is the one on screen and in storage.
  assert.strictEqual(
    popup.elements["filename"].textContent,
    "cherry_blossom_market.jpeg"
  );
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-27",
    needsReview: false,
    reviewStatus: "pending",
  });
});

test("a cancelled file dialog changes nothing", async () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  // Cancelling leaves the input with no file, and the popup as it was.
  await popup.selectFlyer(null);

  assert.strictEqual(popup.messages.length, 0);
  assert.strictEqual(popup.elements["state-message"].textContent, SUCCESS);
  assert.strictEqual(
    popup.elements["filename"].textContent,
    "cherry_blossom_market.jpeg"
  );
});

test("a result from a command-line run still opens the popup", async () => {
  // A run of `python -m src.pipeline` writes extension/latest_result.js, and
  // that path keeps working alongside the new one.
  const popup = openPopup(PIPELINE_RESULT, {});

  assert.strictEqual(popup.elements["result"].hidden, false);
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(popup.elements["state-message"].textContent, SUCCESS);
  assert.strictEqual(popup.elements["status"].textContent, "ok");
});

report();
