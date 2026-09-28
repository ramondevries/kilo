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

    return app
