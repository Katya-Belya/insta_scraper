"""
Tests for src.dates.

Two groups, kept explicitly separate:

  PRESERVED BEHAVIOUR
      Locks in what notebooks/02_region_ocr_test.ipynb already did. These
      encode the existing prototype and should only change deliberately.

  NEW BEHAVIOUR
      The next-occurrence year rule, which replaces the notebook's hardcoded
      `expected_year=2026`. New in this commit.

Requires no Tesseract install.
"""

from datetime import date

import pytest

from src.dates import (
    MONTH_NAME_DATE_RE,
    ExtractedDate,
    extract_date,
    normalize_date,
)


# The exact OCR output the notebook recorded for the sample flyer.
NOTEBOOK_RAW_OCR = "-_ FRIDAY, MARCH 27t\n4PM - 8PM"
NOTEBOOK_CLEAN_OCR = "-_ FRIDAY, MARCH 27t 4PM - 8PM"


# ---------------------------------------------------------------------------
# PRESERVED BEHAVIOUR - extraction
# ---------------------------------------------------------------------------

def test_pattern_is_byte_for_byte_the_notebook_pattern():
    """
    The pattern is now built from the MONTHS tuple. Assert that still compiles
    to exactly the literal the notebook used, so 'derived from a list' can
    never silently broaden what matches.
    """
    notebook_literal = (
        r"\b("
        r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|"
        r"JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
        r")\s+(\d{1,2})(?:ST|ND|RD|TH|T)?\b"
    )
    assert MONTH_NAME_DATE_RE.pattern == notebook_literal


def test_extracts_date_from_notebook_raw_ocr():
    """The headline case: the real OCR output the prototype was built on."""
    assert extract_date(NOTEBOOK_RAW_OCR) == ExtractedDate("March", 27, "March 27")


def test_extracts_date_from_cleaned_ocr():
    """Cleanup collapses the newline; extraction must be unaffected."""
    assert extract_date(NOTEBOOK_CLEAN_OCR) == ExtractedDate("March", 27, "March 27")


@pytest.mark.parametrize(
    "text",
    [
        "MARCH 27",     # no suffix
        "MARCH 27TH",   # full ordinal
        "MARCH 27t",    # OCR-truncated ordinal, as seen on the sample
        "March 27th",   # mixed case
        "march 27",     # lower case
    ],
)
def test_month_and_ordinal_variants(text):
    assert extract_date(text) == ExtractedDate("March", 27, "March 27")


@pytest.mark.parametrize(
    "text,day",
    [("MAY 1ST", 1), ("MAY 2ND", 2), ("MAY 3RD", 3), ("MAY 4TH", 4)],
)
def test_all_ordinal_suffixes(text, day):
    assert extract_date(text).day == day


def test_recognises_all_twelve_months():
    names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    for name in names:
        assert extract_date(f"{name.upper()} 15").month_name == name


@pytest.mark.parametrize(
    "text",
    [
        "",                     # empty
        "4PM - 8PM",            # the time line alone
        "no date here",
        "MARCH27",              # no separator: \s+ is required
        "MARCH 271",            # 3-digit day: \b prevents a partial match
        "2/17/26",              # numeric format is NOT handled by this pattern
    ],
)
def test_returns_none_when_no_month_name_date(text):
    assert extract_date(text) is None


def test_day_is_an_int_with_leading_zero_dropped():
    """Matches the notebook, which did int(match.group(2))."""
    result = extract_date("MARCH 07")
    assert result.day == 7
    assert result.text == "March 7"


def test_first_match_wins():
    """The notebook used .search(), taking the first hit."""
    assert extract_date("MARCH 27 and APRIL 3").text == "March 27"


# ---------------------------------------------------------------------------
# PRESERVED BEHAVIOUR - the documented end-to-end result
# ---------------------------------------------------------------------------

def test_reproduces_the_documented_cherry_blossom_result():
    """
    README documents March 27 normalising to 2026-03-27. The notebook got that
    from a hardcoded expected_year=2026; the same output now comes from the
    next-occurrence rule given any `today` earlier in 2026.
    """
    extracted = extract_date(NOTEBOOK_RAW_OCR)
    assert normalize_date(extracted, today=date(2026, 1, 1)) == "2026-03-27"


# ---------------------------------------------------------------------------
# NEW BEHAVIOUR - next-occurrence year rule
# ---------------------------------------------------------------------------

def test_upcoming_date_this_year_keeps_this_year():
    extracted = ExtractedDate("March", 27, "March 27")
    assert normalize_date(extracted, today=date(2026, 3, 1)) == "2026-03-27"


def test_date_already_past_rolls_to_next_year():
    """The reason the hardcoded year had to go."""
    extracted = ExtractedDate("March", 27, "March 27")
    assert normalize_date(extracted, today=date(2026, 8, 2)) == "2027-03-27"


def test_date_falling_exactly_on_today_counts_as_upcoming():
    extracted = ExtractedDate("March", 27, "March 27")
    assert normalize_date(extracted, today=date(2026, 3, 27)) == "2026-03-27"


def test_one_day_past_rolls_over():
    extracted = ExtractedDate("March", 27, "March 27")
    assert normalize_date(extracted, today=date(2026, 3, 28)) == "2027-03-27"


def test_none_in_none_out():
    assert normalize_date(None, today=date(2026, 1, 1)) is None


def test_impossible_calendar_date_returns_none():
    """June has 30 days; no year in the window makes June 31 real."""
    extracted = ExtractedDate("June", 31, "June 31")
    assert normalize_date(extracted, today=date(2026, 1, 1)) is None


def test_day_zero_returns_none():
    extracted = ExtractedDate("March", 0, "March 0")
    assert normalize_date(extracted, today=date(2026, 1, 1)) is None


LEAP_DAY = ExtractedDate("February", 29, "February 29")


@pytest.mark.parametrize(
    "today,expected",
    [
        # Neither 2026 nor 2027 is a leap year; the next Feb 29 is in 2028.
        (date(2026, 1, 1), "2028-02-29"),
        (date(2027, 1, 1), "2028-02-29"),
        # Already in a leap year, with the date still ahead.
        (date(2028, 1, 1), "2028-02-29"),
        # On the day itself.
        (date(2028, 2, 29), "2028-02-29"),
        # Just past it: skip forward a full leap cycle.
        (date(2028, 3, 1), "2032-02-29"),
    ],
)
def test_leap_day_resolves_to_the_next_leap_year(today, expected):
    """
    Feb 29 must find its next real occurrence rather than giving up. This is
    why SEARCH_YEARS is 5: leap years are 4 apart, so any 5 consecutive years
    contain one.
    """
    assert normalize_date(LEAP_DAY, today=today) == expected


def test_widening_the_window_never_pushes_an_ordinary_date_further_out():
    """
    The wider window must not change any non-leap-day result: every other
    month/day is valid in the first year tried or the second.
    """
    extracted = ExtractedDate("March", 27, "March 27")
    for search_years in (2, 5, 9):
        assert (
            normalize_date(extracted, today=date(2026, 8, 2), search_years=search_years)
            == "2027-03-27"
        )


def test_leap_day_across_a_skipped_century_is_a_documented_limit():
    """
    DOCUMENTED LIMIT, not desired behaviour: 2100 is divisible by 100 but not
    400, so it is not a leap year and the gap 2096 -> 2104 is 8 years, wider
    than the 5-year window. Roughly 70 years out; search_years=9 closes it.
    """
    assert normalize_date(LEAP_DAY, today=date(2097, 1, 1)) is None
    assert normalize_date(LEAP_DAY, today=date(2097, 1, 1), search_years=9) == (
        "2104-02-29"
    )


def test_today_defaults_to_the_real_today():
    """Not asserting an exact value - only that the default is wired up."""
    extracted = ExtractedDate("March", 27, "March 27")
    result = normalize_date(extracted)
    assert result is not None
    assert date.fromisoformat(result) >= date.today()
