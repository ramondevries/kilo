from datetime import date, timedelta

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from app import db
from app.auth import get_current_user, login_required
from app.forms import SettingsForm, SignupForm
from app.models import WeightEntry

bp = Blueprint("main", __name__)

GRID_PAGE_SIZE = 30


def _stats(entries):
    if not entries:
        return None

    latest = entries[-1]
    first = entries[0]
    stats = {
        "current": latest.weight,
        "start": first.weight,
        "total_change": latest.weight - first.weight,
        "change_7d": None,
        "change_30d": None,
    }

    for days, key in ((7, "change_7d"), (30, "change_30d")):
        cutoff = latest.entry_date - timedelta(days=days)
        baseline = next((e for e in entries if e.entry_date <= cutoff), None)
        if baseline is not None:
            stats[key] = latest.weight - baseline.weight

    return stats


def _entries_sorted(user):
    return (
        WeightEntry.query.filter_by(user_id=user.id).order_by(WeightEntry.entry_date.asc()).all()
    )


def _overview(user):
    unit = current_app.config["WEIGHT_UNIT"]
    entries = _entries_sorted(user)
    return {
        "stats": _stats(entries),
        "chart_labels": [e.entry_date.isoformat() for e in entries],
        "chart_values": [e.weight for e in entries],
        "bmi": user.bmi(unit),
        "unit": unit,
    }


def _grid_page(user, end_date, size=GRID_PAGE_SIZE):
    """The `size` days ending on (and including) end_date, newest first."""
    days = [end_date - timedelta(days=i) for i in range(size)]
    entries = {
        e.entry_date: e
        for e in WeightEntry.query.filter(
            WeightEntry.user_id == user.id, WeightEntry.entry_date.in_(days)
        ).all()
    }
    return [
        {
            "date": d.isoformat(),
            "weight": entries[d].weight if d in entries else None,
            "note": (entries[d].note or "") if d in entries else "",
        }
        for d in days
    ]


@bp.route("/", methods=["GET"])
def index():
    user = get_current_user()
    if user is None:
        return render_template("login.html", form=SignupForm())

    grid_days = _grid_page(user, date.today())
    return render_template(
        "index.html",
        grid_days=grid_days,
        grid_page_size=GRID_PAGE_SIZE,
        **_overview(user),
    )


@bp.route("/entries/window", methods=["GET"])
@login_required
def entries_window():
    before_str = request.args.get("before")
    try:
        end_date = date.fromisoformat(before_str) - timedelta(days=1)
    except (TypeError, ValueError):
        return jsonify(error="invalid date"), 400

    user = get_current_user()
    return jsonify(days=_grid_page(user, end_date))


@bp.route("/entries/field", methods=["POST"])
@login_required
def save_field():
    data = request.get_json(silent=True) or {}
    try:
        entry_date = date.fromisoformat(data.get("date", ""))
    except ValueError:
        return jsonify(error="invalid date"), 400

    user = get_current_user()
    entry = WeightEntry.query.filter_by(user_id=user.id, entry_date=entry_date).first()

    weight_raw = data.get("weight")
    if weight_raw in (None, ""):
        if entry is not None:
            db.session.delete(entry)
            db.session.commit()
        return jsonify(status="cleared", **_overview(user))

    try:
        weight = float(weight_raw)
    except (TypeError, ValueError):
        return jsonify(error="invalid weight"), 400
    if not (1 <= weight <= 1000):
        return jsonify(error="weight out of range"), 400

    note = (data.get("note") or "").strip()[:280] or None

    if entry is not None:
        entry.weight = weight
        entry.note = note
    else:
        entry = WeightEntry(user_id=user.id, entry_date=entry_date, weight=weight, note=note)
        db.session.add(entry)

    db.session.commit()
    return jsonify(status="saved", **_overview(user))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = get_current_user()
    form = SettingsForm()

    if request.method == "GET" and user.height_cm is not None:
        form.height_unit.data = user.height_unit
        if user.height_unit == "m":
            form.height_value.data = round(user.height_cm / 100, 2)
        else:
            form.height_value.data = round(user.height_cm, 1)

    if form.validate_on_submit():
        value = form.height_value.data
        unit = form.height_unit.data
        user.height_cm = value * 100 if unit == "m" else value
        user.height_unit = unit
        db.session.commit()
        flash("Height updated.", "success")
        return redirect(url_for("main.settings"))

    return render_template("settings.html", form=form, user=user)
