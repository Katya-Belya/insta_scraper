# Mentor Meeting Notes — September 2, 2026

### Connected the Python Pipeline to Chrome

The extension now displays a real result from the Python extraction pipeline instead of sample data.

The current development flow is:

```text
Python pipeline → Chrome extension → Human review
```

The popup shows the filename, extracted date, reviewed date, pipeline status, and review status.

### Completed Accept and Edit

The user can now:

* Accept a correctly extracted date
* Edit and save an incorrect date
* Cancel an edit
* See validation messages for missing or invalid dates

Reviewed results are saved in Chrome storage and remain available after the popup is closed and reopened.

Both actions now produce the same basic result:

* `originalEventDate`: what the pipeline extracted
* `eventDate`: the final reviewed date
* `reviewStatus`: `pending`, `accepted`, or `edited`

This gives later features one reliable `eventDate` to use.

### Tested Calendar Export

I also completed a CSV-to-ICS experiment. It generated nine calendar events, skipped rows without dates, and imported successfully into Google Calendar.

This proved that the project can create usable calendar files. The next step is connecting that export process directly to the reviewed result in the extension.

### Repository Status

The completed work and calendar prototype are preserved, merged into `main`, and pushed to GitHub. The repository is clean and up to date.

---

## Current V1 Status

Completed:

* Real pipeline result displayed in Chrome
* Accept and Edit workflows
* Date validation
* Persistent reviewed results
* Consistent `pending`, `accepted`, and `edited` states
* Working calendar-export proof of concept

Remaining:

* Add an Export button
* Connect the reviewed result to `.ics` export
* Add a presentable way to select one flyer
* Improve the interface
* Complete and document one end-to-end demonstration

---

## Mentor Feedback

### Stay focused on the V1 workflow

Avoid spending more time on general repository cleanup unless a specific issue blocks the project.

### Add an Export button

The extension should export the final reviewed date:

| Review status | Export behavior           |
| ------------- | ------------------------- |
| `pending`     | Do not allow export       |
| `accepted`    | Export the accepted date  |
| `edited`      | Export the corrected date |

Accept/Edit and Export should remain separate actions:

* **Accept** confirms the extracted date.
* **Edit** corrects and confirms the date.
* **Export** creates the calendar file.

### One flyer is enough

V1 only needs to demonstrate one flyer moving through the full workflow. It does not need batch processing, a review queue, duplicate detection, or multiple events from one flyer.

### Make the experience presentable

The extension should give a nontechnical user:

* A clear way to select one flyer
* A simple view of the extracted result
* Understandable Accept, Edit, and Export buttons
* Clear loading, validation, success, and error messages

The interface does not need to be elaborate. It just needs to feel clear and intentional.

---

## Next Steps

### 1. Add Calendar Export

* Add an Export button.
* Allow export only after Accept or Edit.
* Use the final reviewed `eventDate`.
* Test both accepted and edited results.
* Import the generated `.ics` file into Google Calendar.

### 2. Add a Flyer Input

* Add a Select Flyer or Upload Flyer button.
* Show the selected filename or a small preview.
* Send the image to the Python pipeline.
* Return the extracted result to the popup as `pending`.

### 3. Polish and Demonstrate

* Improve the layout, labels, and button states.
* Use plain-language messages.
* Demonstrate one flyer from selection through calendar export.
* Update the README.

---

## Deferred Beyond V1

For now, defer:

* Further OCR optimization
* Larger benchmark expansion
* Multiple-flyer processing
* Review queues and batch export
* Duplicate detection
* Multiple events per flyer
* Direct Instagram capture
* Mobile support
* Broad repository refactoring

## V1 Goal

> One flyer, one reviewed result, and one successful calendar export through a clear Chrome interface.

The immediate task is to connect the reviewed result to an Export button. After that, focus on flyer input and interface polish.
