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

"""Cache lifetimes of static files (app/__init__.py): a file linked by its static_url() address
(`?v=<mtime>`) is kept by the browser for a year, everything else is checked again each time.
"""

import re
import time

import pytest

from app import VERSIONED_STATIC_MAX_AGE, db
from app.models import User

YEAR = int(VERSIONED_STATIC_MAX_AGE.total_seconds())


def _static_links(page):
    return re.findall(r'(?:src|href|data-light|data-dark)="(/static/[^"]*)"', page)


def test_a_versioned_static_file_is_cached_for_a_year(client):
    page = client.get("/").get_data(as_text=True)
    [style] = [link for link in _static_links(page) if link.startswith("/static/style.css")]
    response = client.get(style)
    assert response.status_code == 200
    assert response.cache_control.public
    assert response.cache_control.max_age == YEAR
    assert response.cache_control.immutable
    assert not response.cache_control.no_cache
    assert response.expires.timestamp() == pytest.approx(time.time() + YEAR, abs=60)


def test_a_304_for_a_versioned_file_keeps_the_year(client):
    first = client.get("/static/style.css?v=1")
    again = client.get("/static/style.css?v=1", headers={"If-None-Match": first.headers["ETag"]})
    assert again.status_code == 304
    assert again.cache_control.max_age == YEAR


def test_an_unversioned_static_address_is_checked_again_each_time(client):
    response = client.get("/static/kilo-og.png")
    assert response.status_code == 200
    assert response.cache_control.no_cache
    assert response.cache_control.max_age is None
    assert response.expires is None


def test_a_missing_file_is_not_cached(client):
    response = client.get("/static/no-such-file.css?v=1")
    assert response.status_code == 404
    assert response.cache_control.max_age is None


def test_other_pages_with_a_v_parameter_are_not_cached(client):
    assert client.get("/about?v=1").cache_control.max_age is None


@pytest.fixture
def every_page(logged_in_client, app):
    """The HTML of every kind of page: signed out, signed in, settings and a public chart."""
    client, user_id = logged_in_client
    with app.app_context():
        user = db.session.get(User, user_id)
        user.public_enabled, user.public_id = True, "shared"
        db.session.commit()
    pages = [client.get(path).get_data(as_text=True) for path in ("/", "/settings", "/public/shared")]
    client.post("/logout")
    pages += [client.get(path).get_data(as_text=True) for path in ("/", "/about", "/signup")]
    return pages


def test_every_static_file_a_page_links_is_versioned(every_page):
    """So a deploy can never leave a browser with an old script or style sheet for a year."""
    links = [link for page in every_page for link in _static_links(page)]
    assert len(links) > 20
    assert [link for link in links if not re.search(r"\?v=\d+$", link)] == []
