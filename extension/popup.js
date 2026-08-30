// Key used to remember the reviewed result in chrome.storage.local.
const STORAGE_KEY = "flyerResult";

// The real result written by the pipeline into latest_result.js.
const flyerResult = window.flyerResult;

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

  // Show the accepted state: there is nothing left to accept, so the
  // Accept button is switched off and the popup says so.
  const accepted = result.status === "accepted";
  document.getElementById("accept").disabled = accepted;
  document.getElementById("message").textContent = accepted ? "Accepted!" : "";
}

// chrome.storage.local is asynchronous, so the popup is filled in once the
// stored value comes back.
chrome.storage.local.get(STORAGE_KEY, (stored) => {
  const savedResult = stored[STORAGE_KEY];

  // Only reuse a saved status when it belongs to the result that is currently
  // loaded. A newer pipeline run writes a different flyer, which has not been
  // reviewed yet.
  if (savedResult && savedResult.filename === flyerResult.filename) {
    flyerResult.status = savedResult.status;
  }

  renderResult(flyerResult);
});

// Find the Accept button and respond when the user clicks it.
document.getElementById("accept").addEventListener("click", () => {
  flyerResult.status = "accepted";

  // Persist the accepted result so it stays accepted after the popup closes.
  chrome.storage.local.set({ [STORAGE_KEY]: flyerResult }, () => {
    renderResult(flyerResult);
  });
});

// The Edit button is only a placeholder for now.