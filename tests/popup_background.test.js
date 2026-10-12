/*
 * Tests for the popup and background worker running together.
 *
 * Run with:
 *
 *     node tests/popup_background.test.js
 *
 * extension/background.js owns extraction so that it survives the popup
 * closing; extension/popup.js only reads the file, hands it to the worker and
 * redraws from chrome.storage.local. These tests load both scripts into
 * separate vm contexts that share one stubbed chrome.storage.local (with
 * onChanged events) and route chrome.runtime.sendMessage from the popup to
 * the worker. The native host is a mocked port: nothing real is launched and
 * no native-host registration is touched.
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const { createRunner } = require("./popup_harness");

const read = (name) =>
  fs.readFileSync(path.join(__dirname, "..", "extension", name), "utf8");
const BACKGROUND_SOURCE = read("background.js");
const POPUP_SOURCE = read("popup.js");
const ICS_SOURCE = read("ics.js");

// Every element popup.js looks up by id.
const ELEMENT_IDS = [
  "file-input",
  "filename",
  "state-message",
  "clear-results",
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
  "add-to-google-calendar",
  "message",
];

// Let promises, storage events and the worker's async chain settle.
async function flush() {
  for (let tick = 0; tick < 10; tick += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

function hostResult(result) {
  return { ok: true, result };
}

const PAST_RESULT = {
  filename: "old_market.jpeg",
  eventDate: "2026-03-27",
  status: "explicit_past_date",
  needsReview: true,
};

const OK_RESULT = {
  filename: "cherry_blossom_market.jpeg",
  eventDate: "2027-03-27",
  status: "ok",
  needsReview: false,
};

// One browser: shared storage, one background worker, any number of popups.
//
// `host` decides how the mocked native host answers each message:
//   - return a response object (or a promise of one) to answer it
//   - return { disconnect: "message" } to drop the port with lastError set
//   - throw to stand for connectNative failing outright
function createBrowser({ host, seed = {} } = {}) {
  const store = JSON.parse(JSON.stringify(seed));
  const changeListeners = new Set();
  const messageListeners = [];
  const tabs = [];
  let lastError;

  function emitChanges(changes) {
    for (const listener of [...changeListeners]) {
      listener(changes, "local");
    }
  }

  function storageFor() {
    return {
      local: {
        get(keys, callback) {
          const list = Array.isArray(keys) ? keys : [keys];
          const answer = {};
          for (const key of list) {
            if (key in store) answer[key] = JSON.parse(JSON.stringify(store[key]));
          }
          const promise = Promise.resolve(answer);
          if (callback) promise.then(callback);
          return promise;
        },
        set(items, callback) {
          const changes = {};
          for (const [key, value] of Object.entries(items)) {
            changes[key] = { oldValue: store[key], newValue: value };
            store[key] = JSON.parse(JSON.stringify(value));
          }
          const promise = Promise.resolve().then(() => emitChanges(changes));
          if (callback) promise.then(callback);
          return promise;
        },
      },
    };
  }

  // The mocked native port the worker connects to.
  function connectNative() {
    if (host.connectThrows) {
      throw new Error(host.connectThrows);
    }
    const onMessage = [];
    const onDisconnect = [];
    return {
      onMessage: { addListener: (fn) => onMessage.push(fn) },
      onDisconnect: { addListener: (fn) => onDisconnect.push(fn) },
      postMessage(message) {
        Promise.resolve(host.respond(message)).then((answer) => {
          if (answer && answer.disconnect) {
            lastError = { message: answer.disconnect };
            onDisconnect.forEach((fn) => fn());
            lastError = undefined;
            return;
          }
          onMessage.forEach((fn) => fn(answer));
        });
      },
      disconnect() {},
    };
  }

  const backgroundChrome = {
    runtime: {
      id: "extension-id",
      get lastError() {
        return lastError;
      },
      connectNative,
      onMessage: { addListener: (fn) => messageListeners.push(fn) },
    },
    storage: storageFor(),
  };

  function startWorker() {
    messageListeners.length = 0;
    const context = { chrome: backgroundChrome, console: { error() {} }, Promise, Date, Error };
    vm.createContext(context);
    vm.runInContext(BACKGROUND_SOURCE, context);
  }

  startWorker();

  // Deliver a popup message to the worker the way Chrome does.
  function sendMessage(message) {
    if (host.workerUnreachable) {
      return Promise.reject(new Error("Could not establish connection."));
    }
    return new Promise((resolve) => {
      for (const listener of messageListeners) {
        const keepOpen = listener(message, { id: "extension-id" }, resolve);
        if (keepOpen) return;
      }
      resolve(undefined);
    });
  }

  function openPopup() {
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
        addEventListener(type, fn) {
          (this.listeners[type] = this.listeners[type] ?? []).push(fn);
        },
        dispatch(type, event) {
          for (const fn of this.listeners[type] ?? []) fn(event);
        },
        click() {
          if (this.disabled) return;
          this.dispatch("click", { target: this });
        },
        focus() {},
      };
    }
    // Markup defaults from popup.html that the scripts rely on.
    elements["result"].hidden = true;
    elements["save"].hidden = true;
    elements["event-date-input"].hidden = true;
    elements["original-event-date-row"].hidden = true;
    for (const id of ["export", "add-to-google-calendar", "clear-results"]) {
      elements[id].disabled = true;
    }

    const downloads = [];
    let blobs = [];
    const popupListeners = [];

    const chrome = {
      runtime: { sendMessage, id: "extension-id" },
      storage: {
        local: storageFor().local,
        onChanged: {
          addListener(fn) {
            popupListeners.push(fn);
            changeListeners.add(fn);
          },
        },
      },
      tabs: { create: (options) => tabs.push(options.url) },
    };

    const sandbox = {
      window: {},
      document: {
        getElementById: (id) => elements[id],
        createElement: () => ({
          href: "",
          download: "",
          click() {
            downloads.push({ href: this.href, filename: this.download });
          },
        }),
      },
      chrome,
      console: { error() {} },
      Blob,
      URL: {
        createObjectURL(blob) {
          blobs.push(blob);
          return `blob:${blobs.length}`;
        },
        revokeObjectURL() {},
      },
      URLSearchParams,
      FileReader: class {
        readAsDataURL(file) {
          Promise.resolve().then(() => {
            this.result = `data:${file.type};base64,${Buffer.from(file.bytes).toString("base64")}`;
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
      downloads,
      async icsText(index = 0) {
        return blobs[index].text();
      },
      async selectFlyer(name, type = "image/jpeg") {
        const input = elements["file-input"];
        input.files = [{ name, type, bytes: "image-bytes" }];
        input.dispatch("change", { target: input });
        await flush();
      },
      // Closing the popup destroys its page: it stops hearing storage events.
      close() {
        popupListeners.forEach((fn) => changeListeners.delete(fn));
      },
    };
  }

  return { store, tabs, openPopup, restartWorker: startWorker };
}

// A host whose answer is held back until release() is called.
function deferredHost(answer) {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  return {
    respond: () => gate.then(() => answer),
    release: () => release(),
  };
}

const calendarState = (popup) => ({
  google: popup.elements["add-to-google-calendar"].disabled,
  ics: popup.elements["export"].disabled,
});

const { test, report } = createRunner();

test("both calendar actions stay off while the review is pending", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);

  assert.strictEqual(popup.elements["review-status"].textContent, "pending");
  assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });

  popup.elements["add-to-google-calendar"].click();
  popup.elements["export"].click();
  assert.strictEqual(browser.tabs.length, 0);
  assert.strictEqual(popup.downloads.length, 0);
});

test("Accept enables both calendar actions with the accepted date", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);

  popup.elements["accept"].click();
  await flush();

  assert.deepStrictEqual(calendarState(popup), { google: false, ics: false });

  popup.elements["add-to-google-calendar"].click();
  assert.match(browser.tabs[0], /dates=20270327%2F20270328/);

  popup.elements["export"].click();
  assert.match(await popup.icsText(), /DTSTART;VALUE=DATE:20270327/);
});

test("both calendar actions are off while editing and use the saved date", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);
  popup.elements["accept"].click();
  await flush();

  // Editing an accepted date locks the calendar until the edit is saved.
  popup.elements["edit"].click();
  assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });

  popup.elements["event-date-input"].value = "2027-04-02";
  popup.elements["add-to-google-calendar"].click();
  popup.elements["export"].click();
  assert.strictEqual(browser.tabs.length, 0);
  assert.strictEqual(popup.downloads.length, 0);

  popup.elements["save"].click();
  await flush();

  assert.deepStrictEqual(calendarState(popup), { google: false, ics: false });
  assert.strictEqual(browser.store.flyerResult.eventDate, "2027-04-02");
  assert.strictEqual(browser.store.flyerResult.originalEventDate, "2027-03-27");

  popup.elements["add-to-google-calendar"].click();
  assert.match(browser.tabs[0], /dates=20270402%2F20270403/);

  popup.elements["export"].click();
  assert.match(await popup.icsText(), /DTSTART;VALUE=DATE:20270402/);
});

test("a pending result's edit saved directly enables the calendar", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);

  popup.elements["edit"].click();
  assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });

  popup.elements["event-date-input"].value = "2027-05-01";
  popup.elements["save"].click();
  await flush();

  assert.strictEqual(popup.elements["review-status"].textContent, "edited");
  assert.deepStrictEqual(calendarState(popup), { google: false, ics: false });
});

test("extraction finishes after the popup closes and reopens pending", async () => {
  const host = deferredHost(hostResult(PAST_RESULT));
  const browser = createBrowser({ host });

  const first = browser.openPopup();
  await flush();
  await first.selectFlyer(PAST_RESULT.filename);

  assert.strictEqual(first.elements["state-message"].textContent, "Reading the flyer...");
  assert.strictEqual(first.elements["file-input"].disabled, true);
  assert.strictEqual(first.elements["result"].hidden, true);
  assert.strictEqual(browser.store.flyerExtraction.state, "processing");

  // The user closes the popup mid-extraction; the worker keeps going.
  first.close();
  host.release();
  await flush();

  assert.strictEqual(browser.store.flyerExtraction.state, "complete");

  const reopened = browser.openPopup();
  await flush();

  assert.strictEqual(reopened.elements["result"].hidden, false);
  assert.strictEqual(reopened.elements["event-date"].textContent, "2026-03-27");
  assert.strictEqual(reopened.elements["review-status"].textContent, "pending");
  assert.strictEqual(reopened.elements["file-input"].disabled, false);
  assert.deepStrictEqual(calendarState(reopened), { google: true, ics: true });

  // The past-date explanation is shown as a warning.
  assert.match(reopened.elements["status"].textContent, /already passed/);
  assert.strictEqual(reopened.elements["status"].className, "is-warning");
  assert.strictEqual(reopened.elements["status-row"].hidden, false);
});

test("a popup reopened during extraction shows progress, then the result", async () => {
  const host = deferredHost(hostResult(OK_RESULT));
  const browser = createBrowser({ host });

  const first = browser.openPopup();
  await flush();
  await first.selectFlyer(OK_RESULT.filename);
  first.close();

  const reopened = browser.openPopup();
  await flush();
  assert.strictEqual(reopened.elements["state-message"].textContent, "Reading the flyer...");
  assert.strictEqual(reopened.elements["filename"].textContent, OK_RESULT.filename);
  assert.strictEqual(reopened.elements["clear-results"].disabled, true);

  host.release();
  await flush();

  assert.strictEqual(reopened.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(
    reopened.elements["state-message"].textContent,
    "Found an event date. Review it below."
  );
});

test("warning explanations stay visible after the date is accepted", async () => {
  const distant = {
    filename: "far.jpeg",
    eventDate: "2027-09-01",
    status: "inferred_year_distant",
    needsReview: true,
  };
  const browser = createBrowser({ host: { respond: () => hostResult(distant) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(distant.filename);

  popup.elements["accept"].click();
  await flush();

  assert.match(popup.elements["status"].textContent, /Check the year/);
  assert.strictEqual(popup.elements["status"].className, "is-warning");
  assert.strictEqual(popup.elements["needs-review"].textContent, "Yes");
  assert.match(popup.elements["result"].className, /is-uncertain/);
});

const CONNECTION_ERROR =
  "Cannot reach the extractor. Reinstall the native host and reload.";

for (const [name, host] of [
  ["connectNative throws", { connectThrows: "Specified native messaging host not found." }],
  ["the port disconnects", { respond: () => ({ disconnect: "Native host has exited." }) }],
  ["the host has no pipeline", { respond: () => ({ ok: false, error: "pipeline_unavailable" }) }],
  ["the worker is unreachable", { workerUnreachable: true, respond: () => null }],
]) {
  test(`a connection error is shown when ${name}`, async () => {
    const browser = createBrowser({ host });
    const popup = browser.openPopup();
    await flush();
    await popup.selectFlyer("flyer.jpeg");

    assert.strictEqual(popup.elements["state-message"].textContent, CONNECTION_ERROR);
    assert.strictEqual(popup.elements["state-message"].className, "is-error");
    assert.strictEqual(popup.elements["file-input"].disabled, false);
  });
}

test("a connection error leaves the previous review in place", async () => {
  const seed = {
    flyerResult: {
      filename: "kept.jpeg",
      originalEventDate: "2027-03-27",
      eventDate: "2027-03-27",
      needsReview: false,
      reviewStatus: "accepted",
    },
  };
  const browser = createBrowser({
    seed,
    host: { respond: () => ({ disconnect: "Native host has exited." }) },
  });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer("new.jpeg");

  assert.strictEqual(popup.elements["state-message"].textContent, CONNECTION_ERROR);
  assert.strictEqual(popup.elements["event-date"].textContent, "2027-03-27");
  assert.strictEqual(browser.store.flyerResult.filename, "kept.jpeg");
  assert.deepStrictEqual(calendarState(popup), { google: false, ics: false });
});

test("Clear results empties the popup", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);
  assert.strictEqual(popup.elements["clear-results"].disabled, false);

  popup.elements["clear-results"].click();
  await flush();

  assert.strictEqual(popup.elements["result"].hidden, true);
  assert.strictEqual(
    popup.elements["state-message"].textContent,
    "Select a flyer to extract its event date."
  );
  assert.strictEqual(popup.elements["clear-results"].disabled, true);
  assert.strictEqual(browser.store.flyerResult, null);
});

test("an extraction interrupted by a worker restart becomes an error", async () => {
  const browser = createBrowser({
    seed: { flyerExtraction: { filename: "lost.jpeg", state: "processing" } },
    host: { respond: () => null },
  });
  await flush();

  const popup = browser.openPopup();
  await flush();

  assert.strictEqual(
    popup.elements["state-message"].textContent,
    "lost.jpeg could not be read. Try another image."
  );
  assert.strictEqual(popup.elements["file-input"].disabled, false);
});

report();
