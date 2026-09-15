"""
India manual data entry.

Four India series have no free API and must be keyed in each month: the two
PMIs, GST collections, CPI, and the PLFS unemployment rate. This replaces the
old workflow of editing a constant at the top of a script and running it.

    python -m econ.india.manual status
    python -m econ.india.manual set 2026-05 --mfg-pmi 57.2 --svc-pmi 60.1 --gst 2.01
    python -m econ.india.manual set 2026-05 --cpi 2.8 --core-cpi 4.1
    python -m econ.india.manual show 2026-05

Partial months are fine — set what has been released and come back for the
rest. Every write is range-checked, records its source in source_flags, and
prints the before/after so a fat-fingered decimal is visible immediately.

Sources and the monthly release calendar: docs/project_reminders.md
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "india_macro.db"

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Field:
    """One manually entered series: its CLI flag, DB column, and sane bounds."""

    def __init__(self, flag, column, unit, low, high, source, help_text):
        self.flag = flag
        self.column = column
        self.unit = unit
        self.low = low
        self.high = high
        self.source = source
        self.help_text = help_text

    @property
    def dest(self):
        return self.flag.lstrip("-").replace("-", "_")


# Bounds are deliberately wide — they exist to catch a misplaced decimal or a
# value typed into the wrong flag, not to second-guess the data.
FIELDS = [
    Field("--mfg-pmi", "india_mfg_pmi", "index", 25, 75, "spglobal",
          "Manufacturing PMI (S&P Global, 1st business day)"),
    Field("--svc-pmi", "india_svc_pmi", "index", 25, 75, "spglobal",
          "Services PMI (S&P Global, ~3rd business day)"),
    Field("--gst", "india_gst_revenue", "Rs lakh crore", 0.5, 5.0, "pib",
          "Gross GST collections in Rs LAKH CRORE, e.g. 1.96 (PIB, 1st)"),
    Field("--cpi", "india_cpi_yoy", "% YoY", -5, 25, "mospi",
          "CPI headline %% YoY (MoSPI, ~12th)"),
    Field("--core-cpi", "india_core_cpi_yoy", "% YoY", -5, 25, "mospi",
          "CPI core %% YoY (MoSPI, ~12th)"),
    Field("--food-cpi", "india_food_cpi_yoy", "% YoY", -10, 30, "mospi",
          "CPI food & beverages %% YoY (MoSPI, ~12th)"),
    Field("--unemployment", "india_unemployment", "%", 0, 30, "plfs",
          "PLFS unemployment rate %% (MoSPI)"),
    # IIP is entered by hand rather than parsed from the DBIE workbook. In the
    # September 2026 vintage RBI switched that column to a basis that matches no
    # published MoSPI figure (Dec-25 read 147.1 where MoSPI publishes 170.7) and
    # carried an unexplained 16% step at Jan-2026, which turned every 2026 YoY
    # into a comparison across a discontinuity. MoSPI states the growth rate
    # directly in its monthly release, so that number is taken at source.
    Field("--iip", "india_iip_yoy", "% YoY", -30, 30, "mospi",
          "IIP %% YoY as stated by MoSPI/PIB, e.g. 4.8 (~12th, with CPI)"),
]
BY_DEST = {f.dest: f for f in FIELDS}

# Composite PMI is published as a weighted blend of the two headline PMIs.
# Derived rather than typed, so it can never drift out of step with its inputs.
COMPOSITE_COLUMN = "india_composite_pmi"
COMPOSITE_MFG_WEIGHT = 0.4
COMPOSITE_SVC_WEIGHT = 0.6


def connect():
    if not DB_PATH.exists():
        sys.exit(f"Database not found: {DB_PATH}\n"
                 f"Run: python data/fetchers/india_fetcher.py --append")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def read_month(conn, month):
    return conn.execute(
        "SELECT * FROM india_monthly WHERE month = ?", (month,)
    ).fetchone()


def fmt(value):
    return "—" if value is None else f"{value:g}"


# ── set ─────────────────────────────────────────────────────────────────────

def cmd_set(args):
    month = args.month
    if not MONTH_RE.match(month):
        sys.exit(f"Month must look like 2026-05, got: {month!r}")

    supplied = {
        BY_DEST[d]: v
        for d, v in vars(args).items()
        if d in BY_DEST and v is not None
    }
    if not supplied:
        sys.exit("Nothing to set. Pass at least one value — see --help.")

    errors = []
    for field, value in supplied.items():
        if not (field.low <= value <= field.high):
            errors.append(
                f"  {field.flag} {value} is outside {field.low}–{field.high} "
                f"({field.unit}). {field.help_text}"
            )
    if errors:
        sys.exit("Refusing to write — values look wrong:\n" + "\n".join(errors))

    conn = connect()
    existing = read_month(conn, month)

    if existing is None:
        print(f"  {month} has no row yet — it will be created.")
        before = {}
    else:
        before = {f.column: existing[f.column] for f in supplied}

    updates = {f.column: v for f, v in supplied.items()}

    # Derive composite PMI whenever both inputs are known after this write.
    merged_mfg = updates.get("india_mfg_pmi",
                             existing["india_mfg_pmi"] if existing else None)
    merged_svc = updates.get("india_svc_pmi",
                             existing["india_svc_pmi"] if existing else None)
    if merged_mfg is not None and merged_svc is not None:
        updates[COMPOSITE_COLUMN] = round(
            COMPOSITE_MFG_WEIGHT * merged_mfg + COMPOSITE_SVC_WEIGHT * merged_svc, 2
        )

    # Merge provenance rather than replacing it, so a later fetcher run that
    # writes DBIE columns does not erase the record of what was hand-entered.
    flags = {}
    if existing is not None and existing["source_flags"]:
        try:
            flags = json.loads(existing["source_flags"])
        except (ValueError, TypeError):
            flags = {}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for field in supplied:
        flags[field.column] = f"manual:{field.source}:{stamp}"
    if COMPOSITE_COLUMN in updates:
        flags[COMPOSITE_COLUMN] = f"derived:pmi_weighted:{stamp}"

    print(f"\n  {month}")
    print(f"  {'column':<28} {'before':>10}  {'after':>10}")
    for column, value in updates.items():
        print(f"  {column:<28} {fmt(before.get(column)):>10}  {fmt(value):>10}")

    if args.dry_run:
        print("\n  --dry-run: nothing written.")
        return

    cols = list(updates) + ["source_flags", "fetched_at"]
    vals = list(updates.values()) + [
        json.dumps(flags),
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    ]
    if existing is None:
        conn.execute(
            f"INSERT INTO india_monthly (month, {', '.join(cols)}) "
            f"VALUES (?{', ?' * len(cols)})",
            [month] + vals,
        )
    else:
        conn.execute(
            f"UPDATE india_monthly SET {', '.join(f'{c} = ?' for c in cols)} "
            f"WHERE month = ?",
            vals + [month],
        )
    conn.commit()
    print(f"\n  Written. Regenerate with:  PYTHONPATH=. python generate_india.py")


# ── status ──────────────────────────────────────────────────────────────────

def cmd_status(args):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM india_monthly ORDER BY month DESC LIMIT ?", (args.months,)
    ).fetchall()
    if not rows:
        sys.exit("No rows in india_monthly.")

    labels = [f.flag.lstrip("-") for f in FIELDS]
    width = max(len(l) for l in labels) + 1

    print(f"\n  Manual series — last {len(rows)} months "
          f"(ok = present, .. = not entered)\n")
    print("  month    " + " ".join(f"{l:>{width}}" for l in labels))
    gaps = 0
    for row in rows:
        cells = []
        for field in FIELDS:
            present = row[field.column] is not None
            cells.append(f"{'ok' if present else '..':>{width}}")
            gaps += 0 if present else 1
        print(f"  {row['month']}  " + " ".join(cells))

    print(f"\n  {gaps} values not yet entered across {len(rows)} months.")
    if gaps:
        newest = rows[0]["month"]
        print(f"  e.g.  python -m econ.india.manual set {newest} --mfg-pmi 57.2")
    print("  Release calendar and source URLs: docs/project_reminders.md")


# ── show ────────────────────────────────────────────────────────────────────

def cmd_show(args):
    conn = connect()
    row = read_month(conn, args.month)
    if row is None:
        sys.exit(f"No row for {args.month}.")
    try:
        flags = json.loads(row["source_flags"] or "{}")
    except (ValueError, TypeError):
        flags = {}

    print(f"\n  {args.month}\n")
    print(f"  {'column':<28} {'value':>10}   source")
    for field in FIELDS:
        print(f"  {field.column:<28} {fmt(row[field.column]):>10}   "
              f"{flags.get(field.column, '—')}")
    print(f"  {COMPOSITE_COLUMN:<28} {fmt(row[COMPOSITE_COLUMN]):>10}   "
          f"{flags.get(COMPOSITE_COLUMN, '—')}")
    print(f"\n  last write: {row['fetched_at']}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m econ.india.manual",
        description="Enter the India series that have no API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sources and release dates: docs/project_reminders.md",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_set = sub.add_parser("set", help="write values for one month")
    p_set.add_argument("month", help="target month, e.g. 2026-05")
    p_set.add_argument("--dry-run", action="store_true",
                       help="show the change without writing")
    for field in FIELDS:
        p_set.add_argument(field.flag, type=float, metavar=field.unit.upper(),
                           help=field.help_text)
    p_set.set_defaults(func=cmd_set)

    p_status = sub.add_parser("status", help="show which values are missing")
    p_status.add_argument("--months", type=int, default=12,
                          help="how many recent months to show (default 12)")
    p_status.set_defaults(func=cmd_status)

    p_show = sub.add_parser("show", help="show one month with provenance")
    p_show.add_argument("month", help="month to show, e.g. 2026-05")
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
