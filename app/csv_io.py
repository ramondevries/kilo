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

"""CSV import and export of weight entries.

The format is one `date,weight[,note]` line per entry, with dates as d-M-yy or
d-M-yyyy and weights in kilograms.
"""

import csv
import io
from datetime import date

from flask_babel import gettext as _

from app.utils import parse_decimal

MIN_WEIGHT_KG = 1
MAX_WEIGHT_KG = 1000


class CsvRowError(Exception):
    """A CSV row could not be parsed (the caller words the message, with the line number)."""


def parse_ddmyy(text):
    """Parse a d-M-yy or d-M-yyyy date, e.g. '23-9-26' or '23-9-2026'."""
    parts = text.strip().split("-")
    if len(parts) != 3:
        raise CsvRowError()
    try:
        day, month, year = (int(p) for p in parts)
    except ValueError:
        raise CsvRowError()
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        raise CsvRowError()


def format_ddmyy(d):
    """Format a date as d-M-yy, e.g. 23-9-26 (the reverse of `parse_ddmyy`)."""
    return f"{d.day}-{d.month}-{d.strftime('%y')}"


def parse_csv(file_bytes):
    """Parse CSV bytes of `date,weight,note` lines (weight always in kg).

    Returns (rows, errors) where rows is a list of
    (entry_date, weight_kg, note) tuples and errors is a list of
    one-line descriptions of skipped rows.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace") if isinstance(file_bytes, bytes) else file_bytes

    rows = []
    errors = []
    for lineno, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < 2:
            # NOTE: date,weight[,note] names the columns of a CSV line; translate the names (note is optional).
            errors.append(_("line %(line)d: expected date,weight[,note]", line=lineno))
            continue

        date_str, weight_str = row[0].strip(), row[1].strip()
        note = ",".join(row[2:]).strip()[:280] or None

        try:
            entry_date = parse_ddmyy(date_str)
        except CsvRowError:
            errors.append(_("line %(line)d: invalid date %(value)s", line=lineno, value=repr(date_str)))
            continue

        weight_kg = parse_decimal(weight_str)
        if weight_kg is None:
            errors.append(_("line %(line)d: invalid weight %(value)s", line=lineno, value=repr(weight_str)))
            continue
        if not (MIN_WEIGHT_KG <= weight_kg <= MAX_WEIGHT_KG):
            errors.append(_("line %(line)d: weight out of range", line=lineno))
            continue

        rows.append((entry_date, weight_kg, note))

    return rows, errors


def export_csv(entries):
    """Render entries as CSV text: `date,weight,note`, with the weight in kg to one decimal."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for entry in entries:
        writer.writerow([format_ddmyy(entry.entry_date), f"{entry.weight:.1f}", entry.note or ""])
    return buf.getvalue()
