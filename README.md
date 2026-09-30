# Kilo Tracker

A small Flask app for logging your weight over time: add daily entries, see
a trend chart, and track 7-day/30-day/total change.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Run

```bash
python run.py
```

Then open http://127.0.0.1:5000. Data is stored in `instance/weight.db`
(SQLite, created automatically).

Set `WEIGHT_UNIT=lb` (default `kg`) to change the displayed unit.

## Email sign-up

Visit `/signup` to sign up with just an email address: you'll receive a
6-digit verification code by email (valid for 30 minutes) and entering it
signs you in. By default outgoing mail is suppressed and the code is only
logged to the console, so sign-up works out of the box with no mail server.

To send real emails in production, configure an SMTP server via env vars and
turn off suppression:

```bash
export MAIL_SERVER=smtp.example.com
export MAIL_PORT=587
export MAIL_USE_TLS=1
export MAIL_USERNAME=...
export MAIL_PASSWORD=...
export MAIL_DEFAULT_SENDER=no-reply@example.com
export MAIL_SUPPRESS_SEND=0
```

## Test

```bash
pytest
```
