"""
World tab manual data entry.

A handful of World scoreboard cells have no free machine-readable source:
the manufacturing PMIs (US, euro area, UK, Japan, China), Japan's CPI, and
China's unemployment rate and 10-year yield. They live in
data/world_manual.csv and are keyed in here, one month at a time.

    python -m data.world_manual_entry status
    python -m data.world_manual_entry set 2026-08 --country US --pmi 52.4
    python -m data.world_manual_entry set 2026-08 --country CN --pmi 50.2 --unemployment 5.3
    python -m data.world_manual_entry set 2026-08 --country JP --cpi 2.9 --dry-run

A missing month shows as "awaiting entry" on the dashboard; nothing is ever
carried forward or estimated. Values are range-checked and every row
records its source. India's PMI, CPI and unemployment are NOT entered here —
they come from the India database (python -m data.india_manual_entry).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.world_settings import COUNTRIES, MANUAL_FIELDS, MANUAL_RANGES

CSV_PATH = Path(__file__).resolve().parent / "world_manual.csv"
HEADER = ["month", "country", "field", "value", "source"]
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
FLAGS = {"pmi": "mfg_pmi", "cpi": "cpi_yoy", "unemployment": "unemployment", "ten_year": "ten_year"}


class ManualDataError(ValueError):
    """A row in world_manual.csv is malformed or implausible."""


def validate_row(row: dict) -> dict:
    """Check one CSV row; return it with value as float. Raises ManualDataError."""
    month, country, field = row.get("month", ""), row.get("country", ""), row.get("field", "")
    where = f"{month} {country} {field}"
    if not MONTH.match(month):
        raise ManualDataError(f"{where}: month must be YYYY-MM")
    if (country, field) not in MANUAL_FIELDS:
        raise ManualDataError(f"{where}: not a manual cell (automatic sources are never overridden)")
    if not (row.get("source") or "").strip():
        raise ManualDataError(f"{where}: source is required")
    try:
        value = float(row["value"])
    except (TypeError, ValueError):
        raise ManualDataError(f"{where}: value {row.get('value')!r} is not a number")
    low, high = MANUAL_RANGES[field]
    if not low <= value <= high:
        raise ManualDataError(f"{where}: {value} is outside the plausible range {low}–{high}")
    if month > date.today().strftime("%Y-%m"):
        raise ManualDataError(f"{where}: month is in the future")
    return {**row, "value": value}


def load_rows(path: Path = CSV_PATH) -> list[dict]:
    """Every row, validated. Duplicate (month, country, field) rows are an error."""
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != HEADER:
            raise ManualDataError(f"{path.name}: header must be {','.join(HEADER)}")
        rows = [validate_row(r) for r in reader]
    seen = set()
    for r in rows:
        key = (r["month"], r["country"], r["field"])
        if key in seen:
            raise ManualDataError(f"{path.name}: duplicate row {' '.join(key)}")
        seen.add(key)
    return rows


def _write_rows(rows: list[dict], path: Path = CSV_PATH) -> None:
    rows = sorted(rows, key=lambda r: (r["month"], r["country"], r["field"]))
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "value": f"{float(r['value']):g}"})


def cmd_set(args) -> int:
    country = args.country.upper()
    updates = {FLAGS[k]: v for k, v in vars(args).items() if k in FLAGS and v is not None}
    if not updates:
        print("Nothing to set: pass at least one of --pmi, --cpi, --unemployment, --ten-year")
        return 1
    rows = load_rows()
    index = {(r["month"], r["country"], r["field"]): r for r in rows}
    for field, value in updates.items():
        if (country, field) not in MANUAL_FIELDS:
            print(f"Refused: {country} {field} is fetched automatically, not entered by hand.")
            return 1
        new = validate_row({
            "month": args.month, "country": country, "field": field,
            "value": value, "source": MANUAL_FIELDS[(country, field)][0],
        })
        old = index.get((args.month, country, field))
        before = f"{old['value']:g}" if old else "—"
        print(f"  {args.month} {country} {field:<13} {before:>6} -> {new['value']:g}   ({new['source']})")
        index[(args.month, country, field)] = new
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0
    _write_rows(list(index.values()))
    print(f"Saved to {CSV_PATH.relative_to(CSV_PATH.parent.parent)}")
    return 0


def cmd_status(args) -> int:
    rows = load_rows()
    have = {(r["month"], r["country"], r["field"]): r["value"] for r in rows}
    today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(args.months):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        months.append(f"{y}-{m:02d}")
    months.reverse()
    cells = sorted(MANUAL_FIELDS, key=lambda k: (list(COUNTRIES).index(k[0]), k[1]))
    print(f"{'cell':<17}" + "".join(f"{mo:>9}" for mo in months))
    for country, field in cells:
        line = f"{country + ' ' + field:<17}"
        for mo in months:
            v = have.get((mo, country, field))
            line += f"{v:>9g}" if v is not None else f"{'..':>9}"
        print(line)
    print("\n.. = not entered. Releases: PMIs on the 1st business day; Japan CPI ~3rd week;")
    print("China unemployment ~mid-month; China 10Y is the month-end close. Sources: docs/project_reminders.md")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_set = sub.add_parser("set", help="enter values for one country and month")
    p_set.add_argument("month", help="month the figure refers to, e.g. 2026-08")
    p_set.add_argument("--country", required=True, choices=[c for c in COUNTRIES if c != "IN"])
    p_set.add_argument("--pmi", type=float, help="manufacturing PMI, e.g. 52.4")
    p_set.add_argument("--cpi", type=float, help="CPI inflation, %% YoY (Japan only)")
    p_set.add_argument("--unemployment", type=float, help="unemployment rate, %% (China only)")
    p_set.add_argument("--ten-year", dest="ten_year", type=float, help="10-year yield, %% month-end (China only)")
    p_set.add_argument("--dry-run", action="store_true", help="show the change without saving")
    p_set.set_defaults(func=cmd_set)

    p_status = sub.add_parser("status", help="which manual cells are filled for recent months")
    p_status.add_argument("--months", type=int, default=6)
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ManualDataError as exc:
        print(f"Refused: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
