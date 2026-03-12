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

---

## Notes

This README is designed to:

- explain the project in **~10 seconds**
- be **easy for recruiters to skim**
- still show the **pipeline thinking**

The longer design explanation can live separately as a **design document**.