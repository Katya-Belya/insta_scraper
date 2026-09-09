# Mentor Meeting Notes — September 9, 2026

### Completed the End-to-End V1 Workflow

The extension now supports one flyer moving through the full workflow:

```text
Select flyer
    ↓
Python OCR/date extraction
    ↓
Pending result
    ↓
Accept or Edit
    ↓
ICS export
    ↓
Google Calendar
```

The reviewed-result calendar export is complete and uses the final reviewed `eventDate`.

The extension also now has a visible Select Flyer workflow connected to the existing Python extraction pipeline.

The upload work has been merged into `main`.

### Current Runtime Architecture

The current extraction flow uses a local Python service:

```text
Chrome extension
    ↓
POST image to localhost
    ↓
python -m src.server
    ↓
Existing OCR/date pipeline
    ↓
JSON result returned to Chrome
```

This works, but the user has to start:

```text
python -m src.server
```

before selecting a flyer.

That makes the workflow functional for development and demos, but not self-contained for a nontechnical user.

### Issues Identified During Testing

Several limitations remain:

* If a month/day has already passed in the current year, the parser assumes the next occurrence and may assign the following year.
* Re-importing the same `.ics` data can create duplicate calendar events.
* The generated calendar event currently uses the image filename as its title.
* Event time is not extracted, so calendar events are date-only/all-day.
* The `.ics` file still has to be downloaded and then manually opened/imported.
* The Python service must be started outside the browser before new flyer extraction can run.

---

## Current V1 Status

Completed:

* Real flyer selection in Chrome
* Runtime connection to the Python OCR/date pipeline
* Pending review state
* Accept and Edit workflows
* Persistent reviewed results
* Calendar export
* Successful Google Calendar import
* One complete single-flyer workflow
* Upload feature merged into `main`

Remaining:

* Remove or hide the manual Python-server startup step
* Simplify calendar output so the user does not have to manually handle the `.ics` file
* Reduce the happy path to roughly three clicks
* Decide whether the year-inference issue should be fixed before V1 is considered complete
* Revisit duplicate calendar behavior
* Polish the interface and error states
* Update final documentation
* Prepare the October lightning talk

---

## Mentor Feedback

### Make the workflow self-contained

The biggest remaining issue is that the user currently has to leave the browser and run:

```text
python -m src.server
```

before the extension can process a flyer.

The preferred experience is for the extension to invoke the existing Python extraction pipeline automatically.

A likely next architecture to investigate is Chrome Native Messaging:

```text
Chrome extension
    ↓
Native Messaging
    ↓
Python helper starts automatically
    ↓
Existing OCR/date pipeline
    ↓
Result returned to Chrome
```

The immediate goal is not to solve packaging or installation. First prove that Chrome can invoke the existing Python process without requiring a separate terminal step.

### Reduce the workflow to about three clicks

The current output flow is still too manual:

```text
Export ICS
    ↓
Download file
    ↓
Open/import file
    ↓
Google Calendar
```

The preferred user experience should be closer to:

```text
1. Select Flyer
2. Accept or Edit
3. Add to Calendar
```

The `.ics` workflow can remain as a secondary export option, but it should not necessarily be the main happy path if a more direct calendar flow is possible.

### Stay focused on friction in the core workflow

Do not expand into additional extraction features until the basic user path is self-contained and simple.

The current priority is reducing friction, not adding more capabilities.

---

## Next Steps

### 1. Make Flyer Input Self-Contained

* Prototype Chrome Native Messaging.
* Keep the existing Python OCR/date pipeline.
* Replace the manual `python -m src.server` startup step.
* Prove that Select Flyer can automatically invoke Python and return a result.
* Do not solve installer/packaging work yet.

### 2. Simplify Calendar Output

* Investigate a direct Add to Google Calendar flow.
* Reduce or eliminate manual `.ics` handling from the primary workflow.
* Keep `.ics` export as a secondary option if useful.
* Re-test duplicate behavior under the final output approach.

### 3. Address Core Correctness Issues

* Test and document the past-date/next-year inference problem.
* Decide whether Edit is an adequate V1 safeguard or whether the inference rule needs adjustment.
* Revisit duplicate calendar-event behavior.
* Confirm failed extraction does not overwrite the previous reviewed result.

### 4. Polish the User Experience

* Make Select Flyer the obvious starting point.
* Show clear processing, success, and error states.
* Keep Accept/Edit straightforward.
* Make the final calendar action obvious.
* Remove or hide implementation details that a nontechnical user should not have to understand.

### 5. Stabilize and Document

* Run one clean end-to-end workflow without manually starting a server.
* Test one correct result and one edited result.
* Test no-date and failure cases.
* Update README and CHANGELOG after the architecture settles.
* Document remaining limitations.

### 6. Prepare the Lightning Talk

* Commit to presenting by September 30.
* Choose a working title.
* Prepare the October 15 presentation.
* Build a reliable live-demo sequence.
* Prepare screenshots or a recording as a fallback.
* Focus the story on the evolution from a Python prototype to a more self-contained Chrome workflow.

---

## Deferred Beyond V1

For now, continue to defer:

* Semantic event-title extraction
* Start and end time extraction
* Multiple-flyer processing
* Review queues and batch export
* Duplicate detection beyond what is needed for the final V1 output path
* Multiple events per flyer
* Direct Instagram capture
* Mobile support
* Broad repository refactoring
* Full installer/packaging work until the Native Messaging architecture is proven

## V1 Goal

> One flyer, one reviewed result, and one calendar action through a clear, self-contained Chrome workflow.

The immediate task is to remove the manual Python-server step. After that, simplify calendar output so the entire happy path can happen in roughly three clicks without leaving the browser.
