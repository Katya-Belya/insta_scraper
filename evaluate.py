from datetime import date
from pathlib import Path

from src.pipeline import extract_event_date


RAW_DIR = Path("data/raw")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Use a fixed date so results are reproducible.
REFERENCE_TODAY = date(2026, 1, 1)


def main() -> None:
    image_paths = sorted(
        path
        for path in RAW_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not image_paths:
        print(f"No images found in {RAW_DIR}")
        return

    for image_path in image_paths:
        print("-" * 60)
        print(f"Filename: {image_path.name}")

        try:
            result = extract_event_date(
                image_path,
                today=REFERENCE_TODAY,
                use_full_image=True,
            )
        except Exception as error:
            print(f"ERROR: {error}")
            continue

        print("Raw OCR:")
        print(result.raw_text or "[no OCR text]")
        print(f"Date found: {result.date_found}")
        print(f"Event date: {result.event_date}")
        print(f"Valid: {result.valid}")

    print("-" * 60)


if __name__ == "__main__":
    main()