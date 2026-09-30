import re

from app import mail
from app.models import User
from app.utils import hash_email


def _get_code(outbox):
    body = outbox[-1].body
    match = re.search(r"\b(\d{6})\b", body)
    assert match, f"no code found in email body: {body!r}"
    return match.group(1)


def test_signup_sends_code_and_creates_unverified_user(client, app):
    with mail.record_messages() as outbox:
        resp = client.post("/signup", data={"email": "New@Example.com"}, follow_redirects=True)
    assert resp.status_code == 200
    assert len(outbox) == 1
    assert outbox[0].recipients == ["new@example.com"]

    with app.app_context():
        user = User.query.filter_by(email_hash=hash_email("new@example.com")).first()
        assert user is not None
        assert not user.is_verified


def test_verify_with_correct_code_signs_in(client, app):
    with mail.record_messages() as outbox:
        client.post("/signup", data={"email": "a@example.com"})
    code = _get_code(outbox)

    resp = client.post("/verify", data={"code": code}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email_hash=hash_email("a@example.com")).first()
        assert user.is_verified

    with client.session_transaction() as sess:
        assert sess.get("user_id") == user.id
        assert "pending_email" not in sess


def test_verify_with_wrong_code_fails(client, app):
    with mail.record_messages():
        client.post("/signup", data={"email": "b@example.com"})

    resp = client.post("/verify", data={"code": "000000"}, follow_redirects=True)
    assert b"Incorrect code" in resp.data

    with app.app_context():
        user = User.query.filter_by(email_hash=hash_email("b@example.com")).first()
        assert not user.is_verified


def test_resend_code_issues_new_code(client, app):
    with mail.record_messages() as outbox:
        client.post("/signup", data={"email": "c@example.com"})
    first_code = _get_code(outbox)

    with mail.record_messages() as outbox2:
        client.post("/verify/resend", follow_redirects=True)
    second_code = _get_code(outbox2)

    resp = client.post("/verify", data={"code": first_code}, follow_redirects=True)
    assert b"Incorrect code" in resp.data or b"expired" in resp.data

    resp = client.post("/verify", data={"code": second_code}, follow_redirects=True)
    assert b"verified" in resp.data.lower()


def test_logout_clears_session(client, app):
    with mail.record_messages() as outbox:
        client.post("/signup", data={"email": "d@example.com"})
    code = _get_code(outbox)
    client.post("/verify", data={"code": code})

    client.post("/logout", follow_redirects=True)
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_signin_code_is_valid_for_30_minutes(client, app):
    from datetime import timedelta

    from app.utils import utcnow

    with mail.record_messages() as outbox:
        client.post("/signup", data={"email": "ttl@example.com"})
    assert "30 minutes" in outbox[0].body
    with app.app_context():
        user = User.query.filter_by(email_hash=hash_email("ttl@example.com")).first()
        remaining = user.code_expires_at - utcnow()
        assert timedelta(minutes=29) < remaining <= timedelta(minutes=30)
