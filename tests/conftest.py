import re

import pytest

from app import create_app, db, mail
from app.models import User


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
        }
    )

    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def signup_and_verify(client, email):
    with mail.record_messages() as outbox:
        client.post("/signup", data={"email": email})
    match = re.search(r"\b(\d{6})\b", outbox[-1].body)
    client.post("/verify", data={"code": match.group(1)})


@pytest.fixture
def logged_in_client(client, app):
    signup_and_verify(client, "user@example.com")
    with app.app_context():
        user = User.query.first()
        user_id = user.id
    return client, user_id
