from datetime import timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app import db
from app.forms import WeightEntryForm
from app.models import WeightEntry

bp = Blueprint("main", __name__)


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


@bp.route("/", methods=["GET"])
def index():
    entries = WeightEntry.query.order_by(WeightEntry.entry_date.asc()).all()
    form = WeightEntryForm()
    chart_labels = [e.entry_date.isoformat() for e in entries]
    chart_values = [e.weight for e in entries]

    return render_template(
        "index.html",
        entries=list(reversed(entries)),
        form=form,
        stats=_stats(entries),
        chart_labels=chart_labels,
        chart_values=chart_values,
        unit=current_app.config["WEIGHT_UNIT"],
    )


@bp.route("/entries", methods=["POST"])
def create_entry():
    form = WeightEntryForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flash(error, "error")
        return redirect(url_for("main.index"))

    existing = WeightEntry.query.filter_by(entry_date=form.entry_date.data).first()
    if existing:
        existing.weight = form.weight.data
        existing.note = form.note.data
        flash(f"Updated entry for {existing.entry_date}.", "success")
    else:
        db.session.add(
            WeightEntry(
                entry_date=form.entry_date.data,
                weight=form.weight.data,
                note=form.note.data,
            )
        )
        flash(f"Added entry for {form.entry_date.data}.", "success")

    db.session.commit()
    return redirect(url_for("main.index"))


@bp.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
def edit_entry(entry_id):
    entry = WeightEntry.query.get_or_404(entry_id)
    form = WeightEntryForm(obj=entry)

    if form.validate_on_submit():
        conflict = WeightEntry.query.filter(
            WeightEntry.entry_date == form.entry_date.data, WeightEntry.id != entry.id
        ).first()
        if conflict:
            flash(f"An entry for {form.entry_date.data} already exists.", "error")
            return render_template("edit.html", form=form, entry=entry)

        entry.entry_date = form.entry_date.data
        entry.weight = form.weight.data
        entry.note = form.note.data
        db.session.commit()
        flash(f"Updated entry for {entry.entry_date}.", "success")
        return redirect(url_for("main.index"))

    return render_template("edit.html", form=form, entry=entry)


@bp.route("/entries/<int:entry_id>/delete", methods=["POST"])
def delete_entry(entry_id):
    entry = WeightEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash(f"Deleted entry for {entry.entry_date}.", "success")
    return redirect(url_for("main.index"))
