import hashlib


def normalize_email(email):
    return email.strip().lower()


def hash_email(email):
    """SHA-256 of the normalized email — matches Gravatar's hash spec
    (https://docs.gravatar.com/rest/hash/) so it doubles as the avatar id."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()
