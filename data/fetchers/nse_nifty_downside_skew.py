"""Seed and refresh three years of weekly NSE NIFTY option-chain snapshots."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data.paths import NSE_NIFTY_DOWNSIDE_SKEW_DIR
from data.processors.nse_nifty_downside_skew import (
    HISTORY_MONTHS, ROOT, SUPPORTED_VERSIONS, VERSION, digest, extract_snapshot,
    load_history, load_nifty_close_history, parse_snapshot, publish,
)

UDIFF_URL = "https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date}_F_0000.csv.zip"
LEGACY_URL = "https://archives.nseindia.com/content/historical/DERIVATIVES/{year}/{month}/fo{legacy_date}bhav.csv.zip"
UDIFF_START = pd.Timestamp("2024-07-08").date()
RECHECK_DAYS = 14


def _today_ist() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()


def session() -> requests.Session:
    client = requests.Session()
    client.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/133.0.0.0 Safari/537.36",
        "Accept": "application/zip,application/octet-stream,*/*",
        "Referer": "https://www.nseindia.com/all-reports-derivatives",
    })
    client.mount("https://", HTTPAdapter(max_retries=Retry(
        total=4, backoff_factor=.8, status_forcelist=(429, 500, 502, 503, 504))))
    return client


def _save_subset(root: Path, payload: bytes) -> dict:
    sha = digest(payload)
    relative = f"raw/{sha}.csv"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(payload)
    return {"subset_path": relative, "subset_sha256": sha, "subset_bytes": len(payload)}


def _source_for_day(day: pd.Timestamp) -> tuple[str, str]:
    if day.date() < UDIFF_START:
        return LEGACY_URL.format(
            year=day.strftime("%Y"), month=day.strftime("%b").upper(),
            legacy_date=day.strftime("%d%b%Y").upper(),
        ), "legacy"
    return UDIFF_URL.format(date=day.strftime("%Y%m%d")), "udiff"


def _fetch_day(client: requests.Session, root: Path, day: pd.Timestamp,
               underlying_spot: float) -> dict:
    url, archive_format = _source_for_day(day)
    response = client.get(url, timeout=(10, 60))
    response.raise_for_status()
    archive = response.content
    subset, row_count = extract_snapshot(archive, day.date(), underlying_spot=underlying_spot)
    return {
        "date": day.date().isoformat(),
        "url": url,
        "archive_format": archive_format,
        "archive_sha256": digest(archive),
        "archive_bytes": len(archive),
        "rows": row_count,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        **_save_subset(root, subset),
    }


def _save_checkpoint(root: Path, retained_start: pd.Timestamp, final_day: pd.Timestamp,
                     sources: dict[str, dict]) -> None:
    path = root / "refresh.checkpoint.json"
    pending = root / "refresh.checkpoint.pending.json"
    pending.write_text(json.dumps({
        "calculation_version": VERSION,
        "retained_start": retained_start.date().isoformat(),
        "final_date": final_day.date().isoformat(),
        "sources": [sources[key] for key in sorted(sources)],
    }, indent=2) + "\n")
    pending.replace(path)


def _weekly_dates(end_date: pd.Timestamp) -> tuple[pd.DatetimeIndex, pd.Timestamp, pd.Series]:
    nifty = load_nifty_close_history().dropna().sort_index()
    if nifty.empty or nifty.index.has_duplicates:
        raise ValueError("Official NSE NIFTY 50 date calendar is unavailable or invalid")
    end_date = min(end_date.normalize(), nifty.index[-1])
    start_date = end_date - pd.DateOffset(months=HISTORY_MONTHS)
    matched = nifty.loc[(nifty.index >= start_date) & (nifty.index <= end_date)]
    dates = matched.groupby(matched.index.to_period("W-FRI"), sort=True).tail(1).index
    if len(dates) < 140:
        raise ValueError(f"Only {len(dates)} NSE weeks are available in the requested 36-month window")
    return pd.DatetimeIndex(dates, name="date"), start_date, nifty


def refresh(root: Path = NSE_NIFTY_DOWNSIDE_SKEW_DIR,
            end: str | date | None = None) -> tuple[pd.DataFrame, dict]:
    root = Path(root)
    completed_day = pd.Timestamp(end or (_today_ist() - timedelta(days=1))).normalize()
    if completed_day.date() >= _today_ist():
        raise ValueError("Only completed NSE trading dates can be requested")
    weekly_dates, retained_start, nifty = _weekly_dates(completed_day)
    final_day = weekly_dates[-1]

    previous_sources: dict[str, dict] = {}
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        old_manifest = json.loads(manifest_path.read_text())
        if old_manifest.get("calculation_version") in SUPPORTED_VERSIONS:
            _, old_manifest = load_history(root)
            previous_sources = {
                source["date"]: source for source in old_manifest["sources"]
                if pd.Timestamp(source["date"]) >= retained_start
            }
    checkpoint_path = root / "refresh.checkpoint.json"
    checkpoint_sources: dict[str, dict] = {}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        if (checkpoint.get("calculation_version") == VERSION
                and checkpoint.get("retained_start") == retained_start.date().isoformat()
                and checkpoint.get("final_date") == final_day.date().isoformat()):
            checkpoint_sources = {
                item["date"]: item for item in checkpoint.get("sources", [])
                if pd.Timestamp(item["date"]) >= retained_start
            }

    client = session()
    sources: dict[str, dict] = {}
    for day in weekly_dates:
        key = day.date().isoformat()
        cached = checkpoint_sources.get(key) or previous_sources.get(key)
        if cached and (final_day - day).days > RECHECK_DAYS:
            sources[key] = cached
        else:
            if day not in nifty.index:
                raise ValueError(f"No official NIFTY 50 spot close is available for {key}")
            sources[key] = _fetch_day(client, root, day, float(nifty.loc[day]))
            print(f"   NSE NIFTY weekly chain: {key} ({len(sources)} of {len(weekly_dates)})", flush=True)
            time.sleep(.12)
            checkpoint_sources[key] = sources[key]
            _save_checkpoint(root, retained_start, final_day, checkpoint_sources)

    frames = []
    for key in sorted(sources):
        source = sources[key]
        subset = (root / source["subset_path"]).read_bytes()
        if digest(subset) != source["subset_sha256"]:
            raise ValueError(f"NSE NIFTY option subset changed for {key}")
        frame = parse_snapshot(subset, key)
        if len(frame) != int(source["rows"]):
            raise ValueError(f"NSE NIFTY option rows changed for {key}")
        frames.append(frame)
    options = pd.concat(frames, ignore_index=True)
    options = options.loc[options["date"] >= retained_start].copy()
    source_dates = sorted(set(options["date"].dt.strftime("%Y-%m-%d")))
    selected_dates = [day.date().isoformat() for day in weekly_dates if day >= retained_start]
    if source_dates != selected_dates:
        missing = sorted(set(selected_dates).difference(source_dates))
        raise ValueError(f"NSE option chain snapshots do not cover weekly dates: {missing[:5]}")

    metadata = {
        "calculation_version": VERSION,
        "history_months": HISTORY_MONTHS,
        "source_note": "NSE official daily F&O bhavcopies: legacy archive before 8 July 2024 and UDiFF archive from 8 July 2024. One complete NIFTY index-option chain is kept for each week's final trading session. Local raw extracts retain only 7–60 day expiries. Legacy rows use the matching official NIFTY 50 spot close; UDiFF rows use NSE's underlying price. IV is solved from traded daily closes using Black–Scholes spot deltas (6% continuously compounded rate, 1.2% dividend yield); constant 30-day volatility is interpolated in total variance.",
        "source_url_templates": {"legacy": LEGACY_URL, "udiff": UDIFF_URL},
        "weekly_date_calendar": "Official NSE / NIFTY Indices NIFTY 50 daily closes",
        "legacy_underlying_source": "NIFTY 50 official historical index closes",
        "requested_end": final_day.date().isoformat(),
        "retained_start": retained_start.date().isoformat(),
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "sources": [sources[key] for key in sorted(sources)],
    }
    published, manifest = publish(options, metadata, root)
    checkpoint_path.unlink(missing_ok=True)
    print(f"NSE NIFTY downside-skew store: {len(published):,} contract rows; "
          f"{len(manifest['sources'])} weekly snapshots; through {manifest['last_option_date']}", flush=True)
    return published, manifest


def main() -> int:
    try:
        refresh(NSE_NIFTY_DOWNSIDE_SKEW_DIR)
    except Exception as exc:
        print(f"NSE NIFTY downside-skew refresh failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

