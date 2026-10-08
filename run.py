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

"""Development entry point: `python run.py` starts the app with the debugger on."""

import logging

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Flask picks the logger's level when the logger is first used, and create_app() already
    # used it (the weak SECRET_KEY warning) before debug mode is switched on below. Without
    # this the sign-in code, logged at INFO so it can be read from the console, is dropped.
    app.logger.setLevel(logging.DEBUG)
    app.run(debug=True)
