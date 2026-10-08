/*
 * Tests for the extension's review workflow (extension/popup.js).
 *
 * Run with:
 *
 *     node tests/popup_review.test.js
 *
 * These cover what happens to a result once it is in front of the user:
 * accepting it, correcting it, persisting it, and exporting it. The flyer
 * input that produces the result in the first place is covered separately, in
 * tests/popup_flyer_input.test.js.
 *
 * The stub popup these run against lives in tests/popup_harness.js.
 */

const assert = require("assert");

const {
  PIPELINE_RESULT,
  assertRecord,
  createRunner,
  openPopup,
} = require("./popup_harness");

const { test, report } = createRunner();

test("a fresh flyer opens as an unreviewed result", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  assert.strictEqual(
    popup.elements["filename"].textContent,
    "cherry_blossom_market.jpeg"
  );
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(
    popup.elements["status"].textContent,
    "Date and year printed on the flyer."
  );
  assert.strictEqual(popup.elements["review-status"].textContent, "pending");
  assert.strictEqual(popup.elements["needs-review"].textContent, "No");

  // Nothing was corrected, so there is no original date worth showing.
  assert.strictEqual(popup.elements["original-event-date-row"].hidden, true);

  // A result nobody has reviewed is the one case where Accept applies.
  assert.strictEqual(popup.elements["accept"].disabled, false);

  assert.strictEqual(popup.stored(), undefined, "nothing stored before review");
});

test("Accept persists the reviewed result as accepted", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  popup.elements["accept"].click();

  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-27",
    needsReview: false,
    reviewStatus: "accepted",
  });

  assert.strictEqual(popup.elements["review-status"].textContent, "accepted");
  assert.strictEqual(popup.elements["message"].textContent, "Accepted!");

  // The review is settled, so there is nothing left to accept.
  assert.strictEqual(popup.elements["accept"].disabled, true);

  // The pipeline's own status is not what the review writes to.
  assert.strictEqual(
    popup.elements["status"].textContent,
    "Date and year printed on the flyer."
  );
});

test("saving an edited date keeps the date the pipeline read", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  popup.elements["edit"].click();
  assert.strictEqual(popup.elements["event-date-input"].value, "2027-03-27");
  assert.strictEqual(popup.elements["event-date-input"].hidden, false);

  // Accepting mid-edit would store the old date.
  assert.strictEqual(popup.elements["accept"].disabled, true);

  popup.elements["event-date-input"].value = "  2027-03-28  ";
  popup.elements["save"].click();

  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-28",
    needsReview: false,
    reviewStatus: "edited",
  });

  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-28");
  assert.strictEqual(popup.elements["original-event-date-row"].hidden, false);
  assert.strictEqual(
    popup.elements["original-event-date"].textContent,
    "2027-03-27"
  );
  assert.strictEqual(popup.elements["message"].textContent, "Saved!");
  assert.strictEqual(
    popup.elements["status"].textContent,
    "Date and year printed on the flyer."
  );
});

test("Accept is off once an edit has been saved", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  popup.elements["edit"].click();
  popup.elements["event-date-input"].value = "2027-03-28";
  popup.elements["save"].click();

  // The user already chose a date, so accepting would only relabel it as if
  // it were the one the pipeline read.
  assert.strictEqual(popup.elements["accept"].disabled, true);

  // A click on a disabled button never reaches the popup, and the saved
  // review stays as it was.
  popup.elements["accept"].click();

  assert.strictEqual(popup.elements["review-status"].textContent, "edited");
  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-28",
    needsReview: false,
    reviewStatus: "edited",
  });
});

test("an empty date is refused and leaves the edit open", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  popup.elements["edit"].click();
  popup.elements["event-date-input"].value = "   ";
  popup.elements["save"].click();

  assert.strictEqual(popup.stored(), undefined, "nothing persisted");
  assert.strictEqual(
    popup.elements["message"].textContent,
    "Enter an event date."
  );
  assert.strictEqual(popup.elements["save"].hidden, false, "still editing");
});

test("reopening the popup restores a settled review", () => {
  const first = openPopup(PIPELINE_RESULT, {});
  first.elements["edit"].click();
  first.elements["event-date-input"].value = "2027-03-28";
  first.elements["save"].click();

  // Reopening reads the same chrome.storage.local the first popup wrote.
  const reopened = openPopup(PIPELINE_RESULT, first.store);

  assert.strictEqual(reopened.elements["event-date"].textContent, "2027-03-28");
  assert.strictEqual(
    reopened.elements["original-event-date"].textContent,
    "2027-03-27"
  );
  assert.strictEqual(reopened.elements["review-status"].textContent, "edited");
  assert.strictEqual(
    reopened.elements["status"].textContent,
    "Date and year printed on the flyer."
  );

  // The review stays settled across reopening, so Accept stays off.
  assert.strictEqual(reopened.elements["accept"].disabled, true);
});

test("reopening an accepted review leaves Accept off", () => {
  const first = openPopup(PIPELINE_RESULT, {});
  first.elements["accept"].click();

  const reopened = openPopup(PIPELINE_RESULT, first.store);

  assert.strictEqual(reopened.elements["review-status"].textContent, "accepted");
  assert.strictEqual(reopened.elements["accept"].disabled, true);
  assert.strictEqual(reopened.elements["message"].textContent, "Accepted!");
});

test("a corrected date can still be corrected again", () => {
  const first = openPopup(PIPELINE_RESULT, {});
  first.elements["edit"].click();
  first.elements["event-date-input"].value = "2027-03-28";
  first.elements["save"].click();

  const reopened = openPopup(PIPELINE_RESULT, first.store);

  // Editing is the way to change a settled review, and the second correction
  // still does not disturb the date the pipeline read.
  reopened.elements["edit"].click();
  assert.strictEqual(reopened.elements["event-date-input"].value, "2027-03-28");

  reopened.elements["event-date-input"].value = "2027-03-29";
  reopened.elements["save"].click();

  assertRecord(reopened.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-29",
    needsReview: false,
    reviewStatus: "edited",
  });
});

test("a review stored for a different flyer is ignored", () => {
  const otherFlyer = {
    flyerResult: {
      filename: "old_flyer.jpeg",
      originalEventDate: "2027-01-01",
      eventDate: "2027-01-02",
      needsReview: true,
      reviewStatus: "edited",
    },
  };

  const popup = openPopup(PIPELINE_RESULT, otherFlyer);

  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(popup.elements["review-status"].textContent, "pending");
  assert.strictEqual(popup.elements["original-event-date-row"].hidden, true);

  // The new flyer has not been reviewed, so Accept applies to it.
  assert.strictEqual(popup.elements["accept"].disabled, false);
});

test("a record written by the older popup still reviews", () => {
  // The previous popup stored only filename, eventDate and status.
  const olderRecord = {
    flyerResult: {
      filename: "cherry_blossom_market.jpeg",
      eventDate: "2027-03-28",
      status: "accepted",
    },
  };

  const popup = openPopup(PIPELINE_RESULT, olderRecord);

  // The corrected date survives, and the date the pipeline read fills in the
  // originalEventDate the older record never had.
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-28");
  assert.strictEqual(
    popup.elements["original-event-date"].textContent,
    "2027-03-27"
  );

  // The older record has no reviewStatus, so the flyer is reviewed again.
  assert.strictEqual(popup.elements["review-status"].textContent, "pending");
  assert.strictEqual(popup.elements["accept"].disabled, false);

  popup.elements["accept"].click();

  assertRecord(popup.stored(), {
    filename: "cherry_blossom_market.jpeg",
    originalEventDate: "2027-03-27",
    eventDate: "2027-03-28",
    needsReview: false,
    reviewStatus: "accepted",
  });
});

test("a flyer with no readable date can be given one", () => {
  const noDateFound = {
    filename: "mystery.jpeg",
    eventDate: null,
    status: "no_date_found",
    needsReview: true,
  };

  const popup = openPopup(noDateFound, {});

  // A missing date shows as blank rather than as the text "null".
  assert.strictEqual(popup.elements["event-date"].textContent, "");
  assert.strictEqual(popup.elements["needs-review"].textContent, "Yes");
  assert.strictEqual(
    popup.elements["status"].textContent,
    "No date was found on the flyer."
  );
  assert.strictEqual(popup.elements["original-event-date-row"].hidden, true);

  popup.elements["edit"].click();
  assert.strictEqual(popup.elements["event-date-input"].value, "");

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

test("clicks before the stored review arrives are ignored", () => {
  const popup = openPopup(PIPELINE_RESULT, {}, { deferStorage: true });

  // chrome.storage.local has not answered yet, so there is no reviewed result
  // to act on and the buttons do nothing rather than failing.
  popup.elements["accept"].click();
  popup.elements["edit"].click();

  assert.strictEqual(popup.stored(), undefined);
  assert.strictEqual(popup.elements["event-date-input"].hidden, false);

  // Once the read answers, the popup fills in as usual.
  popup.answerStorage();

  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(popup.elements["review-status"].textContent, "pending");
  assert.strictEqual(popup.elements["accept"].disabled, false);
});

test("a pending result cannot be exported", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  popup.elements["export"].click();

  assert.strictEqual(
    popup.elements["message"].textContent,
    "Accept or edit the result before exporting."
  );
});

test("an edited result downloads an ICS file", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  popup.elements["edit"].click();
  popup.elements["event-date-input"].value = "2027-03-29";
  popup.elements["save"].click();
  popup.elements["export"].click();

  assert.strictEqual(popup.downloads.length, 1);
  assert.strictEqual(
    popup.downloads[0].filename,
    "reviewed_events.ics"
  );
  assert.strictEqual(
    popup.elements["message"].textContent,
    "Calendar file downloaded!"
  );
});

// Pipeline results for the statuses that carry a review warning. The dates
// only have to look like what the pipeline would send for that status.
function resultWithStatus(status, eventDate, needsReview = true) {
  return { filename: `${status}.jpeg`, eventDate, status, needsReview };
}

test("an inferred year is explained and needs review", () => {
  const popup = openPopup(resultWithStatus("inferred_year", "2026-10-10"), {});

  assert.strictEqual(
    popup.elements["status"].textContent,
    "No year on the flyer. The year shown is the next time this date " +
      "comes around - confirm it."
  );
  assert.strictEqual(popup.elements["status"].className, "");
  assert.strictEqual(popup.elements["needs-review"].textContent, "Yes");
  assert.strictEqual(
    popup.elements["state-message"].textContent,
    "Found an event date. Review it below."
  );
});

test("a distant inferred year shows the stronger check-the-year warning", () => {
  const popup = openPopup(
    resultWithStatus("inferred_year_distant", "2027-03-27"),
    {}
  );

  assert.match(popup.elements["status"].textContent, /^Check the year:/);
  assert.strictEqual(popup.elements["status"].className, "is-warning");
  assert.strictEqual(popup.elements["needs-review"].textContent, "Yes");
});

test("a printed date already past is a warning, not an error", () => {
  const popup = openPopup(
    resultWithStatus("explicit_past_date", "2025-08-24"),
    {}
  );

  assert.strictEqual(
    popup.elements["status"].textContent,
    "The date printed on the flyer has already passed. Check that this is " +
      "the event you want before accepting."
  );
  assert.strictEqual(popup.elements["status"].className, "is-warning");
  // The date is still a real date, so it is shown for review.
  assert.strictEqual(popup.elements["event-date"].textContent, "2025-08-24");
  assert.strictEqual(popup.elements["accept"].disabled, false);
});

test("an invalid date asks for a correction", () => {
  const popup = openPopup(resultWithStatus("invalid_date", null), {});

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    "The date on this flyer is not a real calendar date. Use Edit to correct it."
  );
  assert.strictEqual(popup.elements["state-message"].className, "is-error");
  assert.strictEqual(
    popup.elements["status"].textContent,
    "The date on the flyer is not a real calendar date."
  );

  // Accepting a missing date still exports nothing.
  popup.elements["accept"].click();
  popup.elements["export"].click();
  assert.strictEqual(popup.downloads.length, 0);
  assert.strictEqual(
    popup.elements["message"].textContent,
    "The reviewed result has no valid event date."
  );
});

test("an unknown status is shown as it is", () => {
  const popup = openPopup(resultWithStatus("something_new", "2027-01-01"), {});

  assert.strictEqual(popup.elements["status"].textContent, "something_new");
});

for (const [status, eventDate] of [
  ["inferred_year", "2026-10-10"],
  ["inferred_year_distant", "2027-03-27"],
  ["explicit_past_date", "2025-08-24"],
]) {
  test(`a ${status} result exports only after it is accepted`, () => {
    const popup = openPopup(resultWithStatus(status, eventDate), {});

    popup.elements["export"].click();
    assert.strictEqual(popup.downloads.length, 0);
    assert.strictEqual(
      popup.elements["message"].textContent,
      "Accept or edit the result before exporting."
    );

    popup.elements["accept"].click();
    popup.elements["export"].click();
    assert.strictEqual(popup.downloads.length, 1);
    assert.strictEqual(
      popup.elements["message"].textContent,
      "Calendar file downloaded!"
    );
  });
}

report();
