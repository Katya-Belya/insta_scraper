/*
 * Tests for the extension's review workflow (extension/popup.js).
 *
 * Run with:
 *
 *     node tests/popup_review.test.js
 *
 * The popup is plain browser JavaScript with no build step, so instead of a
 * test framework these tests run popup.js inside a Node vm context and hand it
 * a stub `document`, `window.flyerResult`, and `chrome.storage.local`. That is
 * enough to drive the whole review workflow - click Accept, edit and save a
 * date, reopen the popup - and to inspect exactly what was persisted.
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const POPUP_SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "extension", "popup.js"),
  "utf8"
);

const ICS_SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "extension", "ics.js"),
  "utf8"
);

// Every element popup.js looks up by id.
const ELEMENT_IDS = [
  "filename",
  "event-date",
  "event-date-input",
  "original-event-date-row",
  "original-event-date",
  "status",
  "needs-review",
  "review-status",
  "accept",
  "edit",
  "save",
  "export",
  "message",
];

// A pipeline result of the shape written into extension/latest_result.js.
const PIPELINE_RESULT = {
  filename: "cherry_blossom_market.jpeg",
  eventDate: "2027-03-27",
  status: "ok",
  needsReview: false,
};

// The stored record is built inside the vm context, so it carries that
// context's Object prototype and cannot be compared with deepStrictEqual
// directly. Comparing the JSON round-trip checks the values instead.
function assertRecord(actual, expected) {
  assert.deepStrictEqual(JSON.parse(JSON.stringify(actual)), expected);
}

// Load popup.js against a fresh stub popup.
//
// `storageSeed` is what chrome.storage.local already holds, which is how a
// popup that is being reopened sees an earlier review.
//
// With `deferStorage`, the storage read does not answer until the returned
// `answerStorage()` is called, which is how the popup looks in the moment
// between opening and the stored review coming back.
function openPopup(pipelineResult, storageSeed, { deferStorage = false } = {}) {
  const elements = {};

  for (const id of ELEMENT_IDS) {
    elements[id] = {
      id,
      textContent: "",
      value: "",
      hidden: false,
      disabled: false,
      listeners: [],
      addEventListener(type, listener) {
        this.listeners.push(listener);
      },
      click() {
        // A disabled button fires no click event in a browser, so neither
        // does this one.
        if (this.disabled) {
          return;
        }

        for (const listener of this.listeners) {
          listener();
        }
      },
      focus() {},
    };
  }

  const store = Object.assign({}, storageSeed);
  let pendingRead = null;

  const chrome = {
    storage: {
      local: {
        get(key, callback) {
          const answer = () => {
            callback(key in store ? { [key]: store[key] } : {});
          };

          if (deferStorage) {
            pendingRead = answer;
          } else {
            answer();
          }
        },
        set(items, callback) {
          Object.assign(store, items);

          if (callback) {
            callback();
          }
        },
      },
    },
  };

  const downloads = [];

  const sandbox = {
    window: { flyerResult: pipelineResult },
    document: {
      getElementById: (id) => elements[id],
      createElement: () => ({
        href: "",
        download: "",
        click() {
          downloads.push({
            href: this.href,
            filename: this.download,
          });
        },
      }),
    },
    chrome,
    Blob,
    URL: {
      createObjectURL: () => "blob:test-download",
      revokeObjectURL: () => {},
    },
  };

  vm.createContext(sandbox);
  vm.runInContext(ICS_SOURCE, sandbox);
  vm.runInContext(POPUP_SOURCE, sandbox);

  return {
    elements,
    store,
    downloads,
    // The reviewed result as it was persisted, or undefined if the review has
    // not been saved yet.
    stored: () => store.flyerResult,
    answerStorage: () => pendingRead(),
  };
}

const failures = [];

function test(name, run) {
  try {
    run();
    console.log(`ok   ${name}`);
  } catch (error) {
    failures.push(name);
    console.log(`FAIL ${name}\n     ${error.message}`);
  }
}

test("a fresh flyer opens as an unreviewed result", () => {
  const popup = openPopup(PIPELINE_RESULT, {});

  assert.strictEqual(
    popup.elements["filename"].textContent,
    "cherry_blossom_market.jpeg"
  );
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(popup.elements["status"].textContent, "ok");
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
  assert.strictEqual(popup.elements["status"].textContent, "ok");
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
  assert.strictEqual(popup.elements["status"].textContent, "ok");
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
  assert.strictEqual(reopened.elements["status"].textContent, "ok");

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
  assert.strictEqual(popup.elements["status"].textContent, "no_date_found");
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

if (failures.length > 0) {
  console.log(`\n${failures.length} failed.`);
  process.exit(1);
}

console.log("\nAll checks passed.");