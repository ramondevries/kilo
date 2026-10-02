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

"""Tests for the git-based version shown on the About page."""

import os
import re
import subprocess

import pytest

from app.version import app_version, read_version

COMMIT_DATE = "2026-03-04T12:00:00+00:00"


def _git(repo, *args):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_AUTHOR_DATE": COMMIT_DATE, "GIT_COMMITTER_DATE": COMMIT_DATE,
    }
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "f.txt").write_text("x")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_untagged_checkout_uses_the_7_character_commit_id(repo):
    version = read_version(repo)
    assert re.fullmatch(r"[0-9a-f]{7}", version["commit"])
    assert version["tag"] is None
    assert version["label"] == version["commit"]
    assert version["date"] == "2026-03-04"


def test_tagged_checkout_uses_the_tag(repo):
    _git(repo, "tag", "v1.2.0")
    version = read_version(repo)
    assert version["tag"] == "v1.2.0"
    assert version["label"] == "v1.2.0"
    assert re.fullmatch(r"[0-9a-f]{7}", version["commit"])


def test_newest_tag_wins_when_several_point_at_the_commit(repo):
    _git(repo, "tag", "v1.9.0")
    _git(repo, "tag", "v1.10.0")
    assert read_version(repo)["tag"] == "v1.10.0"


def test_no_version_outside_a_git_repository(tmp_path):
    assert read_version(tmp_path) is None


def test_about_page_shows_the_version(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.app_version",
        lambda: {"commit": "abc1234", "tag": None, "date": "2026-10-01", "label": "abc1234"},
    )
    html = client.get("/about").data.decode()
    assert "abc1234" in html
    assert "committed Oct 1, 2026" in html  # the date is formatted for the locale
    assert "/commit/abc1234" in html


def test_about_page_links_the_tag_when_there_is_one(client, monkeypatch):
    monkeypatch.setattr(
        "app.auth.app_version",
        lambda: {"commit": "abc1234", "tag": "v2.0", "date": "2026-10-01", "label": "v2.0"},
    )
    html = client.get("/about").data.decode()
    assert "/releases/tag/v2.0" in html
    assert "/commit/abc1234" not in html


def test_about_page_still_renders_without_a_version(client, monkeypatch):
    monkeypatch.setattr("app.auth.app_version", lambda: None)
    resp = client.get("/about")
    assert resp.status_code == 200
    assert b"Version" not in resp.data


def test_this_checkout_has_a_version():
    version = app_version()
    assert version is None or re.fullmatch(r"[0-9a-f]{7}", version["commit"])
