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
