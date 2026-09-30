import hashlib
import re
from datetime import UTC, datetime

# A plain decimal number: digits with an optional decimal point. Stricter than
# float(), which also accepts "1e2", "1_0", "nan" and "inf".
DECIMAL_RE = re.compile(r"^(\d+(\.\d*)?|\.\d+)$")

# How long an emailed code stays valid. Deleting an account is destructive,
# so its confirmation code gets a shorter window than the sign-in code.
SIGNIN_CODE_TTL_MINUTES = 30
DELETE_CODE_TTL_MINUTES = 10


def normalize_email(email):
    return email.strip().lower()


def hash_email(email):
    """SHA-256 of the normalized email — matches Gravatar's hash spec
    (https://docs.gravatar.com/rest/hash/) so it doubles as the avatar id."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def utcnow():
    # Naive UTC, matching the naive DateTime columns stored in SQLite.
    return datetime.now(UTC).replace(tzinfo=None)
