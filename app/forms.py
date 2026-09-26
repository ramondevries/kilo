from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, StringField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, Regexp


class WeightEntryForm(FlaskForm):
    entry_date = DateField("Date", validators=[DataRequired()], default=date.today)
    weight = FloatField("Weight", validators=[DataRequired(), NumberRange(min=1, max=1000)])
    note = StringField("Note", validators=[Optional(), Length(max=280)])


class SignupForm(FlaskForm):
    email = StringField(
        "Email", validators=[DataRequired(), Email(), Length(max=255)]
    )


class VerifyCodeForm(FlaskForm):
    code = StringField(
        "Verification code",
        validators=[DataRequired(), Regexp(r"^\d{6}$", message="Enter the 6-digit code.")],
    )
