# Instagram Event Scraper

A Python project for converting Instagram event flyers into structured event data using image preprocessing, optical character recognition (OCR), pattern matching, and post-processing.

The long-term goal is to turn difficult-to-search social media posts into clean, calendar-ready event records.

## Example Flyer

![Cherry Blossom Market](data/sample/cherry_blossom_market.jpeg)

*Sample flyer used during OCR development.*


## Current Status

The project currently includes a working prototype for extracting and normalizing event dates from flyer images.

The prototype:

- loads a flyer image,
- crops a likely date region,
- applies grayscale image preprocessing,
- extracts text with Tesseract OCR,
- detects date patterns with regular expressions,
- and corrects likely OCR errors through post-processing.

### Example

Using the sample flyer in `data/sample/cherry_blossom_market.jpeg`

**Raw OCR result**

```text
FRIDAY, MARCH 27th
4PM - 8PM
```

**Extracted date**

```text
March 27
```

**Normalized date**

```text
2026-03-27
```

The normalization step converts extracted dates into a consistent machine-readable format suitable for downstream processing and calendar export.

## V1 Workflow

One flyer, one reviewed date, one calendar file, all from the Chrome popup:

```text
Select Flyer  ->  Native Messaging  ->  pipeline  ->  reviewed result
 (popup)          (src/native_host.py)  (src/*.py)    (Accept / Edit)
                                                            |
                                                            v
                                                  Export to Calendar
                                                   (reviewed_events.ics)
```

The extension cannot run Tesseract, so the popup hands the flyer to a Python
process instead. Chrome launches that process itself, through Native
Messaging, the moment a flyer is selected - so there is nothing for the user
to start first.

`src/native_host.py` contains no extraction logic. It reads one message from
stdin, writes the flyer to a temporary file, calls the same
`extract_event_date()` the command-line runner calls, and writes back the four
fields the popup already reads: `filename`, `eventDate`, `status`, and
`needsReview`.

A Native Messaging message is JSON, so the image travels base64-encoded:

```text
->  {"type": "extract", "filename": "flyer.jpeg", "imageBase64": "..."}
<-  {"ok": true, "result": {"filename": "flyer.jpeg",
                            "eventDate": "2027-03-27",
                            "status": "ok", "needsReview": false}}
```

Anything that goes wrong answers in one shape instead, which is how the popup
chooses its error state:

```text
<-  {"ok": false, "error": "unsupported_file_type", "message": "..."}
```

There is also `{"type": "ping"}`, which answers
`{"ok": true, "message": "pong"}`. It needs neither an image nor the OCR
stack, so it is the quickest way to tell a broken host registration apart from
a broken pipeline.

### Setting it up

This replaces `python -m src.server`, which the popup no longer uses.

1. Load `extension/` in Chrome at `chrome://extensions` with Developer mode
   on ("Load unpacked").
2. Copy the extension's id - the 32-letter string under **Flyer Event
   Extractor** on that page.
3. Register the native host, using the interpreter that has this project's
   requirements installed:

   ```bash
   python native_host/install_host.py <extension-id>
   ```

4. Reload the extension, open the popup, and click **Select Flyer**.

Step 3 writes a host manifest into Chrome's `NativeMessagingHosts` directory
(or, on Windows, the matching registry key). It records the two things that
differ on every machine: the absolute path of
`native_host/flyer_extractor_host.py` and the id from step 2. Chrome assigns a
new id if the extension is removed and loaded again, so rerun it when that
happens.

The interpreter matters. Chrome inherits none of the shell's environment, so a
host registered from outside the project's virtual environment finds no Pillow
and no pytesseract. `install_host.py` records whichever interpreter runs it,
which is why it should be run from the activated environment. A host that
cannot import the pipeline says so rather than dying, and the popup shows the
connection-error state.

This is a prototype's setup, not an installer: it registers the host for one
user, against a checkout that stays where it is. Packaging is deliberately
still out of scope.

While a flyer moves through the workflow the popup is in exactly one state:

| State            | What the popup shows                                     |
| ---------------- | -------------------------------------------------------- |
| idle             | Nothing has been selected yet                             |
| processing       | The flyer is being read                                   |
| success          | A date was extracted and is ready to review               |
| no date found    | The flyer was read but no date was legible; Edit adds one |
| invalid file     | The chosen file is not an image the pipeline can read     |
| connection error | Chrome could not launch the host, or the host has no       |
|                  | pipeline behind it                                        |

An extraction that fails leaves the previous reviewed result untouched, so an
unregistered host or a stray file selection cannot discard a review.

The extracted result is stored in `chrome.storage.local` with `reviewStatus`
set to `pending`, which is where the review workflow below picks it up.

### Reviewing and exporting

The popup keeps one canonical reviewed result per flyer:

| Field               | Meaning                                          |
| ------------------- | ------------------------------------------------ |
| `filename`          | The flyer the result is about                     |
| `originalEventDate` | The date the pipeline read, never changed         |
| `eventDate`         | The date the review settled on                    |
| `needsReview`       | The pipeline's own "a human should look at this"  |
| `reviewStatus`      | `pending`, `accepted`, or `edited`                |

**Accept** confirms the extracted date, **Edit** and **Save** replace it, and
**Export to Calendar** writes `reviewed_events.ics` from the reviewed
`eventDate`. Only `accepted` and `edited` results can be exported.

The command-line runner still works as it did: `python -m src.pipeline <path>`
writes `results.csv` and `extension/latest_result.js`, and a popup opened after
such a run shows that result.

### Running the tests

```bash
pytest
node tests/popup_flyer_input.test.js
node tests/popup_review.test.js
node tests/ics.test.js
```

The extension tests stub the native host, and `tests/test_native_host.py`
stubs `src.pipeline`, so neither needs a registered host or an OCR install.

## Key Findings

- Cropping the date region improves OCR accuracy.
- Grayscale preprocessing generally produces better results than processing the full-color flyer directly.
- Tesseract often identifies the month and day correctly while misreading the year.
- Regular expressions and post-processing substantially improve the usefulness of raw OCR output.

## Current Limitations

- The pipeline has only been validated on a small number of flyers.
- Year correction is currently heuristic-based.
- Time, venue, price, and event-name extraction are not yet implemented as a complete pipeline.
- Instagram caption ingestion is planned but not yet implemented.
- Only one flyer at a time is handled: there is no review queue or batch
  export.
- Event name, time, venue, and price are still not extracted, so an exported
  calendar entry is an all-day event named after the flyer's filename.

## Planned Pipeline

```text
Instagram post
(caption + flyer image)
        ↓
Caption and image ingestion
        ↓
Image preprocessing
        ↓
OCR
        ↓
Event-field extraction
        ↓
Normalization and confidence scoring
        ↓
Manual review of low-confidence results
        ↓
CSV or ICS export
```

## Planned Output Fields

The completed pipeline may extract fields such as:

- event name
- date
- start time
- end time
- venue
- address
- price
- source account
- confidence score

Potential export formats include:

- CSV
- ICS for calendar applications such as Google Calendar

## Project Structure

```text
insta_scraper/
├── data/
│   ├── processed/
│   ├── raw/
│   └── sample/
│       └── cherry_blossom_market.jpeg
├── evaluation/
│   ├── README.md
│   ├── ground_truth_v2.csv
│   ├── results_benchmark_v2.1.csv
│   └── ...
├── extension/
│   ├── ics.js
│   ├── manifest.json
│   ├── popup.html
│   └── popup.js
├── native_host/
│   ├── com.flyer_extractor.host.json
│   ├── flyer_extractor_host.py
│   └── install_host.py
├── notebooks/
│   ├── 01_ocr_smoke_test.ipynb
│   └── 02_region_ocr_test.ipynb
├── src/
│   ├── __init__.py
│   ├── dates.py
│   ├── native_host.py
│   ├── ocr.py
│   ├── pipeline.py
│   └── server.py
├── tests/
│   ├── ics.test.js
│   ├── popup_flyer_input.test.js
│   ├── popup_harness.js
│   ├── popup_review.test.js
│   ├── test_dates.py
│   ├── test_native_host.py
│   ├── test_ocr.py
│   ├── test_pipeline.py
│   └── test_server.py
├── .gitignore
├── .pre-commit-config.yaml
├── CHANGELOG.md
├── LICENSE
├── README.md
├── conftest.py
├── evaluate.py
└── requirements.txt
```

### Folder Purposes

- `data/sample/` contains permanent demonstration images.
- `data/raw/` is intended for newly ingested, unprocessed images.
- `data/processed/` is intended for cropped or preprocessed image outputs.
- `evaluation/` collects ground-truth spreadsheets, benchmark results, and run
  logs from earlier pipeline versions.
- `extension/` is a Chrome extension: the user selects a flyer in its popup,
  the popup sends it to the native host, and the extracted date is reviewed
  and exported there.
- `native_host/` is what Chrome launches: `flyer_extractor_host.py` is the
  script named in the host manifest, `com.flyer_extractor.host.json` is the
  template that manifest is built from, and `install_host.py` registers it for
  this machine.
- `notebooks/` contains exploratory OCR experiments.
- `src/` contains the pipeline itself: `ocr.py` reads a flyer image, `dates.py`
  finds and normalizes dates in that text, `pipeline.py` runs the stages in
  order and writes the output, and `native_host.py` puts that same pipeline
  behind Chrome Native Messaging so the extension can use it. `server.py` is
  the local HTTP interface that did that job before; the popup no longer calls
  it, and it is kept for now only because removing it is a separate decision.
- `tests/` holds the Python tests, run with `pytest`, alongside the extension
  tests, which run with `node`. `popup_flyer_input.test.js` covers selecting a
  flyer and extracting it, `popup_review.test.js` covers reviewing the result,
  `ics.test.js` covers calendar export, `popup_harness.js` is the stub popup
  the first two run against, and `test_native_host.py` covers the Native
  Messaging wire format and its dispatch into the pipeline.

`data/raw/` and `data/processed/` are gitignored. Ingested flyers are
third-party content and may identify event organizers and attendees, so they
stay local; only `data/sample/` is tracked.

`results.csv` and `extension/latest_result.js` are gitignored too: the pipeline
writes both, so they are outputs of a run rather than source.

## Requirements

- Python 3.10 or later
- Google Chrome, for the extension and the native host
- The Tesseract OCR engine, installed separately and available on `PATH`
- Python packages listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

## Notebook Hygiene

**Clear all notebook outputs before committing.** Rendered flyer images are
stored inside `.ipynb` files as base64 data, so committing outputs publishes
the images themselves along with the code.

A `pre-commit` hook enforces this automatically. Set it up once per clone:

```bash
pip install pre-commit
pre-commit install
```

After that, `nbstripout` strips outputs from any notebook you commit. To keep
one cell's output — a final result worth seeing in the diff — add
`"keep_output": true` to that cell's metadata.

## Why This Project Exists

Event information posted on Instagram is often difficult to search, sort, and transfer into a calendar.

Important details may be divided between:

- captions,
- flyer images,
- account metadata,
- and external ticket links.