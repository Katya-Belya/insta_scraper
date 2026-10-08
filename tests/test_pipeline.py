from dataclasses import fields
from datetime import date, timedelta

import pytest

import src.pipeline as pipeline
from src.pipeline import FlyerResult, extract_event_date, format_result


def test_flyer_result_fields_match_expected_columns():
    assert [field.name for field in fields(FlyerResult)] == [
        "filename",
        "raw_text",
        "clean_text",
        "date_found",
        "event_date",
        "valid",
        "status",
        "needs_review",
    ]


def test_format_result_uses_flyer_result_fields():
    result = FlyerResult(
        filename="august_happy_hour.jpg",
        raw_text="Tuesday (8/4)@ 7pm",
        clean_text="Tuesday (8/4)@ 7pm",
        date_found="August 4",
        event_date="2027-08-04",
        valid=True,
        status="ok",
        needs_review=False,
    )

    formatted = format_result(result)

    assert "august_happy_hour.jpg" in formatted
    assert "August 4" in formatted
    assert "2027-08-04" in formatted
    assert "True" in formatted
    assert "ok" in formatted
    assert "False" in formatted

# ---------------------------------------------------------------------------
# Date status and review rules, through extract_event_date() with OCR stubbed
# ---------------------------------------------------------------------------


TODAY = date(2026, 10, 7)


@pytest.fixture
def ocr_text(monkeypatch):
    """Make the OCR stages return whatever text a test sets."""
    holder = {"text": ""}

    monkeypatch.setattr(pipeline, "load_image", lambda path: object())
    monkeypatch.setattr(pipeline, "crop_date_region", lambda image: image)
    monkeypatch.setattr(pipeline, "preprocess", lambda image: image)
    monkeypatch.setattr(pipeline, "image_to_text", lambda image: holder["text"])

    def run(text, today=TODAY, **kwargs):
        holder["text"] = text
        return extract_event_date("flyer.jpg", today=today, **kwargs)

    return run


def test_explicit_future_date_is_ok_without_review(ocr_text):
    result = ocr_text("Saturday, March 27, 2027")
    assert (result.event_date, result.status) == ("2027-03-27", "ok")
    assert result.valid is True
    assert result.needs_review is False
    assert result.date_found == "March 27, 2027"


def test_explicit_date_today_is_ok(ocr_text):
    result = ocr_text("10/7/2026")
    assert (result.event_date, result.status) == ("2026-10-07", "ok")
    assert result.needs_review is False


@pytest.mark.parametrize("text", ["August 24, 1999", "8/24/1999"])
def test_explicit_year_before_2000_is_a_flagged_past_date(ocr_text, text):
    result = ocr_text(text)
    assert result.event_date == "1999-08-24"
    assert result.date_found == "August 24, 1999"
    assert result.status == "explicit_past_date"
    assert result.valid is True
    assert result.needs_review is True


def test_explicit_year_after_2099_is_kept(ocr_text):
    result = ocr_text("8/24/2150")
    assert (result.event_date, result.status) == ("2150-08-24", "ok")


@pytest.mark.parametrize("text", ["8/24/19999", "AUGUST 24, 19999", "8/24/0000"])
def test_malformed_year_is_not_read_as_a_yearless_date(ocr_text, text):
    result = ocr_text(text)
    assert result.status == "no_date_found"
    assert result.event_date is None


def test_explicit_past_date_is_valid_but_needs_review(ocr_text):
    result = ocr_text("Monday, August 24, 2025")
    assert result.event_date == "2025-08-24"
    assert result.status == "explicit_past_date"
    assert result.valid is True
    assert result.needs_review is True


def test_missing_year_a_few_days_away_still_needs_review(ocr_text):
    result = ocr_text("SAT. OCT 10")
    assert result.event_date == "2026-10-10"
    assert result.status == "inferred_year"
    assert result.valid is True
    assert result.needs_review is True


def test_recently_passed_month_day_is_a_distant_suggestion(ocr_text):
    result = ocr_text("OCT 1")
    assert result.event_date == "2027-10-01"
    assert result.status == "inferred_year_distant"
    assert result.valid is True
    assert result.needs_review is True


def test_december_to_january_rollover_is_inferred(ocr_text):
    result = ocr_text("JAN 3", today=date(2026, 12, 20))
    assert result.event_date == "2027-01-03"
    assert result.status == "inferred_year"
    assert result.needs_review is True


@pytest.mark.parametrize(
    "text,expected_date,expected_status",
    [
        # TODAY + 90 days = 2027-01-05; + 91 days = 2027-01-06.
        ("JAN 5", "2027-01-05", "inferred_year"),
        ("JAN 6", "2027-01-06", "inferred_year_distant"),
    ],
)
def test_distant_threshold_is_more_than_90_days(
    ocr_text, text, expected_date, expected_status
):
    result = ocr_text(text)
    assert (result.event_date, result.status) == (expected_date, expected_status)
    assert result.needs_review is True


def test_distant_threshold_is_configurable(ocr_text):
    result = ocr_text("JAN 6", distant_inferred_days=91)
    assert result.status == "inferred_year"


@pytest.mark.parametrize("text", ["February 29, 2027", "2/29/2027", "June 31"])
def test_invalid_date_requires_correction(ocr_text, text):
    result = ocr_text(text)
    assert result.event_date is None
    assert result.status == "invalid_date"
    assert result.valid is False
    assert result.needs_review is True
    assert result.date_found is not None


def test_all_invalid_candidates_report_invalid_not_missing(ocr_text):
    result = ocr_text("June 31, 2026 and 2/29/2027")
    assert result.status == "invalid_date"
    assert result.date_found == "June 31, 2026"


def test_no_candidates_report_no_date_found(ocr_text):
    result = ocr_text("4PM - 8PM")
    assert result.status == "no_date_found"
    assert result.valid is False
    assert result.needs_review is True


def test_upcoming_candidate_beats_past_candidate(ocr_text):
    result = ocr_text("Posted August 24, 2026. Event 10/20/2026")
    assert (result.event_date, result.status) == ("2026-10-20", "ok")


def test_only_past_candidates_return_the_most_recent_flagged(ocr_text):
    result = ocr_text("May 1, 2025 and August 24, 2025")
    assert result.event_date == "2025-08-24"
    assert result.status == "explicit_past_date"
    assert result.needs_review is True


def test_today_is_resolved_once_per_call(ocr_text, monkeypatch):
    """With no `today`, every stage must see the same single date.today()."""
    calls = []

    class FakeDate(date):
        @classmethod
        def today(cls):
            calls.append(1)
            # Each call would return a later day, so a second call would show.
            return date(2026, 10, 7) + timedelta(days=len(calls) - 1)

    monkeypatch.setattr(pipeline, "date", FakeDate)

    seen = []
    real_select = pipeline.select_event_date
    real_normalize = pipeline.normalize_date

    def spy_select(candidates, today=None):
        seen.append(today)
        return real_select(candidates, today=today)

    def spy_normalize(extracted, today=None):
        seen.append(today)
        return real_normalize(extracted, today=today)

    monkeypatch.setattr(pipeline, "select_event_date", spy_select)
    monkeypatch.setattr(pipeline, "normalize_date", spy_normalize)

    result = ocr_text("OCT 7", today=None)

    assert len(calls) == 1
    assert seen == [date(2026, 10, 7), date(2026, 10, 7)]
    assert result.event_date == "2026-10-07"
    assert result.status == "inferred_year"
