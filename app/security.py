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

"""Who is asking, and a security log that fail2ban can read.

`client_ip()` finds the visitor's address behind the reverse proxy, and
`log_event()` writes one line per suspicious request (an unknown page, a wrong
sign-in code) to a log file of its own, with a fixed format::

    2026-10-05 15:30:00 kilo-notfound ip=203.0.113.9 path=/.env
    2026-10-05 15:31:12 kilo-auth ip=203.0.113.9 event=code-wrong

The file is set with SECURITY_LOG_FILE (see the README); without it nothing is
written. Nothing here changes what a visitor sees. Only the address and the
event are logged, never an email address, a code or a hash.
"""

import ipaddress
import logging
from logging.handlers import WatchedFileHandler
from urllib.parse import quote

from flask import request

LOGGER_NAME = "kilo.security"

# A free-text field (a path) is cut to this many characters before it is logged.
MAX_FIELD_LENGTH = 200

_HANDLER_MARK = "_kilo_security_handler"


def _parse_ip(text):
    """An `ipaddress` object for `text`, or None. IPv4-mapped IPv6 addresses become IPv4."""
    try:
        address = ipaddress.ip_address((text or "").strip())
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address


def client_ip():
    """The visitor's address as text, or None when it can't be told.

    Behind Apache or nginx the connection itself always comes from 127.0.0.1, and the
    proxy passes the real address in `X-Real-IP` (it overwrites whatever the visitor
    sent, see the README). That header is believed ONLY when the connection comes
    from the loopback interface: anyone else could send a forged one. A missing or
    unusable header gives None, never "127.0.0.1", so that everyone is not lumped
    together as one visitor.
    """
    remote = _parse_ip(request.remote_addr)
    if remote is None:
        return None
    if not remote.is_loopback:
        return remote.compressed  # a direct connection: headers are not trusted
    forwarded = _parse_ip(request.headers.get("X-Real-IP"))
    if forwarded is None or forwarded.is_loopback or forwarded.is_unspecified:
        return None
    return forwarded.compressed


def _clean(value):
    """A value as one safe token for a log line.

    Anything a visitor controls (a path can contain a decoded newline) is percent-encoded
    and cut short, so it cannot start a new line or add an `ip=` field: such a forged
    line could get an innocent address banned. The visitor's own text is always last.
    """
    return quote(str(value)[:MAX_FIELD_LENGTH], safe="/:@.,-_~")


def log_event(kind, **fields):
    """Write `kilo-<kind> ip=<address or -> name=value ...` to the security log.

    `kind` and the field names come from the code, the values may come from the visitor.
    """
    parts = [f"kilo-{kind}", f"ip={client_ip() or '-'}"]
    parts += [f"{name}={_clean(value)}" for name, value in fields.items()]
    logging.getLogger(LOGGER_NAME).info(" ".join(parts))


def init_app(app):
    """Send the security log to SECURITY_LOG_FILE, or nowhere when that is not set.

    The file is reopened by itself after logrotate has moved it. A file that cannot be
    opened (no permission) is reported once in the application log and does not stop
    the app. Called for every app that is created, so an earlier handler is replaced.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    for handler in [h for h in logger.handlers if getattr(h, _HANDLER_MARK, False)]:
        logger.removeHandler(handler)
        handler.close()

    path = app.config.get("SECURITY_LOG_FILE")
    # With a file the lines go only there; without one they stay with the normal logging.
    logger.propagate = not path
    if not path:
        return
    try:
        handler = WatchedFileHandler(path, encoding="utf-8")
    except OSError as error:
        logger.propagate = True
        app.logger.warning("Cannot write the security log %s: %s", path, error)
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    setattr(handler, _HANDLER_MARK, True)
    logger.addHandler(handler)
