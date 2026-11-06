"""Refresh official NSE daily inputs for the India options risk-premium chart.

Run: python -m data.fetchers.nse_options_risk_premium
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from threading import local

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data.paths import NSE_OPTIONS_RISK_PREMIUM_DIR
from data.processors.nse_options_risk_premium import (
    CHART_DAYS, DAILY_SOURCE, ROOT, VERSION, digest, load_history, parse_daily,
)

LOOKBACK_BUFFER_DAYS = 365
RECHECK_DAYS = 14
_THREAD_STATE = local()


def _today_ist() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()


def _download(day: pd.Timestamp) -> tuple[pd.Timestamp, int, bytes | None]:
    url = DAILY_SOURCE.format(date=day.strftime("%d%m%Y"))
    client = getattr(_THREAD_STATE, "client", None)
    if client is None:
        retry = Retry(total=2, backoff_factor=0.4, status_forcelist=(429, 500, 502, 503, 504))
        client = requests.Session()
        client.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; EconomicsHub NSE daily archive reader)",
            "Accept": "text/csv,*/*",
            "Referer": "https://www.nseindia.com/reports-indices-historical-vix",
        })
        client.mount("https://", HTTPAdapter(max_retries=retry))
        _THREAD_STATE.client = client
    response = client.get(url, timeout=(10, 30))
    if response.status_code in (404, 410):
        return day, response.status_code, None
    response.raise_for_status()
    payload = response.content
    parse_daily(payload, day)
    return day, response.status_code, payload


def refresh(root: Path = ROOT, end: str | date | None = None,
            start: str | date | None = None) -> tuple[pd.DataFrame, dict]:
    """Fetch recent missing NSE daily reports and publish a rolling audited window.

    NSE reports are requested by calendar date. Missing reports are recorded as
    unavailable; weekends and exchange holidays are not inferred or imputed.
    The retained window is one chart year plus a full year of NIFTY history for
    the trailing 252-session drawdown calculation.
    """
    root = Path(root)
    today = _today_ist()
    end_date = pd.Timestamp(end or (today - timedelta(days=1))).normalize()
    if end_date.date() >= today:
        raise ValueError("Only completed NSE report dates can be fetched")
    retained_start = end_date - pd.Timedelta(days=CHART_DAYS + LOOKBACK_BUFFER_DAYS)

    prior_sources: list[dict] = []
    if (root / "manifest.json").exists():
        _, previous = load_history(root)
        previous_sources = [s for s in previous["sources"] if pd.Timestamp(s["date"]) >= retained_start]
        previous_last = pd.Timestamp(previous["last_date"])
        first_fetch = pd.Timestamp(start or max(retained_start, previous_last - pd.Timedelta(days=RECHECK_DAYS)))
        prior_sources = previous_sources
    else:
        first_fetch = pd.Timestamp(start or retained_start)
    first_fetch = max(first_fetch.normalize(), retained_start)
    if end_date < first_fetch:
        raise ValueError("End precedes the requested NSE report window")
    if (end_date - first_fetch).days > 900:
        raise ValueError("Initial NSE history request exceeds 900 calendar days")

    existing_by_date = {item["date"]: item for item in prior_sources}
    dates = list(pd.date_range(first_fetch, end_date, freq="D"))
    received: list[dict] = []
    unavailable: list[str] = []
    root.mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(exist_ok=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_download, day): day for day in dates}
        for future in as_completed(futures):
            day, status, payload = future.result()
            key = str(day.date())
            if status in (404, 410):
                unavailable.append(key)
                continue
            sha = digest(payload)
            if key in existing_by_date and existing_by_date[key]["sha256"] != sha:
                raise ValueError(f"NSE revised an archived report for {key}; previous manifest retained")
            relative = f"raw/{sha}.csv"
            target = root / relative
            if not target.exists():
                target.write_bytes(payload)
            received.append({
                "date": key,
                "source_url": DAILY_SOURCE.format(date=day.strftime("%d%m%Y")),
                "path": relative,
                "sha256": sha,
                "bytes": len(payload),
            })

    by_date = {item["date"]: item for item in prior_sources}
    by_date.update({item["date"]: item for item in received})
    sources = [by_date[key] for key in sorted(by_date)]
    if not sources:
        raise ValueError("NSE returned no valid daily index reports")
    observations = []
    for item in sources:
        day = date.fromisoformat(item["date"])
        values = parse_daily((root / item["path"]).read_bytes(), day)
        observations.append({"date": day.isoformat(), **values})
    frame = pd.DataFrame(observations).sort_values("date")
    if frame["date"].duplicated().any():
        raise ValueError("Duplicate report dates in NSE options risk-premium history")
    if pd.Timestamp(frame["date"].iloc[-1]) < end_date - pd.Timedelta(days=10):
        raise ValueError("Latest NSE options risk-premium report is more than ten days old")

    csv_bytes = frame.to_csv(index=False, float_format="%.10g").encode("utf-8")
    observations_sha = digest(csv_bytes)
    observations_path = f"derived/{observations_sha}.csv"
    observations_file = root / observations_path
    observations_file.parent.mkdir(exist_ok=True)
    if not observations_file.exists():
        observations_file.write_bytes(csv_bytes)
    manifest = {
        "calculation_version": VERSION,
        "source_description": "NSE daily index closing reports; exact Nifty 50 and India VIX rows",
        "source_url_template": DAILY_SOURCE,
        "chart_window_calendar_days": CHART_DAYS,
        "retained_start": frame["date"].iloc[0],
        "last_date": frame["date"].iloc[-1],
        "matched_dates": len(frame),
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "unavailable_report_dates_this_refresh": sorted(unavailable),
        "sources": sources,
        "observations_path": observations_path,
        "observations_sha256": observations_sha,
    }
    pending = root / "manifest.pending.json"
    pending.write_text(json.dumps(manifest, indent=2) + "\n")
    pending.replace(root / "manifest.json")
    panel, metadata = load_history(root)
    print(
        f"NSE options risk premium: {len(panel)} sessions; "
        f"through {metadata['last_date']}; {len(unavailable)} dates had no report"
    )
    return panel, metadata


def main() -> int:
    try:
        refresh(NSE_OPTIONS_RISK_PREMIUM_DIR)
    except Exception as exc:
        print(f"NSE options risk-premium refresh failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
