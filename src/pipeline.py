"""
Composition of the four stages into the end-to-end flyer -> date pipeline.

Kept separate from ocr.py and dates.py so those stay single-concern, and so
this stays the one place that knows the stage ordering.
"""

import argparse
import csv
import sys
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

# Import the date-specific parts of the pipeline.
# extract_dates() finds all recognizable date candidates in OCR text.
# select_event_date() chooses the most plausible event date.
# normalize_date() turns that month/day into an ISO date.
from src.dates import extract_dates, select_event_date, normalize_date

# Import the image/OCR-specific parts of the pipeline.
from src.ocr import (
    clean_ocr_text,
    crop_date_region,
    image_to_text,
    load_image,
    preprocess,
)


# File types that the command-line runner is allowed to process.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class FlyerResult:
    """
    Structured result for one processed flyer.

    Instead of returning several unrelated variables, the pipeline packages
    everything we know about one flyer into one FlyerResult object.

    Each FlyerResult can later become one row in a CSV file.
    """

    filename: str

    # Text exactly as Tesseract returned it.
    raw_text: str

    # OCR text after whitespace cleanup.
    clean_text: str

    # Human-readable date found in the flyer, such as "August 15".
    # None means that no recognizable date was extracted.
    date_found: Optional[str]

    # Normalized date, such as "2027-08-15".
    # None means the date could not be normalized.
    event_date: Optional[str]

    # True when we successfully produced a normalized event date.
    valid: bool

    # Short explanation of what happened during processing.
    # Examples: "ok", "no_date_found", or "invalid_date".
    status: str

    # True means a human should check this flyer manually.
    needs_review: bool


def extract_event_date(
    image_path,
    today: Optional[date] = None,
    use_full_image: bool = False,
) -> FlyerResult:
    """
    Run the full pipeline over one flyer image.

Stages, in order:
    load -> optional crop -> preprocess -> OCR -> clean
         -> find date candidates -> select event date -> normalize

    'today' is used both to choose among date candidates and to infer the year.
    Pass it explicitly when reproducible output is needed, such as in benchmarks.

    'use_full_image=True' skips the cherry-blossom-specific crop and runs OCR
    over the entire flyer.
    """

    # STEP 1: Load the image file into Python.
    image = load_image(image_path)

    # STEP 2: Decide whether OCR should examine the whole flyer
    # or only the old hand-selected date region.
    if use_full_image:
        region = image
    else:
        region = crop_date_region(image)

    # STEP 3: Prepare the image for OCR.
    # Currently this converts it to grayscale and enlarges it.
    region = preprocess(region)

    # STEP 4: Ask Tesseract to read the image.
    # This is the unmodified OCR output.
    raw_text = image_to_text(region)

    # STEP 5: Clean up OCR whitespace so the text is easier to search.
    clean_text = clean_ocr_text(raw_text)

    # STEP 6: Find ALL dates that OCR was able to recognize.
    #
    # Before this change, the pipeline used extract_date(), which returned
    # only the first date it saw.
    #
    # That caused problems with Instagram screenshots. For example:
    #
    #     July 22        <- Instagram/post date
    #     August 24      <- actual event date
    #
    # We now keep both dates so we can decide which one is more likely
    # to be the event date.
    candidates = extract_dates(clean_text)

    # STEP 7: Choose the best date from the candidates.
    #
    # select_event_date() currently prefers the nearest upcoming date.
    #
    # We pass `today` into this function because "upcoming" depends on
    # what day we are pretending it is.
    extracted = select_event_date(
        candidates,
        today=today,
    )

    # STEP 8: Add a year to the selected month/day.
    #
    # For example:
    #
    #     August 24
    #
    # becomes:
    #
    #     2026-08-24
    #
    # IMPORTANT: We pass the SAME `today` value here that we used above.
    # Otherwise date selection and year selection could disagree.
    normalized = normalize_date(
        extracted,
        today=today,
    )

    # STEP 9: Decide whether a person needs to review the result.
    if extracted is None:
        # OCR did not give us any date that the parser could recognize.
        status = "no_date_found"
        needs_review = True

    elif normalized is None:
        # We found something that looked like a date, but could not turn
        # it into a real calendar date.
        status = "invalid_date"
        needs_review = True

    else:
        # We found a date and successfully turned it into YYYY-MM-DD.
        status = "ok"
        needs_review = False

    # STEP 10: Put everything we learned about this flyer into one object.
    return FlyerResult(
        filename=Path(image_path).name,
        raw_text=raw_text,
        clean_text=clean_text,
        date_found=extracted.text if extracted is not None else None,
        event_date=normalized,
        valid=normalized is not None,
        status=status,
        needs_review=needs_review,
    )


def collect_image_paths(path: Path) -> list[Path]:
    """
    Turn a command-line path into a list of image files to process.

    The user may give us:
        - one image file
        - a folder containing many images

    Either way, this function returns a list of image paths.
    """

    # Fail early if the requested path does not exist.
    if not path.exists():
        raise ValueError(f"No such file or directory: {path}")

    # If the user supplied one file, make sure it is an image type we support.
    if path.is_file():
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {path.suffix}")

        # Return a list containing that single image.
        # This lets the rest of the program treat one flyer
        # and many flyers the same way.
        return [path]

    # If the user supplied a directory, find all supported image files in it.
    # sorted() makes the processing order predictable.
    return sorted(
        p
        for p in path.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def process_flyers(
    image_paths,
    today: Optional[date] = None,
):
    """
    Process several flyer images and collect all their FlyerResults.

    `today` is optional. Normally it is None, which means the real current
    date will be used.

    For a benchmark, we can provide a fixed date so running the same
    benchmark later gives us the same results.
    """

    results = []

    for image_path in image_paths:

        # Give every flyer the SAME reference date.
        #
        # This matters for benchmarks. We do not want flyer #1 to be
        # interpreted using one date and flyer #2 using another.
        result = extract_event_date(
            image_path,
            today=today,
            use_full_image=True,
        )

        results.append(result)

    return results


def format_result(result: FlyerResult) -> str:
    """
    Turn one FlyerResult into human-readable terminal output.

    This does not change the data itself.
    It only decides how the result should look when printed.
    """

    return (
        f"Filename: {result.filename}\n"
        f"Date found: {result.date_found}\n"
        f"Event date: {result.event_date}\n"
        f"Valid: {result.valid}\n"
        f"Status: {result.status}\n"
        f"Needs review: {result.needs_review}"
    )


def write_csv(results, output_path):
    """
    Write a collection of FlyerResult objects to a CSV file.

    Each FlyerResult becomes one row.
    Each FlyerResult field becomes one CSV column.
    """

    # These become the column names in the first row of the CSV.
    fieldnames = [
        "filename",
        "raw_text",
        "clean_text",
        "date_found",
        "event_date",
        "valid",
        "status",
        "needs_review",
    ]

    # Open the output file for writing.
    #
    # "w" means write mode.
    # newline="" prevents extra blank rows on Windows.
    # utf-8 lets us safely store a wide range of text characters.
    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:

        # DictWriter lets us build each row using column names.
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        # Write the CSV header row.
        writer.writeheader()

        # Convert every FlyerResult into one CSV row.
        for result in results:
            writer.writerow(
                {
                    "filename": result.filename,
                    "raw_text": result.raw_text,
                    "clean_text": result.clean_text,
                    "date_found": result.date_found,
                    "event_date": result.event_date,
                    "valid": result.valid,
                    "status": result.status,
                    "needs_review": result.needs_review,
                }
            )

def write_latest_result_js(result, path="extension/latest_result.js"):
    # Convert the latest FlyerResult into the fields used by the popup.
    flyer_data = {
        "filename": result.filename,
        "eventDate": result.event_date,
        "status": result.status,
        "needsReview": result.needs_review,
    }

    # Write a small JavaScript data file that popup.js can read.
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.flyerResult = ")
        json.dump(flyer_data, f)
        f.write(";")

def main(argv=None) -> int:
    """
    Command-line entry point.

    main() coordinates the other functions:

        command-line argument
                ↓
        collect image paths
                ↓
        process the flyers
                ↓
        save results to CSV
                ↓
        print the results
    """

    # Set up the command-line interface.
    parser = argparse.ArgumentParser(
        description="Extract event dates from flyers."
    )

    # Require one argument:
    # either an image path or a folder path.
    parser.add_argument(
        "path",
        help="Image file or directory of flyer images",
    )

    # Optional benchmark/reference date.
    #
    # Normal use:
    #
    #     python -m src.pipeline data/raw/
    #
    # uses the real current date.
    #
    # Benchmark use:
    #
    #     python -m src.pipeline data/raw/benchmark_v2 --today 2026-08-20
    #
    # tells the pipeline to behave as though today were August 20, 2026.
    #
    # This makes benchmark results reproducible. Otherwise an August 22
    # flyer could become 2027-08-22 simply because we reran the benchmark
    # after August 22 had already passed.
    parser.add_argument(
        "--today",
        help="Reference date in YYYY-MM-DD format (useful for reproducible benchmarks)",
    )

    # Read the user's command-line arguments.
    args = parser.parse_args(argv)

    # Start with no special reference date.
    # None means normal runs will use the real current date.
    reference_date = None

    # If the user supplied --today, convert the text into a real Python date.
    #
    # Example:
    #
    #     --today 2026-08-20
    #
    # turns the string "2026-08-20" into:
    #
    #     date(2026, 8, 20)
    #
    # We use this fixed date when rerunning benchmarks so the results do not
    # change just because we happen to run the benchmark on a different day.
    if args.today:
        try:
            reference_date = date.fromisoformat(args.today)

        except ValueError:
            # date.fromisoformat() expects YYYY-MM-DD.
            # Give a simple message instead of showing a Python traceback.
            print(
                "Error: --today must use YYYY-MM-DD format",
                file=sys.stderr,
            )
            return 1

    # Find the image or images the user asked us to process.
    #
    # This happens whether or not --today was supplied.
    try:
        image_paths = collect_image_paths(Path(args.path))

    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    # Process all flyers using the chosen reference date.
    #
    # If reference_date is None:
    #     normal behavior → use the real current date
    #
    # If reference_date is 2026-08-20:
    #     benchmark behavior → pretend it is August 20, 2026
    results = process_flyers(
        image_paths,
        today=reference_date,
    )

    # Save those same structured results to a CSV file.
    write_csv(results, "results.csv")
    # For the local V1 demo, show the most recently processed result in the extension.
    if results:
        write_latest_result_js(results[-1])

    # Also show the results in the terminal.
    for result in results:
        print(format_result(result))
        print("-" * 60)

    # Returning 0 tells the operating system that the command succeeded.
    return 0


# This block runs only when pipeline.py is executed as the program,
# for example:
#
#     python -m src.pipeline data/raw/
#
# It does not automatically run when another Python file imports pipeline.py.
if __name__ == "__main__":
    raise SystemExit(main())