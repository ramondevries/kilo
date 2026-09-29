from collections import deque
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
from app.utils import to_kg

bp = Blueprint("main", __name__)

GRID_PAGE_SIZE = 30

# (key, label, days spanned — None means "all data"), in display order.
# 1w and all are always shown; the rest only appear once the user's data
# actually spans that long.
CHART_RANGES = [
    ("all", "All", None),
    ("20y", "20Y", 20 * 365),
    ("15y", "15Y", 15 * 365),
    ("10y", "10Y", 10 * 365),
    ("5y", "5Y", 5 * 365),
    ("1y", "1Y", 365),
    ("6m", "6M", 182),
    ("3m", "3M", 91),
    ("1m", "1M", 30),
    ("1w", "1W", 7),
]
CHART_RANGE_KEYS = {key for key, _label, _days in CHART_RANGES}
ALWAYS_SHOWN_RANGES = {"1w", "all"}


CHANGE_PERIODS = (7, 14, 30, 90, 180, 365)


def _stats(entries, moving_average, unit):
    if not entries:
        return None

    latest = entries[-1]
    first = entries[0]
    return {
        "current": latest.weight,
        "start": first.weight,
        "total_change": latest.weight - first.weight,
        "changes": _moving_average_changes(moving_average, unit),
    }


def _moving_average_changes(moving_average, unit):
    """Change in the moving average between the latest day and N days
    earlier, for each period in CHANGE_PERIODS. `moving_average` is the
    daily series (one value per calendar day, ending at the latest entry),
    so N days back is simply N indices back. A period with less history than
    that is None. `change` is in the display unit; `g_per_day` is grams/day
    regardless of unit."""
    changes = []
    for days in CHANGE_PERIODS:
        change = g_per_day = None
        if len(moving_average) > days:
            change = moving_average[-1] - moving_average[-1 - days]
            g_per_day = to_kg(change, unit) * 1000 / days
        changes.append({"days": days, "change": change, "g_per_day": g_per_day})
    return changes


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


def _daily_series(entries, unit, height_cm):
    """Every calendar day from the first entry to the last, inclusive.

    A category-axis chart spaces its labels evenly regardless of the actual
    date gap between them, so if the chart only plotted real entries, a
    stretch with no logged weigh-ins would look visually "compressed" next
    to daily-logged stretches — same on-screen width for a 1-day gap as for
    a 3-week one. Filling every day in between and linearly interpolating
    the weight for the ones with no real entry keeps the spacing uniform
    and the line continuous.

    Returns (labels, values, bmis, is_real) — bmis is None when height isn't
    set; is_real flags which days are actual measurements vs. interpolated
    fill, so the chart can hide dots/tooltip values for the latter.
    Stats/BMI cards use the real entries directly and are unaffected by
    this interpolation.
    """
    if not entries:
        return [], [], None, []

    start = entries[0].entry_date
    total_days = (entries[-1].entry_date - start).days

    values = []
    is_real = []
    prev_offset = 0
    prev_weight = entries[0].weight
    for entry in entries[1:]:
        offset = (entry.entry_date - start).days
        gap = offset - prev_offset
        for step in range(gap):
            values.append(prev_weight + (entry.weight - prev_weight) * (step / gap))
            is_real.append(step == 0)
        prev_offset = offset
        prev_weight = entry.weight
    values.append(prev_weight)
    is_real.append(True)

    labels = [(start + timedelta(days=i)).isoformat() for i in range(total_days + 1)]

    bmis = None
    if height_cm:
        height_m = height_cm / 100
        bmis = [to_kg(v, unit) / (height_m ** 2) for v in values]

    return labels, values, bmis, is_real


def _moving_average(values, window):
    """Trailing average at each index, over up to `window` preceding values
    (fewer at the start of the series, so it needs no burn-in period)."""
    if not values:
        return []
    result = []
    running_sum = 0.0
    buf = deque()
    for v in values:
        buf.append(v)
        running_sum += v
        if len(buf) > window:
            running_sum -= buf.popleft()
        result.append(running_sum / len(buf))
    return result


def _overview(user):
    unit = current_app.config["WEIGHT_UNIT"]
    entries = _entries_sorted(user)
    chart_labels, chart_values, chart_bmis, chart_real = _daily_series(
        entries, unit, user.height_cm
    )
    chart_moving_average = _moving_average(chart_values, user.moving_avg_days)
    return {
        "stats": _stats(entries, chart_moving_average, unit),
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "chart_bmis": chart_bmis,
        "chart_real": chart_real,
        "chart_moving_average": chart_moving_average,
        "moving_avg_days": user.moving_avg_days,
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

    today = date.today()
    grid_days = _grid_page(user, today)
    overview = _overview(user)
    chart_range = user.chart_range if user.chart_range in overview["available_ranges"] else "all"
    return render_template(
        "index.html",
        grid_days=grid_days,
        grid_page_size=GRID_PAGE_SIZE,
        chart_ranges=CHART_RANGES,
        chart_range=chart_range,
        today_date=today.isoformat(),
        today_entry_missing=bool(grid_days) and grid_days[0]["weight"] is None,
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


OUTLIER_THRESHOLD = 0.10


def _outlier_warning(user, entry_date, weight):
    """A human-readable warning if `weight` differs from the nearest real
    entry before or after entry_date by more than OUTLIER_THRESHOLD, else
    None. Compares against actual logged entries (not interpolated days),
    checking whichever date is being edited itself excluded."""
    before = (
        WeightEntry.query.filter(
            WeightEntry.user_id == user.id, WeightEntry.entry_date < entry_date
        )
        .order_by(WeightEntry.entry_date.desc())
        .first()
    )
    after = (
        WeightEntry.query.filter(
            WeightEntry.user_id == user.id, WeightEntry.entry_date > entry_date
        )
        .order_by(WeightEntry.entry_date.asc())
        .first()
    )

    for neighbor in (before, after):
        if neighbor is None or not neighbor.weight:
            continue
        diff_ratio = abs(weight - neighbor.weight) / neighbor.weight
        if diff_ratio > OUTLIER_THRESHOLD:
            return (
                f"{weight:g} is {diff_ratio * 100:.0f}% different from your entry "
                f"of {neighbor.weight:g} on {neighbor.entry_date.isoformat()}."
            )
    return None


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

    if not data.get("confirm"):
        warning = _outlier_warning(user, entry_date, weight)
        if warning:
            return jsonify(status="warning", message=warning)

    note = (data.get("note") or "").strip()[:280] or None

    if entry is not None:
        entry.weight = weight
        entry.note = note
    else:
        entry = WeightEntry(user_id=user.id, entry_date=entry_date, weight=weight, note=note)
        db.session.add(entry)

    db.session.commit()
    return jsonify(status="saved", **_overview(user))


@bp.route("/settings/dark-mode", methods=["POST"])
@login_required
def set_dark_mode():
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    user.dark_mode = bool(data.get("dark_mode"))
    db.session.commit()
    return jsonify(status="saved", dark_mode=user.dark_mode)


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
        form.moving_avg_days.data = user.moving_avg_days
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
        user.moving_avg_days = form.moving_avg_days.data
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
