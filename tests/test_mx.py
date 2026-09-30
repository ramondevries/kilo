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

"""Tests for the signup MX-record check, using a stubbed DNS resolver."""

import dns.exception
import dns.name
import dns.resolver
import pytest

from app import mail
from app.email_utils import MxCheckError, check_mx


class _Record:
    def __init__(self, exchange):
        self.exchange = dns.name.from_text(exchange)


@pytest.fixture
def mx_on(app, monkeypatch):
    app.config["CHECK_EMAIL_MX"] = True

    def fake_resolve(domain, rdtype, **kwargs):
        assert rdtype == "MX"
        if domain == "good-mx.com":
            return [_Record("mail.good-mx.com.")]
        if domain == "nullmx-mx.com":
            return [_Record(".")]
        if domain == "nomx-mx.com":
            raise dns.resolver.NoAnswer()
        if domain == "slow-mx.com":
            raise dns.exception.Timeout()
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(dns.resolver, "resolve", fake_resolve)


def test_check_mx_accepts_domain_with_mx(mx_on):
    check_mx("me@good-mx.com")


@pytest.mark.parametrize("email", ["me@nullmx-mx.com", "me@nomx-mx.com", "me@missing-mx.com"])
def test_check_mx_rejects_domains_without_usable_mx(mx_on, email):
    with pytest.raises(MxCheckError) as exc:
        check_mx(email)
    assert not exc.value.temporary


def test_check_mx_flags_dns_timeout_as_temporary(mx_on):
    with pytest.raises(MxCheckError) as exc:
        check_mx("me@slow-mx.com")
    assert exc.value.temporary


def test_signup_with_mx_domain_sends_code(client, mx_on):
    with mail.record_messages() as outbox:
        resp = client.post("/signup", data={"email": "me@good-mx.com"})
    assert resp.status_code == 302
    assert len(outbox) == 1


def test_signup_without_mx_is_rejected_and_sends_nothing(client, mx_on):
    with mail.record_messages() as outbox:
        resp = client.post("/signup", data={"email": "me@nomx-mx.com"})
    assert resp.status_code == 200
    assert b"no MX record" in resp.data
    assert outbox == []


def test_signup_reports_temporary_dns_failure(client, mx_on):
    with mail.record_messages() as outbox:
        resp = client.post("/signup", data={"email": "me@slow-mx.com"})
    assert b"Try again" in resp.data
    assert outbox == []


def test_mx_check_can_be_disabled(client, app, mx_on):
    app.config["CHECK_EMAIL_MX"] = False
    with mail.record_messages() as outbox:
        client.post("/signup", data={"email": "me@missing-mx.com"})
    assert len(outbox) == 1
