"""
World tab snapshot.

Fetches everything the World tab shows outside its charts — central bank
rates, the six-economy scoreboard, the global rate cycle and the US data
calendar — and returns it as one JSON-ready dict.

Central bank rates are read from each bank's own announcement as well as
from the official daily series, which are dated by the day a new rate takes
effect and posted days later (BIS about a week). `build_rate_update` builds
just the rates, for the weekday refresh (generate_macro.py --rates-only).

Rules (see docs/project_context.md §10):
  * No value is ever estimated, carried forward or filled in.
  * An automatic source that fails, or has stopped updating, is a PROBLEM:
    the caller writes what it has and exits non-zero, so the workflow fails
    and nothing half-broken is published.
  * A manual or hand-refreshed cell that is missing or old is shown as
    "awaiting entry" / "stale" on the page; that is not a problem.

The pure helpers at the top (yoy_by_date, last_move, the announcement
parsers, rate_moves_by_month, …) are covered by tests/test_world.py.
"""

from __future__ import annotations

import copy
import csv
import html
import io
import json
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
    BIS_EXTENDED_AREAS,
    CELL_SOURCES,
    COUNTRIES,
    FRED_RELEASES,
    FX_TICKERS,
    HAND_REFRESHED,
    MAX_AGE_OVERRIDES,
    OECD_CLI_COUNTRIES,
    OECD_CPI_AREAS,
    OECD_UNEMP_AREAS,
    RATE_CYCLE_START,
    SCOREBOARD_COLUMNS,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDIA_DB = PROJECT_ROOT / "data" / "india_macro.db"
DBIE_WORKBOOK = PROJECT_ROOT / "data" / "50 Macroeconomic Indicators.xlsx"
PBOC_LEDGER = PROJECT_ROOT / "data" / "pboc_reverse_repo.csv"
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


def apply_decision(s: pd.Series, rate: float, effective: date, source: str) -> pd.Series:
    """
    A central bank's own announcement on top of an official daily series.
    The daily series (BIS, FRED ECBDFR, the BoE database) date a new rate
    from the day it takes effect and post it days later, so after a
    decision they still show the old rate. When the series has nothing from
    the effective day on, the announced rate is added on that day: the page
    shows a decision as soon as it is announced, even when it takes effect
    later (the BoJ's 18 Sep 2026 hike took effect on 24 Sep). When the series
    already covers the day the two must agree, otherwise one source is wrong
    and we raise.
    """
    eff = pd.Timestamp(effective)
    if not s.empty and s.index[-1] >= eff:
        got = float(s[s.index >= eff].iloc[0])
        if abs(got - rate) > 1e-9:
            raise ValueError(f"{source} gives {rate:.2f}% from {eff:%Y-%m-%d}, "
                             f"but the daily series has {got:.2f}% that day")
        return s
    return pd.concat([s, pd.Series([float(rate)], index=[eff])])


def html_text(page: str) -> str:
    """
    Visible text of an HTML page. Table cells and blocks are separated by a
    space; every other tag is dropped without one, because the PBoC splits
    figures across spans ("1<span>.</span>40%" must read 1.40%).
    """
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", page)
    page = re.sub(r"(?i)</(?:td|th|tr|p|div|li|h\d)>|<br\s*/?>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", page))).strip()


_LONG_DATE = (r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
              r" \d{1,2}, \d{4})")


def parse_boj_statement(text: str) -> dict:
    """
    {'date', 'rate', 'effective'} from a Bank of Japan statement: the date it
    heads, 'The Bank will encourage the uncollateralized overnight call rate
    to remain at around 1.25 percent' and 'The new guideline for money market
    operations will be effective from September 24, 2026'. The decision says
    "will"; a dissent says "would" ('the Bank would encourage ... 1.25
    percent'), so it is never read as the decision. A statement that keeps
    the guideline names no effective day; it holds from the meeting.
    """
    m = re.search(r"The Bank will encourage the uncollateralized overnight call rate to remain at around "
                  r"(\d+(?:\.\d+)?) percent", text)
    decided = re.search(_LONG_DATE, text)
    if not m or not decided:
        raise ValueError("BoJ statement: no date or guideline sentence found — has the wording changed?")
    eff = re.search(r"guideline for money market operations will be effective from " + _LONG_DATE, text)
    when = datetime.strptime(decided.group(1), "%B %d, %Y").date()
    return {"date": when, "rate": float(m.group(1)),
            "effective": datetime.strptime(eff.group(1), "%B %d, %Y").date() if eff else when}


def parse_boj_decisions(page: str) -> list[str]:
    """
    Links to the monetary policy statements on a BoJ decisions page, newest
    first: "Statement on Monetary Policy" when the guideline is kept, "Change
    in the Guideline for Money Market Operations" when it moves. The
    "(Reference) ..." copy of a statement is skipped.
    """
    out = []
    for row in re.findall(r"(?is)<tr\b.*?</tr>", page):
        cells = re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", row)
        if len(cells) < 2:
            continue
        link = re.search(r'href="([^"]+\.pdf)"', cells[1])
        if link and re.match(r"(Statement on Monetary Policy|Change in the Guideline for Money Market Operations)\b",
                             html_text(cells[1])):
            out.append(link.group(1))
    return out


def parse_pboc_omo(text: str) -> float | None:
    """
    The 7-day reverse repo rate in a PBoC open market operations notice
    (Chinese), or None when that day had no 7-day operation: none at all, or
    only a 14-day one. The rate sits in the table after the 期限 (maturity)
    header, in either layout: '7天 1.40% 80亿元 80亿元' (rate first, since 2025)
    or '7天 1820亿元 1.50%' (volume first).
    """
    table = text.find("期限")
    if table < 0:
        return None
    m = re.search(r"(?<!\d)7天\s[^%]{0,30}?(?<![\d.])(\d+(?:\.\d+)?)%", text[table:])
    if not m:
        return None
    rate = float(m.group(1))
    if not 0 < rate < 10:
        raise ValueError(f"PBoC notice: implausible 7-day reverse repo rate {rate}%")
    return rate


def parse_pboc_list(page: str) -> list[tuple[str, str]]:
    """(date, href) of each notice on a page of the PBoC's Chinese open market operations list, newest first."""
    return [(d, href) for href, d in re.findall(
        r'<a href="([^"]+/\d+/index\.html)"[^>]*\stitle="公开市场业务交易公告[^"]*"[^>]*>.*?</a>\s*</font>\s*'
        r'<span class="hui12">(\d{4}-\d{2}-\d{2})</span>', page, flags=re.S)]


_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def parse_ecb_key_rates(page: str) -> pd.Series:
    """
    Deposit facility rate by effective date from the ECB's key interest rate
    table. Only the first row of each year carries the year, and dates can
    carry a footnote number ("18 Sep. 5"); negative rates use a real minus sign.
    """
    table = re.search(r"(?is)<table\b.*?</table>", page)
    if not table:
        raise ValueError("ECB key rates page: no table — has the layout changed?")
    rates, year = {}, None
    for row in re.findall(r"(?is)<tr\b.*?</tr>", table.group(0)):
        cells = [html_text(c) for c in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row)]
        if len(cells) < 3:
            continue
        if re.fullmatch(r"\d{4}", cells[0]):
            year = int(cells[0])
        day = re.match(r"(\d{1,2}) ([A-Z][a-z]{2})", cells[1])
        dfr = cells[2].replace("−", "-")
        if year is None or not day or not re.fullmatch(r"-?\d+\.\d+", dfr):
            continue
        rates[pd.Timestamp(year, _MONTHS[day.group(2)], int(day.group(1)))] = float(dfr)
    if not rates:
        raise ValueError("ECB key rates page: no deposit facility rates parsed")
    return pd.Series(rates).sort_index()


def parse_boe_bank_rate(page: str) -> pd.Series:
    """Bank Rate by date of change from the Bank of England's Bank Rate history table ('18 Dec 25', '3.75')."""
    rates = {}
    for when, rate in re.findall(r"(?is)<td\b[^>]*>\s*(\d{2} [A-Z][a-z]{2} \d{2})\s*</td>\s*<td\b[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>",
                                 page):
        rates[pd.Timestamp(datetime.strptime(when, "%d %b %y"))] = float(rate)
    if not rates:
        raise ValueError("Bank of England Bank Rate page: no rates parsed — has the layout changed?")
    return pd.Series(rates).sort_index()


def extend_series(base: pd.Series, fresher: pd.Series | None) -> pd.Series:
    """
    `base` (BIS) carried past its last day with the moves `fresher` (the
    bank's own, more current source) records after that day. The two can use
    different conventions (BIS takes the middle of the Fed's target range,
    the page its top), so only the changes are carried over, never the level.
    """
    if fresher is None or fresher.empty or base.empty:
        return base
    t0 = base.index[-1]
    before, after = fresher[fresher.index <= t0], fresher[fresher.index > t0]
    if before.empty or after.empty:
        return base
    return pd.concat([base, float(base.iloc[-1]) + (after - float(before.iloc[-1]))])


def rate_moves_by_month(series: dict[str, pd.Series], start: str) -> pd.DataFrame:
    """
    For each month from `start`: how many central banks ended it with a
    higher policy rate than they ended the month before (hikes), how many
    lower (cuts), and how many have data for both month ends (reporting).
    A bank counts once a month however often it moved. A bank whose data stop
    early is not counted for the months it has not reported, so the latest
    month holds only what has been published so far.
    """
    moves = {}
    for area, s in series.items():
        s = s.dropna().sort_index()
        if s.empty:
            continue
        month_end = s.groupby(s.index.to_period("M")).last()
        month_end = month_end.reindex(pd.period_range(month_end.index[0], month_end.index[-1], freq="M"))
        moves[area] = month_end.diff()
    df = pd.DataFrame(moves)
    df = df[df.index >= pd.Period(start, "M")]
    return pd.DataFrame({
        "hikes": (df > 1e-6).sum(axis=1),
        "cuts": (df < -1e-6).sum(axis=1),
        "reporting": df.notna().sum(axis=1),
    })


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


def fetch_bis_policy(start: str) -> dict[str, pd.Series]:
    """
    BIS central bank policy rates for every central bank it covers, daily,
    as {area: Series}. detail=dataonly drops the notes the BIS otherwise
    repeats on every row (7 MB instead of well over 70 MB since 2000).
    """
    r = _get("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.",
             {"startPeriod": start, "format": "csv", "detail": "dataonly"})
    df = pd.read_csv(io.StringIO(r.text))
    out = {
        area: pd.Series(g["OBS_VALUE"].values, index=pd.to_datetime(g["TIME_PERIOD"])).dropna().sort_index()
        for area, g in df.groupby("REF_AREA")
    }
    if len(out) < 30:
        raise ValueError(f"BIS policy rates: only {len(out)} central banks returned")
    return out


BOJ_DECISIONS = "https://www.boj.or.jp/en/mopo/mpmdeci/mpr_{year}/index.htm"


def fetch_boj_decision(today: date) -> dict:
    """
    The latest Bank of Japan monetary policy statement: {'date', 'rate',
    'effective', 'url'}. The year's decisions page is empty until January's
    meeting, so the previous year's is read when this year has no statement.
    """
    import fitz  # PyMuPDF, already used by the RBI Sentinel

    for year in (today.year, today.year - 1):
        try:
            links = parse_boj_decisions(_get(BOJ_DECISIONS.format(year=year)).text)
        except requests.HTTPError:
            links = []   # next year's page does not exist until it has a decision
        if links:
            url = requests.compat.urljoin(BOJ_DECISIONS.format(year=year), links[0])
            with fitz.open(stream=_get(url).content, filetype="pdf") as pdf:
                text = re.sub(r"\s+", " ", " ".join(page.get_text() for page in pdf))
            return {**parse_boj_statement(text), "url": url}
    raise ValueError(f"BoJ: no monetary policy statement on the {today.year} or {today.year - 1} decisions pages")


ECB_KEY_RATES = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html"
BOE_BANK_RATE = "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp"


def fetch_ecb_decision() -> dict:
    """The latest change in the ECB's deposit facility rate: {'rate', 'effective', 'url'}."""
    s = parse_ecb_key_rates(_get(ECB_KEY_RATES).text)
    return {"rate": float(s.iloc[-1]), "effective": s.index[-1].date(), "url": ECB_KEY_RATES}


def fetch_boe_decision() -> dict:
    """The latest change in Bank Rate, which takes effect the day it is announced: {'rate', 'effective', 'url'}."""
    s = parse_boe_bank_rate(_get(BOE_BANK_RATE).text)
    return {"rate": float(s.iloc[-1]), "effective": s.index[-1].date(), "url": BOE_BANK_RATE}


PBOC_OMO_LIST = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/"


def read_pboc_ledger(path: Path = PBOC_LEDGER) -> pd.Series:
    """
    The PBoC's 7-day reverse repo rate from each change on, as a step
    series. Each row is dated by the first 7-day operation at the new rate
    and links the notice that shows it; the first row is where the record
    starts, not a change.
    """
    df = pd.read_csv(path, parse_dates=["date"])
    s = pd.Series(df["rate"].astype(float).values, index=df["date"])
    if s.empty or not s.index.is_monotonic_increasing or s.index.duplicated().any():
        raise ValueError(f"{path.name}: rows must be in date order, one per date")
    if (s.diff().iloc[1:].abs() < 1e-9).any():
        raise ValueError(f"{path.name}: a row repeats the previous rate, so it is not a change")
    if df["source"].isna().any():
        raise ValueError(f"{path.name}: every row needs its source notice")
    return s


def record_pboc_moves(moves: list[dict], path: Path = PBOC_LEDGER) -> None:
    """Append changes found by fetch_pboc_reverse_repo to the ledger, so later runs start from them."""
    with path.open("a", newline="") as fh:
        writer = csv.writer(fh)
        for m in moves:
            writer.writerow([m["date"], f"{m['rate']:.2f}", m["url"]])


def fetch_pboc_reverse_repo(ledger: pd.Series, max_pages: int = 5) -> tuple[dict, list[dict]]:
    """
    The PBoC's 7-day reverse repo rate from its daily open market operations
    notices. The Chinese list is used: it is posted at 09:20 Beijing time,
    hours before the English translation, which also misses some notices.

    Returns (latest, moves). latest = {'date', 'rate', 'url'} of the newest
    notice with a 7-day operation. moves = changes since the ledger's last
    rate, oldest first, each dated by the first 7-day operation at the new
    rate. The walk back through the list stops at the ledger's rate, so on
    an ordinary day it reads one notice; a change further back than
    `max_pages` pages (20 notices each) means the ledger is far out of date.
    """
    known, known_date = float(ledger.iloc[-1]), ledger.index[-1]
    def page_text(url: str) -> str:
        return _get(url).content.decode("utf-8", errors="replace")   # the pages declare no charset

    first_page = page_text(PBOC_OMO_LIST + "index.html")
    paging = re.search(r"(/zhengcehuobisi/125207/125213/125431/125475/[\w]+-)\d+\.html", first_page)
    seen = []   # (date, rate, url), newest first
    for n in range(1, max_pages + 1):
        if n == 1:
            page = first_page
        elif paging:
            page = page_text(requests.compat.urljoin(PBOC_OMO_LIST, f"{paging.group(1)}{n}.html"))
        else:
            raise ValueError("PBoC notices: no link to the next page of the list — has the layout changed?")
        notices = parse_pboc_list(page)
        if not notices:
            raise ValueError("PBoC notices: no open market operations notices on the list page")
        for when, href in notices:
            if pd.Timestamp(when) < known_date:
                raise ValueError(f"PBoC notices: reached {when} without finding the ledger's "
                                 f"{known:.2f}% — check {PBOC_LEDGER.name}")
            url = requests.compat.urljoin(PBOC_OMO_LIST, href)
            rate = parse_pboc_omo(html_text(page_text(url)))
            if rate is None:
                continue
            seen.append((when, rate, url))
            if abs(rate - known) < 1e-9:
                latest = {"date": seen[0][0], "rate": seen[0][1], "url": seen[0][2]}
                moves = [{"date": newer[0], "rate": newer[1], "url": newer[2]}
                         for newer, older in zip(seen, seen[1:]) if abs(newer[1] - older[1]) > 1e-9]
                return latest, moves[::-1]
    raise ValueError(f"PBoC 7-day reverse repo: the ledger's {known:.2f}% is not in the last {max_pages} pages "
                     f"of notices — add the change to {PBOC_LEDGER.name} by hand")


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


def read_rbi_repo_history(db_path: Path) -> pd.Series:
    """Repo rate after each policy cycle in the RBI Sentinel database, dated by the decision."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT policy_cycle, repo_rate_pct FROM mpc_meetings "
            "WHERE repo_rate_pct IS NOT NULL AND policy_cycle IS NOT NULL"
        ).fetchall()
    by_cycle: dict[str, set] = {}
    for cycle, rate in rows:
        by_cycle.setdefault(cycle, set()).add(round(float(rate), 4))
    split = [c for c, rates in by_cycle.items() if len(rates) > 1]
    if split:
        raise ValueError(f"RBI Sentinel database: more than one repo rate recorded for {', '.join(sorted(split))}")
    return pd.Series({pd.Timestamp(c): rates.pop() for c, rates in by_cycle.items()}).sort_index()


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


def _pboc_series() -> pd.Series:
    """The ledger of 7-day reverse repo changes plus today's notice; a new change is written to the ledger."""
    ledger = read_pboc_ledger()
    latest, moves = fetch_pboc_reverse_repo(ledger)
    if moves:
        record_pboc_moves(moves)
        for m in moves:
            print(f"   PBoC 7-day reverse repo moved to {m['rate']:.2f}% on {m['date']}: added to {PBOC_LEDGER.name}")
        ledger = read_pboc_ledger()
    when = pd.Timestamp(latest["date"])
    if when > ledger.index[-1]:
        ledger = pd.concat([ledger, pd.Series([latest["rate"]], index=[when])])
    return ledger


def _policy_rates(fred_series, sentinel_db: Path, today: date, c: _Collector) -> dict:
    """
    Every policy rate the page shows, and the global rate cycle. Each rate is
    an official daily series with the bank's own latest announcement applied
    on top (apply_fomc_decision, apply_decision), so a decision appears the
    day it is announced. China is the PBoC's 7-day reverse repo rate, which it
    names its main policy rate (BIS carries the 1-year loan prime rate).
    """
    fed_lo = c.run("FRED DFEDTARL", fred_series, "DFEDTARL", "2015-01-01")
    fed_hi = c.run("FRED DFEDTARU", fred_series, "DFEDTARU", "2015-01-01")
    fomc = c.run("Fed FOMC statement", fetch_fomc_decision)
    if fomc and fed_lo is not None and fed_hi is not None and not fed_lo.empty and not fed_hi.empty:
        fed_lo, fed_hi = c.run("FOMC statement vs FRED", apply_fomc_decision, fed_lo, fed_hi, fomc) or (fed_lo, fed_hi)

    def with_decision(label: str, s: pd.Series | None, decision: dict | None) -> pd.Series | None:
        if s is None or decision is None:
            return s
        return c.run(f"{label} vs the daily series", apply_decision,
                     s, decision["rate"], decision["effective"], label) if not s.empty else s

    # From a month before the chart starts, so its first month has a month end to compare with.
    bis_start = (pd.Period(RATE_CYCLE_START, "M") - 1).to_timestamp().strftime("%Y-%m-%d")
    bis = c.run("BIS policy rates", fetch_bis_policy, bis_start) or {}
    ecb = with_decision("ECB key rates table", c.run("FRED ECBDFR", fred_series, "ECBDFR", "2015-01-01"),
                        c.run("ECB key rates table", fetch_ecb_decision))
    boe = with_decision("Bank of England Bank Rate table", c.run("Bank of England Bank Rate", fetch_boe, "IUDBEDR",
                                                                 date(2015, 1, 1)),
                        c.run("Bank of England Bank Rate table", fetch_boe_decision))
    boj = with_decision("BoJ statement", bis.get("JP"), c.run("BoJ statement", fetch_boj_decision, today))
    pboc = c.run("PBoC 7-day reverse repo", _pboc_series)
    rbi = c.run("RBI Sentinel database", read_rbi_repo, sentinel_db)
    rbi_history = c.run("RBI Sentinel repo history", read_rbi_repo_history, sentinel_db)

    def bank(bid: str, s: pd.Series | None, display: str | None = None) -> dict:
        if s is None or s.empty:
            return {"id": bid, "status": "unavailable"}
        out = {"id": bid, "status": "ok", "rate": float(s.iloc[-1]),
               "display": display or f"{s.iloc[-1]:.2f}",
               "as_of": s.index[-1].strftime("%Y-%m-%d"),
               "last_move": last_move(s)}
        if (today - s.index[-1].date()).days > SCOREBOARD_COLUMNS["policy_rate"]["max_age"]:
            c.problems.append(f"{bid} policy rate: latest observation {out['as_of']} is stale")
        return out

    fed_display = None
    if fed_lo is not None and fed_hi is not None and not fed_lo.empty and not fed_hi.empty:
        fed_display = f"{fed_lo.iloc[-1]:.2f}–{fed_hi.iloc[-1]:.2f}"
    series = {"US": fed_hi, "EA": ecb, "UK": boe, "JP": boj, "CN": pboc}
    return {
        "banks": [bank("fed", fed_hi, fed_display), bank("ecb", ecb), bank("boe", boe),
                  bank("boj", boj), bank("pboc", pboc)],
        "series": series,
        "fed_display": fed_display,
        "rbi": rbi,
        "rate_cycle": _rate_cycle(bis, {**series, "IN": rbi_history}, today, c),
    }


def _rate_cycle(bis: dict[str, pd.Series], fresher: dict[str, pd.Series | None], today: date,
                c: _Collector) -> dict | None:
    """
    Hikes and cuts per month across the central banks the BIS covers, as
    JSON for the chart. For the big banks whose own announcements are read
    (BIS_EXTENDED_AREAS), moves after BIS's last day are carried on from those.
    """
    if not bis:
        return None
    recent = {a: s for a, s in bis.items() if (pd.Timestamp(today) - s.index[-1]).days <= 120}
    if len(recent) < 30:
        c.problems.append(f"BIS policy rates: only {len(recent)} central banks reported in the last 120 days")
    through = pd.Series([s.index[-1] for s in recent.values()]).median()
    if (pd.Timestamp(today) - through).days > 45:
        c.problems.append(f"BIS policy rates: most central banks' data end on {through:%Y-%m-%d} — "
                          "has the BIS stopped updating?")
    series, extended = dict(bis), []
    for area, cc in BIS_EXTENDED_AREAS.items():
        if area in bis:
            series[area] = extend_series(bis[area], fresher.get(cc))
            tail = series[area][series[area].index >= bis[area].index[-1]]
            if (tail.diff().abs() > 1e-6).any():
                extended.append(area)
    moves = rate_moves_by_month(series, RATE_CYCLE_START)
    return {
        "start": str(moves.index[0]),
        "hikes": [int(v) for v in moves["hikes"]],
        "cuts": [int(v) for v in moves["cuts"]],
        "reporting": [int(v) for v in moves["reporting"]],
        "banks": len(recent),
        "bis_through": through.strftime("%Y-%m-%d"),
        "extended": extended,
    }


def _policy_cell(cc: str, rates: dict, today: date, problems: list[str]) -> dict:
    if cc == "IN":
        rbi = rates["rbi"]
        return _cell("IN", "policy_rate", None, today, kind="day", problems=problems,
                     value=rbi[0] if rbi else None, period=rbi[1] if rbi else None)
    return _cell(cc, "policy_rate", rates["series"][cc], today, kind="day", problems=problems,
                 display=rates["fed_display"] if cc == "US" else None)


def build_rate_update(fred_api_key: str, sentinel_db: Path, today: date | None = None) -> tuple[dict, list[str]]:
    """
    Only the central bank rates, for the weekday refresh
    (generate_macro.py --rates-only): the strip, the scoreboard's
    policy-rate cells and the rate cycle. Returns (update, problems).
    """
    from fredapi import Fred

    today = today or date.today()
    c = _Collector()
    fred = Fred(api_key=fred_api_key)

    def fred_series(sid: str, start: str) -> pd.Series:
        return fred.get_series(sid, observation_start=start).dropna().astype(float)

    rates = _policy_rates(fred_series, sentinel_db, today, c)
    update = {
        "central_banks": rates["banks"],
        "policy_cells": {cc: _policy_cell(cc, rates, today, c.problems) for cc in COUNTRIES},
        "rate_cycle": rates["rate_cycle"],
    }
    return update, c.problems


def rates_fingerprint(snapshot: dict) -> str:
    """
    What the weekday refresh compares before writing: the rates, their last
    moves and the rate cycle, but not observation dates, which move every
    day without anything on the page changing.
    """
    banks = [{k: b.get(k) for k in ("id", "status", "display", "last_move")}
             for b in snapshot.get("central_banks", [])]
    cells = [{k: row["cells"]["policy_rate"].get(k) for k in ("value", "display", "status")}
             for row in snapshot.get("scoreboard", [])]
    return json.dumps([banks, cells, snapshot.get("rate_cycle")], sort_keys=True)


def apply_rate_update(snapshot: dict, update: dict, when: str) -> dict:
    """A copy of `snapshot` with the rates from build_rate_update and the time they were refreshed."""
    out = copy.deepcopy(snapshot)
    out["central_banks"] = update["central_banks"]
    for row in out["scoreboard"]:
        row["cells"]["policy_rate"] = update["policy_cells"][row["country"]]
    out["rate_cycle"] = update["rate_cycle"]
    out["rates_updated_at"] = when
    return out


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
    us_10y = c.run("FRED DGS10", fred_series, "DGS10", f"{today.year - 1}-01-01")
    rates = _policy_rates(fred_series, sentinel_db, today, c)

    oecd_cpi = c.run("OECD CPI", fetch_oecd, "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
                     f"{'+'.join(OECD_CPI_AREAS.values())}.M.N.CPI.PA._T.N.GY", "2023-01") or {}
    oecd_unemp = c.run("OECD unemployment", fetch_oecd, "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0",
                       f"{'+'.join(OECD_UNEMP_AREAS.values())}..._Z.Y._T.Y_GE15..M", "2024-01") or {}
    oecd_cli = c.run("OECD CLI", fetch_oecd, "OECD.SDD.STES,DSD_STES@DF_CLI,4.1",
                     f"{'+'.join(sorted(OECD_CLI_COUNTRIES))}.M.LI...AA...H", "2023-01") or {}

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
    fx = {k: c.run(f"Yahoo {t}", fetch_fx, t, today) for k, (t, _) in FX_TICKERS.items()}
    calendar = c.run("FRED release calendar", fetch_release_calendar, fred_api_key, today) or []

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
            "policy_rate": _policy_cell(cc, rates, today, P),
        }
        ticker, usd_per_local = FX_TICKERS[cc]
        ytd = fx_ytd_pct(fx[cc], usd_per_local, today) if fx[cc] is not None else None
        cells["fx_ytd"] = _cell(cc, "fx_ytd", None, today, kind="day", problems=P,
                                value=ytd[0] if ytd else None, period=ytd[1] if ytd else None)
        cells["fx_ytd"]["label"] = "DXY" if cc == "US" else "vs USD"
        rows.append({"country": cc, "label": COUNTRIES[cc]["label"], "cells": cells})

    snapshot = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "as_of": today.isoformat(),
        "central_banks": rates["banks"],
        "scoreboard": rows,
        "rate_cycle": rates["rate_cycle"],
        "calendar": calendar,
        "problems": list(c.problems),
    }
    series = {
        # Keyed by OECD area code: the ranked chart names them from OECD_CLI_COUNTRIES.
        "cli": {area: oecd_cli[area] for area in OECD_CLI_COUNTRIES if area in oecd_cli},
    }
    return snapshot, series, c.problems
