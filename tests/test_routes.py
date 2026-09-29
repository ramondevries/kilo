import io
import re
from datetime import date, timedelta

import pytest

from app import db
from app.models import User, WeightEntry
from tests.conftest import signup_and_verify


def test_index_shows_login_prompt_when_logged_out(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_index_shows_grid_when_logged_in(logged_in_client):
    client, _ = logged_in_client
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"day-row" in resp.data
    assert b"No entries yet" in resp.data


def test_save_field_creates_entry(logged_in_client, app):
    client, user_id = logged_in_client
    resp = client.post(
        "/entries/field",
        json={"date": "2026-01-01", "weight": 80.5, "note": "morning"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "saved"
    with app.app_context():
        entry = WeightEntry.query.filter_by(user_id=user_id).one()
        assert entry.weight == 80.5
        assert entry.note == "morning"


def test_save_field_upserts_same_date(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/entries/field", json={"date": "2026-01-01", "weight": 80.5})
    client.post("/entries/field", json={"date": "2026-01-01", "weight": 81.0})
    with app.app_context():
        entries = WeightEntry.query.filter_by(user_id=user_id).all()
        assert len(entries) == 1
        assert entries[0].weight == 81.0


def test_save_field_empty_weight_deletes_entry(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/entries/field", json={"date": "2026-01-01", "weight": 80.5})
    resp = client.post("/entries/field", json={"date": "2026-01-01", "weight": ""})
    assert resp.get_json()["status"] == "cleared"
    with app.app_context():
        assert WeightEntry.query.filter_by(user_id=user_id).count() == 0


def test_save_field_rejects_invalid_weight(logged_in_client, app):
    client, user_id = logged_in_client
    resp = client.post("/entries/field", json={"date": "2026-01-01", "weight": -5})
    assert resp.status_code == 400
    with app.app_context():
        assert WeightEntry.query.filter_by(user_id=user_id).count() == 0


def test_save_field_requires_login(client):
    resp = client.post("/entries/field", json={"date": "2026-01-01", "weight": 80.5})
    assert resp.status_code == 302


def test_entries_window_returns_days_before_given_date(logged_in_client, app):
    client, user_id = logged_in_client
    with app.app_context():
        db.session.add(WeightEntry(user_id=user_id, entry_date=date(2026, 1, 1), weight=80.0))
        db.session.commit()

    resp = client.get("/entries/window?before=2026-01-02")
    assert resp.status_code == 200
    days = resp.get_json()["days"]
    assert len(days) == 30
    assert days[0]["date"] == "2026-01-01"
    assert days[0]["weight"] == 80.0
    assert days[-1]["date"] == (date(2026, 1, 1) - timedelta(days=29)).isoformat()


def test_data_is_isolated_between_users(app):
    client_a = app.test_client()
    client_b = app.test_client()

    signup_and_verify(client_a, "a@example.com")
    signup_and_verify(client_b, "b@example.com")

    client_a.post("/entries/field", json={"date": "2026-01-01", "weight": 70.0})
    client_b.post("/entries/field", json={"date": "2026-01-01", "weight": 90.0})

    resp_a = client_a.get("/")
    resp_b = client_b.get("/")
    assert b"70.0" in resp_a.data
    assert b"90.0" not in resp_a.data
    assert b"90.0" in resp_b.data
    assert b"70.0" not in resp_b.data

    with app.app_context():
        assert WeightEntry.query.count() == 2


def test_settings_requires_login(client):
    resp = client.get("/settings")
    assert resp.status_code == 302


def test_settings_updates_height_in_cm(logged_in_client, app):
    client, user_id = logged_in_client
    resp = client.post(
        "/settings", data={"height_value": "180", "height_unit": "cm"}, follow_redirects=True
    )
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.height_cm == 180
        assert user.height_unit == "cm"


def test_settings_updates_height_in_meters(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/settings", data={"height_value": "1.8", "height_unit": "m"})
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.height_cm == 180
        assert user.height_unit == "m"


def test_bmi_shown_once_height_and_weight_are_set(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/settings", data={"height_value": "180", "height_unit": "cm"})
    client.post("/entries/field", json={"date": date.today().isoformat(), "weight": 81.0})

    resp = client.get("/")
    assert resp.status_code == 200
    # 81 / 1.8^2 = 25.0
    assert b"25.0" in resp.data


def test_gravatar_hash_matches_email_hash(logged_in_client, app):
    _, user_id = logged_in_client
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.gravatar_url() == f"https://www.gravatar.com/avatar/{user.email_hash}?s=80&d=mp"


def test_about_page_renders(client):
    resp = client.get("/about")
    assert resp.status_code == 200
    assert b"SHA-256" in resp.data


def test_default_theme_is_light(logged_in_client, app):
    client, user_id = logged_in_client
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.dark_mode is False

    resp = client.get("/")
    assert b'data-theme="light"' in resp.data


def test_logged_out_theme_is_light(client):
    resp = client.get("/")
    assert b'data-theme="light"' in resp.data


def test_settings_toggle_dark_mode(logged_in_client, app):
    client, user_id = logged_in_client
    resp = client.post(
        "/settings",
        data={"height_value": "180", "height_unit": "cm", "dark_mode": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.dark_mode is True

    resp2 = client.get("/")
    assert b'data-theme="dark"' in resp2.data


def test_settings_untoggle_dark_mode(logged_in_client, app):
    client, user_id = logged_in_client
    client.post(
        "/settings", data={"height_value": "180", "height_unit": "cm", "dark_mode": "y"}
    )
    client.post("/settings", data={"height_value": "180", "height_unit": "cm"})
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.dark_mode is False


def _upload(client, text, filename="data.csv"):
    return client.post(
        "/settings/import",
        data={"csv_file": (io.BytesIO(text.encode()), filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_import_creates_entries(logged_in_client, app):
    client, user_id = logged_in_client
    text = "23-9-26,79.7,optional notes\n25-9-26,80.5,\n"
    resp = _upload(client, text)
    assert resp.status_code == 200
    assert b"Imported 2" in resp.data

    with app.app_context():
        entries = WeightEntry.query.filter_by(user_id=user_id).order_by(WeightEntry.entry_date).all()
        assert len(entries) == 2
        assert entries[0].entry_date == date(2026, 9, 23)
        assert entries[0].weight == 79.7
        assert entries[0].note == "optional notes"
        assert entries[1].note is None


def test_import_overwrites_existing_entry_for_same_date(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/entries/field", json={"date": "2026-09-23", "weight": 70.0, "note": "old"})
    _upload(client, "23-9-26,79.7,new note\n")
    with app.app_context():
        entries = WeightEntry.query.filter_by(user_id=user_id).all()
        assert len(entries) == 1
        assert entries[0].weight == 79.7
        assert entries[0].note == "new note"


def test_import_reports_skipped_invalid_lines(logged_in_client, app):
    client, user_id = logged_in_client
    text = "23-9-26,79.7,\nnot-a-date,80,\n24-9-26,not-a-number,\n"
    resp = _upload(client, text)
    assert b"Imported 1" in resp.data
    assert b"Skipped 2" in resp.data
    with app.app_context():
        assert WeightEntry.query.filter_by(user_id=user_id).count() == 1


def test_import_four_digit_year(logged_in_client, app):
    client, user_id = logged_in_client
    _upload(client, "23-9-2026,79.7,\n")
    with app.app_context():
        entry = WeightEntry.query.filter_by(user_id=user_id).one()
        assert entry.entry_date == date(2026, 9, 23)


def test_import_requires_login(client):
    resp = _upload(client, "23-9-26,79.7,\n")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_import_rejects_wrong_file_type(logged_in_client, app):
    client, user_id = logged_in_client
    resp = client.post(
        "/settings/import",
        data={"csv_file": (io.BytesIO(b"not a csv"), "data.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"CSV or text files only" in resp.data
    with app.app_context():
        assert WeightEntry.query.filter_by(user_id=user_id).count() == 0


def test_export_returns_csv_attachment(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/entries/field", json={"date": "2026-09-23", "weight": 79.7, "note": "hi"})

    resp = client.get("/settings/export")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.data.decode() == "23-9-26,79.7,hi\r\n"


def test_export_requires_login(client):
    resp = client.get("/settings/export")
    assert resp.status_code == 302


def test_export_then_import_round_trips(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/entries/field", json={"date": "2026-09-23", "weight": 79.7, "note": "hi"})
    client.post("/entries/field", json={"date": "2026-09-24", "weight": 80.1})

    exported = client.get("/settings/export").data

    with app.app_context():
        WeightEntry.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    _upload(client, exported.decode())
    with app.app_context():
        entries = WeightEntry.query.filter_by(user_id=user_id).order_by(WeightEntry.entry_date).all()
        assert [e.weight for e in entries] == [79.7, 80.1]


def _add_entry(app, user_id, days_ago, weight=70.0):
    with app.app_context():
        db.session.add(
            WeightEntry(
                user_id=user_id, entry_date=date.today() - timedelta(days=days_ago), weight=weight
            )
        )
        db.session.commit()


def _range_buttons(html):
    """Map range key -> {'hidden': bool, 'active': bool} parsed from the rendered buttons."""
    result = {}
    for tag in re.findall(r"<button\b[^>]*data-range=[^>]*>", html):
        key = re.search(r'data-range="(\w+)"', tag).group(1)
        result[key] = {"hidden": " hidden" in tag, "active": "active" in tag}
    return result


def test_chart_range_default_is_all_with_only_always_shown_buttons(logged_in_client):
    client, _ = logged_in_client
    buttons = _range_buttons(client.get("/").data.decode())

    assert buttons["all"]["active"] is True
    assert buttons["1w"]["hidden"] is False
    assert buttons["all"]["hidden"] is False
    for key in ("1m", "3m", "1y", "5y", "10y", "15y", "20y"):
        assert buttons[key]["hidden"] is True, f"{key} should be hidden with no data"


def test_chart_range_buttons_unlock_as_data_spans_grow(logged_in_client, app):
    client, user_id = logged_in_client
    _add_entry(app, user_id, days_ago=0)
    _add_entry(app, user_id, days_ago=400)

    buttons = _range_buttons(client.get("/").data.decode())
    for key in ("1w", "1m", "3m", "1y", "all"):
        assert buttons[key]["hidden"] is False, f"{key} should be visible (400-day span)"
    for key in ("5y", "10y", "15y", "20y"):
        assert buttons[key]["hidden"] is True, f"{key} should still be hidden"


def test_set_chart_range_persists_and_reflects_on_reload(logged_in_client, app):
    client, user_id = logged_in_client
    _add_entry(app, user_id, days_ago=0)
    _add_entry(app, user_id, days_ago=40)

    resp = client.post("/chart-range", json={"range": "1m"})
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.chart_range == "1m"

    buttons = _range_buttons(client.get("/").data.decode())
    assert buttons["1m"]["active"] is True
    assert buttons["all"]["active"] is False


def test_set_chart_range_rejects_invalid_value(logged_in_client, app):
    client, user_id = logged_in_client
    resp = client.post("/chart-range", json={"range": "bogus"})
    assert resp.status_code == 400
    with app.app_context():
        assert db.session.get(User, user_id).chart_range == "all"


def test_set_chart_range_requires_login(client):
    resp = client.post("/chart-range", json={"range": "1m"})
    assert resp.status_code == 302


def test_chart_range_falls_back_to_all_when_stored_range_unavailable(logged_in_client, app):
    client, user_id = logged_in_client
    _add_entry(app, user_id, days_ago=0)
    with app.app_context():
        user = db.session.get(User, user_id)
        user.chart_range = "5y"  # stale preference; data doesn't span 5 years
        db.session.commit()

    buttons = _range_buttons(client.get("/").data.decode())
    assert buttons["5y"]["hidden"] is True
    assert buttons["all"]["active"] is True
    assert buttons["5y"]["active"] is False


def test_chart_bmis_null_without_height(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/entries/field", json={"date": "2026-09-23", "weight": 80.0})
    assert resp.get_json()["chart_bmis"] is None


def test_chart_bmis_computed_with_height(logged_in_client):
    client, _ = logged_in_client
    client.post("/settings", data={"height_value": "180", "height_unit": "cm"})

    client.post("/entries/field", json={"date": "2026-09-23", "weight": 81.0})
    resp = client.post("/entries/field", json={"date": "2026-09-24", "weight": 90.0})
    data = resp.get_json()

    assert data["chart_labels"] == ["2026-09-23", "2026-09-24"]
    assert data["chart_bmis"] == pytest.approx([25.0, 27.777777777777775])


def test_chart_bmis_cleared_alongside_entry(logged_in_client):
    client, _ = logged_in_client
    client.post("/settings", data={"height_value": "180", "height_unit": "cm"})
    client.post("/entries/field", json={"date": "2026-09-23", "weight": 81.0})

    resp = client.post("/entries/field", json={"date": "2026-09-23", "weight": ""})
    data = resp.get_json()
    assert data["chart_bmis"] is None
    assert data["chart_labels"] == []


def test_chart_fills_gaps_with_linear_interpolation(logged_in_client):
    client, _ = logged_in_client
    client.post("/entries/field", json={"date": "2026-09-01", "weight": 70.0})
    resp = client.post("/entries/field", json={"date": "2026-09-05", "weight": 90.0})
    data = resp.get_json()

    assert data["chart_labels"] == [
        "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05",
    ]
    assert data["chart_values"] == pytest.approx([70.0, 75.0, 80.0, 85.0, 90.0])
    assert data["chart_real"] == [True, False, False, False, True]


def test_chart_real_flags_every_point_true_when_no_gaps(logged_in_client):
    client, _ = logged_in_client
    client.post("/entries/field", json={"date": "2026-09-01", "weight": 70.0})
    resp = client.post("/entries/field", json={"date": "2026-09-02", "weight": 71.0})
    assert resp.get_json()["chart_real"] == [True, True]


def test_chart_series_single_entry_has_no_gaps_to_fill(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/entries/field", json={"date": "2026-09-23", "weight": 79.0})
    data = resp.get_json()
    assert data["chart_labels"] == ["2026-09-23"]
    assert data["chart_values"] == [79.0]
    assert data["chart_real"] == [True]


def test_chart_bmis_use_interpolated_weight(logged_in_client):
    client, _ = logged_in_client
    client.post("/settings", data={"height_value": "180", "height_unit": "cm"})
    client.post("/entries/field", json={"date": "2026-09-01", "weight": 70.0})
    resp = client.post("/entries/field", json={"date": "2026-09-05", "weight": 90.0})
    data = resp.get_json()

    # 80.0 kg / 1.8^2 = 24.691... at the midpoint (2026-09-03)
    assert data["chart_bmis"][2] == pytest.approx(80.0 / 1.8 ** 2)


def test_stats_unaffected_by_interpolation(logged_in_client):
    client, _ = logged_in_client
    client.post("/entries/field", json={"date": "2026-09-01", "weight": 70.0})
    resp = client.post("/entries/field", json={"date": "2026-09-05", "weight": 90.0})
    stats = resp.get_json()["stats"]
    # stats are computed from real entries only, not the 5 interpolated points
    assert stats["current"] == 90.0
    assert stats["start"] == 70.0
    assert stats["total_change"] == 20.0


def test_today_prompt_shows_when_todays_entry_missing(logged_in_client):
    client, _ = logged_in_client
    html = client.get("/").data.decode()
    assert "const todayEntryMissing = true;" in html
    assert f'const todayDate = "{date.today().isoformat()}";' in html
    assert 'id="today-prompt"' in html


def test_today_prompt_hidden_flag_when_todays_entry_exists(logged_in_client):
    client, _ = logged_in_client
    client.post("/entries/field", json={"date": date.today().isoformat(), "weight": 80.0})
    html = client.get("/").data.decode()
    assert "const todayEntryMissing = false;" in html


def test_today_prompt_missing_when_only_older_entries_exist(logged_in_client):
    client, _ = logged_in_client
    client.post(
        "/entries/field", json={"date": (date.today() - timedelta(days=1)).isoformat(), "weight": 80.0}
    )
    html = client.get("/").data.decode()
    assert "const todayEntryMissing = true;" in html
