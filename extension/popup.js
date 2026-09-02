// Key used to remember the reviewed result in chrome.storage.local.
const STORAGE_KEY = "flyerResult";

// The real result written by the pipeline into latest_result.js.
const flyerResult = window.flyerResult;

// Switch the event date between the read-only span and the edit field.
function setEditing(editing) {
  document.getElementById("event-date").hidden = editing;
  document.getElementById("event-date-input").hidden = !editing;
  document.getElementById("edit").hidden = editing;
  document.getElementById("save").hidden = !editing;

  // Accepting a result while its date is still being edited would store the
  // old date, so Accept waits until the edit is saved.
  document.getElementById("accept").disabled =
    editing || flyerResult.status === "accepted";
}

// Display the result in the popup.
function renderResult(result) {
  document.getElementById("filename").textContent =
    result.filename;

  document.getElementById("needs-review").textContent =
    result.needsReview ? "Yes" : "No";

  document.getElementById("event-date").textContent =
    result.eventDate;

  document.getElementById("status").textContent =
    result.status;

  // Showing a result always leaves the date read-only; editing starts only
  // when the user asks for it.
  setEditing(false);

  // Show the accepted state: there is nothing left to accept, so the
  // Accept button is switched off (by setEditing) and the popup says so.
  const accepted = result.status === "accepted";
  document.getElementById("message").textContent = accepted ? "Accepted!" : "";
}

// Write the current result to chrome.storage.local and redraw the popup.
function saveResult(onSaved) {
  chrome.storage.local.set({ [STORAGE_KEY]: flyerResult }, () => {
    renderResult(flyerResult);

    if (onSaved) {
      onSaved();
    }
  });
}

// chrome.storage.local is asynchronous, so the popup is filled in once the
// stored value comes back.
chrome.storage.local.get(STORAGE_KEY, (stored) => {
  const savedResult = stored[STORAGE_KEY];

  // Only reuse a saved review when it belongs to the result that is currently
  // loaded. A newer pipeline run writes a different flyer, which has not been
  // reviewed yet.
  if (savedResult && savedResult.filename === flyerResult.filename) {
    flyerResult.status = savedResult.status;

    // A date the user corrected earlier replaces the one read from the flyer.
    if (savedResult.eventDate) {
      flyerResult.eventDate = savedResult.eventDate;
    }
  }

  renderResult(flyerResult);
});

// Find the Accept button and respond when the user clicks it.
document.getElementById("accept").addEventListener("click", () => {
  flyerResult.status = "accepted";

  // Persist the accepted result so it stays accepted after the popup closes.
  saveResult();
});

// The Edit button makes the displayed date editable.
document.getElementById("edit").addEventListener("click", () => {
  const input = document.getElementById("event-date-input");

  // Start from the date that is on screen so the user can correct it.
  input.value = flyerResult.eventDate;

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

  flyerResult.eventDate = correctedDate;

  // Persist the corrected result so the new date is shown the next time the
  // popup is opened.
  saveResult(() => {
    document.getElementById("message").textContent = "Saved!";
  });
});
