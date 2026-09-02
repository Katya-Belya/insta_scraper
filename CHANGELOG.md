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

## Current Status
- The end-to-end pipeline runs from a flyer image to a normalized event date
  and writes `results.csv`
- A run also publishes its most recent result to the Chrome extension
- The CSV to ICS path is proven by a standalone `csv_to_ics.py` proof of
  concept, which is not yet connected to the reviewed-result workflow
- The popup's review workflow is complete: Accept and Edit are both
  implemented and both persist through `chrome.storage.local`
- A reviewed flyer carries a canonical result with `originalEventDate`,
  `eventDate`, `needsReview`, and `reviewStatus`
- OCR remains imperfect, so human review is still part of the flow

---

## Next Steps
- Export only canonical results whose `reviewStatus` is `accepted` or
  `edited`, using `eventDate` as the event's date
- Leave `pending` results out of the export: nobody has reviewed them yet
- Connect the `csv_to_ics.py` proof of concept to that export, so a calendar
  file is built from reviewed results instead of raw pipeline rows
- Extract more event fields (time, venue, price, event name)
- Support Instagram caption ingestion alongside the flyer image

## Known Limitations
- Does not yet handle every text-based date format seen in flyers
- Crop logic is not fully generalized across flyers
- Year normalization is heuristic and not automated
- Only the most recent pipeline result reaches the extension, so flyers are
  reviewed one at a time
- Nothing yet consumes the reviewed results: both the CSV export and the
  `csv_to_ics.py` proof of concept still work from pipeline rows, reviewed
  or not
