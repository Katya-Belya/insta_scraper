"""
Reusable pieces of the Instagram flyer -> event record pipeline.

Deliberately does not re-export anything. Importing `src.dates` should not drag
in PIL or pytesseract, so the text and date logic stays testable in an
environment with no OCR stack installed.

    from src.ocr import crop_date_region, preprocess, image_to_text, clean_ocr_text
    from src.dates import extract_date, normalize_date
    from src.pipeline import extract_event_date
"""
