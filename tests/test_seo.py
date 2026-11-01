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

"""What search engines and link previews read: the sitemap, the description and Open Graph tags of
the two indexable pages (templates/_meta.html), the JSON-LD on the front page, the preview picture,
and `noindex` on the pages that should never be in a search result.

The front page's own text and title are tested in test_routes.py; robots.txt there too.
"""

import html
import json
import re
import struct
from xml.etree import ElementTree

import pytest

from app import db
from app.models import User
from app.routes import OG_IMAGE
from tests.conftest import ROOT, sign_up
from tests.test_errors import BROWSER

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _meta(page, attr, name):
    """The content of every <meta {attr}="{name}"> in the page, unescaped."""
    return [html.unescape(m) for m in re.findall(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', page)]


def test_the_sitemap_lists_the_two_indexable_pages_as_absolute_addresses(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    root = ElementTree.fromstring(response.data)
    assert root.tag == f"{SITEMAP_NS}urlset"
    assert [loc.text for loc in root.iter(f"{SITEMAP_NS}loc")] == ["http://localhost/", "http://localhost/about"]


def test_the_sitemap_needs_no_sign_in(logged_in_client):
    client, _ = logged_in_client
    assert client.get("/sitemap.xml").status_code == 200


@pytest.mark.parametrize("path", ["/", "/about"])
def test_the_indexable_pages_have_a_description_and_a_link_preview(client, path):
    page = client.get(path).get_data(as_text=True)
    title = html.unescape(re.search(r"<title>([^<]*)</title>", page).group(1))
    [description] = _meta(page, "name", "description")
    assert len(description) > 50
    assert _meta(page, "property", "og:title") == [title]
    assert _meta(page, "property", "og:description") == [description]
    assert _meta(page, "property", "og:url") == [f"http://localhost{path}"]
    assert _meta(page, "property", "og:image") == [f"http://localhost/static/{OG_IMAGE}"]
    assert _meta(page, "property", "og:image:alt") == ["Weight chart"]
    assert _meta(page, "name", "twitter:card") == ["summary_large_image"]
    assert _meta(page, "name", "robots") == []


def test_the_link_preview_is_in_the_visitors_language(client):
    page = client.get("/about?lang=nl").get_data(as_text=True)
    assert _meta(page, "property", "og:title") == ["Over — Kilo Tracker"]
    assert _meta(page, "property", "og:description")[0].startswith("Waarom Kilo Tracker is gemaakt")


def test_the_preview_picture_is_a_1200_by_630_png_that_is_served(client):
    path = ROOT / "app" / "static" / OG_IMAGE
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (1200, 630)  # the IHDR chunk's width and height
    assert len(data) < 300_000  # small enough for a preview fetch
    assert client.get(f"/static/{OG_IMAGE}").status_code == 200


def test_the_front_page_describes_kilo_as_a_free_web_app_for_search_engines(client):
    page = client.get("/").get_data(as_text=True)
    [data] = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    facts = json.loads(data)
    assert facts["@type"] == "WebApplication"
    assert facts["name"] == "Kilo Tracker"
    assert facts["url"] == "http://localhost/"
    assert facts["description"] == _meta(page, "name", "description")[0]
    assert facts["offers"]["price"] == "0"


def test_the_signed_in_dashboard_has_no_search_tags(logged_in_client):
    client, _ = logged_in_client
    page = client.get("/").get_data(as_text=True)
    assert "ld+json" not in page
    assert _meta(page, "property", "og:title") == []


def _noindex(page):
    return _meta(page, "name", "robots") == ["noindex"]


def test_the_sign_up_and_code_pages_are_kept_out_of_search(client):
    assert _noindex(client.get("/signup").get_data(as_text=True))
    response, _ = sign_up(client, "someone@example.com")
    assert "Enter your code" in response.get_data(as_text=True)
    assert _noindex(response.get_data(as_text=True))


def test_the_remove_data_page_is_kept_out_of_search(logged_in_client):
    client, _ = logged_in_client
    assert _noindex(client.get("/settings/remove").get_data(as_text=True))


def test_the_error_page_is_kept_out_of_search(app):
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/boom")
    def boom():
        raise RuntimeError("an unexpected bug")

    response = app.test_client().get("/boom", headers=BROWSER)
    assert response.status_code == 500
    assert _noindex(response.get_data(as_text=True))


def test_the_public_chart_has_neither_search_nor_preview_tags(client, app):
    with app.app_context():
        db.session.add(User(email_hash="a" * 64, public_enabled=True, public_id="shared"))
        db.session.commit()
    page = client.get("/public/shared").get_data(as_text=True)
    assert _meta(page, "name", "description") == []
    assert _meta(page, "property", "og:image") == []
