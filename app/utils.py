# Kilo Tracker - a small weight-tracking web app.
# Copyright (C) 2026 Ramón de Vries <ramon@11tools.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See the LICENSE file for the full text.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

"""Small shared helpers: email hashing, decimal validation, code lifetimes and UTC time."""

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
    """Trim and lowercase an email so equivalent addresses hash the same."""
    return email.strip().lower()


def hash_email(email):
    """SHA-256 of the normalized email — matches Gravatar's hash spec
    (https://docs.gravatar.com/rest/hash/) so it doubles as the avatar id."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def utcnow():
    """Current UTC time as a naive datetime (matches the naive DateTime columns in SQLite)."""
    # Naive UTC, matching the naive DateTime columns stored in SQLite.
    return datetime.now(UTC).replace(tzinfo=None)
