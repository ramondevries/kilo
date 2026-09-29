import secrets
from datetime import timedelta
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.email_utils import send_verification_email
from app.forms import SignupForm, VerifyCodeForm
from app.models import User
from app.utils import hash_email, normalize_email, utcnow

bp = Blueprint("auth", __name__)

CODE_TTL_MINUTES = 10


def get_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            flash("Enter your email to sign in.", "error")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    return wrapped


@bp.app_context_processor
def inject_current_user():
    user = get_current_user()
    return {
        "current_user": user,
        "current_email": session.get("email"),
        "theme": "dark" if user and user.dark_mode else "light",
    }


def _issue_code(user, email):
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.code_hash = generate_password_hash(code)
    user.code_expires_at = utcnow() + timedelta(minutes=CODE_TTL_MINUTES)
    user.code_attempts = 0
    db.session.commit()
    send_verification_email(email, code)


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        email_hash = hash_email(email)
        user = User.query.filter_by(email_hash=email_hash).first()
        if user is None:
            user = User(email_hash=email_hash)
            db.session.add(user)
            db.session.commit()

        _issue_code(user, email)
        session["pending_email"] = email
        flash(f"We sent a verification code to {email}.", "success")
        return redirect(url_for("auth.verify"))

    return render_template("signup.html", form=form)


@bp.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get("pending_email")
    if not email:
        flash("Enter your email to get a verification code.", "error")
        return redirect(url_for("auth.signup"))

    user = User.query.filter_by(email_hash=hash_email(email)).first()
    if user is None:
        session.pop("pending_email", None)
        return redirect(url_for("auth.signup"))

    form = VerifyCodeForm()
    if form.validate_on_submit():
        if not user.code_hash or not user.code_expires_at or user.code_expires_at < utcnow():
            flash("That code has expired. Request a new one.", "error")
        elif user.code_attempts >= User.MAX_CODE_ATTEMPTS:
            flash("Too many attempts. Request a new code.", "error")
        elif not check_password_hash(user.code_hash, form.code.data):
            user.code_attempts += 1
            db.session.commit()
            flash("Incorrect code.", "error")
        else:
            user.verified_at = user.verified_at or utcnow()
            user.code_hash = None
            user.code_expires_at = None
            user.code_attempts = 0
            db.session.commit()
            session.pop("pending_email", None)
            session["user_id"] = user.id
            session["email"] = email
            flash("Email verified — you're signed in.", "success")
            return redirect(url_for("main.index"))

    return render_template("verify.html", form=form, email=email)


@bp.route("/verify/resend", methods=["POST"])
def resend_code():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("auth.signup"))

    user = User.query.filter_by(email_hash=hash_email(email)).first()
    if user is None:
        session.pop("pending_email", None)
        return redirect(url_for("auth.signup"))

    _issue_code(user, email)
    flash(f"We sent a new code to {email}.", "success")
    return redirect(url_for("auth.verify"))


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    session.pop("email", None)
    flash("Signed out.", "success")
    return redirect(url_for("main.index"))


@bp.route("/about")
def about():
    return render_template("about.html")
