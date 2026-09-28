from datetime import date, timedelta

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
