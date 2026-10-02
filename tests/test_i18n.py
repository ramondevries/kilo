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

"""Tests for language selection (app/i18n.py)."""

import re

import pytest


def html_lang(response):
    return re.search(r'<html lang="([^"]*)"', response.get_data(as_text=True)).group(1)


@pytest.mark.parametrize(
    "header, expected",
    [
        (None, "en"),
        ("nl-BE,nl;q=0.9", "nl"),
        ("pt-PT", "pt"),
        ("pt-BR,pt;q=0.9,en;q=0.5", "pt"),
        ("ja", "en"),
        ("ja,fr;q=0.8", "fr"),
        ("de-CH,fr;q=0.5", "de"),
        ("fr;q=0.5,es;q=0.9", "es"),
        ("*", "en"),
    ],
)
def test_accept_language(client, header, expected):
    headers = {"Accept-Language": header} if header else {}
    assert html_lang(client.get("/", headers=headers)) == expected


def test_lang_query_overrides_header(client):
    response = client.get("/?lang=de", headers={"Accept-Language": "nl"})
    assert html_lang(response) == "de"


def test_invalid_lang_query_is_ignored(client):
    response = client.get("/?lang=xx", headers={"Accept-Language": "nl"})
    assert html_lang(response) == "nl"


def test_lang_query_is_not_persisted(client):
    client.get("/?lang=de")
    assert html_lang(client.get("/")) == "en"


def _log_weight(client, weight="72.5"):
    from datetime import date

    client.post("/entries/field", json={"date": date.today().isoformat(), "weight": weight, "confirm": True})


@pytest.mark.parametrize(
    "lang, shown, input_value",
    [("en", "72.5 kg", 'value="72.5"'), ("nl", "72,5 kg", 'value="72,5"'), ("de", "72,5 kg", 'value="72,5"')],
)
def test_weights_are_formatted_for_the_locale(logged_in_client, lang, shown, input_value):
    client, _user_id = logged_in_client
    _log_weight(client)
    html = client.get(f"/?lang={lang}").get_data(as_text=True)
    assert shown in html
    assert input_value in html


def test_french_unit_uses_a_narrow_no_break_space(logged_in_client):
    client, _user_id = logged_in_client
    _log_weight(client)
    assert "72,5\u202fkg" in client.get("/?lang=fr").get_data(as_text=True)


def test_dates_are_formatted_for_the_locale(logged_in_client):
    from datetime import date

    client, _user_id = logged_in_client
    _log_weight(client)
    today = date.today()
    html_en = client.get("/?lang=en").get_data(as_text=True)
    html_de = client.get("/?lang=de").get_data(as_text=True)
    assert f"{today:%b} {today.day}, {today.year}" in html_en
    assert f"{today.day:02d}.{today.month:02d}.{today.year}" in html_de


def test_pages_render_in_every_supported_language(logged_in_client, app):
    client, _user_id = logged_in_client
    _log_weight(client)
    for lang in app.config["SUPPORTED_LANGUAGES"]:
        for path in ("/", "/settings", "/settings/remove", "/about"):
            response = client.get(f"{path}?lang={lang}")
            assert response.status_code == 200, (lang, path)
            assert html_lang(response) == lang


@pytest.mark.parametrize("lang, shown", [("en", 'value="186.0"'), ("nl", 'value="186,0"'), ("de", 'value="186,0"')])
def test_settings_shows_the_stored_height_in_the_locale(logged_in_client, lang, shown):
    client, _user_id = logged_in_client
    client.post("/settings", data={"height_value": "186", "height_unit": "cm"})
    assert shown in client.get(f"/settings?lang={lang}").get_data(as_text=True)


def test_settings_keeps_what_was_typed_when_the_form_is_rejected(logged_in_client):
    client, _user_id = logged_in_client
    html = client.post("/settings", data={"height_value": "18,5", "height_unit": "cm"}).get_data(as_text=True)
    assert 'value="18,5"' in html


def test_dutch_browser_gets_dutch_pages(client):
    html = client.get("/", headers={"Accept-Language": "nl-BE,nl;q=0.9"}).get_data(as_text=True)
    assert 'lang="nl"' in html
    assert "Inloggen" in html
    assert "Sign in" not in html
    assert "Enter your email" not in html


def test_unsupported_language_falls_back_to_english(client):
    html = client.get("/", headers={"Accept-Language": "ja"}).get_data(as_text=True)
    assert 'lang="en"' in html
    assert "Sign in" in html


def test_lang_query_translates_the_page(client):
    assert "Anmelden" in client.get("/?lang=de").get_data(as_text=True)


@pytest.mark.parametrize(
    "lang, count, expected",
    [
        ("fr", 0, "Variation sur 0 jour"),  # French uses the singular for 0
        ("fr", 1, "Variation sur 1 jour"),
        ("fr", 2, "Variation sur 2 jours"),
        ("pt", 0, "Variação em 0 dia"),  # so does Brazilian Portuguese
        ("pt", 2, "Variação em 2 dias"),
        ("nl", 0, "Verandering in 0 dagen"),
        ("nl", 1, "Verandering in 1 dag"),
        ("de", 1, "Änderung in 1 Tag"),
        ("de", 7, "Änderung in 7 Tagen"),
        ("es", 1, "Cambio en 1 día"),
        ("it", 2, "Variazione in 2 giorni"),
    ],
)
def test_plural_forms(app, lang, count, expected):
    from flask_babel import ngettext

    with app.test_request_context(f"/?lang={lang}"):
        assert ngettext("%(num)d-day change", "%(num)d-day change", count) == expected


def test_every_language_has_a_catalog(app):
    import os

    for lang in app.config["SUPPORTED_LANGUAGES"]:
        if lang == "en":
            continue
        assert os.path.exists(f"translations/{lang}/LC_MESSAGES/messages.po"), lang
        assert os.path.exists(f"translations/{lang}/LC_MESSAGES/messages.mo"), lang


def test_emails_are_sent_in_the_request_language(client):
    from app import mail

    with mail.record_messages() as outbox:
        client.post("/signup?lang=nl", data={"email": "someone@example.com"})
    assert outbox[0].subject == "Je verificatiecode"
    assert "verloopt over 30 minuten" in outbox[0].body


def test_flash_messages_are_translated(client):
    client.post("/signup?lang=fr", data={"email": "someone@example.com"})
    html = client.get("/verify?lang=fr").get_data(as_text=True)
    assert "Nous avons envoyé un code de vérification à someone@example.com." in html


ALL_LANGUAGES = ["en", "nl", "fr", "es", "pt", "de", "it", "id", "pl", "ro", "hu", "da", "fi", "sv", "nb"]


@pytest.mark.parametrize("lang", ALL_LANGUAGES)
@pytest.mark.parametrize("typed", ["72,5", "72.5", " 72,5 ", "72.50"])
def test_comma_and_point_weights_save_as_72_5_in_every_language(logged_in_client, lang, typed):
    from app.models import WeightEntry

    client, _user_id = logged_in_client
    response = client.post(
        "/entries/field",
        json={"date": "2026-01-01", "weight": typed, "confirm": True},
        headers={"Accept-Language": lang},
    )
    assert response.status_code == 200
    assert WeightEntry.query.one().weight == 72.5


@pytest.mark.parametrize("lang", ALL_LANGUAGES)
@pytest.mark.parametrize("typed", ["1,8", "1.8"])
def test_comma_and_point_heights_save_the_same_in_every_language(logged_in_client, lang, typed):
    from app import db
    from app.models import User

    client, user_id = logged_in_client
    response = client.post(
        "/settings", data={"height_value": typed, "height_unit": "m"}, headers={"Accept-Language": lang}
    )
    assert response.status_code == 302
    assert db.session.get(User, user_id).height_cm == pytest.approx(180)


@pytest.mark.parametrize("lang", ALL_LANGUAGES)
def test_errors_are_in_the_request_language_but_the_status_is_the_same(logged_in_client, lang):
    client, _user_id = logged_in_client
    response = client.post(
        "/entries/field",
        json={"date": "2026-01-01", "weight": "1,234.5"},
        headers={"Accept-Language": lang},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]


@pytest.mark.parametrize(
    "lang, columns, day_pattern",
    [
        ("nl", "datum,gewicht,notitie", "d-M-jj"),
        ("fr", "date,poids,note", "j-M-aa"),
        ("es", "fecha,peso,nota", "d-M-aa"),
        ("pt", "data,peso,nota", "d-M-aa"),
        ("de", "Datum,Gewicht,Notiz", "T-M-JJ"),
        ("it", "data,peso,nota", "g-M-aa"),
        ("id", "tanggal,berat,catatan", "h-B-tt"),
        ("pl", "data,waga,notatka", "d-M-rr"),
        ("ro", "data,greutate,notă", "z-L-aa"),
        ("hu", "dátum,súly,jegyzet", "n-H-éé"),
        ("da", "dato,vægt,note", "d-M-åå"),
        ("fi", "päivämäärä,paino,muistiinpano", "p-K-vv"),
        ("sv", "datum,vikt,anteckning", "d-M-åå"),
        ("nb", "dato,vekt,notat", "d-M-åå"),
    ],
)
def test_the_csv_legend_on_the_import_page_is_translated(logged_in_client, lang, columns, day_pattern):
    client, _user_id = logged_in_client
    html = client.get(f"/settings?lang={lang}").get_data(as_text=True)
    assert f"<code>{columns}</code>" in html
    assert f"<code>{day_pattern}</code>" in html
    assert "<code>date,weight,note</code>" not in html
    assert "<code>d-M-yy</code>" not in html


@pytest.mark.parametrize("lang", ALL_LANGUAGES)
def test_the_csv_file_is_the_same_in_every_language(logged_in_client, lang):
    import io

    from app.models import WeightEntry

    client, _user_id = logged_in_client
    response = client.post(
        "/settings/import",
        data={"csv_file": (io.BytesIO(b"23-9-26,79.7,some text\n24-9-2026,80.5,\n"), "weights.csv")},
        content_type="multipart/form-data",
        headers={"Accept-Language": lang},
    )
    assert response.status_code == 302
    assert sorted(entry.weight for entry in WeightEntry.query.all()) == [79.7, 80.5]
    export = client.get("/settings/export", headers={"Accept-Language": lang}).get_data(as_text=True)
    assert export.splitlines() == ["23-9-26,79.7,some text", "24-9-26,80.5,"]


def test_the_line_format_error_names_the_columns_in_the_request_language(app):
    from app.csv_io import parse_csv

    with app.test_request_context("/?lang=nl"):
        _rows, errors = parse_csv("only-one-column\n")
    assert errors == ["regel 1: verwacht datum,gewicht[,notitie]"]


@pytest.mark.parametrize(
    "header, expected",
    [
        ("nb", "nb"),
        ("nb-NO,nb;q=0.9", "nb"),
        ("no", "nb"),  # browsers also send "no" and "nn" for Norwegian
        ("nn-NO", "nb"),
        ("id-ID", "id"),
        ("pl-PL,pl;q=0.9,en;q=0.5", "pl"),
        ("ro-RO", "ro"),
        ("hu", "hu"),
        ("da-DK", "da"),
        ("fi-FI", "fi"),
        ("sv-SE,sv;q=0.9", "sv"),
        ("ja,no;q=0.8", "nb"),
    ],
)
def test_the_new_languages_are_matched_on_the_primary_subtag(client, header, expected):
    assert html_lang(client.get("/", headers={"Accept-Language": header})) == expected


@pytest.mark.parametrize("override, expected", [("no", "nb"), ("nn", "nb"), ("nb", "nb"), ("pl-PL", "pl"), ("sv", "sv")])
def test_lang_query_accepts_aliases_and_full_tags(client, override, expected):
    assert html_lang(client.get(f"/?lang={override}")) == expected


@pytest.mark.parametrize(
    "lang, count, expected",
    [
        # Polish has three forms: 1, 2-4 (not 12-14), everything else
        ("pl", 1, "Zmiana (1 dzień)"),
        ("pl", 2, "Zmiana (2 dni)"),
        ("pl", 5, "Zmiana (5 dni)"),
        ("pl", 12, "Zmiana (12 dni)"),
        ("pl", 22, "Zmiana (22 dni)"),
        ("pl", 0, "Zmiana (0 dni)"),
        # so does Romanian: 1, 0 and 2-19, 20 and up ("de zile")
        ("ro", 1, "Schimbare în 1 zi"),
        ("ro", 0, "Schimbare în 0 zile"),
        ("ro", 2, "Schimbare în 2 zile"),
        ("ro", 19, "Schimbare în 19 zile"),
        ("ro", 20, "Schimbare în 20 de zile"),
        ("ro", 101, "Schimbare în 101 zile"),
        ("ro", 120, "Schimbare în 120 de zile"),
        # Indonesian has no plural forms
        ("id", 0, "Perubahan 0 hari"),
        ("id", 1, "Perubahan 1 hari"),
        ("id", 7, "Perubahan 7 hari"),
        # the two-form languages
        ("da", 1, "Ændring på 1 dag"),
        ("da", 7, "Ændring på 7 dage"),
        ("sv", 1, "Förändring på 1 dag"),
        ("sv", 7, "Förändring på 7 dagar"),
        ("nb", 1, "Endring på 1 dag"),
        ("nb", 7, "Endring på 7 dager"),
        ("fi", 1, "1 päivän muutos"),
        ("fi", 7, "7 päivän muutos"),
        ("hu", 1, "1 napos változás"),
        ("hu", 7, "7 napos változás"),
    ],
)
def test_plural_forms_of_the_new_languages(app, lang, count, expected):
    from flask_babel import ngettext

    with app.test_request_context(f"/?lang={lang}"):
        assert ngettext("%(num)d-day change", "%(num)d-day change", count) == expected


def test_the_new_languages_format_numbers_and_dates_their_own_way(logged_in_client):
    from datetime import date

    client, _user_id = logged_in_client
    client.post("/entries/field", json={"date": date.today().isoformat(), "weight": "72,5", "confirm": True})
    for lang in ("id", "pl", "ro", "hu", "da", "fi", "sv", "nb"):
        html = client.get(f"/?lang={lang}").get_data(as_text=True)
        assert 'value="72,5"' in html, lang  # all of them write a decimal comma
        assert "72,5 kg" in html or "72,5 kg" in html, lang
