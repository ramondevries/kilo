import threading

from app import SQLITE_BUSY_TIMEOUT_MS, create_app, db
from app.models import User


def _file_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
            "WTF_CSRF_ENABLED": False,
        }
    )


def _pragma(name):
    return db.session.execute(db.text(f"PRAGMA {name}")).scalar()


def test_sqlite_uses_wal_and_a_long_busy_timeout(tmp_path):
    app = _file_app(tmp_path)
    with app.app_context():
        assert _pragma("journal_mode") == "wal"
        assert _pragma("busy_timeout") == SQLITE_BUSY_TIMEOUT_MS
        db.session.remove()


def test_a_reader_is_not_blocked_by_an_open_write_transaction(tmp_path):
    app = _file_app(tmp_path)
    result = {}

    with app.app_context():
        db.session.add(User(email_hash="a" * 64))
        db.session.commit()

        # Hold a write transaction open (uncommitted) on this connection...
        db.session.add(User(email_hash="b" * 64))
        db.session.flush()

        # ...and read from another connection/thread while it's open.
        def reader():
            with app.app_context():
                result["count"] = User.query.count()
                db.session.remove()

        t = threading.Thread(target=reader)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "reader blocked by the open write transaction"
        db.session.rollback()
        db.session.remove()

    assert result["count"] == 1
