# insta_scraper

Python project that converts **Instagram event flyers into structured event data** using image preprocessing, OCR, and pattern extraction.

The goal is to turn messy social media posts into **clean calendar events**.

**Example output formats**

- CSV  
- ICS (Google Calendar compatible)

---

## What This Project Does

- Takes Instagram event posts (captions + flyer images)
- Extracts information such as:
  - date
  - time
  - venue
  - price
- Converts the extracted data into structured events
- Sorts events chronologically
- Exports them to a calendar-friendly format

---

## How It Works

## Current Status

Working prototype for extracting event **dates** from flyer images using OCR and post-processing.

### Example

Raw OCR output:02/17/2077


Extracted:

2/17/2077


Normalized:

2/17/26


Actual flyer text:

TUES 2/17/26 7 PM

### Key Findings

- Best results come from cropping the date region and using grayscale preprocessing
- OCR is generally accurate but frequently misreads the year
- Regex + post-processing significantly improves reliability

### Limitations

- Currently validated on a single flyer
- Year normalization is heuristic-based
- Time and location extraction not yet implemented

### Basic pipeline
Instagram Post
(caption + image)
↓
Caption parsing
↓
OCR on flyer image
↓
Event data extraction
↓
Confidence scoring
↓
CSV / ICS export
Low-confidence results are flagged for **manual review**.

---

## Project Structure

insta_scraper/
│
├── data/
│ └── raw_images/
│
├── notebooks/
│ ├── 01_ocr_smoke_test.ipynb
│ └── 02_region_ocr_test.ipynb
│
├── src/
│
├── README.md
├── progress_notes.md
└── .gitignore


---

## Requirements

- Python 3.10+
- Tesseract OCR

Install dependencies:


pip install -r requirements.txt


---

## Why This Project Exists

Event information on Instagram is often **hard to search or organize**.

This project explores how to automatically extract structured event data from:

- captions
- flyer images

and turn it into something usable for **calendars and datasets**.