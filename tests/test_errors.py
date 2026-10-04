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

"""Tests for the friendly error handling in app/errors.py: CSRF failures and missing pages."""

import html as html_lib
import re

import pytest

from app.models import WeightEntry

BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
EXPIRED = "Your session has expired and nothing was changed. Please try again."
EXPIRED_JSON = "Your session has expired. Reload the page and try again."
NOT_AVAILABLE = "That page isn't available, so you were taken to the start page."


@pytest.fixture
def csrf_on(app):
    """Turn CSRF protection on (the shared fixtures run with it off)."""
    app.config["WTF_CSRF_ENABLED"] = True
    return app


def csrf_token(client):
    html = client.get("/").get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def flashes(html):
    """The error flashes on a page, as the visitor reads them (HTML entities decoded)."""
    return [html_lib.unescape(text) for text in re.findall(r'class="flash flash-error">([^<]+)<', html)]


# ---- CSRF: forms ------------------------------------------------------------


def test_a_form_without_a_token_goes_back_with_a_message(client, csrf_on):
    response = client.post(
        "/signup", data={"email": "a@example.com"}, headers={"Referer": "http://localhost/signup?lang=nl"}
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/signup?lang=nl"
    assert EXPIRED in flashes(client.get("/signup").get_data(as_text=True))


def test_nothing_is_changed_when_the_token_is_refused(client, csrf_on):
    from app.models import User

    client.post("/signup", data={"email": "a@example.com"})
    assert User.query.count() == 0


def test_an_expired_token_gets_the_same_friendly_answer(client, csrf_on):
    token = csrf_token(client)
    csrf_on.config["WTF_CSRF_TIME_LIMIT"] = -1  # every token is now too old
    response = client.post("/signup", data={"email": "a@example.com", "csrf_token": token})
    assert response.status_code == 302
    assert EXPIRED in flashes(client.get("/").get_data(as_text=True))


def test_a_valid_token_still_works(client, csrf_on):
    token = csrf_token(client)
    response = client.post("/signup", data={"email": "a@example.com", "csrf_token": token})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify")


@pytest.mark.parametrize(
    "referrer",
    [
        None,
        "https://evil.example/phish",
        "http://localhost.evil.example/x",  # host that merely starts like ours
        "http://localhost//evil.example",  # path that looks protocol-relative
        "javascript:alert(1)",
        "not a url",
    ],
)
def test_the_redirect_never_leaves_the_site(client, csrf_on, referrer):
    headers = {"Referer": referrer} if referrer else {}
    response = client.post("/signup", data={"email": "a@example.com"}, headers=headers)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


@pytest.mark.parametrize(
    "lang, text",
    [
        ("nl", "Je sessie is verlopen en er is niets gewijzigd. Probeer het opnieuw."),
        ("de", "Deine Sitzung ist abgelaufen und es wurde nichts geändert. Bitte versuche es erneut."),
        ("pl", "Twoja sesja wygasła i nic nie zostało zmienione. Spróbuj ponownie."),
    ],
)
def test_the_form_message_is_in_the_visitors_language(client, csrf_on, lang, text):
    client.environ_base["HTTP_ACCEPT_LANGUAGE"] = lang
    client.post("/signup", data={"email": "a@example.com"})
    assert text in flashes(client.get("/").get_data(as_text=True))


# ---- CSRF: the dashboard's background saves ---------------------------------


def test_a_refused_background_save_answers_with_json_and_a_code(logged_in_client, csrf_on):
    client, _user_id = logged_in_client
    response = client.post("/entries/field", json={"date": "2026-01-01", "weight": "80"})
    assert response.status_code == 400
    assert response.get_json() == {"error": EXPIRED_JSON, "code": "csrf_expired"}
    assert WeightEntry.query.count() == 0


def test_a_background_save_with_a_valid_token_works(logged_in_client, csrf_on):
    client, _user_id = logged_in_client
    token = csrf_token(client)
    response = client.post(
        "/entries/field",
        json={"date": "2026-01-01", "weight": "80", "confirm": True},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 200
    assert WeightEntry.query.count() == 1


def test_an_expired_token_on_a_background_save_is_reported_the_same_way(logged_in_client, csrf_on):
    client, _user_id = logged_in_client
    token = csrf_token(client)
    csrf_on.config["WTF_CSRF_TIME_LIMIT"] = -1
    response = client.post(
        "/entries/field", json={"date": "2026-01-01", "weight": "80"}, headers={"X-CSRFToken": token}
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "csrf_expired"


def test_the_json_message_is_translated(logged_in_client, csrf_on):
    client, _user_id = logged_in_client
    response = client.post(
        "/entries/field",
        json={"date": "2026-01-01", "weight": "80"},
        headers={"Accept-Language": "nl"},
    )
    assert response.get_json()["error"] == "Je sessie is verlopen. Laad de pagina opnieuw en probeer het nog eens."


def test_the_dashboard_has_a_session_expired_dialog_and_uses_it(logged_in_client):
    client, _user_id = logged_in_client
    html = client.get("/", headers={"Accept-Language": "de"}).get_data(as_text=True)
    assert 'id="session-expired-prompt"' in html
    assert "Sitzung abgelaufen" in html and "Seite neu laden" in html
    # title, text and button are all rendered by the page, so they always match its language
    assert "Deine Sitzung ist abgelaufen. Lade die Seite neu und versuche es erneut." in html
    assert html.count("data.code === 'csrf_expired'") == 2  # the row save and the "today" prompt
    assert "location.reload()" in html


# ---- missing pages ----------------------------------------------------------


@pytest.mark.parametrize("path", ["/nope", "/nope/deeper", "/settings/nope", "/about/x", "/entries"])
def test_a_missing_page_sends_a_browser_to_the_start_page(client, path):
    response = client.get(path, headers=BROWSER)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert NOT_AVAILABLE in flashes(client.get("/").get_data(as_text=True))


def test_typing_a_post_only_address_gets_the_same_treatment(client):
    for path in ("/logout", "/verify/resend", "/chart-range"):
        response = client.get(path, headers=BROWSER)
        assert response.status_code == 302, path
        assert response.headers["Location"] == "/"


def test_signed_out_visitors_land_on_the_sign_in_form(client):
    html = client.get("/nope", headers=BROWSER, follow_redirects=True).get_data(as_text=True)
    assert NOT_AVAILABLE in flashes(html)
    assert 'action="/signup"' in html


def test_signed_in_visitors_land_on_their_dashboard(logged_in_client):
    client, _user_id = logged_in_client
    html = client.get("/nope", headers=BROWSER, follow_redirects=True).get_data(as_text=True)
    assert NOT_AVAILABLE in flashes(html)
    assert 'id="weight-chart"' in html


def test_the_missing_page_message_is_translated(client):
    client.environ_base["HTTP_ACCEPT_LANGUAGE"] = "nl"
    html = client.get("/nope", headers=BROWSER, follow_redirects=True).get_data(as_text=True)
    assert "Die pagina is niet beschikbaar, daarom ben je naar de startpagina gebracht." in flashes(html)


@pytest.mark.parametrize(
    "method, path, headers",
    [
        ("get", "/nope", {}),  # curl, scripts and most bots do not ask for HTML explicitly
        ("get", "/nope", {"Accept": "application/json"}),
        ("get", "/static/missing.css", BROWSER),
        ("get", "/favicon.ico", {"Accept": "image/avif,image/webp,*/*"}),
        ("post", "/nope", BROWSER),
        ("head", "/nope", BROWSER),
    ],
)
def test_everything_else_keeps_a_plain_404(client, method, path, headers):
    assert getattr(client, method)(path, headers=headers).status_code == 404


def test_existing_pages_are_not_redirected(client):
    assert client.get("/about", headers=BROWSER).status_code == 200
    assert client.get("/robots.txt", headers=BROWSER).status_code == 200


# ---- how long a page's CSRF token stays valid ----------------------------------


def aged_token(client, app, days):
    """A valid token for the client's session, signed as if its page had been rendered `days` ago.

    Only this one signature is back-dated; patching the clock while a request runs would also
    back-date Flask's own session cookie, which is signed by the same library.
    """
    import time

    from itsdangerous import TimestampSigner, URLSafeTimedSerializer

    client.get("/")  # makes sure the session has its raw CSRF token
    with client.session_transaction() as session:
        raw = session["csrf_token"]
    serializer = URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token")
    original = TimestampSigner.get_timestamp
    TimestampSigner.get_timestamp = lambda self: int(time.time()) - int(days * 24 * 3600)
    try:
        return serializer.dumps(raw)
    finally:
        TimestampSigner.get_timestamp = original


def test_the_csrf_time_limit_is_30_days(app):
    assert app.config["WTF_CSRF_TIME_LIMIT"] == 30 * 24 * 3600


@pytest.mark.parametrize("days, accepted", [(0, True), (1, True), (29, True), (31, False), (60, False)])
def test_a_page_stays_usable_for_30_days_and_then_asks_to_reload(logged_in_client, app, csrf_on, days, accepted):
    client, _user_id = logged_in_client
    token = aged_token(client, app, days)
    response = client.post(
        "/entries/field", json={"date": "2026-01-01", "weight": "80", "confirm": True}, headers={"X-CSRFToken": token}
    )
    if accepted:
        assert response.status_code == 200
    else:
        assert response.status_code == 400 and response.get_json()["code"] == "csrf_expired"
    # only the page's token aged; the user is still signed in (reloading the page fixes it)
    assert client.get("/settings").status_code == 200
