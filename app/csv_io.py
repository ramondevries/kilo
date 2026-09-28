import csv
import io
from datetime import date

from app.utils import from_kg, to_kg

MIN_WEIGHT_KG = 1
MAX_WEIGHT_KG = 1000


class CsvRowError(Exception):
    pass


def parse_ddmyy(text):
    """Parse a d-M-yy or d-M-yyyy date, e.g. '23-9-26' or '23-9-2026'."""
    parts = text.strip().split("-")
    if len(parts) != 3:
        raise CsvRowError(f"invalid date {text!r}")
    try:
        day, month, year = (int(p) for p in parts)
    except ValueError:
        raise CsvRowError(f"invalid date {text!r}")
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        raise CsvRowError(f"invalid date {text!r}")


def format_ddmyy(d):
    return f"{d.day}-{d.month}-{d.strftime('%y')}"


def parse_csv(file_bytes, weight_unit):
    """Parse CSV bytes of `date,weight,note` lines (weight always in kg).

    Returns (rows, errors) where rows is a list of
    (entry_date, weight_in_app_unit, note) tuples and errors is a list of
    one-line descriptions of skipped rows.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace") if isinstance(file_bytes, bytes) else file_bytes

    rows = []
    errors = []
    for lineno, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < 2:
            errors.append(f"line {lineno}: expected date,weight[,note]")
            continue

        date_str, weight_str = row[0].strip(), row[1].strip()
        note = ",".join(row[2:]).strip()[:280] or None

        try:
            entry_date = parse_ddmyy(date_str)
        except CsvRowError as exc:
            errors.append(f"line {lineno}: {exc}")
            continue

        try:
            weight_kg = float(weight_str)
        except ValueError:
            errors.append(f"line {lineno}: invalid weight {weight_str!r}")
            continue
        if not (MIN_WEIGHT_KG <= weight_kg <= MAX_WEIGHT_KG):
            errors.append(f"line {lineno}: weight out of range")
            continue

        rows.append((entry_date, from_kg(weight_kg, weight_unit), note))

    return rows, errors


def export_csv(entries, weight_unit):
    buf = io.StringIO()
    writer = csv.writer(buf)
    for entry in entries:
        weight_kg = to_kg(entry.weight, weight_unit)
        writer.writerow([format_ddmyy(entry.entry_date), f"{weight_kg:.1f}", entry.note or ""])
    return buf.getvalue()
