const flyerResult = window.flyerResult;

document.getElementById("filename").textContent =
  flyerResult.filename;

document.getElementById("needs-review").textContent =
  flyerResult.needsReview ? "Yes" : "No";

// Display the result in the popup.
document.getElementById("event-date").textContent =
  flyerResult.eventDate;

document.getElementById("status").textContent =
  flyerResult.status;

// Find the Accept button and respond when the user clicks it.
document.getElementById("accept").addEventListener("click", () => {
  document.getElementById("message").textContent = "Accepted!";
});

// The Edit button is only a placeholder for now.
// Later it could expose editable event fields.
document.getElementById("edit").addEventListener("click", () => {
  document.getElementById("message").textContent = "Edit clicked.";
});
