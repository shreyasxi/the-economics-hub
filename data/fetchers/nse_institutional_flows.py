"""Seed and refresh six months of daily NSE FPI/DII cash flows.

Bootstrap: ``python -m data.fetchers.nse_institutional_flows --bootstrap``
Daily:     ``python -m data.fetchers.nse_institutional_flows``
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data.paths import NSE_INSTITUTIONAL_FLOWS_DIR
from data.processors.nse_institutional_flows import (
    ARCHIVE_URL, DAILY_COLUMNS, HISTORY_MONTHS, NSE_DAILY_URL, ROOT, VERSION,
    digest, load, parse_archive, parse_nse_daily, publish,
)


def session() -> requests.Session:
    client = requests.Session()
    client.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; EconomicsHub institutional-flow collector)",
        "Accept": "application/json,text/html,*/*",
        "Referer": "https://www.nseindia.com/reports/fii-dii",
    })
    client.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=0.7, status_forcelist=(429, 500, 502, 503, 504))))
    return client


def _save_raw(root: Path, payload: bytes, suffix: str) -> dict:
    sha = digest(payload)
    relative = f"raw/{sha}.{suffix}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(payload)
    return {"path": relative, "sha256": sha, "bytes": len(payload)}


def _fetch_nse(client: requests.Session) -> tuple[pd.DataFrame, bytes]:
    response = client.get(NSE_DAILY_URL, timeout=(10, 30))
    response.raise_for_status()
    return parse_nse_daily(response.content), response.content


def bootstrap(root: Path = ROOT, client: requests.Session | None = None) -> tuple[pd.DataFrame, dict]:
    """Import archive history, then require an exact latest-date NSE cross-check."""
    root = Path(root)
    client = client or session()
    nse_frame, nse_payload = _fetch_nse(client)
    last = nse_frame.index[-1]
    cutoff = str((last - pd.DateOffset(months=HISTORY_MONTHS)).date())
    response = client.get(ARCHIVE_URL, timeout=(10, 45))
    response.raise_for_status()
    archive_frame = parse_archive(response.content, cutoff)
    nse_values = nse_frame.loc[last, DAILY_COLUMNS].astype(float)
    if last not in archive_frame.index:
        raise ValueError("Historical archive does not include the latest NSE observation")
    if not (archive_frame.loc[last, DAILY_COLUMNS].astype(float).sub(nse_values).abs() <= 0.03).all():
        raise ValueError("Latest archive values disagree with NSE's official daily endpoint")

    root.mkdir(parents=True, exist_ok=True)
    archive_raw = _save_raw(root, response.content, "html")
    nse_raw = _save_raw(root, nse_payload, "json")
    sources = {
        "historical_archive": {"url": ARCHIVE_URL, "retrieved_at": datetime.now(timezone.utc).isoformat(), **archive_raw},
    }
    nse_snapshots = [{"date": str(last.date()), "url": NSE_DAILY_URL,
                      "retrieved_at": datetime.now(timezone.utc).isoformat(), **nse_raw}]
    row_sources = {str(day.date()): "third_party_historical_archive" for day in archive_frame.index}
    row_sources[str(last.date())] = "archive_cross_checked_against_nse"
    manifest = {
        "version": VERSION,
        "history_months": HISTORY_MONTHS,
        "source_note": "NSE/BSE cash market daily figures; archive backfill cross-checked against NSE daily API at latest date. NSE daily figures are provisional.",
        "sources": sources,
        "nse_daily_snapshots": nse_snapshots,
        "row_sources": row_sources,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
    frame, metadata = publish(archive_frame, manifest, root)
    print(f"Institutional flows seeded: {len(frame)} sessions; {frame.index[0].date()} to {last.date()}")
    return frame, metadata


def refresh(root: Path = ROOT, client: requests.Session | None = None) -> tuple[pd.DataFrame, dict]:
    """Append the latest NSE observation; refuse gaps that cannot be recovered."""
    root = Path(root)
    frame, previous = load(root)
    client = client or session()
    daily, payload = _fetch_nse(client)
    day = daily.index[-1]
    last = frame.index[-1]
    row_sources = dict(previous.get("row_sources", {}))
    sources = dict(previous.get("sources", {}))
    nse_snapshots = list(previous.get("nse_daily_snapshots", []))

    if day < last:
        raise ValueError(f"NSE daily endpoint regressed from {last.date()} to {day.date()}")
    if day == last:
        if not (frame.loc[day, DAILY_COLUMNS].astype(float).sub(daily.loc[day, DAILY_COLUMNS].astype(float)).abs() <= 0.03).all():
            raise ValueError("NSE latest observation differs from the stored same-date archive value")
        return frame, previous
    else:
        gap = (day - last).days
        if gap > 5:
            raise ValueError(f"NSE collector missed {gap} calendar days; daily endpoint cannot backfill the gap")
        frame = pd.concat([frame, daily]).sort_index()
        row_sources[str(day.date())] = "nse_official_daily_provisional"
    raw = _save_raw(root, payload, "json")
    nse_snapshots.append({"date": str(day.date()), "url": NSE_DAILY_URL,
                          "retrieved_at": datetime.now(timezone.utc).isoformat(), **raw})

    cutoff = day - pd.DateOffset(months=HISTORY_MONTHS)
    frame = frame.loc[frame.index >= cutoff]
    row_sources = {key: value for key, value in row_sources.items() if pd.Timestamp(key) >= cutoff}
    nse_snapshots = [item for item in nse_snapshots if pd.Timestamp(item["date"]) >= cutoff]
    manifest = {
        "version": VERSION,
        "history_months": HISTORY_MONTHS,
        "source_note": "Six-month daily cash-market flow history; historical rows from the public archive, new rows from the provisional NSE daily endpoint.",
        "sources": sources,
        "nse_daily_snapshots": nse_snapshots,
        "row_sources": row_sources,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
    frame, metadata = publish(frame[DAILY_COLUMNS], manifest, root)
    print(f"Institutional flows refreshed: {len(frame)} sessions; through {metadata['last_date']}")
    return frame, metadata


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=NSE_INSTITUTIONAL_FLOWS_DIR)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()
    try:
        if args.bootstrap:
            if (args.root / "manifest.json").exists():
                refresh(args.root)
            else:
                bootstrap(args.root)
        else:
            refresh(args.root)
    except Exception as exc:
        print(f"NSE institutional-flow refresh failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
