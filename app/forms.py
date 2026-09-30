from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, FloatField, IntegerField, SelectField, StringField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Regexp, ValidationError

from app.email_utils import MxCheckError, check_mx
from app.models import User
from app.utils import DECIMAL_RE


class SignupForm(FlaskForm):
    email = StringField(
        "Email", validators=[DataRequired(), Email(), Length(max=255)]
    )

    def validate_email(self, field):
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
    code = StringField(
        "Verification code",
        validators=[DataRequired(), Regexp(r"^\d{6}$", message="Enter the 6-digit code.")],
    )


class SettingsForm(FlaskForm):
    MIN_HEIGHT_CM = 50
    MAX_HEIGHT_CM = 275

    height_value = FloatField("Height", validators=[DataRequired()])
    height_unit = SelectField(
        "Unit", choices=[(u, u) for u in User.HEIGHT_UNITS], validators=[DataRequired()]
    )
    dark_mode = BooleanField("Dark mode")

    moving_avg_days = IntegerField(
        "Moving average (days)", default=30, validators=[NumberRange(min=1, max=3650)]
    )

    def validate_height_value(self, field):
        # The range is in centimetres, so convert first — the entered number
        # means 180 in "cm" but 1.8 in "m".
        raw = (field.raw_data or [""])[0].strip()
        if not DECIMAL_RE.match(raw):
            # FloatField would also take "1e2", "1_8" or "nan".
            raise ValidationError("Enter the height as a plain number, e.g. 180 or 1.8.")
        if field.data is None or self.height_unit.data not in User.HEIGHT_UNITS:
            return  # the field/unit report their own errors
        height_cm = field.data * 100 if self.height_unit.data == "m" else field.data
        if not self.MIN_HEIGHT_CM <= height_cm <= self.MAX_HEIGHT_CM:
            raise ValidationError(
                f"Height must be between {self.MIN_HEIGHT_CM} and {self.MAX_HEIGHT_CM} cm "
                f"({self.MIN_HEIGHT_CM / 100:g} and {self.MAX_HEIGHT_CM / 100:g} m)."
            )


class ImportForm(FlaskForm):
    csv_file = FileField(
        "CSV file",
        validators=[FileRequired(), FileAllowed(["csv", "txt"], "CSV or text files only.")],
    )
