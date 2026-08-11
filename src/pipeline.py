"""
Composition of the four stages into the end-to-end flyer -> date pipeline.

Kept separate from ocr.py and dates.py so those stay single-concern, and so
this stays the one place that knows the stage ordering.
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from src.dates import extract_date, normalize_date
from src.ocr import (
    clean_ocr_text,
    crop_date_region,
    image_to_text,
    load_image,
    preprocess,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class FlyerResult:
    filename: str
    raw_text: str
    clean_text: str
    date_found: Optional[str]
    event_date: Optional[str]
    valid: bool

def extract_event_date(
    image_path,
    today: Optional[date] = None,
    use_full_image: bool = False,
) -> FlyerResult:
    """
    Run the full pipeline over one flyer image.

    Stages, in order:
        load -> optional crop -> preprocess -> OCR -> clean -> extract -> normalize

    `today` is passed through to normalize_date; see that function for the
    next-occurrence rule. Pass it explicitly for reproducible output.

    `use_full_image=True` skips the cherry-blossom-specific crop and runs OCR
    over the entire flyer.
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

    return FlyerResult(
        filename=Path(image_path).name,
        raw_text=raw_text,
        clean_text=clean_text,
        date_found=extracted.text if extracted is not None else None,
        event_date=normalized,
        valid=normalized is not None,
    )

def collect_image_paths(path: Path) -> list[Path]:
    if not path.exists():
        raise ValueError(f"No such file or directory: {path}")

    if path.is_file():
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {path.suffix}")
        return [path]

    return sorted(
        p
        for p in path.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def format_result(result: FlyerResult) -> str:
    return (
        f"Filename: {result.filename}\n"
        f"Date found: {result.date_found}\n"
        f"Event date: {result.event_date}\n"
        f"Valid: {result.valid}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract event dates from flyers."
    )
    parser.add_argument(
        "path",
        help="Image file or directory of flyer images",
    )
    args = parser.parse_args(argv)

    try:
        image_paths = collect_image_paths(Path(args.path))
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    for image_path in image_paths:
        result = extract_event_date(
            image_path,
            use_full_image=True,
        )
        print(format_result(result))
        print("-" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())