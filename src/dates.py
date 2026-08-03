"""
Date extraction and normalization.

Pure text and date logic: no PIL, no pytesseract. This module is importable and
fully testable in an environment with no OCR stack installed.

The extraction pattern is carried over verbatim from
notebooks/02_region_ocr_test.ipynb. It has deliberately NOT been broadened --
it still only matches full month names followed by a day. Numeric dates
(2/17/26), which the notebook explored separately against a different flyer,
are not handled here.
"""

from datetime import date
from typing import NamedTuple, Optional
import re


# Order matters: index + 1 is the month number.
MONTHS = (
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
)

MONTH_NUMBERS = {name: i + 1 for i, name in enumerate(MONTHS)}

# Matches dates such as:
#   MARCH 27
#   MARCH 27th
#   March 27t   (OCR truncation of "27th", seen on the sample flyer)
#
# Built from MONTHS so the alternation cannot drift out of sync with
# MONTH_NUMBERS. test_dates.py asserts this compiles to the exact pattern
# string the notebook used.
MONTH_NAME_DATE_RE = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:ST|ND|RD|TH|T)?\b",
    flags=re.IGNORECASE,
)

# How many years forward normalize_date will look for a valid occurrence.
#
# 5 rather than 2 so that February 29 resolves: leap years are 4 years apart,
# and any 5 consecutive years contain at least one. The window only ever
# matters for Feb 29 -- every other month/day is valid in the first year tried
# or the second, so a wider window cannot push an ordinary date further out.
#
# Residual limit: century years divisible by 100 but not 400 are not leap, so
# the gap 2096 -> 2104 is 8 years and a Feb 29 falling in it returns None.
# That is ~70 years away; a 9-year window would close it.
SEARCH_YEARS = 5


class ExtractedDate(NamedTuple):
    """A month/day pair recovered from OCR text. No year -- flyers rarely show one."""

    month_name: str  # title case, e.g. "March"
    day: int
    text: str        # human-readable, e.g. "March 27"


def extract_date(text: str) -> Optional[ExtractedDate]:
    """
    Find the first month-name date in `text`.

    Returns None if no date is found. Does not validate that the day is real
    for that month -- that happens in normalize_date, which is where a calendar
    is actually consulted.
    """
    match = MONTH_NAME_DATE_RE.search(text)
    if match is None:
        return None

    month_name = match.group(1).title()
    day = int(match.group(2))
    return ExtractedDate(month_name=month_name, day=day, text=f"{month_name} {day}")


def normalize_date(
    extracted: Optional[ExtractedDate],
    today: Optional[date] = None,
    search_years: int = SEARCH_YEARS,
) -> Optional[str]:
    """
    Resolve a month/day pair to an ISO date string (YYYY-MM-DD).

    Flyers usually omit the year, so the year is inferred with a next-occurrence
    rule: the earliest year, starting from `today`'s, in which the month/day is
    a real calendar date that has not already passed. A date falling exactly on
    `today` counts as upcoming.

    `today` defaults to date.today(). Pass it explicitly for reproducible
    results -- with the default, output depends on when the code is run.

    Returns None when no date was extracted, or when the month/day is not a
    valid calendar date within the search window (e.g. "June 31").
    """
    if extracted is None:
        return None
    if today is None:
        today = date.today()

    month = MONTH_NUMBERS.get(extracted.month_name.upper())
    if month is None:
        return None

    for offset in range(search_years):
        try:
            candidate = date(today.year + offset, month, extracted.day)
        except ValueError:
            # Day out of range for this month/year (e.g. June 31, or Feb 29 in
            # a non-leap year). Try the next year rather than giving up.
            continue
        if candidate >= today:
            return candidate.isoformat()

    return None
