import secrets
from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.auth import CODE_TTL_MINUTES, get_current_user, login_required
from app.email_utils import send_deletion_email
from app.forms import VerifyCodeForm
from app.models import User
from app.utils import utcnow

bp = Blueprint("account", __name__)


def _code_pending(user):
    return bool(
        user.delete_code_hash
        and user.delete_code_expires_at
        and user.delete_code_expires_at >= utcnow()
    )


@bp.route("/settings/remove", methods=["GET"])
@login_required
def remove_data():
    user = get_current_user()
    return render_template(
        "remove_data.html",
        form=VerifyCodeForm(),
        exported=bool(session.get("data_exported")),
        code_pending=_code_pending(user),
        email=session.get("email"),
    )


@bp.route("/settings/remove/send-code", methods=["POST"])
@login_required
def send_removal_code():
    user = get_current_user()
    email = session.get("email")
    if not session.get("data_exported"):
        flash("Download your data first.", "error")
        return redirect(url_for("account.remove_data"))
    if not email:
        flash("Sign in again to confirm this request.", "error")
        return redirect(url_for("account.remove_data"))

    code = f"{secrets.randbelow(1_000_000):06d}"
    user.delete_code_hash = generate_password_hash(code)
    user.delete_code_expires_at = utcnow() + timedelta(minutes=CODE_TTL_MINUTES)
    user.delete_code_attempts = 0
    db.session.commit()
    send_deletion_email(email, code)
    flash(f"We sent a confirmation code to {email}.", "success")
    return redirect(url_for("account.remove_data"))


@bp.route("/settings/remove/confirm", methods=["POST"])
@login_required
def confirm_removal():
    user = get_current_user()
    form = VerifyCodeForm()
    if not session.get("data_exported"):
        flash("Download your data first.", "error")
    elif not form.validate_on_submit():
        flash("Enter the 6-digit code.", "error")
    elif not _code_pending(user):
        flash("That code has expired. Request a new one.", "error")
    elif user.delete_code_attempts >= User.MAX_CODE_ATTEMPTS:
        flash("Too many attempts. Request a new code.", "error")
    elif not check_password_hash(user.delete_code_hash, form.code.data):
        user.delete_code_attempts += 1
        db.session.commit()
        flash("Incorrect code.", "error")
    else:
        # WeightEntry rows go with the user (cascade="all, delete-orphan").
        db.session.delete(user)
        db.session.commit()
        session.clear()
        flash("Your account and all your data have been removed.", "success")
        return redirect(url_for("main.index"))
    return redirect(url_for("account.remove_data"))
