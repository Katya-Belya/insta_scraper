"""
Tests for src.dates.

The tests are grouped by what they check:

  ORIGINAL BEHAVIOUR
      Makes sure older date extraction still works after we change the code.

  DATE FORMATS
      Tests different ways dates can appear, such as APR. 25, SEPT. 5TH,
      AUGUST)27th, and 8/4.

  MULTIPLE DATES
      Makes sure extract_dates() can find all dates in the text, not just
      the first one. This is useful when an Instagram screenshot contains
      both an Instagram date and the actual event date.

  DATE NORMALIZATION
      Tests how a month and day are turned into a full date with a year.

  EXPLICIT YEARS / SELECTION
      A printed year is kept as printed; candidate selection prefers upcoming
      dates and falls back to the most recent past one.

These tests do not require Tesseract or OCR.
"""

from datetime import date

import pytest

from src.dates import (
    MONTH_LOOKUP,
    ExtractedDate,
    extract_date,
    extract_dates,
    select_event_date,
    normalize_date
)


# The exact OCR output the notebook recorded for the sample flyer.
NOTEBOOK_RAW_OCR = "-_ FRIDAY, MARCH 27t\n4PM - 8PM"
NOTEBOOK_CLEAN_OCR = "-_ FRIDAY, MARCH 27t 4PM - 8PM"


# ---------------------------------------------------------------------------
# PRESERVED BEHAVIOUR - extraction
# ---------------------------------------------------------------------------

def test_month_lookup_maps_full_names_and_abbrevs_to_canonical_names():
    """Every month token resolves to one title-case full name via MONTH_LOOKUP."""
    for name in (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ):
        assert MONTH_LOOKUP[name.upper()] == name
        assert MONTH_LOOKUP[name.upper()[:3]] == name


def test_full_abbrev_and_numeric_formats_share_canonical_month_names():
    assert extract_date("MARCH 15").month_name == "March"
    assert extract_date("MAR 15").month_name == "March"
    assert extract_date("MAR. 15").month_name == "March"
    assert extract_date("8/15").month_name == "August"

@pytest.mark.parametrize(
    "text",
    [
        "AUGUST)27th",
        "AUGUST,27th",
        "AUGUST.27th",
        "AUGUST-27th",
    ],
)
def test_full_month_tolerates_punctuation_separator(text):
    """
    Regression coverage for OCR punctuation noise found in the benchmark.

    OCR may insert punctuation between a month and day instead of whitespace.
    These variants should all normalize to the same extracted date.
    """
    assert extract_date(text) == ExtractedDate(
        "August", 27, "August 27"
    )


def test_sept_four_letter_abbreviation():
    """
    Regression coverage for the benchmark's 'SEPT. 5TH' format.

    SEPT is a common four-letter abbreviation that is not covered by simply
    taking the first three letters of SEPTEMBER.
    """
    assert extract_date("SEPT. 5TH") == ExtractedDate(
        "September", 5, "September 5"
    )

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
        "2/17/26",              # two-digit year: the whole date is rejected
    ],
)
def test_returns_none_when_no_recognised_date(text):
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
# NEW BEHAVIOUR - abbreviated and numeric formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("SAT. APR 25", ExtractedDate("April", 25, "April 25")),
        ("APR. 25", ExtractedDate("April", 25, "April 25")),
        ("WED. AUG.12", ExtractedDate("August", 12, "August 12")),
        ("Tuesday (8/4)@ 7pm", ExtractedDate("August", 4, "August 4")),
        ("8-4", ExtractedDate("August", 4, "August 4")),
    ],
)
def test_benchmark_flyer_formats(text, expected):
    assert extract_date(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Jan 3",
        "JAN. 3",
        "apr 25",
        "APR.25",
        "AuG.12",
    ],
)
def test_abbreviated_month_variants(text):
    result = extract_date(text)
    assert result is not None
    assert result.day in (3, 25, 12)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("8/4", ExtractedDate("August", 4, "August 4")),
        ("08/04", ExtractedDate("August", 4, "August 4")),
        ("12-25", ExtractedDate("December", 25, "December 25")),
        ("1-1", ExtractedDate("January", 1, "January 1")),
    ],
)
def test_numeric_month_day_formats(text, expected):
    assert extract_date(text) == expected


def test_numeric_date_normalizes_with_next_occurrence_rule():
    extracted = extract_date("8/4")
    assert normalize_date(extracted, today=date(2026, 1, 1)) == "2026-08-04"


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

# ---------------------------------------------------------------------------
# NEW BEHAVIOUR - multiple date candidates
# ---------------------------------------------------------------------------

def test_extract_dates_returns_all_matches_in_order():
    """
    Basic multiple-date case.

    extract_date() preserves the original first-match behavior, but
    extract_dates() should scan the entire text and return every recognized
    date in the order in which it appears.
    """
    assert extract_dates("MARCH 27 and APRIL 3") == [
        ExtractedDate("March", 27, "March 27"),
        ExtractedDate("April", 3, "April 3"),
    ]


def test_extract_dates_finds_ui_and_event_dates():
    """
    Regression case based on the benchmark.

    An Instagram screenshot can contain an unrelated UI/post date before the
    actual event date. Extraction should preserve both candidates rather than
    discarding everything after the first match.

    This test does NOT decide which date is correct. Candidate selection is a
    separate responsibility that will be tested separately.
    """
    text = """
    July 22
    ASK A D.C. NATIVE
    Monday, August 24, 2026
    """

    assert extract_dates(text) == [
        ExtractedDate("July", 22, "July 22"),
        ExtractedDate("August", 24, "August 24, 2026", 2026),
    ]

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

# ---------------------------------------------------------------------------
# NEW BEHAVIOUR - event date selection
# ---------------------------------------------------------------------------

def test_select_event_date_prefers_nearest_upcoming_date():
    """
    Regression case from the benchmark.

    July 22 is an older Instagram/UI date. August 24 is the upcoming event.
    """
    candidates = extract_dates(
        "July 22 ASK A D.C. NATIVE Monday, August 24, 2026"
    )

    result = select_event_date(
        candidates,
        today=date(2026, 8, 20),
    )

    assert result == ExtractedDate(
        "August", 24, "August 24, 2026", 2026
    )


def test_select_event_date_skips_old_ui_date():
    """
    Another benchmark case: July 12 appears before the August 29 event date.
    """
    candidates = extract_dates(
        "July 12 SATURDAY AUGUST 29 SIMPLE UNDERGROUND"
    )

    result = select_event_date(
        candidates,
        today=date(2026, 8, 20),
    )

    assert result == ExtractedDate(
        "August", 29, "August 29"
    )


def test_select_event_date_returns_none_for_no_candidates():
    assert select_event_date([], today=date(2026, 8, 20)) is None


# ---------------------------------------------------------------------------
# NEW BEHAVIOUR - explicit printed years
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "AUGUST 24, 2026",
        "Monday, August 24, 2026",
        "AUGUST 24TH 2026",
        "AUG. 24, 2026",
        "Aug 24 2026",
        "8/24/2026",
        "08/24/2026",
        "8-24-2026",
    ],
)
def test_named_and_numeric_formats_capture_explicit_year(text):
    assert extract_date(text) == ExtractedDate(
        "August", 24, "August 24, 2026", 2026
    )


@pytest.mark.parametrize(
    "text,year",
    [
        ("August 24, 1999", 1999),
        ("AUG. 24 1999", 1999),
        ("Aug 24, 2100", 2100),
        ("August 24, 0999", 999),
        ("8/24/1999", 1999),
        ("8-24-1999", 1999),
        ("08/24/2150", 2150),
        ("8/24/0001", 1),
        ("8/24/9999", 9999),
    ],
)
def test_four_digit_years_outside_20xx_are_kept_exactly(text, year):
    extracted = extract_date(text)
    assert extracted == ExtractedDate(
        "August", 24, f"August 24, {year:04d}", year
    )
    assert normalize_date(extracted, today=date(2026, 10, 7)) == (
        f"{year:04d}-08-24"
    )


def test_implausible_four_digit_year_is_preserved_not_rejected():
    """
    OCR noise from the project notes. The parser keeps the printed year rather
    than rejecting or rewriting it; the pipeline is what flags it for review
    (see test_pipeline.py: explicit_future_distant).
    """
    extracted = extract_date("3/17/3679")
    assert extracted == ExtractedDate("March", 17, "March 17, 3679", 3679)
    assert normalize_date(extracted, today=date(2026, 10, 7)) == "3679-03-17"


@pytest.mark.parametrize(
    "text",
    ["August 24, 1999", "8/24/1999", "AUGUST 24, 19999", "8/24/19999"],
)
def test_year_suffix_is_never_dropped_to_a_yearless_date(text):
    """Either the year is kept, or nothing is extracted - never a bare Aug 24."""
    assert all(found.year is not None for found in extract_dates(text))


def test_three_argument_constructor_still_means_no_year():
    assert ExtractedDate("March", 27, "March 27").year is None


@pytest.mark.parametrize(
    "text",
    [
        "2/17/26",      # would otherwise risk "17/26" or a guessed century
        "2/1/26",       # would otherwise risk the fragment "1/26" -> Jan 26
        "12-25-26",
        "Aug 24 '26",
        "AUGUST 24 ’26",
        "Aug 24 '1999",     # apostrophe form is never a year
        "8/24/199",         # three-digit third part
        "8/24/19999",       # five-digit third part
        "8-24-19999",
        "AUGUST 24, 19999", # five digits after a month name
        "Aug. 24 202600",
        "AUGUST 24, 0000",  # year 0 does not exist in datetime.date
        "8/24/0000",
    ],
)
def test_unusable_years_reject_the_whole_date(text):
    assert extract_dates(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "MARCH 27, 10 - 2PM",   # a time, not a two-digit year
        "MARCH 27 1030PM",      # a time, not a four-digit year
        "8/4-10pm",             # different separator: not a third part
    ],
)
def test_trailing_numbers_that_are_not_years_leave_a_yearless_date(text):
    assert extract_date(text).year is None


def test_explicit_future_year_is_kept():
    extracted = extract_date("March 27, 2028")
    assert normalize_date(extracted, today=date(2026, 3, 1)) == "2028-03-27"


def test_explicit_past_year_is_never_rolled_forward():
    extracted = extract_date("8/24/2025")
    assert normalize_date(extracted, today=date(2026, 10, 7)) == "2025-08-24"


@pytest.mark.parametrize(
    "text",
    [
        "February 29, 2027",    # 2027 is not a leap year
        "2/29/2027",
        "June 31, 2026",
        "4/31/2026",
    ],
)
def test_invalid_explicit_date_does_not_fall_back_to_another_year(text):
    extracted = extract_date(text)
    assert extracted is not None
    assert normalize_date(extracted, today=date(2026, 1, 1)) is None


def test_explicit_leap_day_in_a_leap_year_is_valid():
    extracted = extract_date("Feb 29 2028")
    assert normalize_date(extracted, today=date(2026, 1, 1)) == "2028-02-29"


# ---------------------------------------------------------------------------
# NEW BEHAVIOUR - missing year keeps the next-occurrence rule
# ---------------------------------------------------------------------------

def test_missing_year_within_the_current_year():
    extracted = extract_date("NOV 14")
    assert normalize_date(extracted, today=date(2026, 10, 7)) == "2026-11-14"


def test_missing_year_rolls_over_december_to_january():
    extracted = extract_date("JAN 3")
    assert normalize_date(extracted, today=date(2026, 12, 20)) == "2027-01-03"


def test_recently_passed_month_day_suggests_next_year():
    extracted = extract_date("OCT 1")
    assert normalize_date(extracted, today=date(2026, 10, 7)) == "2027-10-01"


# ---------------------------------------------------------------------------
# NEW BEHAVIOUR - selection with explicit years
# ---------------------------------------------------------------------------

def test_select_prefers_upcoming_over_past_candidates():
    candidates = extract_dates("Last year: August 24, 2025. This year: 8/30/2026")
    result = select_event_date(candidates, today=date(2026, 8, 20))
    assert result.year == 2026 and result.day == 30


def test_select_returns_most_recent_past_candidate_when_all_past():
    candidates = extract_dates("May 1, 2025 and August 24, 2025 and 3/2/2024")
    result = select_event_date(candidates, today=date(2026, 8, 20))
    assert result == ExtractedDate("August", 24, "August 24, 2025", 2025)


def test_select_upcoming_inferred_beats_past_explicit():
    candidates = extract_dates("August 1, 2026 SEPT 5")
    result = select_event_date(candidates, today=date(2026, 8, 20))
    assert result == ExtractedDate("September", 5, "September 5")


def test_select_skips_invalid_candidates_when_a_valid_one_exists():
    candidates = extract_dates("February 29, 2027 then March 3, 2027")
    result = select_event_date(candidates, today=date(2026, 8, 20))
    assert result.month_name == "March"


def test_select_returns_an_invalid_candidate_when_all_are_invalid():
    """Lets the caller say "invalid date" rather than "no date found"."""
    candidates = extract_dates("June 31, 2026 and 2/29/2027")
    result = select_event_date(candidates, today=date(2026, 8, 20))
    assert result == ExtractedDate("June", 31, "June 31, 2026", 2026)
    assert normalize_date(result, today=date(2026, 8, 20)) is None


@pytest.mark.parametrize("text", [
    "SEPTEMBER 19. 2026",
    "Sept. 19. 2026",
    "SEPTEMBER 19. 1999",
])
def test_period_before_printed_year_is_preserved(text):
    year = int(text[-4:])
    extracted = extract_date(text)
    assert extracted == ExtractedDate(
        "September", 19, f"September 19, {year}", year
    )
    assert normalize_date(extracted, today=date(2026, 10, 7)) == (
        f"{year}-09-19"
    )

def test_recent_printed_event_beats_distant_inferred_post_date():
    today = date(2026, 10, 7)
    selected = select_event_date(
        extract_dates("SEPTEMBER 19. 2026 July 30"), today=today
    )
    assert normalize_date(selected, today=today) == "2026-09-19"


def test_near_upcoming_date_beats_recent_printed_past_date():
    today = date(2026, 10, 7)
    selected = select_event_date(
        extract_dates("September 19, 2026 October 10"), today=today
    )
    assert normalize_date(selected, today=today) == "2026-10-10"


def test_old_printed_date_does_not_override_inferred_upcoming_date():
    today = date(2026, 10, 7)
    selected = select_event_date(
        extract_dates("September 19, 1999 July 30"), today=today
    )
    assert normalize_date(selected, today=today) == "2027-07-30"