/*
 * Shared stub popup for the extension tests.
 *
 * extension/popup.js is plain browser JavaScript with no build step, so the
 * tests run it inside a Node vm context and hand it a stub `document`,
 * `window.flyerResult`, `chrome.storage.local` and `fetch`. That is enough to
 * drive the whole V1 workflow - select a flyer, extract it, accept or correct
 * the date, export it - and to inspect exactly what was persisted and what was
 * sent to the local extractor.
 *
 * Used by tests/popup_review.test.js and tests/popup_flyer_input.test.js.
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
  "file-input",
  "filename",
  "state-message",
  "result",
  "event-date",
  "event-date-input",
  "original-event-date-row",
  "original-event-date",
  "status-row",
  "status",
  "needs-review",
  "review-status",
  "accept",
  "edit",
  "save",
  "export",
  "message",
];

// A pipeline result of the shape written into extension/latest_result.js and
// returned by the local extractor.
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

// Let every already-resolved promise in the popup run to completion.
//
// Extraction is a chain of awaits over stubbed calls that resolve
// immediately, so draining the microtask queue a few times is enough: there
// are no timers and no real I/O to wait for.
async function flush() {
  for (let tick = 0; tick < 20; tick += 1) {
    await Promise.resolve();
  }
}

// Build the response object `fetch` resolves to.
function jsonResponse(body, { status = 200 } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

// A stand-in for the File the file input hands the popup.
function fakeFile(name, { type = "image/jpeg", bytes = "image-bytes" } = {}) {
  return { name, type, bytes };
}

// Load popup.js against a fresh stub popup.
//
// `storageSeed` is what chrome.storage.local already holds, which is how a
// popup that is being reopened sees an earlier review.
//
// With `deferStorage`, the storage read does not answer until the returned
// `answerStorage()` is called, which is how the popup looks in the moment
// between opening and the stored review coming back.
//
// `respondToFetch` stands in for the local Python extractor. It is called
// with the request the popup made and returns the response, or throws to
// stand for an extractor that is not running - which is the default, since a
// test that says nothing about the extractor is not expecting one.
function openPopup(
  pipelineResult,
  storageSeed,
  {
    deferStorage = false,
    respondToFetch = () => {
      throw new TypeError("Failed to fetch");
    },
  } = {}
) {
  const elements = {};

  for (const id of ELEMENT_IDS) {
    elements[id] = {
      id,
      textContent: "",
      value: "",
      className: "",
      hidden: false,
      disabled: false,
      files: [],
      listeners: {},
      addEventListener(type, listener) {
        this.listeners[type] = this.listeners[type] ?? [];
        this.listeners[type].push(listener);
      },
      dispatch(type, event) {
        for (const listener of this.listeners[type] ?? []) {
          listener(event);
        }
      },
      click() {
        // A disabled button fires no click event in a browser, so neither
        // does this one.
        if (this.disabled) {
          return;
        }

        this.dispatch("click", { target: this });
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
  const requests = [];

  const sandbox = {
    // A run of the command-line pipeline may or may not have left a result
    // behind, exactly as extension/latest_result.js may or may not exist.
    window: pipelineResult ? { flyerResult: pipelineResult } : {},
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
    TypeError,
    URL: {
      createObjectURL: () => "blob:test-download",
      revokeObjectURL: () => {},
    },
    async fetch(url, options) {
      requests.push({ url, options });
      return respondToFetch(url, options);
    },
  };

  vm.createContext(sandbox);
  vm.runInContext(ICS_SOURCE, sandbox);
  vm.runInContext(POPUP_SOURCE, sandbox);

  return {
    elements,
    store,
    downloads,
    // Every request the popup made to the local extractor.
    requests,
    // The reviewed result as it was persisted, or undefined if the review has
    // not been saved yet.
    stored: () => store.flyerResult,
    answerStorage: () => pendingRead(),
    // Choose a flyer, the way the file input does. Await the result: the
    // extraction it starts is asynchronous.
    async selectFlyer(file) {
      const input = elements["file-input"];

      input.files = file ? [file] : [];
      input.dispatch("change", { target: input });

      await flush();
    },
  };
}

// A tiny test runner, so the extension tests need no framework.
function createRunner() {
  const failures = [];
  const queue = [];

  // Tests are queued rather than run immediately: some of them are async, and
  // they have to finish in order for their output to make sense.
  function test(name, run) {
    queue.push({ name, run });
  }

  async function report() {
    for (const { name, run } of queue) {
      try {
        await run();
        console.log(`ok   ${name}`);
      } catch (error) {
        failures.push(name);
        console.log(`FAIL ${name}\n     ${error.message}`);
      }
    }

    if (failures.length > 0) {
      console.log(`\n${failures.length} failed.`);
      process.exit(1);
    }

    console.log("\nAll checks passed.");
  }

  return { test, report };
}

module.exports = {
  ELEMENT_IDS,
  PIPELINE_RESULT,
  assertRecord,
  createRunner,
  fakeFile,
  flush,
  jsonResponse,
  openPopup,
};
