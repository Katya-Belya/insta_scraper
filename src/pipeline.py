"""
Composition of the four stages into the end-to-end flyer -> date pipeline.

Kept separate from ocr.py and dates.py so those stay single-concern, and so
this stays the one place that knows the stage ordering. This is the entry point
a future batch/evaluation runner should call.
"""

from datetime import date
from typing import Optional

from src.dates import extract_date, normalize_date
from src.ocr import clean_ocr_text, crop_date_region, image_to_text, load_image, preprocess


def extract_event_date(
    image_path,
    today: Optional[date] = None,
    use_full_image: bool = False,
) -> dict:
    """
    Run the full pipeline over one flyer image.

    Stages, in order:
        load -> optional crop -> preprocess -> OCR -> clean -> extract -> normalize

    `today` is passed through to normalize_date; see that function for the
    next-occurrence rule. Pass it explicitly for reproducible output.

    `use_full_image=True` skips the cherry-blossom-specific crop and runs OCR
    over the entire flyer.

    Returns a dict with the same keys the notebook's version returned, plus
    `clean_text` so the cleanup stage is visible rather than hidden.
    """
    image = load_image(image_path)

    if use_full_image:
        region = image
    else:
        region = crop_date_region(image)

    region = preprocess(region)

    raw_text = image_to_text(region)
    clean_text = clean_ocr_text(raw_text)

    extracted = extract_date(clean_text)
    normalized = normalize_date(extracted, today=today)

    return {
        "image": str(image_path),
        "raw_text": raw_text,
        "clean_text": clean_text,
        "date_found": extracted.text if extracted is not None else None,
        "normalized_date": normalized,
        "valid": normalized is not None,
    }
