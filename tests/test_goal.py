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

"""The goal weight: the setting and its direction, the distance and date under the current
average (overview._goal), the colours, the goal line's data and the public chart's switch."""

import json
import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app import db, overview
from app.models import User, WeightEntry
from tests.conftest import input_attrs, page_data

DAY = timedelta(days=1)
START = date(2026, 1, 1)


def goal_for(goal, moving_average, losing=None, trend_days=30, first_weight=None):
    """overview._goal for a moving average with one value per day from START (the entries are
    only the first and the last day: the first one's weight and the last one's date count)."""
    user = SimpleNamespace(goal_weight_kg=goal, goal_losing=losing, trend_days=trend_days)
    entries = [
        SimpleNamespace(entry_date=START, weight=moving_average[0] if first_weight is None else first_weight),
        SimpleNamespace(entry_date=START + (len(moving_average) - 1) * DAY, weight=moving_average[-1]),
    ]
    return overview._goal(user, entries, moving_average)


def falling(days, start=90.0, per_day=0.1):
    """A moving average going down `per_day` kg a day, `days` + 1 values."""
    return [start - per_day * i for i in range(days + 1)]


# --- the calculation --------------------------------------------------------------------------


def test_no_goal_or_no_entries_is_no_goal():
    assert goal_for(None, falling(40)) is None
    user = SimpleNamespace(goal_weight_kg=75.0, goal_losing=True, trend_days=30)
    assert overview._goal(user, [], []) is None


def test_the_date_follows_the_pace_over_the_trend_days():
    # 90.0 down to 86.0 in 40 days: 100 g a day. 11 kg to go to 75 at that pace: 110 days.
    goal = goal_for(75.0, falling(40), losing=True)
    assert goal["reached"] is False
    assert goal["to_go"] == pytest.approx(11.0)
    assert goal["date_status"] == "date"
    assert goal["date"] == (START + 40 * DAY + 110 * DAY).isoformat()


def test_the_trend_days_decide_the_pace():
    # Down 100 g a day for 40 days, then flat for the last 10: over 30 days the pace is
    # 2 kg / 30 days, over 10 days it is 0 (no date).
    average = falling(40) + [86.0] * 10
    assert goal_for(75.0, average, losing=True, trend_days=30)["date_status"] == "date"
    assert goal_for(75.0, average, losing=True, trend_days=10)["date_status"] == "no_pace"


def test_a_part_day_rounds_the_date_up():
    # 0.15 kg to go at 0.1 kg a day: 1.5 days, so the second day after the last entry.
    goal = goal_for(85.85, falling(30, start=89.0), losing=True)
    assert goal["date"] == (START + 30 * DAY + 2 * DAY).isoformat()


def test_flat_or_the_other_way_is_no_date():
    assert goal_for(75.0, [86.0] * 41, losing=True)["date_status"] == "no_pace"
    rising = [80.0 + 0.1 * i for i in range(41)]
    assert goal_for(75.0, rising, losing=True)["date_status"] == "no_pace"
    assert goal_for(75.0, rising, losing=True)["to_go"] == pytest.approx(9.0)


def test_more_than_five_years_away_is_no_date():
    # 1 g a day, 11 kg to go: 11,000 days.
    goal = goal_for(75.0, falling(40, per_day=0.001), losing=True)
    assert goal["date_status"] == "no_pace" and goal["date"] is None
    # Just inside the limit it is a date.
    slow = 11.0 / (overview.GOAL_DATE_MAX_DAYS - 1)
    assert goal_for(75.0, falling(40, start=86.0 + 40 * slow, per_day=slow), losing=True)["date_status"] == "date"


def test_fewer_days_than_the_trend_is_not_enough_data():
    # 30 days of data (31 values) are enough for a 30-day trend; 29 are not.
    assert goal_for(75.0, falling(29), losing=True, trend_days=30)["date_status"] == "short"
    assert goal_for(75.0, falling(30), losing=True, trend_days=30)["date_status"] == "date"


def test_a_goal_above_works_the_other_way_round():
    rising = [60.0 + 0.05 * i for i in range(41)]  # 50 g a day, now 62.0
    goal = goal_for(65.0, rising, losing=False)
    assert goal["to_go"] == pytest.approx(3.0)
    assert goal["date"] == (START + 40 * DAY + 60 * DAY).isoformat()
    assert goal_for(65.0, list(reversed(rising)), losing=False)["date_status"] == "no_pace"


def test_passing_the_goal_in_its_direction_is_reached():
    goal = goal_for(86.5, falling(40), losing=True)  # now 86.0
    assert goal["reached"] is True and goal["to_go"] is None and goal["date"] is None
    assert goal_for(86.0, falling(40), losing=True)["reached"] is True  # exactly at it
    assert goal_for(85.96, falling(40), losing=True)["reached"] is True  # "0.0 kg to go" is reached
    assert goal_for(85.94, falling(40), losing=True)["to_go"] == pytest.approx(0.06)
    assert goal_for(85.0, falling(40), losing=False)["reached"] is True  # gaining: above it


def test_the_saved_direction_wins_over_where_the_average_is_now():
    # Saved as losing; the average went on down past the goal: still reached, not "to go up".
    assert goal_for(87.0, falling(40), losing=True)["reached"] is True
    assert goal_for(87.0, falling(40), losing=False)["reached"] is False


def test_without_a_saved_direction_the_first_entry_decides():
    # Set before any entry: the first entry (90) was above the goal, so losing.
    assert goal_for(87.0, falling(40), losing=None)["losing"] is True
    assert goal_for(87.0, falling(40), losing=None)["reached"] is True
    assert goal_for(95.0, falling(40), losing=None)["losing"] is False


# --- the setting ------------------------------------------------------------------------------


def settings_data(**fields):
    return {"height_value": "180", "height_unit": "cm", "moving_avg_days": "1", "trend_days": "30", **fields}


def add_weights(app, user_id, weights, start=START):
    with app.app_context():
        for i, weight in enumerate(weights):
            db.session.add(WeightEntry(user_id=user_id, entry_date=start + i * DAY, weight=weight))
        db.session.commit()


def user_of(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        return SimpleNamespace(goal=user.goal_weight_kg, losing=user.goal_losing, trend_days=user.trend_days)


def test_the_settings_save_the_goal_and_the_trend_days(logged_in_client, app):
    client, user_id = logged_in_client
    response = client.post("/settings", data=settings_data(goal_weight="72,5", trend_days="14"))
    assert response.status_code == 302
    saved = user_of(app, user_id)
    assert (saved.goal, saved.trend_days) == (72.5, 14)
    page = client.get("/settings")
    assert input_attrs(page, "goal_weight")["value"] == "72.5"
    assert input_attrs(page, "trend_days")["value"] == "14"


def test_a_new_account_has_no_goal_and_a_30_day_trend(logged_in_client, app):
    client, user_id = logged_in_client
    assert (user_of(app, user_id).goal, user_of(app, user_id).trend_days) == (None, 30)
    assert input_attrs(client.get("/settings"), "trend_days")["value"] == "30"


def test_an_empty_goal_removes_it(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/settings", data=settings_data(goal_weight="75"))
    client.post("/settings", data=settings_data(goal_weight=""))
    assert user_of(app, user_id).goal is None


@pytest.mark.parametrize("goal", ["abc", "1e2", "nan", "75.5.5"])
def test_a_goal_that_is_not_a_number_is_refused(logged_in_client, app, goal):
    client, user_id = logged_in_client
    page = client.post("/settings", data=settings_data(goal_weight=goal)).data.decode()
    assert "Enter the goal as a plain number, e.g. 75 or 72.5." in page
    assert "Enter the height" not in page
    assert user_of(app, user_id).goal is None


@pytest.mark.parametrize("goal", ["0.5", "501"])
def test_a_goal_outside_the_weight_limits_is_refused(logged_in_client, app, goal):
    client, user_id = logged_in_client
    page = client.post("/settings", data=settings_data(goal_weight=goal)).data.decode()
    assert "Weight must be between 1 and 500 kg." in page
    assert user_of(app, user_id).goal is None


@pytest.mark.parametrize("days", ["0", "3651", "x"])
def test_trend_days_outside_1_to_3650_are_refused(logged_in_client, app, days):
    client, user_id = logged_in_client
    client.post("/settings", data=settings_data(trend_days=days))
    assert user_of(app, user_id).trend_days == 30


def test_a_goal_gets_its_direction_from_the_average_when_saved(logged_in_client, app):
    client, user_id = logged_in_client
    add_weights(app, user_id, [80.0, 80.0])
    client.post("/settings", data=settings_data(goal_weight="75"))
    assert user_of(app, user_id).losing is True
    client.post("/settings", data=settings_data(goal_weight="85"))
    assert user_of(app, user_id).losing is False


def test_saving_the_same_goal_again_keeps_its_direction(logged_in_client, app):
    """A goal that has been passed stays reached: saving other settings must not turn it round."""
    client, user_id = logged_in_client
    add_weights(app, user_id, [80.0])
    client.post("/settings", data=settings_data(goal_weight="75"))
    add_weights(app, user_id, [74.0, 74.0], start=START + DAY)  # the average is now below 75
    client.post("/settings", data=settings_data(goal_weight="75", moving_avg_days="2"))
    assert user_of(app, user_id).losing is True
    assert page_data(client.get("/").data.decode())["goal"]["reached"] is True


def test_a_goal_set_before_any_entry_has_no_direction_yet(logged_in_client, app):
    client, user_id = logged_in_client
    client.post("/settings", data=settings_data(goal_weight="75"))
    assert user_of(app, user_id).losing is None


# --- the dashboard ----------------------------------------------------------------------------


def post_weights(client, weights, start=START):
    for i, weight in enumerate(weights):
        response = client.post(
            "/entries/field", json={"date": (start + i * DAY).isoformat(), "weight": weight, "confirm": True}
        )
    return response.get_json()


def test_without_a_goal_the_dashboard_has_no_goal(logged_in_client):
    client, _ = logged_in_client
    post_weights(client, [80.0, 79.0])
    page = client.get("/").data.decode()
    assert page_data(page)["goal"] is None
    assert 'id="stat-goal"' not in page
    assert goal_tip(page) == ('<div class="stat-card" id="stat-current-card">', None)  # no tooltip, no focus


def goal_tip(page):
    """(the box's start tag, the text of its goal tooltip), or the tag and None without one."""
    tag = re.search(r'<div class="stat-card" id="stat-current-card"[^>]*>', page, re.S).group(0)
    found = re.search(r'<span class="goal-tip" id="goal-tip" role="tooltip" hidden>([^<]*)</span>', page)
    return tag, found.group(1) if found else None


def test_the_current_average_box_shows_the_distance_and_the_date_on_hover(logged_in_client):
    client, _ = logged_in_client
    client.post("/settings", data=settings_data(goal_weight="75", trend_days="10"))
    post_weights(client, [90.0 - 0.1 * i for i in range(11)])  # 100 g a day, now 89.0
    page = client.get("/").data.decode()
    eta = START + 10 * DAY + 140 * DAY
    # One line in the box; the date (the long one) only in the box's tooltip, which describes the
    # box for screen readers and opens on hover, click and keyboard focus (tabindex).
    tag, text = goal_tip(page)
    assert text == f"Goal can be reached around {eta:%B} {eta.day}, {eta.year}"
    assert 'tabindex="0"' in tag and 'aria-describedby="goal-tip"' in tag and "title=" not in tag
    box = page.split(tag)[1].split("</div>")[0]
    assert '<span class="stat-sub" id="stat-goal">Goal 75.0 kg: 14.0 kg to go</span>' in box
    assert box.count("stat-sub") == 1
    assert page_data(page)["goal"]["date"] == eta.isoformat()


def test_a_reached_goal_says_so_without_a_tooltip(logged_in_client):
    client, _ = logged_in_client
    post_weights(client, [80.0])
    client.post("/settings", data=settings_data(goal_weight="79"))
    post_weights(client, [78.0], start=START + DAY)
    page = client.get("/").data.decode()
    assert '<span class="stat-sub" id="stat-goal">Goal 79.0 kg reached</span>' in page
    assert goal_tip(page)[1] == ""  # empty: never shown


@pytest.mark.parametrize(
    ("weights", "text"),
    [([86.0] * 12, "No date at this pace"), ([90.0, 89.0], "Not enough data for a date yet")],
)
def test_without_a_date_the_tooltip_says_why(logged_in_client, weights, text):
    client, _ = logged_in_client
    client.post("/settings", data=settings_data(goal_weight="75", trend_days="10"))
    post_weights(client, weights)
    page = client.get("/").data.decode()
    assert goal_tip(page)[1] == text


def test_every_save_sends_the_goal_for_the_box_and_the_line(logged_in_client):
    client, _ = logged_in_client
    client.post("/settings", data=settings_data(goal_weight="75"))
    data = post_weights(client, [80.0, 79.0])
    assert data["goal"]["weight"] == 75.0
    assert data["goal"]["to_go"] == pytest.approx(4.0)


def test_the_script_has_the_goal_strings(logged_in_client):
    client, _ = logged_in_client
    page = client.get("/").data.decode()
    i18n = json.loads(re.search(r'<script type="application/json" id="i18n">(\{.*?\})</script>', page, re.S).group(1))
    assert i18n["goal"] == "Goal"
    assert i18n["goalToGo"] == "Goal %(goal)s: %(distance)s to go"
    assert {"goalReached", "goalAround", "goalNoPace", "goalShort"} <= i18n.keys()


def test_the_goal_box_is_translated(logged_in_client):
    client, _ = logged_in_client
    client.post("/settings", data=settings_data(goal_weight="75"))
    post_weights(client, [80.0, 79.0])
    page = client.get("/?lang=nl").data.decode()
    assert "Doel 75,0 kg: nog 4,0 kg" in page
    assert "Nog te weinig gegevens voor een datum" in page


# --- the colours ------------------------------------------------------------------------------


def stats_class(client):
    return client.get("/").data.decode().split('<section class="stats')[1].split('"')[0]


def test_towards_a_goal_above_gaining_is_green_whatever_the_bmi(logged_in_client):
    client, _ = logged_in_client
    post_weights(client, [81.0, 81.0])  # BMI 25 at 1.80 m: losing would be green
    client.post("/settings", data=settings_data(goal_weight="85"))
    assert stats_class(client) == " gain-good"
    assert post_weights(client, [81.5], start=START + 2 * DAY)["gain_is_good"] is True


def test_towards_a_goal_below_losing_is_green_also_under_bmi_22(logged_in_client):
    client, _ = logged_in_client
    client.post("/settings", data=settings_data())
    post_weights(client, [60.0, 60.0])  # BMI 18.5: without a goal gaining would be green
    assert stats_class(client) == " gain-good"
    client.post("/settings", data=settings_data(goal_weight="58"))
    assert stats_class(client) == ""


# --- the public chart -------------------------------------------------------------------------


def share(client, show_goal=True, show_weight=True):
    data = {"public_id": "goalpage", "public_enabled": "y", "public_range": ""}
    if show_goal:
        data["public_show_goal"] = "y"
    if show_weight:
        data["public_show_weight"] = "y"
    return client.post("/settings/public", data=data)


@pytest.fixture
def goal_owner(logged_in_client):
    client, _ = logged_in_client
    post_weights(client, [80.0, 79.0])
    client.post("/settings", data=settings_data(goal_weight="75"))
    return client


def test_the_public_chart_hides_the_goal_by_default(goal_owner, app):
    client = goal_owner
    share(client, show_goal=False)
    page = client.get("/public/goalpage").data.decode()
    assert page_data(page)["goal"] is None
    assert "75.0" not in page
    with app.app_context():
        assert User.query.one().public_show_goal is False


def test_the_public_chart_shows_the_goal_when_switched_on(goal_owner):
    client = goal_owner
    share(client)
    page = client.get("/public/goalpage").data.decode()
    assert page_data(page)["goal"]["weight"] == 75.0


def test_the_goal_never_goes_public_without_the_weight(goal_owner, app):
    client = goal_owner
    share(client, show_goal=True, show_weight=False)
    with app.app_context():
        assert User.query.one().public_show_goal is False
    assert page_data(client.get("/public/goalpage").data.decode())["goal"] is None


def test_an_older_show_goal_without_the_weight_is_ignored(goal_owner, app):
    client = goal_owner
    share(client)
    with app.app_context():
        user = User.query.one()
        user.public_show_weight = False  # as if saved before the rule
        db.session.commit()
    assert page_data(client.get("/public/goalpage").data.decode())["goal"] is None


def test_the_goal_switch_is_greyed_out_while_the_weight_is_hidden(goal_owner):
    client = goal_owner
    share(client, show_goal=False, show_weight=False)
    page = client.get("/settings").data.decode()
    assert "disabled" in input_attrs(page, "public_show_goal")
    assert "checked" not in input_attrs(page, "public_show_goal")
    assert re.search(r'<label class="toggle-row is-disabled" id="public-goal-row">', page)
