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

"""Friendly answers for the errors a visitor can run into.

* An expired or missing CSRF token (a form or tab left open too long, or the
  session cookie is gone): a form is sent back to the page it came from with a
  message saying nothing was changed and to try again; the dashboard's
  background saves (JSON) get a JSON error the page turns into a "Session
  expired" dialog with a Reload button.
* A page that does not exist, or one that can only be posted to (typing /logout
  in the address bar): a browser is sent to the start page - the dashboard, or
  the sign-in form when signed out - with a message. Anything that is not a
  browser opening a page (an image, an API call, a POST) keeps a plain error.
"""

from urllib.parse import urlsplit

from flask import flash, jsonify, redirect, request, url_for
from flask_babel import gettext as _
from flask_wtf.csrf import CSRFError

# Sent as "code" in the JSON error so the page can tell an expired session from
# any other failed save.
CSRF_ERROR_CODE = "csrf_expired"


def _wants_json():
    """True for the page's own fetch() calls (JSON body or an explicit JSON Accept)."""
    return request.is_json or request.accept_mimetypes.best == "application/json"


def _back_url():
    """The page the visitor came from if it is on this site, else the start page.

    Only the path and query are used, so a foreign Referer can never send
    anyone to another site.
    """
    start = url_for("main.index")
    referrer = request.referrer
    if not referrer:
        return start
    parts = urlsplit(referrer)
    if parts.netloc != request.host or not parts.path.startswith("/") or parts.path.startswith("//"):
        return start
    return parts.path + (f"?{parts.query}" if parts.query else "")


def _is_browser_page_request():
    """A browser asking for a web page: GET, explicitly accepting HTML, not a static file."""
    return (
        request.method == "GET"
        and "text/html" in request.headers.get("Accept", "")
        and not request.path.startswith("/static/")
    )


def csrf_failed(error):
    """The CSRF token is missing or too old: say so and what to do, change nothing."""
    if _wants_json():
        message = _("Your session has expired. Reload the page and try again.")
        return jsonify(error=message, code=CSRF_ERROR_CODE), 400
    flash(_("Your session has expired and nothing was changed. Please try again."), "error")
    return redirect(_back_url())


def page_not_available(error):
    """404 or 405: send a browser to the start page, leave every other client alone."""
    if _is_browser_page_request():
        flash(_("That page isn't available, so you were taken to the start page."), "error")
        return redirect(url_for("main.index"))
    return error


def init_app(app):
    """Register the error handlers."""
    app.register_error_handler(CSRFError, csrf_failed)
    app.register_error_handler(404, page_not_available)
    app.register_error_handler(405, page_not_available)
