"""Validated daily NSE FPI/DII cash-market observations and weekly aggregation."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from data.paths import NSE_INSTITUTIONAL_FLOWS_DIR

ROOT = NSE_INSTITUTIONAL_FLOWS_DIR
ARCHIVE_URL = "https://indmarket.in/fii-dii-activity"
NSE_DAILY_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
VERSION = "nse_fpi_dii_cash_weekly_v1"
HISTORY_MONTHS = 6
DAILY_COLUMNS = ["fpi_buy_cr", "fpi_sell_cr", "fpi_net_cr",
                 "dii_buy_cr", "dii_sell_cr", "dii_net_cr"]

# IndMarket's server-rendered historical ledger is embedded in Next.js RSC as
# escaped JSON objects. Keep the parser narrow so a page/schema change fails closed.
_ARCHIVE_ROW = re.compile(
    r'\{\\"id\\":\d+,\\"date\\":\\"(?P<date>\d{4}-\d{2}-\d{2})\\",'
    r'\\"fii_buy\\":(?P<fpi_buy>-?\d+(?:\.\d+)?),'
    r'\\"fii_sell\\":(?P<fpi_sell>-?\d+(?:\.\d+)?),'
    r'\\"fii_net\\":(?P<fpi_net>-?\d+(?:\.\d+)?),'
    r'\\"dii_buy\\":(?P<dii_buy>-?\d+(?:\.\d+)?),'
    r'\\"dii_sell\\":(?P<dii_sell>-?\d+(?:\.\d+)?),'
    r'\\"dii_net\\":(?P<dii_net>-?\d+(?:\.\d+)?)'
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_row(row: dict, date_text: str, source: str) -> dict:
    values = {name: float(row[name]) for name in DAILY_COLUMNS}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError(f"Non-finite institutional flow in {source} for {date_text}")
    for prefix in ("fpi", "dii"):
        buy, sell, net = (values[f"{prefix}_{part}_cr"] for part in ("buy", "sell", "net"))
        if buy < 0 or sell < 0 or abs((buy - sell) - net) > 0.03:
            raise ValueError(f"Buy/sell/net do not reconcile in {source} for {date_text}")
    return values


def parse_archive(payload: bytes, cutoff: str) -> pd.DataFrame:
    """Parse the public historical ledger for the requested start date onward."""
    html = payload.decode("utf-8")
    found: dict[str, dict] = {}
    for match in _ARCHIVE_ROW.finditer(html):
        day = match.group("date")
        if day < cutoff:
            continue
        row = {
            "fpi_buy_cr": match.group("fpi_buy"),
            "fpi_sell_cr": match.group("fpi_sell"),
            "fpi_net_cr": match.group("fpi_net"),
            "dii_buy_cr": match.group("dii_buy"),
            "dii_sell_cr": match.group("dii_sell"),
            "dii_net_cr": match.group("dii_net"),
        }
        values = _validate_row(row, day, "historical archive")
        if day in found and found[day] != values:
            raise ValueError(f"Conflicting duplicate archive observation: {day}")
        found[day] = values
    if len(found) < 100:
        raise ValueError(f"Historical archive returned only {len(found)} rows since {cutoff}")
    frame = pd.DataFrame.from_dict(found, orient="index")
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "date"
    frame = frame.sort_index()
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Historical archive dates must be unique and sorted")
    return frame


def parse_nse_daily(payload: bytes) -> pd.DataFrame:
    """Parse NSE's current daily FII/FPI + DII endpoint (two category rows)."""
    try:
        rows = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("NSE daily FII/DII response is not JSON") from exc
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("Unexpected NSE daily FII/DII response shape")
    by_category = {}
    dates = set()
    for item in rows:
        if not isinstance(item, dict) or item.get("category") not in {"FII/FPI", "DII"}:
            raise ValueError("Unexpected NSE FII/DII category")
        dates.add(pd.to_datetime(item.get("date"), format="%d-%b-%Y", errors="raise").normalize())
        by_category[item["category"]] = item
    if set(by_category) != {"FII/FPI", "DII"} or len(dates) != 1:
        raise ValueError("NSE response must contain one date and both institutional categories")
    date_value = next(iter(dates))
    values = {}
    for category, prefix in (("FII/FPI", "fpi"), ("DII", "dii")):
        item = by_category[category]
        values[f"{prefix}_buy_cr"] = item.get("buyValue")
        values[f"{prefix}_sell_cr"] = item.get("sellValue")
        values[f"{prefix}_net_cr"] = item.get("netValue")
    clean = _validate_row(values, str(date_value.date()), "NSE daily API")
    return pd.DataFrame([clean], index=pd.DatetimeIndex([date_value], name="date"))


def load(root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    root = Path(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing NSE institutional-flow store: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("version") != VERSION:
        raise ValueError("Unrecognized institutional-flow store version")
    rows = manifest.get("observations", [])
    if not rows:
        raise ValueError("Institutional-flow store is empty")
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame = frame.set_index("date").sort_index()
    if frame.index.has_duplicates or list(frame.columns) != DAILY_COLUMNS:
        raise ValueError("Institutional-flow store has duplicate dates or unexpected columns")
    values = frame[DAILY_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Institutional-flow store contains non-finite values")
    for prefix in ("fpi", "dii"):
        if not np.allclose(frame[f"{prefix}_buy_cr"] - frame[f"{prefix}_sell_cr"],
                           frame[f"{prefix}_net_cr"], rtol=0, atol=0.03):
            raise ValueError(f"Stored {prefix.upper()} flows do not reconcile")
    for item in manifest.get("sources", {}).values():
        payload = (root / item["path"]).read_bytes()
        if digest(payload) != item.get("sha256"):
            raise ValueError("Institutional-flow historical source checksum mismatch")
    archive = manifest.get("sources", {}).get("historical_archive")
    row_sources = manifest.get("row_sources", {})
    archive_days = [day for day, source in row_sources.items()
                    if source in {"third_party_historical_archive", "archive_cross_checked_against_nse"}]
    if archive and archive_days:
        original = parse_archive((root / archive["path"]).read_bytes(), min(archive_days))
        for day in archive_days:
            stamp = pd.Timestamp(day)
            if stamp not in frame.index or stamp not in original.index:
                raise ValueError(f"Institutional-flow archive observation missing for {day}")
            if not np.allclose(frame.loc[stamp, DAILY_COLUMNS].to_numpy(dtype=float),
                               original.loc[stamp, DAILY_COLUMNS].to_numpy(dtype=float), rtol=0, atol=0.03):
                raise ValueError(f"Institutional-flow archive values changed for {day}")
    for snapshot in manifest.get("nse_daily_snapshots", []):
        payload = (root / snapshot["path"]).read_bytes()
        if digest(payload) != snapshot.get("sha256"):
            raise ValueError("Institutional-flow NSE snapshot checksum mismatch")
        official = parse_nse_daily(payload)
        stamp = official.index[0]
        if str(stamp.date()) != snapshot.get("date") or stamp not in frame.index:
            raise ValueError("NSE snapshot date does not match stored observations")
        if not np.allclose(frame.loc[stamp, DAILY_COLUMNS].to_numpy(dtype=float),
                           official.loc[stamp, DAILY_COLUMNS].to_numpy(dtype=float), rtol=0, atol=0.03):
            raise ValueError(f"Institutional-flow NSE snapshot differs from stored data for {stamp.date()}")
    expected = manifest.get("observations_sha256")
    raw = (root / manifest["observations_path"]).read_bytes()
    if digest(raw) != expected:
        raise ValueError("Institutional-flow observations checksum mismatch")
    published = pd.read_csv(root / manifest["observations_path"], parse_dates=["date"])
    if not published["date"].equals(pd.Series(frame.index, name="date")):
        raise ValueError("Institutional-flow CSV dates differ from manifest")
    return frame, manifest


def publish(frame: pd.DataFrame, manifest: dict, root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    frame = frame[DAILY_COLUMNS].sort_index()
    frame.index.name = "date"
    csv_bytes = frame.reset_index().to_csv(index=False, float_format="%.8g").encode("utf-8")
    checksum = digest(csv_bytes)
    relative = f"derived/{checksum}.csv"
    target = root / relative
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        target.write_bytes(csv_bytes)
    manifest = {**manifest, "version": VERSION, "first_date": str(frame.index[0].date()),
                "last_date": str(frame.index[-1].date()), "observations": [
                    {"date": str(day.date()), **{key: float(row[key]) for key in DAILY_COLUMNS}}
                    for day, row in frame.iterrows()],
                "observations_path": relative, "observations_sha256": checksum}
    pending = root / "manifest.pending.json"
    pending.write_text(json.dumps(manifest, indent=2) + "\n")
    pending.replace(root / "manifest.json")
    return frame, manifest


def weekly(frame: pd.DataFrame) -> pd.DataFrame:
    """Sum daily net cash-market flows by Friday-ending NSE trading week."""
    data = frame.copy().sort_index()
    grouped = data.groupby(data.index.to_period("W-FRI"))
    result = grouped[["fpi_net_cr", "dii_net_cr"]].sum(min_count=1)
    result["sessions"] = grouped.size()
    result.index = result.index.end_time.normalize()
    result.index.name = "week_ending"
    return result
