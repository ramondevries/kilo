from flask import current_app
from flask_mail import Message

from app import mail


def send_verification_email(email, code):
    message = Message(
        subject="Your verification code",
        recipients=[email],
        body=(
            f"Your verification code is {code}.\n\n"
            "It expires in 10 minutes. If you didn't request this, ignore this email."
        ),
    )
    mail.send(message)
    current_app.logger.info("Verification code for %s: %s", email, code)


def send_deletion_email(email, code):
    message = Message(
        subject="Confirm removal of your data",
        recipients=[email],
        body=(
            f"Your confirmation code is {code}.\n\n"
            "Entering it will permanently delete your account and all your "
            "weight data. It expires in 10 minutes. If you didn't request "
            "this, ignore this email and your data stays untouched."
        ),
    )
    mail.send(message)
    current_app.logger.info("Data removal code for %s: %s", email, code)
