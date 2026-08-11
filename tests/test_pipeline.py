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
    ]


def test_format_result_uses_flyer_result_fields():
    result = FlyerResult(
        filename="august_happy_hour.jpg",
        raw_text="Tuesday (8/4)@ 7pm",
        clean_text="Tuesday (8/4)@ 7pm",
        date_found="August 4",
        event_date="2027-08-04",
        valid=True,
    )

    output = format_result(result)

    assert "august_happy_hour.jpg" in output
    assert "August 4" in output
    assert "2027-08-04" in output
    assert "True" in output