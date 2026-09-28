from datetime import date

import pytest

from app.csv_io import CsvRowError, export_csv, format_ddmyy, parse_csv, parse_ddmyy


def test_parse_ddmyy_two_digit_year():
    assert parse_ddmyy("23-9-26") == date(2026, 9, 23)


def test_parse_ddmyy_four_digit_year():
    assert parse_ddmyy("23-9-2026") == date(2026, 9, 23)


def test_parse_ddmyy_invalid_raises():
    with pytest.raises(CsvRowError):
        parse_ddmyy("not-a-date")
    with pytest.raises(CsvRowError):
        parse_ddmyy("32-13-26")


def test_format_ddmyy_round_trips():
    d = date(2026, 9, 23)
    assert format_ddmyy(d) == "23-9-26"
    assert parse_ddmyy(format_ddmyy(d)) == d


def test_parse_csv_basic_example():
    text = (
        "23-9-26,79.7,optional notes\n"
        "24-9-26,79.7,optional notes\n"
        "25-9-26,80.5,\n"
        "26-9-26,80.3,some text\n"
        "27-9-26,79.5,some text\n"
    )
    rows, errors = parse_csv(text, "kg")
    assert errors == []
    assert len(rows) == 5
    assert rows[0] == (date(2026, 9, 23), 79.7, "optional notes")
    assert rows[2] == (date(2026, 9, 25), 80.5, None)


def test_parse_csv_converts_kg_to_lb():
    rows, errors = parse_csv("1-1-26,100,\n", "lb")
    assert errors == []
    assert rows[0][1] == pytest.approx(220.462, rel=1e-3)


def test_parse_csv_skips_invalid_lines():
    text = "1-1-26,80,\nbad-date,80,\n2-1-26,not-a-number,\n3-1-26,5000,\n4-1-26,81,ok\n"
    rows, errors = parse_csv(text, "kg")
    assert len(rows) == 2
    assert len(errors) == 3
    assert "line 2" in errors[0]
    assert "line 3" in errors[1]
    assert "line 4" in errors[2]


def test_parse_csv_ignores_blank_lines():
    rows, errors = parse_csv("1-1-26,80,\n\n\n2-1-26,81,\n", "kg")
    assert len(rows) == 2
    assert errors == []


def test_export_csv_round_trips_through_parse():
    class FakeEntry:
        def __init__(self, entry_date, weight, note):
            self.entry_date = entry_date
            self.weight = weight
            self.note = note

    entries = [FakeEntry(date(2026, 9, 23), 79.7, "hi"), FakeEntry(date(2026, 9, 24), 80.0, None)]
    text = export_csv(entries, "kg")
    rows, errors = parse_csv(text, "kg")
    assert errors == []
    assert rows == [(date(2026, 9, 23), 79.7, "hi"), (date(2026, 9, 24), 80.0, None)]
