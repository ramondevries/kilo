import os

from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()
mail = Mail()


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
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    from . import auth, routes
    app.register_blueprint(routes.bp)
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
    if "moving_avg_days" not in existing:
        db.session.execute(
            text("ALTER TABLE user ADD COLUMN moving_avg_days INTEGER NOT NULL DEFAULT 30")
        )
        db.session.commit()
