"""
Who owns corporate India: promoter holdings from NSE's shareholding filings.

Every company listed in India files a shareholding pattern with the exchange
within 21 days of each quarter end, under SEBI's listing regulations. The
filing splits the share register into the promoter and promoter group — the
founding family, the parent company or the government — and everyone else.
Two rules shape what the filings show: a promoter may hold no more than 75%,
because at least 25% must sit with the public, and above 50% a promoter
controls the company outright.

NSE serves the filings through two endpoints:

  * the master list, one row per company for the quarter just filed. One
    request covers the whole market, and every run reads it.
  * the same endpoint with a symbol, which returns that company's filings back
    to 2021. Reading the market company by company takes about six minutes, so
    it is not done on a run: it builds nse_promoter_holdings.csv beside this
    file, with

        python -m data.nse_shareholding --rebuild

    which is worth running after each filing season (late January, April,
    July and October).

A failed download, a changed payload, holdings that do not add up or a filing
season that has not arrived raises ValueError, and the India run fails.

Note on the history: the filings are read from the companies listed today, so
earlier quarters do not contain companies that have since delisted, and a
company enters the series when it lists. Any figure drawn across time is
therefore taken over the companies that filed in every quarter shown
(constant_panel), never over a sample that grows underneath the line.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

NSE_HOME = "https://www.nseindia.com/"
NSE_MASTER = "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities"
HISTORY_CSV = Path(__file__).with_name("nse_promoter_holdings.csv")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
}

# SEBI's limits, drawn on the chart: a promoter may hold at most 75%, and above
# 50% holds control. Companies sit above 75% only while a recent listing or a
# government holding is still being brought down to it.
PUBLIC_MINIMUM = 25.0
PROMOTER_CEILING = 100.0 - PUBLIC_MINIMUM
CONTROL = 50.0

# A quarter's filings are due 21 days after it ends, and the next quarter is
# not filed for three months, so the newest filing is up to about seven months
# old before something has gone wrong.
MAX_AGE = 220
MIN_COMPANIES = 1200


def session() -> requests.Session:
    """An NSE session carrying the cookies its API requires."""
    s = requests.Session()
    s.get(NSE_HOME, headers=HEADERS, timeout=20).raise_for_status()
    return s


def _get_json(s: requests.Session, url: str, what: str, attempts: int = 3):
    for attempt in range(attempts):
        try:
            response = s.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == attempts - 1:
                raise ValueError(f"NSE {what}: no usable response after {attempts} attempts")
            time.sleep(3 * (attempt + 1))


def parse_filings(records: list[dict], what: str) -> pd.DataFrame:
    """
    NSE's filing records as one row per company and quarter, in per cent.

    Only filings dated to a quarter end are kept: a company that changes hands
    files again mid-quarter, and those interim filings would otherwise put two
    different registers in the same quarter. Where a company has revised a
    filing, the latest submission wins.
    """
    if not isinstance(records, list) or not records:
        raise ValueError(f"NSE {what}: no filings in the response")
    rows = []
    for record in records:
        try:
            rows.append({
                "symbol": str(record["symbol"]).strip(),
                "name": str(record.get("name") or "").strip(),
                "quarter": pd.to_datetime(record["date"], format="%d-%b-%Y", errors="coerce"),
                "submitted": pd.to_datetime(record.get("submissionDate"), format="%d-%b-%Y", errors="coerce"),
                "promoter": pd.to_numeric(record["pr_and_prgrp"], errors="coerce"),
                "public": pd.to_numeric(record.get("public_val"), errors="coerce"),
            })
        except KeyError as exc:
            raise ValueError(f"NSE {what}: a filing has no {exc} — the payload changed") from exc

    frame = pd.DataFrame(rows).dropna(subset=["quarter", "promoter"])
    if frame.empty:
        raise ValueError(f"NSE {what}: no filings with a date and a promoter holding")
    frame = frame[frame["quarter"].dt.is_quarter_end]
    if frame.empty:
        raise ValueError(f"NSE {what}: no filings dated to a quarter end — the date format changed")

    check_holdings(frame, what)
    frame = (frame.sort_values(["submitted", "promoter"])
                  .groupby(["symbol", "quarter"], as_index=False).last())
    return frame.sort_values(["quarter", "symbol"]).reset_index(drop=True)


def check_holdings(frame: pd.DataFrame, what: str) -> None:
    """Holdings are percentages, and the register adds up to the whole company."""
    outside = frame[(frame["promoter"] < 0) | (frame["promoter"] > 100)]
    if not outside.empty:
        raise ValueError(f"NSE {what}: {len(outside)} filings hold outside 0–100% "
                         f"(worst {outside['promoter'].abs().max():.1f}) — units changed?")
    both = frame.dropna(subset=["public"])
    if not both.empty:
        # Employee trusts are reported separately and are a fraction of a per
        # cent, so promoter plus public reaches 100 but need not hit it exactly.
        off = (both["promoter"] + both["public"] - 100).abs()
        if (off > 1.5).mean() > 0.02:
            raise ValueError(f"NSE {what}: promoter and public holdings do not add to 100% for "
                             f"{(off > 1.5).mean():.0%} of filings — the columns changed")


def fetch_current(s: requests.Session | None = None) -> pd.DataFrame:
    """The quarter just filed, for every listed company: one request."""
    s = s or session()
    frame = parse_filings(_get_json(s, NSE_MASTER, "shareholding master"), "shareholding master")
    latest = frame["quarter"].max()
    frame = frame[frame["quarter"] == latest]
    if len(frame) < MIN_COMPANIES:
        raise ValueError(f"NSE shareholding master: only {len(frame)} companies filed for "
                         f"{latest:%b %Y} (expected at least {MIN_COMPANIES})")
    return frame


def fetch_company(s: requests.Session, symbol: str) -> pd.DataFrame:
    """One company's filings, back to 2021."""
    records = _get_json(s, f"{NSE_MASTER}&symbol={symbol}", f"filings for {symbol}")
    return parse_filings(records, f"filings for {symbol}")


def check_fresh(latest: pd.Timestamp, today: date) -> None:
    age = (today - latest.date()).days
    if age > MAX_AGE:
        raise ValueError(f"NSE shareholding: the newest filings are for {latest:%b %Y}, {age} days old "
                         f"(limit {MAX_AGE}) — the feed may have stopped updating")


def load_history(path: Path = HISTORY_CSV) -> pd.DataFrame:
    if not path.exists():
        raise ValueError(f"{path.name} is missing — build it with: python -m data.nse_shareholding --rebuild")
    frame = pd.read_csv(path, parse_dates=["quarter"])
    missing = {"symbol", "quarter", "promoter"} - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    check_holdings(frame, path.name)
    return frame


def fetch_shareholding(today: date | None = None, history_path: Path = HISTORY_CSV) -> pd.DataFrame:
    """
    Every quarter of filings: the archive from nse_promoter_holdings.csv and
    the quarter just filed, downloaded now. One row per company and quarter.
    """
    today = today or date.today()
    history = load_history(history_path)
    current = fetch_current()
    latest = current["quarter"].max()
    check_fresh(latest, today)

    quarters = sorted(set(history["quarter"]) | {latest})
    expected = pd.date_range(min(quarters), latest, freq="QE")
    behind = [q for q in expected if q not in quarters]
    if behind:
        raise ValueError(f"{history_path.name} has no filings for "
                         f"{', '.join(f'{q:%b %Y}' for q in behind[:4])} and NSE's master list carries only the "
                         f"newest quarter — rebuild it with: python -m data.nse_shareholding --rebuild")

    frame = pd.concat([history[history["quarter"] != latest], current], ignore_index=True)
    return frame.sort_values(["quarter", "symbol"]).reset_index(drop=True)


def constant_panel(frame: pd.DataFrame, quarters: list[pd.Timestamp]) -> pd.DataFrame:
    """
    The filings of the companies that reported in every one of `quarters`, as a
    quarter-by-company table. A median taken across this moves only when
    holdings move, never because the market listed or lost companies.
    """
    wanted = frame[frame["quarter"].isin(quarters)]
    table = wanted.pivot_table(index="quarter", columns="symbol", values="promoter", aggfunc="last")
    table = table.dropna(axis=1)
    if table.empty or len(table.columns) < MIN_COMPANIES // 2:
        raise ValueError(f"only {0 if table.empty else len(table.columns)} companies filed in every quarter "
                         f"from {min(quarters):%b %Y} to {max(quarters):%b %Y}")
    return table.sort_index()


def rebuild(path: Path = HISTORY_CSV, pause: float = 0.0) -> pd.DataFrame:
    """Read every listed company's filing history and write the archive."""
    s = session()
    current = fetch_current(s)
    symbols = sorted(current["symbol"].unique())
    print(f"   {len(symbols)} companies filed for {current['quarter'].max():%b %Y}; reading their histories")

    collected, failed = [], []
    for i, symbol in enumerate(symbols, 1):
        try:
            collected.append(fetch_company(s, symbol))
        except ValueError:
            failed.append(symbol)
        if pause:
            time.sleep(pause)
        if i % 250 == 0:
            print(f"   {i}/{len(symbols)} read, {len(failed)} without filings")

    if len(failed) > len(symbols) * 0.05:
        raise ValueError(f"NSE returned no filings for {len(failed)} of {len(symbols)} companies — "
                         f"the endpoint may be rate limiting")
    frame = (pd.concat(collected, ignore_index=True)
               .sort_values(["quarter", "symbol"])
               .drop_duplicates(["symbol", "quarter"], keep="last")
               .reset_index(drop=True))
    frame.to_csv(path, index=False, date_format="%Y-%m-%d")
    counts = frame.groupby("quarter")["symbol"].size()
    print(f"\n   {len(frame)} filings from {len(symbols) - len(failed)} companies written to {path.name}")
    print(f"   {counts.index.min():%b %Y} to {counts.index.max():%b %Y}, "
          f"{counts.iloc[-1]} companies in the newest quarter")
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description="NSE promoter shareholding")
    parser.add_argument("--rebuild", action="store_true", help="read every company's filing history (about six minutes)")
    args = parser.parse_args()
    if args.rebuild:
        rebuild()
        return 0
    frame = fetch_shareholding()
    latest = frame[frame["quarter"] == frame["quarter"].max()]
    print(f"{len(frame)} filings, newest quarter {frame['quarter'].max():%b %Y} "
          f"({len(latest)} companies, median promoter holding {latest['promoter'].median():.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
