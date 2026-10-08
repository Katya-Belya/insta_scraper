// Own extraction independently of the popup. Only completed review data is
// retained; the image payload stays in memory and is never written to storage.
const JOB_KEY = "flyerExtraction";
const RESULT_KEY = "flyerResult";
const NATIVE_HOST_NAME = "com.insta_scraper.native_host";
let activeJob = null;
let starting = false;

// A connected native port keeps this worker alive while Python is working.
function sendToNativeHost(message) {
  return new Promise((resolve, reject) => {
    let port;
    let settled = false;
    const finish = (error, response) => {
      if (settled) return;
      settled = true;
      if (error) reject(error); else resolve(response);
      port?.disconnect();
    };
    try {
      port = chrome.runtime.connectNative(NATIVE_HOST_NAME);
      port.onMessage.addListener((response) => {
        if (!response) finish(new Error("The native host returned no response."));
        else finish(null, response);
      });
      port.onDisconnect.addListener(() => {
        const error = chrome.runtime.lastError;
        finish(new Error(error?.message || "The extractor disconnected before answering."));
      });
      port.postMessage(message);
    } catch (error) {
      finish(error);
    }
  });
}

async function completeExtraction(job, responsePromise) {
  try {
    const response = await responsePromise;
    if (!response.ok) {
      const errorState = response.error === "unsupported_file_type"
        ? "invalidFile" : response.error === "pipeline_unavailable"
          ? "connectionError" : "extractionError";
      await chrome.storage.local.set({
        [JOB_KEY]: { ...job, state: "error", errorState },
      });
      return;
    }
    const result = response.result;
    if (!result || typeof result.filename !== "string") {
      throw new Error("The extractor returned an invalid result.");
    }
    await chrome.storage.local.set({
      [JOB_KEY]: { ...job, state: "complete", pipelineStatus: result.status ?? null },
      [RESULT_KEY]: {
        filename: result.filename,
        originalEventDate: result.eventDate ?? null,
        eventDate: result.eventDate ?? null,
        needsReview: result.needsReview ?? false,
        reviewStatus: "pending",
      },
    });
  } catch (error) {
    console.error("Flyer extraction failed:", error);
    await chrome.storage.local.set({
      [JOB_KEY]: { ...job, state: "error", errorState: "connectionError" },
    });
  } finally {
    activeJob = null;
  }
}

async function startExtraction(message) {
  await recovery;
  if (starting || activeJob) return { ok: false, error: "An extraction is already running." };
  starting = true;
  try {
    const job = { filename: message.filename, state: "processing", startedAt: Date.now() };
    activeJob = job;
    await chrome.storage.local.set({ [JOB_KEY]: job });
    const responsePromise = sendToNativeHost({
      type: "extract", filename: message.filename, imageBase64: message.imageBase64,
    });
    void completeExtraction(job, responsePromise);
    return { ok: true };
  } catch (error) {
    activeJob = null;
    return { ok: false, error: error.message };
  } finally {
    starting = false;
  }
}

async function clearResults() {
  await recovery;
  if (starting || activeJob) {
    return { ok: false, error: "Wait for extraction to finish before clearing." };
  }
  starting = true;
  try {
    // Keep a cleared marker so latest_result.js cannot restore an old result.
    await chrome.storage.local.set({
      [RESULT_KEY]: null,
      [JOB_KEY]: { state: "cleared" },
    });
    return { ok: true };
  } finally {
    starting = false;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return;
  let operation;
  if (message?.type === "clearResults") {
    operation = clearResults();
  } else if (message?.type === "startExtraction") {
    if (typeof message.filename !== "string" || typeof message.imageBase64 !== "string") {
      sendResponse({ ok: false, error: "Invalid extraction request." });
      return;
    }
    operation = startExtraction(message);
  } else {
    return;
  }
  operation.then(sendResponse, (error) => {
    sendResponse({ ok: false, error: error.message });
  });
  return true;
});

// A browser restart/reload cannot resume Python's interrupted request.
// Convert leftover progress to a visible error instead of showing it forever.
async function recoverInterruptedJob() {
  const stored = await chrome.storage.local.get(JOB_KEY);
  if (!starting && !activeJob && stored[JOB_KEY]?.state === "processing") {
    await chrome.storage.local.set({
      [JOB_KEY]: { ...stored[JOB_KEY], state: "error", errorState: "extractionError" },
    });
  }
}
// Run recovery before allowing the first request in a fresh worker instance.
const recovery = recoverInterruptedJob();
