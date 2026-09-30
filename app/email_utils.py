import dns.exception
import dns.name
import dns.resolver
from flask import current_app
from flask_mail import Message

from app import mail
from app.utils import DELETE_CODE_TTL_MINUTES, SIGNIN_CODE_TTL_MINUTES


def send_verification_email(email, code):
    message = Message(
        subject="Your verification code",
        recipients=[email],
        body=(
            f"Your verification code is {code}.\n\n"
            f"It expires in {SIGNIN_CODE_TTL_MINUTES} minutes. If you didn't request this, ignore this email."
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
            f"weight data. It expires in {DELETE_CODE_TTL_MINUTES} minutes. If you didn't request "
            "this, ignore this email and your data stays untouched."
        ),
    )
    mail.send(message)
    current_app.logger.info("Data removal code for %s: %s", email, code)


class MxCheckError(Exception):
    """The domain can't receive mail (`temporary` is False) or we couldn't
    tell because DNS was unreachable (`temporary` is True)."""

    def __init__(self, message, temporary=False):
        super().__init__(message)
        self.temporary = temporary


def check_mx(email):
    """Raise MxCheckError unless the email's domain publishes a usable MX
    record. A "null MX" (a single record pointing at ".", RFC 7505) means
    the domain explicitly accepts no mail, so it counts as missing."""
    no_mx = "That email domain doesn't accept mail (no MX record)."
    try_again = "Couldn't check that email domain right now. Try again."
    domain = email.rsplit("@", 1)[-1].strip().rstrip(".")
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.name.NameTooLong, dns.name.EmptyLabel):
        raise MxCheckError(no_mx)
    except (dns.exception.Timeout, dns.resolver.NoNameservers):
        raise MxCheckError(try_again, temporary=True)

    if not any(str(r.exchange).rstrip(".") for r in answers):
        raise MxCheckError(no_mx)
