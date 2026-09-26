from datetime import date, timedelta

from app.models import WeightEntry


def test_index_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"No entries yet" in resp.data


def test_create_entry(client, app):
    resp = client.post(
        "/entries",
        data={"entry_date": "2026-01-01", "weight": "80.5", "note": "morning"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        entry = WeightEntry.query.one()
        assert entry.weight == 80.5
        assert entry.note == "morning"


def test_create_entry_upserts_same_date(client, app):
    client.post("/entries", data={"entry_date": "2026-01-01", "weight": "80.5"})
    client.post("/entries", data={"entry_date": "2026-01-01", "weight": "81.0"})
    with app.app_context():
        entries = WeightEntry.query.all()
        assert len(entries) == 1
        assert entries[0].weight == 81.0


def test_create_entry_rejects_invalid_weight(client, app):
    resp = client.post(
        "/entries", data={"entry_date": "2026-01-01", "weight": "-5"}, follow_redirects=True
    )
    assert resp.status_code == 200
    with app.app_context():
        assert WeightEntry.query.count() == 0


def test_edit_entry(client, app):
    with app.app_context():
        entry = WeightEntry(entry_date=date(2026, 1, 1), weight=80.0)
        from app import db

        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    resp = client.post(
        f"/entries/{entry_id}/edit",
        data={"entry_date": "2026-01-02", "weight": "79.0", "note": "updated"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        from app import db

        entry = db.session.get(WeightEntry, entry_id)
        assert entry.entry_date == date(2026, 1, 2)
        assert entry.weight == 79.0


def test_delete_entry(client, app):
    from app import db

    with app.app_context():
        entry = WeightEntry(entry_date=date(2026, 1, 1), weight=80.0)
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    resp = client.post(f"/entries/{entry_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert WeightEntry.query.count() == 0


def test_stats_computed_on_index(client, app):
    from app import db

    today = date(2026, 1, 31)
    with app.app_context():
        db.session.add(WeightEntry(entry_date=today - timedelta(days=30), weight=90.0))
        db.session.add(WeightEntry(entry_date=today - timedelta(days=7), weight=85.0))
        db.session.add(WeightEntry(entry_date=today, weight=83.0))
        db.session.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"83.0" in resp.data
