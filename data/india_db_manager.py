"""
data/india_db_manager.py

SQLite CRUD layer for the India Macro pipeline.
Manages two tables:
  - india_monthly  : monthly macro indicators (replaces india_manual.csv)
  - india_weekly   : weekly forex reserves (released every Friday by RBI)

All DB access goes through this module — no inline SQL elsewhere.
Pattern mirrors rbi_sentinel/db/manager.py.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger("india.db")

DB_PATH = Path(__file__).parent / "india_macro.db"

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── Monthly macro indicators ──────────────────────────────────────────────────
-- One row per calendar month.  MANUAL columns are user-entered;
-- AUTO columns are populated by india_fetcher.py.

CREATE TABLE IF NOT EXISTS india_monthly (
    month                   TEXT PRIMARY KEY,   -- "YYYY-MM"

    -- MANUAL
    india_mfg_pmi           REAL,               -- S&P Global Mfg PMI
    india_svc_pmi           REAL,               -- S&P Global Services PMI
    india_composite_pmi     REAL,               -- Blended composite PMI
    india_gst_revenue       REAL,               -- ₹ Lakh Crore (Finance Ministry)
    india_unemployment      REAL,               -- % (PLFS, sparse)

    -- AUTO: FRED (OECD-sourced, ~6-week lag)
    india_cpi_yoy           REAL,               -- Headline CPI % YoY  [CPALTT01INM657N]
    india_core_cpi_yoy      REAL,               -- Core CPI % YoY      [CPGRLE01INM657N]
    india_food_cpi_yoy      REAL,               -- Food CPI % YoY      [CPALFD01INM661N]

    -- AUTO: DBIE
    india_bank_credit_yoy   REAL,               -- Bank credit growth % YoY
    india_deposit_growth_yoy REAL,              -- Bank deposit growth % YoY
    india_iip_yoy           REAL,               -- IIP industrial production % YoY
    india_m3_yoy            REAL,               -- M3 money supply % YoY
    india_exports_usd_bn    REAL,               -- Merchandise exports USD bn
    india_imports_usd_bn    REAL,               -- Merchandise imports USD bn
    india_trade_deficit_usd_bn REAL,            -- Trade deficit USD bn (derived)

    -- Audit
    source_flags            TEXT,               -- JSON: {"cpi_yoy": "fred", ...}
    fetched_at              TEXT DEFAULT (datetime('now'))
);

-- ── Weekly forex reserves ─────────────────────────────────────────────────────
-- RBI releases weekly forex reserve data every Friday.

CREATE TABLE IF NOT EXISTS india_weekly (
    week_ending             TEXT PRIMARY KEY,   -- "YYYY-MM-DD" (Friday)
    forex_reserves_usd_bn   REAL,               -- Total reserves USD bn
    forex_reserves_wow_chg  REAL,               -- WoW change USD bn (derived)
    fpi_net_flows_usd_bn    REAL,               -- Net FPI/FII flows USD bn (NSE, jugaad-data)
    fetched_at              TEXT DEFAULT (datetime('now'))
);

-- ── Indices ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_monthly_month ON india_monthly(month);
CREATE INDEX IF NOT EXISTS idx_weekly_date   ON india_weekly(week_ending);
"""


# ── Connection ─────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist. Safe to call on every pipeline run."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)
    log.info("India macro DB initialised at %s", DB_PATH)


# ── india_monthly ──────────────────────────────────────────────────────────────

def upsert_monthly(month: str, data: dict) -> None:
    """
    Insert or update a monthly row.  Idempotent.
    Only updates columns present in `data` — omitted columns are left unchanged.

    Args:
        month: "YYYY-MM"
        data:  dict of column → value  (column names must match schema)
    """
    if not data:
        return

    cols = list(data.keys())
    placeholders = ", ".join("?" * len(cols))
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in cols)

    sql = f"""
        INSERT INTO india_monthly (month, {', '.join(cols)})
        VALUES (?, {placeholders})
        ON CONFLICT(month) DO UPDATE SET
            {update_clause},
            fetched_at = datetime('now')
    """
    with _connect() as conn:
        conn.execute(sql, [month] + list(data.values()))
    log.debug("Upserted india_monthly for %s", month)


def get_monthly_series(
    columns: Optional[list[str]] = None,
    n_months: Optional[int] = None,
) -> pd.DataFrame:
    """
    Return a DataFrame of monthly data, sorted oldest-first.
    Renames 'month' → 'date' and parses it as datetime for chart compatibility.

    Args:
        columns:  list of column names to fetch (None = all columns)
        n_months: limit to last N months (None = all available)
    """
    col_clause = ", ".join(["month"] + columns) if columns else "*"
    if n_months:
        sql = f"""
            SELECT {col_clause} FROM india_monthly
            ORDER BY month DESC LIMIT ?
        """
        params = [n_months]
    else:
        sql = f"SELECT {col_clause} FROM india_monthly ORDER BY month ASC"
        params = []

    with _connect() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        return df

    # Normalise for chart compatibility
    df = df.sort_values("month").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["month"])
    df = df.drop(columns=["month", "source_flags", "fetched_at"], errors="ignore")
    return df


# ── india_weekly ───────────────────────────────────────────────────────────────

def upsert_weekly(week_ending: str, data: dict) -> None:
    """
    Insert or update a weekly forex reserve row.  Idempotent.

    Args:
        week_ending: "YYYY-MM-DD" (the Friday of the RBI release)
        data: dict with keys: forex_reserves_usd_bn, forex_reserves_wow_chg
    """
    if not data:
        return

    cols = list(data.keys())
    placeholders = ", ".join("?" * len(cols))
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in cols)

    sql = f"""
        INSERT INTO india_weekly (week_ending, {', '.join(cols)})
        VALUES (?, {placeholders})
        ON CONFLICT(week_ending) DO UPDATE SET
            {update_clause},
            fetched_at = datetime('now')
    """
    with _connect() as conn:
        conn.execute(sql, [week_ending] + list(data.values()))
    log.debug("Upserted india_weekly for %s", week_ending)


def get_weekly_series(n_weeks: Optional[int] = None) -> pd.DataFrame:
    """
    Return a DataFrame of weekly forex reserve data, sorted oldest-first.
    Parses 'week_ending' as datetime.

    Args:
        n_weeks: limit to last N weeks (None = all available)
    """
    if n_weeks:
        sql = "SELECT * FROM india_weekly ORDER BY week_ending DESC LIMIT ?"
        params = [n_weeks]
    else:
        sql = "SELECT * FROM india_weekly ORDER BY week_ending ASC"
        params = []

    with _connect() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        return df

    df = df.sort_values("week_ending").reset_index(drop=True)
    df["week_ending"] = pd.to_datetime(df["week_ending"])
    df = df.drop(columns=["fetched_at"], errors="ignore")
    return df


# ── Seed from CSV ──────────────────────────────────────────────────────────────

def seed_from_csv(csv_path: Path) -> int:
    """
    One-time migration: load all rows from the legacy india_manual.csv into
    india_monthly.  Skips rows that already exist (idempotent).

    Returns the number of rows upserted.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.dropna(subset=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Remove trailing unnamed columns (artifact of extra commas in CSV)
    df = df[[c for c in df.columns if not c.startswith("Unnamed")]]

    # Rename 'date' → 'month' in "YYYY-MM" format
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df = df.drop(columns=["date"])

    # Column rename map: CSV name → DB column name
    rename_map = {
        "india_mfg_pmi":         "india_mfg_pmi",
        "india_svc_pmi":         "india_svc_pmi",
        "india_composite_pmi":   "india_composite_pmi",
        "india_gst_revenue":     "india_gst_revenue",
        "india_bank_credit_yoy": "india_bank_credit_yoy",
        "india_unemployment":    "india_unemployment",
        "india_cpi_yoy":         "india_cpi_yoy",
        "india_core_cpi_yoy":    "india_core_cpi_yoy",
        "india_food_cpi_yoy":    "india_food_cpi_yoy",
    }

    count = 0
    for _, row in df.iterrows():
        month = row["month"]
        data = {}
        for csv_col, db_col in rename_map.items():
            if csv_col in row.index:
                val = row[csv_col]
                if pd.notna(val):
                    data[db_col] = float(val)
        if data:
            upsert_monthly(month, data)
            count += 1

    log.info("Seeded %d months from %s into india_monthly", count, csv_path.name)
    return count


# ── Diagnostics ────────────────────────────────────────────────────────────────

def get_latest_monthly_date() -> Optional[str]:
    """Return the most recent month in india_monthly, or None if empty."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT month FROM india_monthly ORDER BY month DESC LIMIT 1"
        ).fetchone()
    return row["month"] if row else None


def get_latest_weekly_date() -> Optional[str]:
    """Return the most recent week_ending in india_weekly, or None if empty."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT week_ending FROM india_weekly ORDER BY week_ending DESC LIMIT 1"
        ).fetchone()
    return row["week_ending"] if row else None


def db_exists() -> bool:
    """Return True if the DB file exists and has been initialised."""
    return DB_PATH.exists()
