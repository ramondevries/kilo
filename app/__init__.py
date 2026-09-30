import os
import sqlite3

from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
csrf = CSRFProtect()
mail = Mail()


SQLITE_BUSY_TIMEOUT_MS = 30_000


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, connection_record):
    """Make SQLite behave with several app processes (e.g. gunicorn workers)
    sharing one database file.

    WAL lets readers and the single writer work at the same time instead of
    blocking each other; a long busy timeout makes a writer wait for the lock
    rather than fail with "database is locked" after the 5s default."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, fewer fsyncs
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    cursor.close()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(app.instance_path, "weight.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        WEIGHT_UNIT=os.environ.get("WEIGHT_UNIT", "kg"),
        MAIL_SERVER=os.environ.get("MAIL_SERVER", "localhost"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", 25)),
        MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "0") == "1",
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@weight-tracker.local"),
        MAIL_SUPPRESS_SEND=os.environ.get("MAIL_SUPPRESS_SEND", "1") == "1",
        CHECK_EMAIL_MX=os.environ.get("CHECK_EMAIL_MX", "1") == "1",
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    from . import account, auth, routes
    app.register_blueprint(routes.bp)
    app.register_blueprint(account.bp)
    app.register_blueprint(auth.bp)

    with app.app_context():
        db.create_all()
        _add_missing_columns()

    return app


def _add_missing_columns():
    """db.create_all() only creates tables that don't exist yet — it never
    alters an existing one. There's no migration framework here, so new
    nullable-with-default columns are added by hand with a plain ALTER TABLE
    when a pre-existing database is missing them."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "user" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("user")}
    new_columns = {
        "moving_avg_days": "INTEGER NOT NULL DEFAULT 30",
        "delete_code_hash": "VARCHAR(255)",
        "delete_code_expires_at": "DATETIME",
        "delete_code_attempts": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, ddl in new_columns.items():
        if name not in existing:
            db.session.execute(text(f"ALTER TABLE user ADD COLUMN {name} {ddl}"))
    db.session.commit()
