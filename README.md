# Kilo Tracker

A small Flask app for logging your weight over time: add daily entries, see
a trend chart, and track 7-day/30-day/total change.

## Try it now

Want to see where your weight is really heading? **Kilo Tracker is free to use
at [kilo.11tools.com](https://kilo.11tools.com)** - no install, no password and
nothing to pay. Sign in with just your email address, log your weight in
seconds, and watch the trend line cut through the daily ups and downs. It works
great on your phone, shows your BMI at a glance, and you can import or export
all your data as CSV whenever you like (the CSV and XML exports of The Hacker's Diet Online and the CSV export of Yet Another Diet Tool can be imported too). Give it a spin, and if you'd rather host
it yourself, everything you need is below.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pybabel compile -d translations
```

## Run

```bash
python run.py
```

Then open http://127.0.0.1:5000. Data is stored in `instance/weight.db`
(SQLite, created automatically).

Weights are in kilograms and heights in centimetres or metres.

## Languages

Kilo speaks English, Dutch, French, Spanish, Brazilian Portuguese, German,
Italian, Indonesian, Polish, Romanian, Hungarian, Danish, Finnish, Swedish and
Norwegian (Bokmål). The language follows the browser's `Accept-Language` setting (there is
no switcher); add `?lang=de` to a URL to try another one. The translations are
machine-generated and welcome improvements: see [TRANSLATING.md](TRANSLATING.md).
The compiled catalogs (`*.mo`) are not in git: run `pybabel compile -d
translations` after cloning and after every update, as below.

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
.venv/bin/pybabel compile -d translations
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

# Production runs behind HTTPS: only ever send the sign-in cookie over it.
SESSION_COOKIE_SECURE=1

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
| `SECRET_KEY` | `dev` | Session signing key. Always set your own (the app warns in its log if it is `dev` or short). |
| `SESSION_COOKIE_SECURE` | `0` | `1` in production: the sign-in cookie is then only sent over HTTPS |
| `MAIL_SERVER` | `localhost` | SMTP host |
| `MAIL_PORT` | `25` | SMTP port, usually `587` |
| `MAIL_USE_TLS` | `0` | `1` for STARTTLS (port 587). Implicit SSL on port 465 is not supported. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | unset | SMTP login |
| `MAIL_DEFAULT_SENDER` | `no-reply@weight-tracker.local` | The From address |
| `MAIL_SUPPRESS_SEND` | `1` | `0` to really send mail |
| `CHECK_EMAIL_MX` | `1` | `0` to disable the MX-record check at sign-up |

Signed-in users stay signed in when they close the browser: the `session` cookie lasts
30 days after the last visit (renewed on every visit) and never more than 90 days after the
sign-in, after which the email code is asked for again. Logging out removes it. The cookie is
signed with `SECRET_KEY` (anyone who knows the key can forge a sign-in, so keep it secret and
constant; changing it signs everyone out) and holds the signed-in address, so with
`SESSION_COOKIE_SECURE=1` it is only sent over HTTPS.

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
Environment="PATH=/srv/kilo/.venv/bin:/usr/bin"
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
    client_max_body_size 8m;   # the app limits uploads itself: 8 MB for imports, 1 MB elsewhere

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

With Apache (`mod_proxy`, `mod_proxy_http` and `mod_headers` enabled):

```apache
<VirtualHost *:443>
    ServerName kilo.example.com
    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Real-IP "expr=%{REMOTE_ADDR}"
    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/
</VirtualHost>
```

The page language comes from the browser's `Accept-Language` header, which
both proxies pass on, and every page answers with `Vary: Accept-Language`. If
you cache responses in front of the app (Apache `mod_cache`, a CDN), let the
cache honour `Vary`: a cache that ignores it, or a rule that strips it (`Header
unset Vary`), serves the first visitor's language to everyone.

#### Logging the visitor's IP address

Behind a proxy, gunicorn's access log shows `127.0.0.1` for everyone, because it
logs the address of whoever connected to it. The proxy examples above therefore
set `X-Real-IP`; tell gunicorn to log that header instead, in a
`gunicorn.conf.py` (start gunicorn with `--config gunicorn.conf.py`):

```python
accesslog = "-"   # or a file; "-" goes to the journal
access_log_format = '%({x-real-ip}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
```

(Passing it as `--access-logformat` on the `ExecStart` line of a systemd unit
needs every `%` doubled to `%%`, because systemd reads `%` as a specifier; the
config file avoids that.)

`set` replaces whatever the client sent, so the header cannot be forged, as long
as gunicorn only listens on `127.0.0.1` (the examples bind it there). Restart
gunicorn afterwards. The app itself never needs the address; if you add something
that does (rate limiting), wrap it in Werkzeug's `ProxyFix(x_for=1)`. If another
proxy or a CDN sits in front of this one, the address you see is that proxy's;
with Apache add `mod_remoteip` (`RemoteIPHeader X-Forwarded-For`).

### Backups and updates

Back up the database with SQLite's own tool, not a plain file copy (recent
writes can still be in the `-wal` file):

```bash
sqlite3 /srv/kilo/instance/weight.db ".backup /backups/weight.db"
```

To update: `git pull`, `.venv/bin/pip install -r requirements.txt`,
`.venv/bin/pybabel compile -d translations` (the translations are compiled at
deploy time, not stored in git), then `sudo systemctl restart kilo`. New
database columns are added automatically at startup.

The About page shows the running version, read from the git checkout: the tag
of the checked-out commit if it has one (for example `git tag v1.0.0`),
otherwise the 7-character commit id, plus the commit date. It is read once, so
restart the service after updating. If no version is shown, the app couldn't
run `git` on its folder - for example when the checkout belongs to another
user (`git config --global --add safe.directory /srv/kilo` fixes that).

## Test

```bash
pytest
```

The tests also check that the translations are complete and up to date; you can
run that check on its own with `python scripts/check_i18n.py` (see
[TRANSLATING.md](TRANSLATING.md)).

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
