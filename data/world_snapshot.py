"""
World tab snapshot.

Fetches everything the World tab shows outside its charts — central bank
rates, the six-economy scoreboard, the growth/inflation regime and the US
data calendar — and returns it as one JSON-ready dict.

Rules (see docs/project_context.md §10):
  * No value is ever estimated, carried forward or filled in.
  * An automatic source that fails, or has stopped updating, is a PROBLEM:
    the caller writes what it has and exits non-zero, so the workflow fails
    and nothing half-broken is published.
  * A manual or hand-refreshed cell that is missing or old is shown as
    "awaiting entry" / "stale" on the page; that is not a problem.

The pure helpers at the top (yoy_by_date, last_move, regime_label, …) are
covered by tests/test_world.py.
"""

from __future__ import annotations

import io
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from config.world_settings import (
    BIS_POLICY_AREAS,
    CELL_SOURCES,
    CENTRAL_BANKS,
    COUNTRIES,
    FRED_RELEASES,
    FX_TICKERS,
    HAND_REFRESHED,
    MAX_AGE_OVERRIDES,
    OECD_CLI_AREAS,
    OECD_CLI_COUNTRIES,
    OECD_CPI_AREAS,
    OECD_UNEMP_AREAS,
    SCOREBOARD_COLUMNS,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDIA_DB = PROJECT_ROOT / "data" / "india_macro.db"
DBIE_WORKBOOK = PROJECT_ROOT / "data" / "50 Macroeconomic Indicators.xlsx"
HEADERS = {"User-Agent": "Mozilla/5.0 (EconomicsHub data pipeline; +https://github.com/shreyasxi/the-economics-hub)"}


# ═══════════════════════════════════════════════
# PURE HELPERS
# ═══════════════════════════════════════════════

def monthly(series: pd.Series) -> pd.Series:
    """Index a monthly series by month start, dropping gaps (never filling them)."""
    s = series.dropna().astype(float)
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
    return s[~s.index.duplicated(keep="last")].sort_index()


def yoy_by_date(index_level: pd.Series) -> pd.Series:
    """
    Year-on-year % change matched by calendar month, not by row position.

    FRED has no October 2025 CPI (the US shutdown cancelled it). Counting 12
    rows back then compares August 2026 with July 2025 — a 13-month change
    that put US CPI at 3.71% instead of 3.35%. A month with no value a year
    earlier gets no YoY figure.
    """
    s = monthly(index_level)
    prior = s.copy()
    prior.index = prior.index + pd.DateOffset(months=12)
    return ((s / prior.reindex(s.index) - 1) * 100).dropna()


def value_months_ago(s: pd.Series, months: int) -> float | None:
    """Value exactly `months` calendar months before the latest, or None if that month is missing."""
    if s.empty:
        return None
    target = s.index[-1] - pd.DateOffset(months=months)
    return float(s[target]) if target in s.index else None


def value_days_ago(s: pd.Series, days: int) -> float | None:
    """Last value on or before `days` before the latest observation."""
    if s.empty:
        return None
    earlier = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
    return float(earlier.iloc[-1]) if not earlier.empty else None


def last_move(s: pd.Series) -> dict | None:
    """Date and size (bps) of the most recent change in a daily policy-rate series."""
    s = s.dropna()
    changes = s.diff()
    changes = changes[changes.abs() > 1e-9]
    if changes.empty:
        return None
    when = changes.index[-1]
    return {"date": when.strftime("%Y-%m-%d"), "bps": int(round(changes.iloc[-1] * 100))}


def parse_fomc_range(text: str) -> tuple[float, float]:
    """
    Target range from an FOMC statement, e.g. '...by 1/4 percentage point to
    3-3/4 to 4 percent' -> (3.75, 4.0). The decision sentence comes before any
    dissent ('preferred to raise the target range...'), so the first match wins.
    """
    m = re.search(r"target range for the federal funds rate\b.*?\b(?:to|at) "
                  r"(\d+(?:-\d/\d)?|\d/\d) to (\d+(?:-\d/\d)?|\d/\d) percent", text, flags=re.S)
    if not m:
        raise ValueError("FOMC statement: no target range sentence found — has the wording changed?")

    def number(s: str) -> float:
        whole, _, frac = s.rpartition("-") if "-" in s else ("", "", s)
        if "/" in frac:
            n, d = frac.split("/")
            return (float(whole) if whole else 0.0) + int(n) / int(d)
        return float(frac)

    return number(m.group(1)), number(m.group(2))


def apply_fomc_decision(lo: pd.Series, hi: pd.Series, decision: dict) -> tuple[pd.Series, pd.Series]:
    """
    FRED dates a new target range from the day it takes effect (the day after
    the announcement) and only posts that observation the next US morning, so
    for ~18 hours after a decision FRED still shows the old range. The Fed's own
    statement is the authority: when FRED has nothing from the effective day
    on, the announced range is added on that day. When FRED already covers it,
    the two must agree, otherwise one of the sources is wrong and we raise.
    """
    effective = pd.Timestamp(decision["date"]) + pd.Timedelta(days=1)
    new_lo, new_hi = decision["lo"], decision["hi"]
    if hi.index[-1] >= effective:
        got = (float(lo[lo.index >= effective].iloc[0]), float(hi[hi.index >= effective].iloc[0]))
        if abs(got[0] - new_lo) > 1e-9 or abs(got[1] - new_hi) > 1e-9:
            raise ValueError(f"FRED range {got[0]:.2f}-{got[1]:.2f} on {effective:%Y-%m-%d} disagrees with the "
                             f"FOMC statement of {decision['date']} ({new_lo:.2f}-{new_hi:.2f})")
        return lo, hi
    return (pd.concat([lo, pd.Series([new_lo], index=[effective])]),
            pd.concat([hi, pd.Series([new_hi], index=[effective])]))


def age_days(period: str, today: date) -> int:
    """Days from the start of an observation period ('YYYY-MM' or 'YYYY-MM-DD') to today."""
    start = datetime.strptime(period, "%Y-%m" if len(period) == 7 else "%Y-%m-%d").date()
    return (today - start).days


def regime_label(growth_change: float, inflation_change: float) -> str:
    """Quadrant from leading-indicator momentum (x) and inflation momentum (y)."""
    if growth_change >= 0:
        return "Overheating" if inflation_change >= 0 else "Goldilocks"
    return "Stagflation" if inflation_change >= 0 else "Slowdown"


def fx_ytd_pct(closes: pd.Series, usd_per_local: bool, today: date) -> tuple[float, str] | None:
    """
    Year-to-date change of a currency against the dollar, in %; positive =
    the local currency strengthened. For DXY (the US row) positive = a
    stronger dollar. Measured from the last close of the previous year.
    """
    s = closes.dropna()
    base = s[s.index.year < today.year]
    cur = s[s.index.year == today.year]
    if base.empty or cur.empty:
        return None
    b, c = float(base.iloc[-1]), float(cur.iloc[-1])
    pct = (c / b - 1) * 100 if usd_per_local else (b / c - 1) * 100
    return pct, cur.index[-1].strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════
# FETCHERS — each raises on failure
# ═══════════════════════════════════════════════

def _get(url: str, params: dict | None = None, attempts: int = 3) -> requests.Response:
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == attempts - 1:
                raise
            time.sleep(4 * (attempt + 1))


def fetch_oecd(flow: str, key: str, start: str) -> dict[str, pd.Series]:
    """OECD SDMX data as {REF_AREA: monthly Series}. One series per area is required."""
    r = _get(f"https://sdmx.oecd.org/public/rest/data/{flow}/{key}",
             {"startPeriod": start, "dimensionAtObservation": "AllDimensions", "format": "csv"})
    df = pd.read_csv(io.StringIO(r.text))
    out = {}
    for area, g in df.groupby("REF_AREA"):
        if g["TIME_PERIOD"].duplicated().any():
            raise ValueError(f"OECD {flow}: more than one series for {area} — the key is too loose")
        out[area] = monthly(pd.Series(g["OBS_VALUE"].values, index=pd.to_datetime(g["TIME_PERIOD"])))
    return out


def fetch_bis_policy(areas: list[str], start: str) -> dict[str, pd.Series]:
    """BIS central bank policy rates, daily, as {area: Series}."""
    r = _get(f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{'+'.join(areas)}",
             {"startPeriod": start, "format": "csv"})
    df = pd.read_csv(io.StringIO(r.text))
    return {
        area: pd.Series(g["OBS_VALUE"].values, index=pd.to_datetime(g["TIME_PERIOD"])).dropna().sort_index()
        for area, g in df.groupby("REF_AREA")
    }


def fetch_eurostat(dataset: str, params: dict) -> pd.Series:
    """
    A Eurostat JSON-stat query as a monthly Series. When several geographies
    come back (the euro area code changes as members join: EA20 -> EA21) the
    one with the latest observation is used.
    """
    j = _get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}",
             {**params, "format": "JSON", "lang": "EN"}).json()
    ids, sizes = j["id"], j["size"]
    strides = [int(np.prod(sizes[i + 1:])) for i in range(len(sizes))]
    positions = {d: {pos: code for code, pos in j["dimension"][d]["category"]["index"].items()} for d in ids}
    by_geo: dict[str, dict] = {}
    for flat, value in j["value"].items():
        flat, coords = int(flat), {}
        for d, stride, size in zip(ids, strides, sizes):
            coords[d] = positions[d][(flat // stride) % size]
        by_geo.setdefault(coords["geo"], {})[coords["time"]] = value
    if not by_geo:
        raise ValueError(f"Eurostat {dataset}: no observations returned")
    geo = max(by_geo, key=lambda g: max(by_geo[g]))
    return monthly(pd.Series(by_geo[geo]).rename(index=pd.Timestamp))


def fetch_bundesbank_10y(start: str) -> pd.Series:
    r = _get("https://api.statistiken.bundesbank.de/rest/data/BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A",
             {"startPeriod": start, "format": "csv", "lang": "en"})
    rows = {}
    for line in r.text.splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and len(parts[0]) == 10 and parts[0][4] == "-":
            try:
                rows[pd.Timestamp(parts[0])] = float(parts[1])
            except ValueError:
                continue   # "." = no value that day
    if not rows:
        raise ValueError("Bundesbank: no yields parsed")
    return pd.Series(rows).sort_index()


def fetch_boe(code: str, start: date) -> pd.Series:
    r = _get("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp",
             {"csv.x": "yes", "Datefrom": start.strftime("%d/%b/%Y"), "Dateto": "now",
              "SeriesCodes": code, "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N"})
    df = pd.read_csv(io.StringIO(r.text))
    if code not in df.columns:
        raise ValueError(f"Bank of England: {code} missing from response")
    return pd.Series(pd.to_numeric(df[code], errors="coerce").values,
                     index=pd.to_datetime(df["DATE"], format="%d %b %Y")).dropna().sort_index()


FOMC_FEED = "https://www.federalreserve.gov/feeds/press_monetary.xml"


def fetch_fomc_decision() -> dict:
    """The latest FOMC statement in the Fed's monetary policy feed: {'date', 'lo', 'hi', 'url'}."""
    root = ET.fromstring(_get(FOMC_FEED).content)
    for item in root.iter("item"):
        if (item.findtext("title") or "").strip() == "Federal Reserve issues FOMC statement":
            url = (item.findtext("link") or "").strip()
            when = parsedate_to_datetime((item.findtext("pubDate") or "").strip()).date()
            text = re.sub(r"<[^>]+>", " ", _get(url).text)
            lo, hi = parse_fomc_range(re.sub(r"\s+", " ", text))
            return {"date": when.isoformat(), "lo": lo, "hi": hi, "url": url}
    raise ValueError("Fed press feed: no FOMC statement among the recent releases")


def fetch_jgb_10y() -> pd.Series:
    """Japan 10-year JGB yield: MoF's history file (to last month) plus this month's file."""
    base = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"
    frames = []
    for url in (base + "historical/jgbcme_all.csv", base + "jgbcme.csv"):
        df = pd.read_csv(io.StringIO(_get(url).text), skiprows=1)
        if "10Y" not in df.columns:
            raise ValueError(f"MoF JGB file {url}: no 10Y column")
        frames.append(pd.Series(pd.to_numeric(df["10Y"], errors="coerce").values,
                                index=pd.to_datetime(df["Date"], format="%Y/%m/%d", errors="coerce")))
    s = pd.concat(frames).dropna()
    s = s[s.index.notna()]
    return s[~s.index.duplicated(keep="last")].sort_index()


def fetch_fx(ticker: str, today: date) -> pd.Series:
    import yfinance as yf
    df = yf.download(ticker, start=f"{today.year - 1}-12-01", progress=False, auto_adjust=False)
    closes = df["Close"]
    if isinstance(closes, pd.DataFrame):
        closes = closes.iloc[:, 0]
    return closes.dropna()


def read_india_db(path: Path = INDIA_DB) -> dict[str, pd.Series]:
    with sqlite3.connect(path) as conn:
        df = pd.read_sql("SELECT month, india_mfg_pmi, india_cpi_yoy, india_unemployment FROM india_monthly", conn)
    df.index = pd.to_datetime(df.pop("month"))
    return {
        "mfg_pmi": monthly(df["india_mfg_pmi"]),
        "cpi_yoy": monthly(df["india_cpi_yoy"]),
        "unemployment": monthly(df["india_unemployment"]),
    }


def read_dbie_ten_year(path: Path = DBIE_WORKBOOK) -> pd.Series:
    """FBIL 10-year G-Sec yield from the RBI DBIE workbook's Weekly sheet."""
    col = "10-Year G-Sec Yield (FBIL) (%)"
    df = pd.read_excel(path, sheet_name="Weekly", header=3)
    if col not in df.columns or "Period" not in df.columns:
        raise ValueError(f"DBIE workbook: Weekly sheet has no '{col}' column — RBI changed the layout")
    s = pd.Series(pd.to_numeric(df[col], errors="coerce").values, index=pd.to_datetime(df["Period"], errors="coerce"))
    return s[s.index.notna()].dropna().sort_index()


def read_rbi_repo(db_path: Path) -> tuple[float, str] | None:
    """Repo rate and decision date of the latest policy cycle in the RBI Sentinel database."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT policy_cycle, repo_rate_pct FROM mpc_meetings "
            "WHERE repo_rate_pct IS NOT NULL ORDER BY policy_cycle DESC, meeting_date DESC LIMIT 1"
        ).fetchone()
    return (float(row[1]), row[0]) if row else None


def read_manual(rows: list[dict]) -> dict[tuple[str, str], pd.Series]:
    grouped: dict[tuple[str, str], dict] = {}
    for r in rows:
        grouped.setdefault((r["country"], r["field"]), {})[pd.Timestamp(r["month"] + "-01")] = r["value"]
    return {k: pd.Series(v).sort_index() for k, v in grouped.items()}


def fetch_release_calendar(api_key: str, today: date) -> list[dict]:
    """Upcoming US release dates from FRED's release calendar."""
    events = []
    for rid, label in FRED_RELEASES.items():
        j = _get("https://api.stlouisfed.org/fred/release/dates", {
            "release_id": rid, "api_key": api_key, "file_type": "json",
            "realtime_start": today.isoformat(), "include_release_dates_with_no_data": "true",
            "sort_order": "asc", "limit": 6,
        }).json()
        events += [{"date": d["date"], "label": label, "kind": "data"}
                   for d in j.get("release_dates", []) if d["date"] >= today.isoformat()]
    return sorted(events, key=lambda e: e["date"])


# ═══════════════════════════════════════════════
# BUILD
# ═══════════════════════════════════════════════

class _Collector:
    """Runs fetches, keeping going after a failure but remembering it."""

    def __init__(self):
        self.problems: list[str] = []

    def run(self, label: str, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001 — every failure is reported, none hidden
            self.problems.append(f"{label}: {type(exc).__name__}: {str(exc)[:200]}")
            return None


def _cell(country: str, column: str, series: pd.Series | None, today: date, *,
          kind: str, problems: list[str], compare: str | None = None,
          value: float | None = None, period: str | None = None, display: str | None = None) -> dict:
    """
    One scoreboard cell. `kind` is 'month' or 'day'. The change shown beside a
    value is vs the previous month (monthly) or ~one month earlier (daily)
    and is only computed when that exact earlier observation exists.
    """
    source = CELL_SOURCES[country][column]
    manual = source == "manual"
    cell = {"source": source, "manual": manual}
    if value is None and series is not None and not series.empty:
        value = float(series.iloc[-1])
        period = series.index[-1].strftime("%Y-%m" if kind == "month" else "%Y-%m-%d")
        if compare == "month":
            prev = value_months_ago(series, 1)
            cell["change"] = None if prev is None else round(value - prev, 2)
        elif compare == "day":
            prev = value_days_ago(series, 28)
            cell["change"] = None if prev is None else round(value - prev, 3)
    if value is None:
        cell["status"] = "awaiting" if manual else "unavailable"
        if not manual:
            problems.append(f"{COUNTRIES[country]['label']} {column}: no data from {source}")
        return cell

    cell.update({"value": round(value, 3), "period": period})
    if display:
        cell["display"] = display
    max_age = MAX_AGE_OVERRIDES.get((country, column), SCOREBOARD_COLUMNS[column]["max_age"])
    age = age_days(period, today)
    stale = age > max_age and not (country == "IN" and column == "policy_rate")  # holds until the next MPC
    if stale and not manual and (country, column) not in HAND_REFRESHED:
        problems.append(
            f"{COUNTRIES[country]['label']} {column}: latest {period} from {source} is {age} days old "
            f"(limit {max_age}) — the source may have stopped updating"
        )
    cell["status"] = "stale" if stale else "ok"
    return cell


def build_snapshot(fred_api_key: str, sentinel_db: Path, manual_rows: list[dict],
                   today: date | None = None) -> tuple[dict, dict, list[str]]:
    """
    Returns (snapshot, series, problems).
      snapshot  JSON-ready dict for the app
      series    pandas series the World charts draw from
      problems  automatic sources that failed or are stale — non-empty means fail the run
    """
    from fredapi import Fred

    today = today or date.today()
    c = _Collector()
    fred = Fred(api_key=fred_api_key)
    manual = read_manual(manual_rows)

    def fred_series(sid: str, start: str) -> pd.Series:
        return fred.get_series(sid, observation_start=start).dropna().astype(float)

    # ── Fetch ────────────────────────────────────────────────────────────
    us_cpi = c.run("FRED CPIAUCSL", fred_series, "CPIAUCSL", "2022-01-01")
    us_unemp = c.run("FRED UNRATE", fred_series, "UNRATE", "2024-01-01")
    fed_lo = c.run("FRED DFEDTARL", fred_series, "DFEDTARL", "2015-01-01")
    fed_hi = c.run("FRED DFEDTARU", fred_series, "DFEDTARU", "2015-01-01")
    fomc = c.run("Fed FOMC statement", fetch_fomc_decision)
    if fomc and fed_lo is not None and fed_hi is not None and not fed_lo.empty and not fed_hi.empty:
        fed_lo, fed_hi = c.run("FOMC statement vs FRED", apply_fomc_decision, fed_lo, fed_hi, fomc) or (fed_lo, fed_hi)
    boe_rate = c.run("Bank of England Bank Rate", fetch_boe, "IUDBEDR", date(2015, 1, 1))
    us_10y = c.run("FRED DGS10", fred_series, "DGS10", f"{today.year - 1}-01-01")
    ecb_dfr = c.run("FRED ECBDFR", fred_series, "ECBDFR", "2015-01-01")

    oecd_cpi = c.run("OECD CPI", fetch_oecd, "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
                     f"{'+'.join(OECD_CPI_AREAS.values())}.M.N.CPI.PA._T.N.GY", "2023-01") or {}
    oecd_unemp = c.run("OECD unemployment", fetch_oecd, "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0",
                       f"{'+'.join(OECD_UNEMP_AREAS.values())}..._Z.Y._T.Y_GE15..M", "2024-01") or {}
    oecd_cli = c.run("OECD CLI", fetch_oecd, "OECD.SDD.STES,DSD_STES@DF_CLI,4.1",
                     f"{'+'.join(sorted(set(OECD_CLI_AREAS.values()) | set(OECD_CLI_COUNTRIES)))}"
                     ".M.LI...AA...H", "2023-01") or {}
    bis = c.run("BIS policy rates", fetch_bis_policy, list(BIS_POLICY_AREAS.values()), "2015-01-01") or {}

    ea_hicp = c.run("Eurostat HICP", fetch_eurostat, "prc_hicp_minr",
                    {"geo": "EA", "unit": "RCH_A", "coicop18": "TOTAL", "sinceTimePeriod": "2023-01"})
    ea_unemp = c.run("Eurostat unemployment", fetch_eurostat, "une_rt_m",
                     {"geo": ["EA21", "EA20"], "s_adj": "SA", "age": "TOTAL", "sex": "T",
                      "unit": "PC_ACT", "sinceTimePeriod": "2024-01"})
    de_10y = c.run("Bundesbank 10Y", fetch_bundesbank_10y, f"{today.year - 1}-12-01")
    uk_10y = c.run("Bank of England 10Y", fetch_boe, "IUDMNPY", today - timedelta(days=120))
    jp_10y = c.run("MoF JGB 10Y", fetch_jgb_10y)

    india = c.run("India database", read_india_db) or {}
    in_10y = c.run("DBIE workbook 10Y", read_dbie_ten_year)
    rbi = c.run("RBI Sentinel database", read_rbi_repo, sentinel_db)
    fx = {k: c.run(f"Yahoo {t}", fetch_fx, t, today) for k, (t, _) in FX_TICKERS.items()}
    calendar = c.run("FRED release calendar", fetch_release_calendar, fred_api_key, today) or []

    # ── Central banks ────────────────────────────────────────────────────
    def bank(bid: str, s: pd.Series | None, display: str | None = None, move_series: pd.Series | None = None) -> dict:
        if s is None or s.empty:
            return {"id": bid, "status": "unavailable"}
        out = {"id": bid, "status": "ok", "rate": float(s.iloc[-1]),
               "display": display or f"{s.iloc[-1]:.2f}",
               "as_of": s.index[-1].strftime("%Y-%m-%d"),
               "last_move": last_move(move_series if move_series is not None else s)}
        if (today - s.index[-1].date()).days > SCOREBOARD_COLUMNS["policy_rate"]["max_age"]:
            c.problems.append(f"{bid} policy rate: latest observation {out['as_of']} is stale")
        return out

    fed_display = None
    if fed_lo is not None and fed_hi is not None and not fed_lo.empty and not fed_hi.empty:
        fed_display = f"{fed_lo.iloc[-1]:.2f}–{fed_hi.iloc[-1]:.2f}"
    banks = [
        bank("fed", fed_hi, fed_display),
        bank("ecb", ecb_dfr),
        bank("boe", boe_rate),
        bank("boj", bis.get("JP")),
        bank("pboc", bis.get("CN")),
    ]

    # ── Scoreboard ───────────────────────────────────────────────────────
    P = c.problems
    us_cpi_yoy = yoy_by_date(us_cpi) if us_cpi is not None else None
    cpi = {
        "US": us_cpi_yoy, "EA": ea_hicp, "UK": oecd_cpi.get("GBR"), "CN": oecd_cpi.get("CHN"),
        "JP": manual.get(("JP", "cpi_yoy")), "IN": india.get("cpi_yoy"),
    }
    unemp = {
        "US": monthly(us_unemp) if us_unemp is not None else None, "EA": ea_unemp,
        "UK": oecd_unemp.get("GBR"), "JP": oecd_unemp.get("JPN"),
        "CN": manual.get(("CN", "unemployment")), "IN": india.get("unemployment"),
    }
    ten = {"US": us_10y, "EA": de_10y, "UK": uk_10y, "JP": jp_10y,
           "CN": manual.get(("CN", "ten_year")), "IN": in_10y}
    policy = {"US": fed_hi, "EA": ecb_dfr, "UK": boe_rate, "JP": bis.get("JP"), "CN": bis.get("CN")}

    rows = []
    for cc in COUNTRIES:
        pmi_series = india.get("mfg_pmi") if cc == "IN" else manual.get((cc, "mfg_pmi"))
        cells = {
            "mfg_pmi": _cell(cc, "mfg_pmi", pmi_series, today, kind="month", compare="month", problems=P),
            "cpi_yoy": _cell(cc, "cpi_yoy", cpi[cc], today, kind="month", compare="month", problems=P),
            "unemployment": _cell(cc, "unemployment", unemp[cc], today, kind="month", compare="month", problems=P),
            "ten_year": _cell(cc, "ten_year", ten[cc], today,
                              kind="month" if cc == "CN" else "day",
                              compare="month" if cc == "CN" else "day", problems=P),
        }
        if cc == "IN":
            cells["policy_rate"] = _cell("IN", "policy_rate", None, today, kind="day", problems=P,
                                         value=rbi[0] if rbi else None, period=rbi[1] if rbi else None)
        else:
            cells["policy_rate"] = _cell(cc, "policy_rate", policy[cc], today, kind="day", problems=P,
                                         display=fed_display if cc == "US" else None)
        ticker, usd_per_local = FX_TICKERS[cc]
        ytd = fx_ytd_pct(fx[cc], usd_per_local, today) if fx[cc] is not None else None
        cells["fx_ytd"] = _cell(cc, "fx_ytd", None, today, kind="day", problems=P,
                                value=ytd[0] if ytd else None, period=ytd[1] if ytd else None)
        cells["fx_ytd"]["label"] = "DXY" if cc == "US" else "vs USD"
        rows.append({"country": cc, "label": COUNTRIES[cc]["label"], "cells": cells})

    # ── Regime: leading-indicator momentum vs inflation momentum ─────────
    regime = []
    for cc, area in OECD_CLI_AREAS.items():
        cli, infl = oecd_cli.get(area), cpi.get(cc)
        if cli is None or infl is None or cli.empty or infl.empty:
            continue
        g_now, i_now = value_months_ago(cli, 3), value_months_ago(infl, 3)
        if g_now is None or i_now is None:
            continue
        point = {
            "country": cc, "growth_change": round(float(cli.iloc[-1]) - g_now, 3),
            "inflation_change": round(float(infl.iloc[-1]) - i_now, 3),
            "cli_period": cli.index[-1].strftime("%Y-%m"), "cpi_period": infl.index[-1].strftime("%Y-%m"),
        }
        point["label"] = regime_label(point["growth_change"], point["inflation_change"])
        # The same reading one month earlier, for the direction-of-travel tail.
        cli_prev, infl_prev = cli.iloc[:-1], infl.iloc[:-1]
        g_prev, i_prev = value_months_ago(cli_prev, 3), value_months_ago(infl_prev, 3)
        if g_prev is not None and i_prev is not None and not cli_prev.empty and not infl_prev.empty:
            point["previous"] = {"growth_change": round(float(cli_prev.iloc[-1]) - g_prev, 3),
                                 "inflation_change": round(float(infl_prev.iloc[-1]) - i_prev, 3)}
        regime.append(point)

    snapshot = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "as_of": today.isoformat(),
        "central_banks": banks,
        "scoreboard": rows,
        "regime": regime,
        "calendar": calendar,
        "problems": list(c.problems),
    }
    series = {
        # Keyed by OECD area code: the ranked chart names them from OECD_CLI_COUNTRIES.
        "cli": {area: oecd_cli[area] for area in OECD_CLI_COUNTRIES if area in oecd_cli},
    }
    return snapshot, series, c.problems
