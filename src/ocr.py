"""
Image preprocessing and OCR, plus cleanup of raw OCR text.

Extracted from notebooks/02_region_ocr_test.ipynb without behaviour changes.

Only `image_to_text` actually invokes Tesseract. Importing this module does not
require the Tesseract binary, so `clean_ocr_text`, `crop_date_region` and
`preprocess` can be exercised in tests without an OCR install.
"""

import re

from PIL import Image
import pytesseract


# --- Crop strategy -----------------------------------------------------------
#
# These values are carried over verbatim from the notebook. They are NOT a
# general strategy: they were hand-tuned against cherry_blossom_market.jpeg.
#
# MIDDLE_BAND is fractional, so it scales with image size. DATE_BOX is in
# absolute pixels relative to that band, so on a flyer narrower than ~900px it
# will silently mis-crop -- PIL returns a smaller region rather than raising
# when the box overruns the image.
#
# Left exactly as-is on purpose: picking a crop strategy that generalises is a
# separate decision, and one for you to make. When you get there the options
# are roughly:
#   (a) make DATE_BOX fractional too,
#   (b) locate text with pytesseract.image_to_data and crop to word boxes,
#   (c) try several candidate regions and keep the first that yields a date.
MIDDLE_BAND = (0.0, 0.3, 1.0, 0.7)   # (left, top, right, bottom), as fractions
DATE_BOX = (50, 140, 900, 450)       # absolute px, relative to the middle band

# PSM 6 = "assume a single uniform block of text". The notebook compared PSM
# 6/7/8/13 and found minimal difference; 6 is what the working pipeline used.
DEFAULT_PSM = 6

# The notebook found 2x upscaling of a grayscale crop read best. Thresholding
# was tested and made results worse, so it is deliberately not applied here.
DEFAULT_SCALE = 2


def crop_date_region(image, middle_band=MIDDLE_BAND, date_box=DATE_BOX):
    """
    Crop the region of a flyer expected to contain the date.

    Applies the fractional `middle_band` first, then `date_box` (absolute
    pixels) within that band -- the same two-step crop the notebook used.
    """
    width, height = image.size
    left, top, right, bottom = middle_band
    band = image.crop(
        (
            int(width * left),
            int(height * top),
            int(width * right),
            int(height * bottom),
        )
    )
    return band.crop(date_box)


def preprocess(image, scale=DEFAULT_SCALE):
    """
    Convert to grayscale and upscale. No thresholding: the notebook's
    preprocessing experiments found it degraded OCR accuracy on these flyers.
    """
    image = image.convert("L")
    return image.resize((image.width * scale, image.height * scale))

def preprocess_full_image(image, scale=DEFAULT_SCALE):
    """
    Prepare an entire flyer for OCR without cropping.

    Converts the full image to grayscale and upscales it using the same
    preprocessing settings as the existing cropped pipeline.
    """
    return preprocess(image, scale=scale)

def image_to_text(image, psm=DEFAULT_PSM):
    """
    Run Tesseract over an already-cropped, already-preprocessed image.

    This is the only function here that requires the Tesseract binary.
    """
    return pytesseract.image_to_string(image, config=f"--psm {psm}").strip()


def clean_ocr_text(text: str) -> str:
    """
    Normalize OCR output by collapsing whitespace and stripping
    leading/trailing spaces.
    """
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_image(path):
    """Open an image file. Thin wrapper so callers need not import PIL."""
    return Image.open(path)
