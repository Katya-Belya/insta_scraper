# Progress Notes

## Phase 1: Feasibility (OCR Works)
- Set up Tesseract and environment
- Ran OCR on full images (too noisy)
- Introduced region-based cropping
- Successfully extracted rough date text

Example:
RAW OCR: Pa 3/17/3679!  
DATE FOUND: 3/17/36

---

## Phase 2: Crop Optimization
- Tested multiple crop regions
- Identified best crop:
  (120, 930, 980, 1080)
- Result: reduced noise and improved OCR consistency

---

## Phase 3: Preprocessing Experiments
Tested:
- grayscale
- resize
- threshold
- threshold + resize

Finding:
- grayscale alone performed best
- resizing and thresholding degraded OCR accuracy

---

## Phase 4: OCR Configuration
- Tested multiple PSM modes (6, 7, 8, 13)
- Finding: minimal impact on results
- Added character whitelist (digits + "/")

---

## Phase 5: Date Extraction
- Implemented regex:
  (\d{1,2})/(\d{1,2})/(\d{2,4})
- Parsed month/day/year
- Added validation (month 1–12, day 1–31)

---

## Phase 6: Post-processing
- Identified consistent OCR errors in year field
- Applied normalization to correct misread years

Example:
RAW OCR: 02/17/2077  
NORMALIZED: 2/17/26  (manual correction for now)

Key insight:
- Isolating the date region and constraining OCR to a narrow character set significantly improved reliability.

---

## Status After Phase 6
- Date extraction works on a single flyer
- OCR is stable but imperfect
- Post-processing improves accuracy

---

## OCR Experiment Summary (Mar 24)
- Implemented region-based OCR (top/middle/bottom)
- Confirmed date location varies across flyers
- Tuned crop boxes for improved accuracy
- Identified grayscale preprocessing as most reliable
- Built regex-based numeric date extraction
- Observed OCR errors (e.g., incorrect year parsing)
- Began restructuring notebook into logical sections

---

## Phase 7: Pipeline and CSV Output
- Moved the notebook experiments into `src/` (`ocr.py`, `dates.py`,
  `pipeline.py`)
- Packaged everything known about one flyer into a `FlyerResult`
- Added multiple date candidates and nearest-upcoming-date selection
- Added a command-line runner that processes one image or a folder
- CSV export writes one row per flyer to `results.csv`

---

## CSV to ICS Proof of Concept
- Built a standalone `csv_to_ics.py` converter on top of `icalendar`
- Reads the pipeline's CSV output and writes a calendar file
- Rows without a usable date are skipped rather than exported
- Each exported row becomes an all-day event
- Tested end to end: an earlier nine-event file was generated and imported
  successfully into Google Calendar

This proves the CSV to ICS path works. It is only a proof of concept: the
converter is standalone and is not yet connected to the canonical
reviewed-result workflow, so it still exports pipeline rows rather than
reviewed ones.

---

## Phase 8: Chrome Integration
- A run writes `extension/latest_result.js`, a small data file holding the
  most recent `FlyerResult` (`filename`, `eventDate`, `status`, `needsReview`)
- `extension/` holds a Chrome extension whose popup reads that file and shows
  the result
- Gave the popup Accept and Edit buttons for reviewing what the pipeline read

---

## Phase 9: Canonical Review Workflow
The popup now maintains one canonical reviewed result, which is the single
object describing a flyer after review:

- `originalEventDate` - the date the pipeline read, never changed by a review
- `eventDate` - the date the review settled on
- `needsReview` - the pipeline's own "a human should look at this" flag
- `reviewStatus` - what the human did about it

Review statuses are:

- `pending` - nobody has reviewed this flyer yet
- `accepted` - the user confirmed the date the pipeline read
- `edited` - the user replaced that date

Behavior:

- Accept and Edit both persist the canonical result through
  `chrome.storage.local`, so a review survives closing and reopening the popup
- Editing preserves the pipeline's original date: only `eventDate` moves, and
  `originalEventDate` still holds what OCR read
- The pipeline's `status` stays separate from the human `reviewStatus`, so a
  review can never overwrite a pipeline value
- Accept is disabled once a review has settled, after either acceptance or
  editing: there is nothing left to accept, and accepting a corrected date
  would relabel it as the one the pipeline read
- The workflow is covered by `tests/popup_review.test.js`, run with
  `node tests/popup_review.test.js`

---

## Phase 10: Calendar Export from Reviewed Results

* Added an **Export to Calendar** button to the Chrome extension
* Added `extension/ics.js` to create calendar files directly in JavaScript
* Only `accepted` and `edited` results can be exported
* `pending` results are blocked until the user reviews them
* Export uses the reviewed `eventDate`, including any correction made by the user
* Each result is exported as an all-day event because event times are not yet extracted
* The calendar description tells the user to verify the time against the original flyer
* The JPEG filename is temporarily used as the event title
* The downloaded file is named `reviewed_events.ics`
* Added automated tests for accepted, edited, and pending results
* Tested the full workflow in Chrome and successfully imported an edited event into Google Calendar

---

## Current Status

- The pipeline processes flyer images, extracts a normalized event date, and writes `results.csv`
- The most recent pipeline result is also sent to the Chrome extension
- The popup lets the user Accept the extracted date or Edit and Save a correction
- The reviewed result persists in `chrome.storage.local`
- Accepted and edited results can be downloaded as `reviewed_events.ics`
- Pending results cannot be exported
- Calendar export uses the reviewed `eventDate`, not the original OCR date
- The standalone `csv_to_ics.py` remains as an earlier proof of concept; the extension now generates its own calendar file directly in JavaScript
- OCR remains imperfect, so human review is still part of the workflow

---

## Next Steps

- Let the user select a flyer from inside the extension
- Extract and review an event title from the flyer
- Extract and review event times, venues, and other details
- Replace the temporary JPEG-based calendar title with the reviewed event title
- Support multiple reviewed flyers and batch calendar export
- Support Instagram caption ingestion alongside flyer images

---

## Known Limitations

- Some flyer date formats and layouts are still not handled correctly
- Crop selection is not fully generalized across flyers
- Year selection still relies on heuristics
- The extension handles only the most recent flyer, so flyers are reviewed and exported one at a time
- Event times are not extracted, so calendar exports are currently all-day placeholders
- The JPEG filename is temporarily used as the calendar event title
- The downloaded calendar file always uses the generic name `reviewed_events.ics`
- Venue, price, and other event details are not yet included in the export