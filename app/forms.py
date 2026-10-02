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

"""WTForms forms: signup, code verification, settings and CSV import."""

from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, FloatField, IntegerField, SelectField, StringField
from wtforms.validators import (
    DataRequired, Email, InputRequired, Length, NumberRange, Regexp, ValidationError,
)

from app.email_utils import MxCheckError, check_mx
from app.models import User
from app.utils import parse_decimal


class SignupForm(FlaskForm):
    """Email address entry for signing in or up."""
    email = StringField(
        "Email", validators=[DataRequired(), Email(), Length(max=255)]
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
            raise ValidationError(str(exc))


class VerifyCodeForm(FlaskForm):
    """The 6-digit code from the email."""
    code = StringField(
        "Verification code",
        validators=[DataRequired(), Regexp(r"^\d{6}$", message="Enter the 6-digit code.")],
    )


class DecimalFloatField(FloatField):
    """A FloatField that takes "1.8" and "1,8" alike and nothing else.

    Plain FloatField uses float(), which rejects the comma but accepts "1e2",
    "1_8" and "nan"; this one goes through `parse_decimal`.
    """

    def process_formdata(self, valuelist):
        if not valuelist or not valuelist[0].strip():
            return  # empty: left to the "required" validator
        value = parse_decimal(valuelist[0])
        if value is None:
            raise ValueError("Enter the height as a plain number, e.g. 180 or 1.8.")
        self.data = value


class SettingsForm(FlaskForm):
    """User settings: height (cm or m, 50-275 cm), dark mode and the moving-average window in days."""
    MIN_HEIGHT_CM = 50
    MAX_HEIGHT_CM = 275

    # InputRequired, not DataRequired: a typo then gets the "plain number"
    # message from the field instead of also "This field is required".
    height_value = DecimalFloatField("Height", validators=[InputRequired()])
    height_unit = SelectField(
        "Unit", choices=[(u, u) for u in User.HEIGHT_UNITS], validators=[DataRequired()]
    )
    dark_mode = BooleanField("Dark mode")

    moving_avg_days = IntegerField(
        "Moving average (days)", default=10, validators=[NumberRange(min=1, max=3650)]
    )

    def validate_height_value(self, field):
        """Require a plain decimal number that is within MIN_HEIGHT_CM..MAX_HEIGHT_CM once converted to cm."""
        # The range is in centimetres, so convert first — the entered number
        # means 180 in "cm" but 1.8 in "m".
        if field.data is None or self.height_unit.data not in User.HEIGHT_UNITS:
            return  # the field/unit report their own errors
        height_cm = field.data * 100 if self.height_unit.data == "m" else field.data
        if not self.MIN_HEIGHT_CM <= height_cm <= self.MAX_HEIGHT_CM:
            raise ValidationError(
                f"Height must be between {self.MIN_HEIGHT_CM} and {self.MAX_HEIGHT_CM} cm "
                f"({self.MIN_HEIGHT_CM / 100:g} and {self.MAX_HEIGHT_CM / 100:g} m)."
            )


class ImportForm(FlaskForm):
    """Upload of a CSV file to import."""
    csv_file = FileField(
        "CSV file",
        validators=[FileRequired(), FileAllowed(["csv", "txt"], "CSV or text files only.")],
    )
