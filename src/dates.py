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
(M/D and M-D), each with an optional printed year.

Explicit years:
  - Any four-digit year that datetime.date supports (0001-9999) is kept
    exactly as printed, past or future: "AUGUST 24, 1999", "Aug. 24 2026",
    "8/24/1999", "8-24-2026". A past year is flagged for review downstream;
    it is never dropped or moved.
  - Month-name dates take the year after the day. Numeric dates take it as a
    third part using the same separator as the first two.
  - Two-digit years are deliberately NOT interpreted. "2/17/26" and
    "Aug 24 '26" are rejected as a whole: guessing a century would turn an OCR
    misread into a confident date, and dropping the year would turn a dated
    flyer into a yearless one.
  - Any other year-shaped suffix also rejects the whole date rather than
    leaving a yearless fragment: a numeric third part that is not exactly
    four digits ("8/24/199", "8/24/19999"), a run of five or more digits after
    a month-name date ("AUGUST 24, 19999"), or the year 0000, which
    datetime.date cannot represent.
  - One to three digits after a month-name date ("MARCH 27, 10 - 2PM") are
    left alone rather than read as a year, because flyers commonly follow the
    date with a time. That date is treated as yearless, which always requires
    review. So is a four-digit run glued to letters ("MARCH 27 1030PM").
"""

from datetime import MAXYEAR, MINYEAR, date
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

# Optional year after a month-name date. Every digit run is captured in full,
# so a malformed year cannot be half-read; _named_year() decides what it is.
# An apostrophe form ("AUG 24 '26") is captured only so the whole date can be
# rejected.
_NAMED_YEAR = (
    r"(?:\s*[,.]?\s*(?P<{name}_year>\d+)\b"
    r"|\s*['\u2019](?P<{name}_short_year>\d+)\b)?"
)

# Matches dates such as:
#   MARCH 27 / MARCH 27th / March 27t   (full month, OCR ordinals)
#   APR 25 / APR. 25 / AUG.12           (abbrev, optional period, flexible space)
#   AUGUST 24, 2026 / AUG 24 2026       (month name with a printed year)
#   (8/4) / 8-4                         (numeric month/day, no year)
#   8/24/2026 / 8-24-2026               (numeric with a printed year)
#
# A numeric third part is always consumed in full (\d+), whatever its length,
# so "2/17/26" can never be re-read as the yearless fragment "17/26" or
# "1/26". _extracted_date_from_match decides whether that part is a usable year.
DATE_RE = re.compile(
    rf"\b({_FULL})[\s.,:;()\-]+(?P<day_full>\d{{1,2}})(?:ST|ND|RD|TH|T)?\b"
    + _NAMED_YEAR.format(name="full")
    + rf"|\b(?P<month_abbr>{_ABBR})\.?\s*(?P<day_abbr>\d{{1,2}})(?:ST|ND|RD|TH|T)?\b"
    + _NAMED_YEAR.format(name="abbr")
    + r"|\b(?P<month_num>\d{1,2})(?P<sep>[/\-])(?P<day_num>\d{1,2})"
    r"(?:(?P=sep)(?P<year_num>\d+)|(?!\d)(?!(?P=sep)\d))",
    flags=re.IGNORECASE,
)

# Returned by the year helpers below when a year-shaped suffix makes the whole
# date unusable.
_REJECT = object()

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

    `year` is the year printed on the flyer, or None when the flyer omits it.
    A missing year is inferred later by normalize_date(); a printed one is
    always kept as printed.
    """

    month_name: str  # Canonical full name, e.g. "August"
    day: int         # Numeric day, e.g. 27
    text: str        # Human-readable form, e.g. "August 27" or "August 27, 2026"
    year: Optional[int] = None  # Explicit printed year, e.g. 2026


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


def _four_digit_year(year_text: str):
    """A four-digit printed year, or _REJECT if datetime.date cannot hold it."""
    year = int(year_text)
    return year if MINYEAR <= year <= MAXYEAR else _REJECT


def _named_year(year_text: Optional[str], following_text: str = ""):
    """Interpret a possible year after a month-name date."""
    if year_text is None or len(year_text) <= 3:
        return None

    # A number followed by a numbered street is an address number,
    # not the event year: "SEPT. 5TH 3718 14TH ST NW".
    if re.match(
        r"\s+\d{1,3}(?:ST|ND|RD|TH)?\s+"
        r"(?:STREET|ST|AVENUE|AVE|ROAD|RD|BOULEVARD|BLVD)\b",
        following_text,
        flags=re.IGNORECASE,
    ):
        return None

    if len(year_text) == 4:
        return _four_digit_year(year_text)
    return _REJECT


def _numeric_year(year_text: Optional[str]):
    """
    Interpret the third part of a numeric date.

    Returns the year, None when there is no third part, or _REJECT for
    anything that is not a four-digit year ("2/17/26", "8/24/19999").
    """
    if year_text is None:
        return None
    if len(year_text) == 4:
        return _four_digit_year(year_text)
    return _REJECT


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

    # Full month-name match, such as "AUGUST 27" or "AUGUST 27, 2026".
    if match.group(1) is not None:
        month_name = _canonical_month_name(match.group(1))
        day = int(match.group("day_full"))
        if match.group("full_short_year") is not None:
            return None  # Apostrophe year: reject the whole date.
        year_text = match.group("full_year")
        year = _named_year(
            year_text,
            match.string[match.end("full_year"):] if year_text else "",
        )

    # Abbreviated month match, such as "AUG. 27" or "SEPT. 5TH".
    elif match.group("month_abbr") is not None:
        month_name = _canonical_month_name(match.group("month_abbr"))
        day = int(match.group("day_abbr"))
        if match.group("abbr_short_year") is not None:
            return None  # Apostrophe year: reject the whole date.
        year_text = match.group("abbr_year")
        year = _named_year(
            year_text,
            match.string[match.end("abbr_year"):] if year_text else "",
        )

    # Numeric match, such as "8/27", "8-27" or "8/27/2026".
    else:
        month_name = _month_name_from_number(
            int(match.group("month_num"))
        )
        day = int(match.group("day_num"))
        year = _numeric_year(match.group("year_num"))

    # A year-shaped suffix that is not a usable year rejects the whole date
    # rather than guessing a year or quietly dropping it.
    if year is _REJECT:
        return None

    # A regex match is not useful if its month cannot be interpreted.
    if month_name is None:
        return None

    # Four digits, as printed: year 999 would otherwise read "999".
    text = f"{month_name} {day}" if year is None else f"{month_name} {day}, {year:04d}"

    # All supported input formats leave this function in one standard form.
    return ExtractedDate(
        month_name=month_name,
        day=day,
        text=text,
        year=year,
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
    Choose the most plausible event date among the candidates.

    This helps when OCR text contains several dates, such as an older
    Instagram/UI date followed by the actual upcoming event date.

    In order of preference:
      1. The earliest valid candidate on or after `today`. A yearless candidate
         always lands here, because its year is inferred as the next
         occurrence.
      2. If every valid candidate is in the past (only possible with a printed
         year), the most recent one. The caller flags it for review.
      3. If no candidate is a real calendar date, the first candidate, so the
         caller can report it as an invalid date rather than as no date.

    Returns None only when there are no candidates at all.
    """
    if not candidates:
        return None

    if today is None:
        today = date.today()

    upcoming = []
    past = []

    for candidate in candidates:
        normalized = normalize_date(candidate, today=today)

        if normalized is None:
            continue

        resolved = date.fromisoformat(normalized)
        (upcoming if resolved >= today else past).append((resolved, candidate))

    # Prefer a recent printed date over a distant inferred occurrence.
    if upcoming:
        nearest = min(upcoming, key=lambda item: item[0])
        recent_explicit = [
            item for item in past
            if item[1].year is not None
            and (today - item[0]).days <= 90
        ]
        if (
            nearest[1].year is None
            and (nearest[0] - today).days > 90
            and recent_explicit
        ):
            return max(recent_explicit, key=lambda item: item[0])[1]
        return nearest[1]

    if past:
        return max(past, key=lambda item: item[0])[1]

    return candidates[0]


def normalize_date(
    extracted: Optional[ExtractedDate],
    today: Optional[date] = None,
    search_years: int = SEARCH_YEARS,
) -> Optional[str]:
    """
    Resolve an extracted date to an ISO date string (YYYY-MM-DD).

    A year printed on the flyer is used as is, even if that date is in the
    past: rolling it forward would invent an event that was never announced.
    If the printed date does not exist (e.g. February 29, 2027) the result is
    None; it never falls back to another year.

    Flyers usually omit the year, so a missing year is inferred with a next-occurrence
    rule: the earliest year, starting from `today`'s, in which the month/day is
    a real calendar date that has not already passed. A date falling exactly on
    `today` counts as upcoming.

    `today` defaults to date.today(). Pass it explicitly for reproducible
    results -- with the default, output depends on when the code is run.

    Returns None when no date was extracted, when an explicit date is not a
    real calendar date, or when a yearless month/day is not a valid calendar
    date within the search window (e.g. "June 31").
    """
    if extracted is None:
        return None
    if today is None:
        today = date.today()

    month = MONTH_NUMBERS.get(extracted.month_name.upper())
    if month is None:
        return None

    if extracted.year is not None:
        try:
            return date(extracted.year, month, extracted.day).isoformat()
        except ValueError:
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
