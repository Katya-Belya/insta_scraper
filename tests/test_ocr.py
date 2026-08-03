"""
Tests for the parts of src.ocr that do not invoke Tesseract:
text cleanup, cropping, and preprocessing.

`image_to_text` is the only function requiring the Tesseract binary and is
deliberately not covered here -- it is exercised end-to-end in the notebook.
These tests run in an environment with no OCR install.

All PRESERVED BEHAVIOUR: clean_ocr_text is unchanged from src/ocr_utils.py,
and the crop/preprocess steps are lifted verbatim from the notebook.
"""

from PIL import Image

import pytest

from src.ocr import (
    DATE_BOX,
    MIDDLE_BAND,
    clean_ocr_text,
    crop_date_region,
    preprocess,
)


# ---------------------------------------------------------------------------
# clean_ocr_text - carried over unchanged from the original ocr_utils.py
# ---------------------------------------------------------------------------

def test_collapses_newlines_into_spaces():
    assert clean_ocr_text("-_ FRIDAY, MARCH 27t\n4PM - 8PM") == (
        "-_ FRIDAY, MARCH 27t 4PM - 8PM"
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  leading and trailing  ", "leading and trailing"),
        ("multiple   internal    spaces", "multiple internal spaces"),
        ("tabs\tand\tnewlines\n", "tabs and newlines"),
        ("mixed \n\t  whitespace", "mixed whitespace"),
        ("", ""),
        ("   ", ""),
        ("already clean", "already clean"),
    ],
)
def test_whitespace_normalisation(raw, expected):
    assert clean_ocr_text(raw) == expected


def test_is_idempotent():
    once = clean_ocr_text("FRIDAY,\n\nMARCH  27t ")
    assert clean_ocr_text(once) == once


# ---------------------------------------------------------------------------
# preprocess - grayscale + 2x upscale, no thresholding
# ---------------------------------------------------------------------------

def test_converts_to_grayscale_and_doubles_size():
    image = Image.new("RGB", (100, 50), "white")
    result = preprocess(image)
    assert result.mode == "L"
    assert result.size == (200, 100)


def test_scale_is_configurable():
    image = Image.new("RGB", (100, 50), "white")
    assert preprocess(image, scale=3).size == (300, 150)


def test_does_not_threshold():
    """
    Thresholding was tested in the notebook and made OCR worse. A mid-gray
    pixel must survive as mid-gray, not get pushed to pure black or white.
    """
    image = Image.new("RGB", (10, 10), (128, 128, 128))
    result = preprocess(image, scale=1)
    assert result.getpixel((5, 5)) not in (0, 255)


# ---------------------------------------------------------------------------
# crop_date_region - the two-step crop, kept exactly as the notebook had it
# ---------------------------------------------------------------------------

def test_applies_middle_band_then_date_box():
    image = Image.new("RGB", (1000, 1000), "white")
    result = crop_date_region(image)
    # Middle band -> 1000x400. DATE_BOX (50,140,900,450) is 850 wide, 310 tall.
    assert result.size == (850, 310)


def test_date_box_overruns_a_short_band_without_raising():
    """
    DOCUMENTS A LIMITATION rather than endorsing it. DATE_BOX is in absolute
    pixels, so on a small flyer it extends past the cropped band. PIL pads
    instead of raising, so a bad crop fails silently -- exactly the
    generalisation problem noted in src/ocr.py. Left for the crop-strategy
    decision.
    """
    small = Image.new("RGB", (200, 200), "white")
    result = crop_date_region(small)
    assert result.size == (850, 310)  # far larger than the 200x80 band


def test_crop_boxes_are_the_notebook_values():
    assert MIDDLE_BAND == (0.0, 0.3, 1.0, 0.7)
    assert DATE_BOX == (50, 140, 900, 450)
