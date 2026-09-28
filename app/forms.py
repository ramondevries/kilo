from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, StringField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Regexp

from app.models import User


class SignupForm(FlaskForm):
    email = StringField(
        "Email", validators=[DataRequired(), Email(), Length(max=255)]
    )


class VerifyCodeForm(FlaskForm):
    code = StringField(
        "Verification code",
        validators=[DataRequired(), Regexp(r"^\d{6}$", message="Enter the 6-digit code.")],
    )


class SettingsForm(FlaskForm):
    height_value = FloatField(
        "Height", validators=[DataRequired(), NumberRange(min=1, max=300)]
    )
    height_unit = SelectField(
        "Unit", choices=[(u, u) for u in User.HEIGHT_UNITS], validators=[DataRequired()]
    )
