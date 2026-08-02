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
- CSV and ICS export are planned but not yet implemented.

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
├── notebooks/
│   ├── 01_ocr_smoke_test.ipynb
│   └── 02_region_ocr_test.ipynb
├── src/
│   └── ocr_utils.py
├── .gitignore
├── CHANGELOG.md
├── LICENSE
├── README.md
└── requirements.txt
```

### Folder Purposes

- `data/sample/` contains permanent demonstration images.
- `data/raw/` is intended for newly ingested, unprocessed images.
- `data/processed/` is intended for cropped or preprocessed image outputs.
- `notebooks/` contains exploratory OCR experiments.
- `src/` contains reusable Python functions as the prototype is gradually refactored.

`data/raw/` and `data/processed/` are gitignored. Ingested flyers are
third-party content and may identify event organizers and attendees, so they
stay local; only `data/sample/` is tracked.

## Requirements

- Python 3.10 or later
- The Tesseract OCR engine, installed separately and available on `PATH`
- Python packages listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

## Why This Project Exists

Event information posted on Instagram is often difficult to search, sort, and transfer into a calendar.

Important details may be divided between:

- captions,
- flyer images,
- account metadata,
- and external ticket links.