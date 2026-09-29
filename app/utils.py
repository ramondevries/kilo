import hashlib
from datetime import UTC, datetime

KG_PER_LB = 0.45359237


def normalize_email(email):
    return email.strip().lower()


def hash_email(email):
    """SHA-256 of the normalized email — matches Gravatar's hash spec
    (https://docs.gravatar.com/rest/hash/) so it doubles as the avatar id."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def to_kg(value, unit):
    return value * KG_PER_LB if unit == "lb" else value


def from_kg(value_kg, unit):
    return value_kg / KG_PER_LB if unit == "lb" else value_kg


def utcnow():
    # Naive UTC, matching the naive DateTime columns stored in SQLite.
    return datetime.now(UTC).replace(tzinfo=None)
