"""
Utility functions for OCR preprocessing and text extraction.

As the project matures, helper functions from the exploratory notebooks
will be moved here to create a reusable OCR pipeline.
"""

import re


def clean_ocr_text(text: str) -> str:
    """
    Normalize OCR output by collapsing whitespace and stripping
    leading/trailing spaces.
    """
    text = re.sub(r"\s+", " ", text)
    return text.strip()