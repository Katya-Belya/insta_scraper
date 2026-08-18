from dataclasses import fields

from src.pipeline import FlyerResult, format_result


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