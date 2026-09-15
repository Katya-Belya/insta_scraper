/*
 * Temporary: the extension half of the native messaging ping test.
 *
 * Milestone 1 of the native messaging POC. It is kept out of popup.js on
 * purpose - the review workflow in that file has nothing to do with this, and
 * a separate script means the ping test can be deleted in one step once the
 * real transport replaces it.
 *
 * Clicking the button sends {"action": "ping"} to the Python host, which
 * Chrome starts by itself. Either the host's {"ok": true, "message": "pong"}
 * or the reason it could not be reached is shown under the button.
 */

// Must match "name" in native_host/com.insta_scraper.native_host.json and the
// registry key register_host.bat writes.
const NATIVE_HOST_NAME = "com.insta_scraper.native_host";

// What the popup says while Chrome is starting the host.
const PINGING_MESSAGE = "Pinging native host...";

const pingButton = document.getElementById("ping-native-host");
const pingResult = document.getElementById("ping-native-host-result");

function showPingResult(text, tone) {
  if (!pingResult) {
    return;
  }

  pingResult.textContent = text;
  pingResult.className = tone;
}

if (pingButton) {
  pingButton.addEventListener("click", () => {
    showPingResult(PINGING_MESSAGE, "is-working");

    chrome.runtime.sendNativeMessage(
      NATIVE_HOST_NAME,
      { action: "ping" },
      (response) => {
        // Every way this can fail - host not registered, extension ID missing
        // from allowed_origins, Python not on PATH, host crashed on startup -
        // arrives here rather than as an exception, and the text of
        // lastError is the only clue about which one it was. Reading it also
        // stops Chrome from logging it as an unchecked error.
        const error = chrome.runtime.lastError;

        if (error) {
          showPingResult(`Native host error: ${error.message}`, "is-error");
          return;
        }

        if (response && response.ok && response.message === "pong") {
          showPingResult(`Native host replied: ${response.message}`, "is-success");
          return;
        }

        // The host answered, but not with the pong this milestone is about.
        showPingResult(
          `Unexpected reply: ${JSON.stringify(response)}`,
          "is-error"
        );
      }
    );
  });
}
