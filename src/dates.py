"""
Date extraction and normalization.

Pure text and date logic: no PIL, no pytesseract. This module is importable and
fully testable in an environment with no OCR stack installed.

Matches full month names, abbreviated month names (with optional trailing
period and flexible spacing), and numeric month/day forms (M/D and M-D).
Three-part numeric dates with a year (e.g. 2/17/26) are not handled.
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

# Full uppercase name and three-letter abbrev both map to the same title-case name.
MONTH_LOOKUP: dict[str, str] = {}
for _name in MONTHS:
    _canonical = _name.title()
    MONTH_LOOKUP[_name] = _canonical
    MONTH_LOOKUP[_name[:3]] = _canonical

_FULL = "|".join(MONTHS)
_ABBR = "|".join(name[:3] for name in MONTHS)

# Matches dates such as:
#   MARCH 27 / MARCH 27th / March 27t   (full month, OCR ordinals)
#   APR 25 / APR. 25 / AUG.12           (abbrev, optional period, flexible space)
#   (8/4) / 8-4                         (numeric month/day, no year)
DATE_RE = re.compile(
    rf"\b({_FULL})\s+(?P<day_full>\d{{1,2}})(?:ST|ND|RD|TH|T)?\b"
    rf"|\b(?P<month_abbr>{_ABBR})\.?\s*(?P<day_abbr>\d{{1,2}})(?:ST|ND|RD|TH|T)?\b"
    rf"|\b(?P<month_num>\d{{1,2}})[/\-](?P<day_num>\d{{1,2}})(?!/\d)\b",
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
# the gap 2096 -> 2104 is 8 years, wider than the 5-year window. That is ~70
# years away; a 9-year window would close it.
SEARCH_YEARS = 5


class ExtractedDate(NamedTuple):
    """A month/day pair recovered from OCR text. No year -- flyers rarely show one."""

    month_name: str  # title case, e.g. "March"
    day: int
    text: str        # human-readable, e.g. "March 27"


def _canonical_month_name(token: str) -> Optional[str]:
    return MONTH_LOOKUP.get(token.upper().rstrip("."))


def _month_name_from_number(month: int) -> Optional[str]:
    if 1 <= month <= 12:
        return MONTHS[month - 1].title()
    return None


def extract_date(text: str) -> Optional[ExtractedDate]:
    """
    Find the first month/day date in `text`.

    Returns None if no date is found. Does not validate that the day is real
    for that month -- that happens in normalize_date, which is where a calendar
    is actually consulted.
    """
    match = DATE_RE.search(text)
    if match is None:
        return None

    if match.group(1) is not None:
        month_name = _canonical_month_name(match.group(1))
        day = int(match.group("day_full"))
    elif match.group("month_abbr") is not None:
        month_name = _canonical_month_name(match.group("month_abbr"))
        day = int(match.group("day_abbr"))
    else:
        month_name = _month_name_from_number(int(match.group("month_num")))
        day = int(match.group("day_num"))

    if month_name is None:
        return None

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
