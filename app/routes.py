from datetime import date, timedelta

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db
from app.auth import get_current_user, login_required
from app.csv_io import export_csv, parse_csv
from app.forms import ImportForm, SettingsForm, SignupForm
from app.models import WeightEntry

bp = Blueprint("main", __name__)

GRID_PAGE_SIZE = 30

# (key, label, days spanned — None means "all data"). 1w and all are always
# shown; the rest only appear once the user's data actually spans that long.
CHART_RANGES = [
    ("1w", "1W", 7),
    ("1m", "1M", 30),
    ("3m", "3M", 91),
    ("1y", "1Y", 365),
    ("5y", "5Y", 5 * 365),
    ("10y", "10Y", 10 * 365),
    ("15y", "15Y", 15 * 365),
    ("20y", "20Y", 20 * 365),
    ("all", "All", None),
]
CHART_RANGE_KEYS = {key for key, _label, _days in CHART_RANGES}
ALWAYS_SHOWN_RANGES = {"1w", "all"}


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


def _available_range_keys(entries):
    span_days = (date.today() - entries[0].entry_date).days if entries else 0
    return [
        key
        for key, _label, days in CHART_RANGES
        if key in ALWAYS_SHOWN_RANGES or (days is not None and span_days >= days)
    ]


def _overview(user):
    unit = current_app.config["WEIGHT_UNIT"]
    entries = _entries_sorted(user)
    return {
        "stats": _stats(entries),
        "chart_labels": [e.entry_date.isoformat() for e in entries],
        "chart_values": [e.weight for e in entries],
        "bmi": user.bmi(unit),
        "unit": unit,
        "available_ranges": _available_range_keys(entries),
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
    overview = _overview(user)
    chart_range = user.chart_range if user.chart_range in overview["available_ranges"] else "all"
    return render_template(
        "index.html",
        grid_days=grid_days,
        grid_page_size=GRID_PAGE_SIZE,
        chart_ranges=CHART_RANGES,
        chart_range=chart_range,
        **overview,
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


@bp.route("/chart-range", methods=["POST"])
@login_required
def set_chart_range():
    data = request.get_json(silent=True) or {}
    range_key = data.get("range")
    if range_key not in CHART_RANGE_KEYS:
        return jsonify(error="invalid range"), 400

    user = get_current_user()
    user.chart_range = range_key
    db.session.commit()
    return jsonify(status="saved")


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = get_current_user()
    form = SettingsForm()

    if request.method == "GET":
        form.dark_mode.data = user.dark_mode
        if user.height_cm is not None:
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
        user.dark_mode = form.dark_mode.data
        db.session.commit()
        flash("Settings updated.", "success")
        return redirect(url_for("main.settings"))

    return render_template("settings.html", form=form, import_form=ImportForm(), user=user)


@bp.route("/settings/export", methods=["GET"])
@login_required
def export_entries():
    user = get_current_user()
    unit = current_app.config["WEIGHT_UNIT"]
    csv_text = export_csv(_entries_sorted(user), unit)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=weight-export.csv"},
    )


@bp.route("/settings/import", methods=["POST"])
@login_required
def import_entries():
    user = get_current_user()
    form = ImportForm()

    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flash(error, "error")
        return redirect(url_for("main.settings"))

    unit = current_app.config["WEIGHT_UNIT"]
    rows, errors = parse_csv(form.csv_file.data.read(), unit)

    imported = 0
    for entry_date, weight, note in rows:
        entry = WeightEntry.query.filter_by(user_id=user.id, entry_date=entry_date).first()
        if entry is not None:
            entry.weight = weight
            entry.note = note
        else:
            db.session.add(WeightEntry(user_id=user.id, entry_date=entry_date, weight=weight, note=note))
        imported += 1
    db.session.commit()

    if imported:
        flash(f"Imported {imported} entr{'y' if imported == 1 else 'ies'}.", "success")
    if errors:
        preview = "; ".join(errors[:5])
        more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        flash(f"Skipped {len(errors)} invalid line(s): {preview}{more}", "error")
    if not imported and not errors:
        flash("No rows found in the file.", "error")

    return redirect(url_for("main.settings"))
