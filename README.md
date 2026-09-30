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

Weights are in kilograms and heights in centimetres or metres.

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

## Production

`python run.py` starts the Flask development server with the debugger on. Don't
use it in production; run the app under [gunicorn](https://gunicorn.org/)
instead, behind a reverse proxy that terminates HTTPS.

### 1. Install

```bash
git clone https://github.com/ramondevries/kilo.git /srv/kilo
cd /srv/kilo
python -m venv .venv
.venv/bin/pip install -r requirements.txt gunicorn
```

Create a system user to run it (for example `kilo`) that owns `/srv/kilo`. The
`instance/` folder inside it holds the SQLite database (`weight.db`) and must
be writable by that user.

### 2. Configure with `kilo.env`

All settings are environment variables. Put them in an environment file, for
example `/etc/kilo.env`, readable only by the service user
(`chmod 600 /etc/kilo.env`), and keep it out of git:

```bash
# Signs the session cookies. Required in production: generate one with
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-64-random-hex-characters

# Outgoing mail (see "Email sign-up" above). MAIL_SUPPRESS_SEND must be 0,
# otherwise no email is sent and the codes are only written to the log.
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=1
MAIL_USERNAME=your-smtp-user
MAIL_PASSWORD=your-smtp-password
MAIL_DEFAULT_SENDER=Kilo Tracker <no-reply@example.com>
MAIL_SUPPRESS_SEND=0

# Optional: set to 0 to skip the MX-record check of the email domain at
# sign-up (it needs outbound DNS from the server).
# CHECK_EMAIL_MX=1
```

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev` | Session signing key. Always set your own. |
| `MAIL_SERVER` | `localhost` | SMTP host |
| `MAIL_PORT` | `25` | SMTP port, usually `587` |
| `MAIL_USE_TLS` | `0` | `1` for STARTTLS (port 587). Implicit SSL on port 465 is not supported. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | unset | SMTP login |
| `MAIL_DEFAULT_SENDER` | `no-reply@weight-tracker.local` | The From address |
| `MAIL_SUPPRESS_SEND` | `1` | `0` to really send mail |
| `CHECK_EMAIL_MX` | `1` | `0` to disable the MX-record check at sign-up |

Values with spaces or `<>` (such as `MAIL_DEFAULT_SENDER`) are fine in a
systemd `EnvironmentFile`; if you source the file from a shell instead, quote
them.

### 3. Run gunicorn with systemd

`run.py` exposes the app as `run:app`. Create `/etc/systemd/system/kilo.service`:

```ini
[Unit]
Description=Kilo Tracker
After=network.target

[Service]
User=kilo
WorkingDirectory=/srv/kilo
EnvironmentFile=/etc/kilo.env
ExecStart=/srv/kilo/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 run:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kilo
sudo systemctl status kilo
journalctl -u kilo -f        # logs (verification codes too, if mail is suppressed)
```

`--workers 3` is a sensible start; several workers can share the SQLite
database safely (it runs in WAL mode with a 30 second busy timeout). After
changing `kilo.env`, restart with `sudo systemctl restart kilo`.

### 4. Reverse proxy (nginx) with HTTPS

Get a certificate (for example with `certbot --nginx`) and proxy to gunicorn:

```nginx
server {
    server_name kilo.example.com;
    client_max_body_size 1m;   # the app rejects uploads over 1 MB anyway

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Backups and updates

Back up the database with SQLite's own tool, not a plain file copy (recent
writes can still be in the `-wal` file):

```bash
sqlite3 /srv/kilo/instance/weight.db ".backup /backups/weight.db"
```

To update: `git pull`, `.venv/bin/pip install -r requirements.txt`, then
`sudo systemctl restart kilo`. New database columns are added automatically at
startup.

## Test

```bash
pytest
```

## License

Copyright (C) 2026 Ramón de Vries <ramon@11tools.com>

Kilo Tracker is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. See the [LICENSE](LICENSE) file for the full text.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.

The Kilo name and logo (the icons and wordmarks in `app/static/kilo-*.svg`)
are not covered by this license. They may not be reused without permission.
