/*
 * Shared stub popup for the extension tests.
 *
 * extension/popup.js is plain browser JavaScript with no build step, so the
 * tests run it inside a Node vm context and hand it a stub `document`,
 * `window.flyerResult`, `chrome.storage.local`, `chrome.runtime` and
 * `FileReader`. That is enough to drive the whole V1 workflow - select a
 * flyer, extract it, accept or correct the date, export it - and to inspect
 * exactly what was persisted and what was sent to the native host.
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
// carried in the native host's `result` field.
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

// The answer a native host gives for a flyer it read, as src/native_host.py
// builds it.
function hostResult(result) {
  return { ok: true, result };
}

// The answer a native host gives for a flyer it refused or could not read.
function hostFailure(error, message = "") {
  return { ok: false, error, message };
}

// A stand-in for the File the file input hands the popup.
//
// `bytes` is what the stub FileReader below reads out of it, so it is what
// ends up base64-encoded in the message to the host.
function fakeFile(name, { type = "image/jpeg", bytes = "image-bytes" } = {}) {
  return { name, type, bytes };
}

// The base64 the popup will send for a file made by fakeFile().
function base64Of(file) {
  return Buffer.from(file.bytes, "utf8").toString("base64");
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
// `respondToHost` stands in for the Python native host. It is called with the
// message the popup sent and returns the host's answer, or throws to stand for
// a host Chrome could not launch - which is the default, since a test that
// says nothing about the host is not expecting one.
function openPopup(
  pipelineResult,
  storageSeed,
  {
    deferStorage = false,
    respondToHost = () => {
      throw new Error("Specified native messaging host not found.");
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

  // Every message the popup sent to the native host.
  const messages = [];

  // The error Chrome reports through chrome.runtime.lastError rather than by
  // throwing. Set for the duration of the callback, exactly as Chrome does.
  let lastError;

  const chrome = {
    runtime: {
      get lastError() {
        return lastError;
      },

      // Chrome launches the host, delivers one message, and calls back with
      // its single answer. A host it cannot launch - or one that dies without
      // answering - calls back with no response and lastError set.
      sendNativeMessage(hostName, message, callback) {
        messages.push({ hostName, message });

        let response;

        try {
          response = respondToHost(message, hostName);
        } catch (error) {
          lastError = { message: error.message };
          callback(undefined);
          lastError = undefined;
          return;
        }

        Promise.resolve(response).then((answer) => {
          callback(answer);
        });
      },
    },
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
    Error,
    TypeError,
    URL: {
      createObjectURL: () => "blob:test-download",
      revokeObjectURL: () => {},
    },
    // Enough of FileReader for readAsDataURL, which is how the popup turns
    // the selected file into the base64 it sends. The result carries the same
    // "data:<type>;base64," prefix a browser produces, because the popup
    // strips it back off.
    FileReader: class {
      readAsDataURL(file) {
        const encoded = Buffer.from(file.bytes, "utf8").toString("base64");

        // A real FileReader answers asynchronously, and the popup awaits it.
        Promise.resolve().then(() => {
          this.result = `data:${file.type || "application/octet-stream"};base64,${encoded}`;
          this.onload();
        });
      }
    },
  };

  vm.createContext(sandbox);
  vm.runInContext(ICS_SOURCE, sandbox);
  vm.runInContext(POPUP_SOURCE, sandbox);

  return {
    elements,
    store,
    downloads,
    // Every message the popup sent to the native host.
    messages,
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
  base64Of,
  createRunner,
  fakeFile,
  flush,
  hostFailure,
  hostResult,
  openPopup,
};
