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

"""Outgoing email and email-domain checks.

Sends the sign-in and account-removal codes, and verifies at signup that an
address's domain publishes an MX record.
"""

import dns.exception
import dns.name
import dns.resolver
from flask import current_app
from flask_babel import gettext as _, ngettext
from flask_mail import Message

from app import mail
from app.utils import DELETE_CODE_TTL_MINUTES, SIGNIN_CODE_TTL_MINUTES


def send_verification_email(email, code):
    """Email the sign-in `code` to `email`.

    The code is also logged, so it can be read from the console when sending is
    suppressed (development).
    """
    message = Message(
        # NOTE: The email subject; the code is at the end, with no full stop, so it can be copied.
        subject=_("Your verification code is %(code)s", code=code),
        recipients=[email],
        body=ngettext(
            "Your verification code is %(code)s.\n\n"
            "It expires in %(num)d minute. If you didn't request this, ignore this email.",
            "Your verification code is %(code)s.\n\n"
            "It expires in %(num)d minutes. If you didn't request this, ignore this email.",
            SIGNIN_CODE_TTL_MINUTES,
            code=code,
        ),
    )
    mail.send(message)
    current_app.logger.info("Verification code for %s: %s", email, code)


def send_deletion_email(email, code):
    """Email the account-removal confirmation `code` to `email`."""
    message = Message(
        subject=_("Confirm removal of your data"),
        recipients=[email],
        body=ngettext(
            "Your confirmation code is %(code)s.\n\n"
            "Entering it will permanently delete your account and all your "
            "weight data. It expires in %(num)d minute. If you didn't request "
            "this, ignore this email and your data stays untouched.",
            "Your confirmation code is %(code)s.\n\n"
            "Entering it will permanently delete your account and all your "
            "weight data. It expires in %(num)d minutes. If you didn't request "
            "this, ignore this email and your data stays untouched.",
            DELETE_CODE_TTL_MINUTES,
            code=code,
        ),
    )
    mail.send(message)
    current_app.logger.info("Data removal code for %s: %s", email, code)


class MxCheckError(Exception):
    """The domain can't receive mail (`temporary` is False) or we couldn't
    tell because DNS was unreachable (`temporary` is True)."""

    def __init__(self, message, temporary=False):
        super().__init__(message)
        self.temporary = temporary


def check_mx(email):
    """Raise MxCheckError unless the email's domain publishes a usable MX
    record. A "null MX" (a single record pointing at ".", RFC 7505) means
    the domain explicitly accepts no mail, so it counts as missing."""
    no_mx = _("That email domain doesn't accept mail (no MX record).")
    try_again = _("Couldn't check that email domain right now. Try again.")
    domain = email.rsplit("@", 1)[-1].strip().rstrip(".")
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.name.NameTooLong, dns.name.EmptyLabel) as exc:
        raise MxCheckError(no_mx) from exc
    except (dns.exception.Timeout, dns.resolver.NoNameservers) as exc:
        raise MxCheckError(try_again, temporary=True) from exc

    if not any(str(r.exchange).rstrip(".") for r in answers):
        raise MxCheckError(no_mx)
