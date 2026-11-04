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

"""WTForms forms: signup, code verification, settings, the public chart and CSV import."""

from flask import current_app
from flask_babel import format_decimal, gettext as _, lazy_gettext as _l
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, FloatField, IntegerField, SelectField, StringField
from wtforms.validators import (
    DataRequired, Email, InputRequired, Length, NumberRange, Optional, Regexp, ValidationError,
)

from app.csv_io import MAX_WEIGHT_KG, MIN_WEIGHT_KG
from app.email_utils import MxCheckError, check_mx
from app.models import User
from app.utils import MAX_HEIGHT_CM, MIN_HEIGHT_CM, height_to_cm, parse_decimal


class SignupForm(FlaskForm):
    """Email address entry for signing in or up."""
    email = StringField(
        _l("Email"), validators=[DataRequired(), Email(), Length(max=255)]
    )

    def validate_email(self, field):
        """Reject addresses whose domain has no usable MX record (when CHECK_EMAIL_MX is on)."""
        # Runs only after the format checks above pass (WTForms stops the
        # chain on the first failing validator, but inline validators run
        # regardless — so skip if there are already errors).
        if field.errors or not current_app.config["CHECK_EMAIL_MX"]:
            return
        try:
            check_mx(field.data)
        except MxCheckError as exc:
            raise ValidationError(str(exc)) from exc


class VerifyCodeForm(FlaskForm):
    """The 6-digit code from the email."""
    code = StringField(
        _l("Verification code"),
        validators=[DataRequired(), Regexp(r"^\d{6}$", message=_l("Enter the 6-digit code."))],
    )


class DecimalFloatField(FloatField):
    """A FloatField that takes "1.8" and "1,8" alike and nothing else.

    Plain FloatField uses float(), which rejects the comma but accepts "1e2",
    "1_8" and "nan"; this one goes through `parse_decimal`. `not_a_number` makes the
    error message for anything else (the height's by default).
    """

    def __init__(self, *args, not_a_number=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.not_a_number = not_a_number or (
            lambda: _("Enter the height as a plain number, e.g. 180 or 1.8.")
        )

    def process_formdata(self, valuelist):
        if not valuelist or not valuelist[0].strip():
            self.data = None  # empty: left to the "required" validator, or no value
            return
        value = parse_decimal(valuelist[0])
        if value is None:
            raise ValueError(self.not_a_number())
        self.data = value

    def _value(self):
        # Re-show what the user typed; otherwise the stored number with the
        # language's decimal separator (186,0 rather than 186.0).
        if self.raw_data:
            return self.raw_data[0]
        if self.data is not None:
            return format_decimal(self.data, format="0.0#")
        return ""


class SettingsForm(FlaskForm):
    """User settings: height (cm or m, 50-275 cm), dark mode, the moving-average window in days, the
    goal weight (optional) and the days the goal date's trend is measured over."""
    MIN_HEIGHT_CM = MIN_HEIGHT_CM
    MAX_HEIGHT_CM = MAX_HEIGHT_CM

    # InputRequired, not DataRequired: a typo then gets the "plain number"
    # message from the field instead of also "This field is required".
    # NOTE: Label of the body height field in the settings.
    height_value = DecimalFloatField(_l("Height"), validators=[InputRequired()])
    # NOTE: Label of the cm/m dropdown next to the height field.
    height_unit = SelectField(
        _l("Unit"), choices=[(u, u) for u in User.HEIGHT_UNITS], validators=[DataRequired()]
    )
    dark_mode = BooleanField(_l("Dark mode"))

    moving_avg_days = IntegerField(
        _l("Moving average (days)"), default=10, validators=[NumberRange(min=1, max=3650)]
    )
    goal_weight = DecimalFloatField(
        # NOTE: Label of the optional goal weight field in the settings.
        _l("Goal weight (kg)"),
        # NOTE: Error under the goal weight field in the settings.
        not_a_number=lambda: _("Enter the goal as a plain number, e.g. 75 or 72.5."),
        validators=[Optional()],
    )
    trend_days = IntegerField(
        # NOTE: Settings label: the days over which the goal date's pace is measured.
        _l("Goal date trend (days)"), default=30, validators=[NumberRange(min=1, max=3650)]
    )

    def validate_goal_weight(self, field):
        """Like any weight: MIN_WEIGHT_KG..MAX_WEIGHT_KG, or empty for no goal."""
        if field.data is not None and not MIN_WEIGHT_KG <= field.data <= MAX_WEIGHT_KG:
            raise ValidationError(
                _(
                    "Weight must be between %(min)s and %(max)s kg.",
                    min=format_decimal(MIN_WEIGHT_KG),
                    max=format_decimal(MAX_WEIGHT_KG),
                )
            )

    def validate_height_value(self, field):
        """Require a plain decimal number that is within MIN_HEIGHT_CM..MAX_HEIGHT_CM once converted to cm."""
        # The range is in centimetres, so convert first — the entered number
        # means 180 in "cm" but 1.8 in "m".
        if field.data is None or self.height_unit.data not in User.HEIGHT_UNITS:
            return  # the field/unit report their own errors
        height_cm = height_to_cm(field.data, self.height_unit.data)
        if not self.MIN_HEIGHT_CM <= height_cm <= self.MAX_HEIGHT_CM:
            raise ValidationError(
                _(
                    "Height must be between %(min_cm)s and %(max_cm)s cm (%(min_m)s and %(max_m)s m).",
                    min_cm=format_decimal(self.MIN_HEIGHT_CM),
                    max_cm=format_decimal(self.MAX_HEIGHT_CM),
                    min_m=format_decimal(self.MIN_HEIGHT_CM / 100),
                    max_m=format_decimal(self.MAX_HEIGHT_CM / 100),
                )
            )


class PublicChartForm(FlaskForm):
    """Sharing the chart at /public/<id>: on or off, and the id (empty: a new one is made up).

    The id is compared in lowercase, so "Ramon" and "ramon" are the same page. Set `user_id`
    before validating, so the user's own id does not count as taken.
    """
    MIN_ID_LENGTH = 3
    MAX_ID_LENGTH = 64
    user_id = None

    # NOTE: Switch in the settings that makes the weight chart visible on a public web page.
    public_enabled = BooleanField(_l("Share my chart on a public page"))
    # NOTE: Switch in the settings: show the kilograms on the public chart, or only the shape of the line.
    public_show_weight = BooleanField(_l("Show my weight"))
    # NOTE: Switch in the settings: show the boxes with the current average, BMI and changes under the public chart.
    public_show_stats = BooleanField(_l("Show the stat boxes on the public page"))
    # NOTE: Switch in the settings: show the goal weight on the public chart.
    public_show_goal = BooleanField(_l("Show my goal"))
    public_dark_mode = BooleanField(_l("Dark mode"))
    public_id = StringField(
        # NOTE: Label of the field with the last part of the public page's address (the "ramon" in .../public/ramon).
        _l("Page ID"),
        filters=[lambda value: value.strip().lower() if value else value],
        validators=[
            Regexp(
                rf"^([a-z0-9_-]{{{MIN_ID_LENGTH},{MAX_ID_LENGTH}}})?$",
                message=_l(
                    "Use %(min)d to %(max)d letters (a-z), digits, hyphens or underscores.",
                    min=MIN_ID_LENGTH,
                    max=MAX_ID_LENGTH,
                ),
            ),
        ],
    )

    def validate_public_id(self, field):
        """Refuse an id another user already has (shared or not)."""
        if field.errors or not field.data:
            return
        taken = User.query.filter(User.public_id == field.data, User.id != self.user_id).first()
        if taken is not None:
            raise ValidationError(_("That ID is already taken. Choose another one."))


class ImportForm(FlaskForm):
    """Upload of a file to import: a CSV, or a Hacker's Diet CSV/XML export."""
    csv_file = FileField(
        _l("CSV or XML file"),
        validators=[FileRequired(), FileAllowed(["csv", "txt", "xml"], _l("CSV, XML or text files only."))],
    )
