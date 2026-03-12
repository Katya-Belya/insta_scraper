# insta_scraper
Python project that converts Instagram event flyers into structured data using image preprocessing, OCR, and pattern extraction.


Instagram Event Extraction → Calendar Pipeline

Overview

This project extracts structured event data (date, time, venue, price,
artists) from Instagram event posts (captions + flyer images) and
converts them into chronologically ordered events suitable for calendar
import (CSV + ICS).

Core problem solved:

Unstructured social media content → structured, normalized event objects
with confidence scoring.

This is an information extraction pipeline with a human-in-the-loop
review stage.

Goals

-   Extract event date and time from captions and/or flyer images.
-   Normalize dates to timezone-aware datetimes.
-   Infer missing year when necessary.
-   Extract venue names and price when present.
-   Score extraction confidence.
-   Flag ambiguous cases for review.
-   Export sorted events to CSV and ICS (Google Calendar compatible).

Non-Goals (v1)

-   Live Instagram scraping.
-   Web UI.
-   Google Calendar API integration.
-   Perfect NLP understanding.
-   Full automation without review.

This is an extraction-first system.

Architecture

Raw Posts (images + captions) ↓ Caption Parsing (rules + date parsing) ↓
(if low confidence) OCR Extraction (image → text) ↓ Unified Parsing
Logic ↓ Conflict Reconciliation ↓ Confidence Scoring ↓ Review Queue (if
needed) ↓ Export (CSV + ICS)

Project Structure

project/ │ ├── data/ │ ├── raw_images/ │ ├── posts.csv │ ├──
raw_posts.jsonl │ ├── events_extracted.csv │ ├── events_review.csv │ └──
events_final.csv │ ├── src/ │ ├── ingest.py │ ├── parse_text.py │ ├──
ocr.py │ ├── reconcile.py │ ├── score.py │ └── export_ics.py │ ├──
requirements.txt └── README.txt

Data Model (Event Object)

Minimum required: - title - start_datetime - venue_name

Optional: - doors_datetime - price - artists - notes - source -
extraction_source - confidence - needs_review

Extraction Strategy

1)  Caption-First Parsing

Captions are parsed using: - Regex patterns - Date parsing libraries -
Keyword detection (doors, show, at, @, $)

If high confidence, extraction stops.

2)  OCR Fallback

If caption parsing fails or is low confidence: - Preprocess image
(grayscale, contrast adjust) - Run OCR - Parse OCR text with the same
extraction logic

There is no separate parsing logic for captions vs OCR — unified
parsing.

3)  Conflict Resolution

If both caption and OCR provide data:

Rules: - Prefer explicit month/day over relative date (“next Friday”) -
Prefer consistent date/time agreement - Boost confidence if both sources
match

4)  Confidence Scoring

Example rubric:

+0.4 if date found +0.3 if time found +0.2 if venue found +0.1 if price
found

Score < 0.6 → needs_review = True

Year Inference Logic

If event month/day is before the post date: - Assume event is in the
following year.

Default timezone: America/New_York

Installation

Requirements: - Python 3.10+ - Tesseract OCR (installed system-wide)

Python dependencies:

pip install -r requirements.txt

Example requirements.txt:

pandas dateparser pytz ics pillow pytesseract

Evaluation

Acceptance criteria for v1:

-   Correct date + start time extracted for ≥70% of posts.
-   All ambiguous cases flagged for review.
-   Chronological ordering correct.
-   ICS imports without errors.

Why This Project Matters

This system demonstrates:

-   Real-world information extraction.
-   OCR + structured parsing.
-   Ambiguity handling.
-   Deterministic heuristics over blind AI.
-   Human-in-the-loop system design.
-   ETL architecture thinking.

It is an applied data engineering + NLP pipeline built around messy
real-world inputs.