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
  "status-label",
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

  popup.elements["event-date-input"].value = "04-02-2027";
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

  popup.elements["event-date-input"].value = "05-01-2027";
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
  assert.strictEqual(reopened.elements["event-date"].textContent, "03-27-2026");
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

  assert.strictEqual(reopened.elements["event-date"].textContent, "03-27-2027");
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

for (const [name, result] of [
  ["no date was found", { filename: "blurry.jpg", eventDate: null, status: "no_date_found", needsReview: true }],
  ["the date is not a real day", { filename: "feb30.jpg", eventDate: null, status: "invalid_date", needsReview: true }],
]) {
  test(`Accept is off and Edit leads when ${name}`, async () => {
    const browser = createBrowser({ host: { respond: () => hostResult(result) } });
    const popup = browser.openPopup();
    await flush();
    await popup.selectFlyer(result.filename);

    assert.strictEqual(popup.elements["review-status"].textContent, "pending");
    assert.strictEqual(popup.elements["accept"].disabled, true);
    assert.strictEqual(popup.elements["edit"].disabled, false);
    assert.strictEqual(popup.elements["edit"].hidden, false);
    assert.match(popup.elements["result"].className, /has-no-date/);
    assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });

    // A click on the disabled Accept changes nothing.
    popup.elements["accept"].click();
    await flush();
    assert.strictEqual(browser.store.flyerResult.reviewStatus, "pending");

    // Entering a date through Edit is what unlocks the calendar.
    popup.elements["edit"].click();
    popup.elements["event-date-input"].value = "06-12-2027";
    popup.elements["save"].click();
    await flush();

    assert.strictEqual(browser.store.flyerResult.reviewStatus, "edited");
    assert.doesNotMatch(popup.elements["result"].className, /has-no-date/);
    assert.deepStrictEqual(calendarState(popup), { google: false, ics: false });
    popup.elements["add-to-google-calendar"].click();
    assert.match(browser.tabs[0], /dates=20270612%2F20270613/);
  });
}

test("a restored pending date that is not a real day cannot be accepted", async () => {
  const browser = createBrowser({
    seed: {
      flyerResult: {
        filename: "restored.jpg",
        originalEventDate: "2027-02-30",
        eventDate: "2027-02-30",
        needsReview: true,
        reviewStatus: "pending",
      },
    },
    host: { respond: () => null },
  });
  const popup = browser.openPopup();
  await flush();

  assert.strictEqual(popup.elements["accept"].disabled, true);
  assert.strictEqual(popup.elements["edit"].disabled, false);
});

test("a pending result with a valid date can still be accepted", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);

  assert.strictEqual(popup.elements["accept"].disabled, false);
  assert.doesNotMatch(popup.elements["result"].className, /has-no-date/);
});

const INVALID_DATE_MESSAGE = "Enter a valid date in MM-DD-YYYY format.";

// Open a popup on an extracted result and start editing its date.
async function editingPopup(result = OK_RESULT) {
  const browser = createBrowser({ host: { respond: () => hostResult(result) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(result.filename);
  popup.elements["edit"].click();
  return { browser, popup };
}

for (const [name, typed] of [
  ["malformed text", "March 3"],
  ["an impossible date", "02-30-2027"],
  ["a date in the stored YYYY-MM-DD form", "2027-04-02"],
]) {
  test(`Save refuses ${name} and keeps editing open`, async () => {
    const { browser, popup } = await editingPopup();

    popup.elements["event-date-input"].value = typed;
    popup.elements["save"].click();
    await flush();

    assert.strictEqual(popup.elements["message"].textContent, INVALID_DATE_MESSAGE);
    assert.strictEqual(popup.elements["event-date-input"].hidden, false);
    assert.strictEqual(popup.elements["save"].hidden, false);
    assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });

    // Nothing was saved: the stored review is still the pending original.
    assert.strictEqual(browser.store.flyerResult.eventDate, "2027-03-27");
    assert.strictEqual(browser.store.flyerResult.reviewStatus, "pending");
  });
}

test("a valid correction after a refused one is saved", async () => {
  const { browser, popup } = await editingPopup();

  popup.elements["event-date-input"].value = "13-01-2027";
  popup.elements["save"].click();
  await flush();
  assert.strictEqual(popup.elements["message"].textContent, INVALID_DATE_MESSAGE);

  popup.elements["event-date-input"].value = "03-28-2027";
  popup.elements["save"].click();
  await flush();

  assert.strictEqual(popup.elements["message"].textContent, "Saved!");
  assert.strictEqual(popup.elements["event-date-input"].hidden, true);
  assert.strictEqual(browser.store.flyerResult.eventDate, "2027-03-28");
  assert.strictEqual(browser.store.flyerResult.reviewStatus, "edited");
  assert.deepStrictEqual(calendarState(popup), { google: false, ics: false });

  popup.elements["add-to-google-calendar"].click();
  assert.match(browser.tabs[0], /dates=20270328%2F20270329/);
});

test("a stored edited result with an invalid date keeps the calendar off", async () => {
  const browser = createBrowser({
    seed: {
      flyerResult: {
        filename: "older.jpg",
        originalEventDate: "2027-03-27",
        eventDate: "March 3",
        needsReview: false,
        reviewStatus: "edited",
      },
    },
    host: { respond: () => null },
  });
  const popup = browser.openPopup();
  await flush();

  assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });
  assert.match(popup.elements["result"].className, /is-invalid-date/);
});

test("an invalid date is marked Invalid date, a missing one No date found", async () => {
  const invalid = { filename: "feb30.jpg", eventDate: null, status: "invalid_date", needsReview: true };
  const missing = { filename: "blurry.jpg", eventDate: null, status: "no_date_found", needsReview: true };

  const { popup: invalidPopup } = await editingPopup(invalid);
  assert.match(invalidPopup.elements["result"].className, /is-invalid-date/);

  const { popup: missingPopup } = await editingPopup(missing);
  assert.match(missingPopup.elements["result"].className, /has-no-date/);
  assert.doesNotMatch(missingPopup.elements["result"].className, /is-invalid-date/);
});

test("a warning shown after a correction is labelled as the original's", async () => {
  const { popup } = await editingPopup(PAST_RESULT);

  // Before the correction the warning is about the date on screen.
  assert.strictEqual(popup.elements["status-label"].textContent, "");

  popup.elements["event-date-input"].value = "03-27-2027";
  popup.elements["save"].click();
  await flush();

  assert.strictEqual(
    popup.elements["status-label"].textContent,
    "Original extraction warning"
  );
  assert.match(popup.elements["status"].textContent, /already passed/);
  assert.strictEqual(popup.elements["status"].className, "is-warning");
});

test("an accepted warning keeps no original-extraction label", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(PAST_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(PAST_RESULT.filename);
  popup.elements["accept"].click();
  await flush();

  assert.strictEqual(popup.elements["status-label"].textContent, "");
  assert.strictEqual(popup.elements["status"].className, "is-warning");
});

test("an empty popup has both calendar actions off", async () => {
  const browser = createBrowser({ host: { respond: () => null } });
  const popup = browser.openPopup();
  await flush();

  assert.strictEqual(popup.elements["result"].hidden, true);
  assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });
});

for (const review of ["accepted", "edited"]) {
  test(`Clear results after an ${review} result turns the calendar off`, async () => {
    const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
    const popup = browser.openPopup();
    await flush();
    await popup.selectFlyer(OK_RESULT.filename);

    if (review === "accepted") {
      popup.elements["accept"].click();
    } else {
      popup.elements["edit"].click();
      popup.elements["event-date-input"].value = "03-29-2027";
      popup.elements["save"].click();
    }
    await flush();
    assert.strictEqual(browser.store.flyerResult.reviewStatus, review);
    assert.deepStrictEqual(calendarState(popup), { google: false, ics: false });

    popup.elements["clear-results"].click();
    await flush();

    assert.strictEqual(popup.elements["result"].hidden, true);
    assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });

    // A popup opened after clearing starts empty as well.
    const reopened = browser.openPopup();
    await flush();
    assert.strictEqual(reopened.elements["result"].hidden, true);
    assert.deepStrictEqual(calendarState(reopened), { google: true, ics: true });
  });
}

// Accept a result with this filename and download its ICS file.
async function downloadIcsFor(filename) {
  const result = { ...OK_RESULT, filename };
  const browser = createBrowser({ host: { respond: () => hostResult(result) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(filename || "unnamed.jpeg");
  popup.elements["accept"].click();
  await flush();
  popup.elements["export"].click();
  return popup;
}

for (const [filename, expected] of [
  ["cherry_blossom_market.jpeg", "cherry_blossom_market_2027-03-27.ics"],
  ["1000035675.jpg", "1000035675_2027-03-27.ics"],
  ["Spring Fair.PNG", "Spring_Fair_2027-03-27.ics"],
  ['a/b\\c:d*e?f"g<h>i|j.webp', "a_b_c_d_e_f_g_h_i_j_2027-03-27.ics"],
  ["???.png", "flyer-event_2027-03-27.ics"],
  ["  ...jpg", "flyer-event_2027-03-27.ics"],
]) {
  test(`the ICS file for ${JSON.stringify(filename)} is ${expected}`, async () => {
    const popup = await downloadIcsFor(filename);

    assert.strictEqual(popup.downloads.length, 1);
    assert.strictEqual(popup.downloads[0].filename, expected);
  });
}

test("the ICS file name uses the saved edited date; contents are unchanged", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);
  popup.elements["edit"].click();
  popup.elements["event-date-input"].value = "04-02-2027";
  popup.elements["save"].click();
  await flush();
  popup.elements["export"].click();

  assert.strictEqual(popup.downloads[0].filename, "cherry_blossom_market_2027-04-02.ics");

  const ics = await popup.icsText();
  assert.match(ics, /SUMMARY:cherry_blossom_market\.jpeg/);
  assert.match(ics, /DTSTART;VALUE=DATE:20270402/);
  assert.match(ics, /DTEND;VALUE=DATE:20270403/);
});

test("04-02-2027 displays and exports as April 2, 2027; 02-30-2027 is refused", async () => {
  const browser = createBrowser({ host: { respond: () => hostResult(OK_RESULT) } });
  const popup = browser.openPopup();
  await flush();
  await popup.selectFlyer(OK_RESULT.filename);

  // The pipeline's 2027-03-27 is shown, and offered for editing, as MM-DD-YYYY.
  assert.strictEqual(popup.elements["event-date"].textContent, "03-27-2027");
  popup.elements["edit"].click();
  assert.strictEqual(popup.elements["event-date-input"].value, "03-27-2027");
  assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });

  // An impossible date is refused; editing stays open with the calendar off.
  popup.elements["event-date-input"].value = "02-30-2027";
  popup.elements["save"].click();
  await flush();
  assert.strictEqual(
    popup.elements["message"].textContent,
    "Enter a valid date in MM-DD-YYYY format."
  );
  assert.strictEqual(popup.elements["event-date-input"].hidden, false);
  assert.deepStrictEqual(calendarState(popup), { google: true, ics: true });
  assert.strictEqual(browser.store.flyerResult.eventDate, "2027-03-27");

  popup.elements["event-date-input"].value = "04-02-2027";
  popup.elements["save"].click();
  await flush();

  // Shown as MM-DD-YYYY, stored as YYYY-MM-DD.
  assert.strictEqual(popup.elements["event-date"].textContent, "04-02-2027");
  assert.strictEqual(popup.elements["original-event-date"].textContent, "03-27-2027");
  assert.strictEqual(popup.elements["original-event-date-row"].hidden, false);
  assert.strictEqual(browser.store.flyerResult.eventDate, "2027-04-02");
  assert.strictEqual(browser.store.flyerResult.originalEventDate, "2027-03-27");

  // Google Calendar and the ICS file get April 2, 2027.
  popup.elements["add-to-google-calendar"].click();
  assert.match(browser.tabs[0], /dates=20270402%2F20270403/);
  popup.elements["export"].click();
  assert.strictEqual(popup.downloads[0].filename, "cherry_blossom_market_2027-04-02.ics");
  const ics = await popup.icsText();
  assert.match(ics, /DTSTART;VALUE=DATE:20270402/);
  assert.match(ics, /DTEND;VALUE=DATE:20270403/);

  // Reopening shows the saved date in the same format, and Edit prefills it.
  const reopened = browser.openPopup();
  await flush();
  assert.strictEqual(reopened.elements["event-date"].textContent, "04-02-2027");
  reopened.elements["edit"].click();
  assert.strictEqual(reopened.elements["event-date-input"].value, "04-02-2027");
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
  assert.strictEqual(popup.elements["event-date"].textContent, "03-27-2027");
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
