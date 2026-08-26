"""
Date extraction and normalization.

Pure text and date logic: no PIL, no pytesseract. This module is importable and
fully testable in an environment with no OCR stack installed.

The module separates three responsibilities:
1. Recognize date-like text.
2. Convert matches into structured date candidates.
3. Normalize a selected month/day to a calendar date.

Matches full month names, abbreviated month names (with optional trailing
period and flexible punctuation/spacing), and numeric month/day forms
(M/D and M-D).

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

# Common four-letter September abbreviation.
MONTH_LOOKUP["SEPT"] = "September"

_FULL = "|".join(MONTHS)
_ABBR = "|".join([*(name[:3] for name in MONTHS), "SEPT"])

# Matches dates such as:
#   MARCH 27 / MARCH 27th / March 27t   (full month, OCR ordinals)
#   APR 25 / APR. 25 / AUG.12           (abbrev, optional period, flexible space)
#   (8/4) / 8-4                         (numeric month/day, no year)
DATE_RE = re.compile(
    rf"\b({_FULL})[\s.,:;()\-]+(?P<day_full>\d{{1,2}})(?:ST|ND|RD|TH|T)?\b"
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
    """
    Structured representation of a date found in OCR text.

    The parser extracts only month and day. The year is deliberately handled
    later by normalize_date(), because many event flyers omit the year.
    """

    month_name: str  # Canonical full name, e.g. "August"
    day: int         # Numeric day, e.g. 27
    text: str        # Human-readable normalized form, e.g. "August 27"


def _canonical_month_name(token: str) -> Optional[str]:
    """
    Convert a month token found by the regex into its canonical full name.

    Examples:
        "AUG"  -> "August"
        "AUG." -> "August"
        "SEPT" -> "September"

    Returning one canonical form means later code does not need to care
    which spelling or abbreviation appeared in the OCR.
    """
    return MONTH_LOOKUP.get(token.upper().rstrip("."))


def _month_name_from_number(month: int) -> Optional[str]:
    """
    Convert a numeric month into the same canonical month-name format.

    Example:
        8 -> "August"

    Invalid month numbers return None rather than creating an invalid date.
    """
    if 1 <= month <= 12:
        return MONTHS[month - 1].title()
    return None


def _extracted_date_from_match(match: re.Match) -> Optional[ExtractedDate]:
    """
    Turn one regex match into an ExtractedDate.

    DATE_RE recognizes three possible forms:
        1. Full month:       AUGUST 27
        2. Abbreviation:     AUG. 27
        3. Numeric:          8/27

    This helper converts all three forms into the same ExtractedDate
    representation so the rest of the pipeline can treat them identically.
    """

    # Full month-name match, such as "AUGUST 27".
    if match.group(1) is not None:
        month_name = _canonical_month_name(match.group(1))
        day = int(match.group("day_full"))

    # Abbreviated month match, such as "AUG. 27" or "SEPT. 5TH".
    elif match.group("month_abbr") is not None:
        month_name = _canonical_month_name(match.group("month_abbr"))
        day = int(match.group("day_abbr"))

    # Numeric match, such as "8/27" or "8-27".
    else:
        month_name = _month_name_from_number(
            int(match.group("month_num"))
        )
        day = int(match.group("day_num"))

    # A regex match is not useful if its month cannot be interpreted.
    if month_name is None:
        return None

    # All supported input formats leave this function in one standard form.
    return ExtractedDate(
        month_name=month_name,
        day=day,
        text=f"{month_name} {day}",
    )


def extract_dates(text: str) -> list[ExtractedDate]:
    """
    Find every recognizable month/day date in the text.

    Unlike extract_date(), this does NOT stop at the first match.

    This became necessary because an Instagram screenshot can contain several
    dates: for example, an Instagram/UI date plus the actual event date.
    At this stage we intentionally keep every candidate. Deciding which
    candidate is the event date is a separate responsibility.
    """
    dates = []

    # finditer() scans the entire OCR text and yields every DATE_RE match
    # in the same order in which the matches appear in the text.
    for match in DATE_RE.finditer(text):
        extracted = _extracted_date_from_match(match)

        if extracted is not None:
            dates.append(extracted)

    return dates


def extract_date(text: str) -> Optional[ExtractedDate]:
    """
    Return only the first recognizable date.

    This preserves the behavior of the original pipeline and existing tests.
    New code that needs to reason about multiple possible dates should use
    extract_dates() and perform date selection separately.
    """
    dates = extract_dates(text)
    return dates[0] if dates else None

def select_event_date(
    candidates: list[ExtractedDate],
    today: Optional[date] = None,
) -> Optional[ExtractedDate]:
    """
    Choose the candidate whose next occurrence is closest to today.

    This helps when OCR text contains several dates, such as an older
    Instagram/UI date followed by the actual upcoming event date.
    """
    if not candidates:
        return None

    if today is None:
        today = date.today()

    ranked = []

    for candidate in candidates:
        normalized = normalize_date(candidate, today=today)

        if normalized is not None:
            ranked.append(
                (date.fromisoformat(normalized), candidate)
            )

    if not ranked:
        return None

    # Earliest upcoming normalized date wins.
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]

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
