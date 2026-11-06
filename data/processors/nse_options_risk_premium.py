"""Validated NSE daily inputs and calculations for the options risk-premium chart."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from data.paths import NSE_OPTIONS_RISK_PREMIUM_DIR

ROOT = NSE_OPTIONS_RISK_PREMIUM_DIR
DAILY_SOURCE = "https://archives.nseindia.com/content/indices/ind_close_all_{date}.csv"
SCHEMA = [
    "Index Name", "Index Date", "Open Index Value", "High Index Value",
    "Low Index Value", "Closing Index Value", "Points Change", "Change(%)",
    "Volume", "Turnover (Rs. Cr.)", "P/E", "P/B", "Div Yield",
]
TARGETS = {"Nifty 50": "nifty50_close", "India VIX": "india_vix_close"}
VERSION = "nse_india_vix_nifty50_options_risk_premium_v1"
CHART_DAYS = 365
REALIZED_WINDOW_DAYS = 30
TRADING_DAYS_PER_YEAR = 252
DRAWDOWN_SESSIONS = 252


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_daily(payload: bytes, expected_date: date | pd.Timestamp) -> dict[str, float]:
    """Read exact NIFTY 50 and India VIX identities from one official NSE report."""
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != SCHEMA:
        raise ValueError("Unexpected NSE daily indices CSV schema")
    found: dict[str, float] = {}
    expected = pd.Timestamp(expected_date).date()
    for row in reader:
        name = row["Index Name"]
        if name not in TARGETS:
            continue
        if name in found:
            raise ValueError(f"Duplicate {name} row in NSE daily report")
        observed = datetime.strptime(row["Index Date"], "%d-%m-%Y").date()
        if observed != expected:
            raise ValueError("NSE index date differs from requested report date")
        value = float(row["Closing Index Value"].replace(",", "").strip())
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid close for {name}")
        found[TARGETS[name]] = value
    if set(found) != set(TARGETS.values()):
        raise ValueError("NSE daily report is missing Nifty 50 or India VIX")
    return found


def _read_manifest(root: Path) -> tuple[list[dict], dict]:
    root = Path(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing NSE options risk-premium store: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("calculation_version") != VERSION:
        raise ValueError("Unrecognized NSE options risk-premium store version")
    sources = manifest.get("sources", [])
    if not sources:
        raise ValueError("NSE options risk-premium store has no source reports")
    rows = []
    for item in sources:
        day = date.fromisoformat(item["date"])
        source_url = DAILY_SOURCE.format(date=day.strftime("%d%m%Y"))
        if item.get("source_url") != source_url:
            raise ValueError(f"Unexpected NSE source URL for {day}")
        payload = (root / item["path"]).read_bytes()
        if digest(payload) != item.get("sha256"):
            raise ValueError(f"NSE source checksum mismatch for {day}")
        values = parse_daily(payload, day)
        rows.append({"date": pd.Timestamp(day), **values})
    data = pd.DataFrame(rows).set_index("date").sort_index()
    if data.index.has_duplicates or not data.index.is_monotonic_increasing:
        raise ValueError("NSE options risk-premium dates must be unique and sorted")
    if not np.isfinite(data.to_numpy()).all() or (data <= 0).any().any():
        raise ValueError("NSE options risk-premium values must be finite and positive")
    if str(data.index[-1].date()) != manifest.get("last_date"):
        raise ValueError("NSE options risk-premium last date does not match its manifest")
    observations_path = root / manifest.get("observations_path", "")
    observations_bytes = observations_path.read_bytes()
    if digest(observations_bytes) != manifest.get("observations_sha256"):
        raise ValueError("NSE options risk-premium observations checksum mismatch")
    published = pd.read_csv(observations_path, parse_dates=["date"]).set_index("date").sort_index()
    if not published.index.equals(data.index) or list(published.columns) != list(data.columns):
        raise ValueError("NSE options risk-premium observations differ from the source manifest")
    if not np.allclose(published.to_numpy(dtype=float), data.to_numpy(dtype=float), rtol=0, atol=1e-8):
        raise ValueError("NSE options risk-premium observations differ from the source reports")
    return sources, data


def load_history(root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    """Load checksum-verified official daily NIFTY 50 and India VIX closes."""
    _, data = _read_manifest(Path(root))
    manifest = json.loads((Path(root) / "manifest.json").read_text())
    return data, manifest


def calculate_panel(nifty50: pd.Series, india_vix: pd.Series) -> pd.DataFrame:
    """Calculate annualized trailing 30-calendar-day realized vol, IV gap and drawdown.

    Volatility uses daily log returns and sample standard deviation annualized by
    sqrt(252). The calendar window matches India VIX's stated 30-calendar-day
    horizon. Drawdown compares each close with its trailing 252-session high.
    """
    for label, series in (("NIFTY 50", nifty50), ("India VIX", india_vix)):
        if not isinstance(series.index, pd.DatetimeIndex) or series.index.has_duplicates:
            raise ValueError(f"{label} needs a unique DatetimeIndex")
        if not np.isfinite(series.to_numpy(dtype=float)).all() or (series <= 0).any():
            raise ValueError(f"{label} values must be finite and positive")
    if not nifty50.index.is_monotonic_increasing or not india_vix.index.is_monotonic_increasing:
        raise ValueError("NSE close series must be sorted by date")

    nifty = nifty50.astype(float).sort_index().rename("nifty50_close")
    vix = india_vix.astype(float).sort_index().rename("india_vix_close")
    if len(nifty) < DRAWDOWN_SESSIONS + 20:
        raise ValueError("Insufficient matched daily history for the drawdown calculation")

    log_return = np.log(nifty).diff()
    realized = log_return.rolling(
        f"{REALIZED_WINDOW_DAYS}D", min_periods=15,
    ).std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100
    drawdown = (
        nifty
        / nifty.rolling(DRAWDOWN_SESSIONS, min_periods=DRAWDOWN_SESSIONS).max()
        - 1
    ) * 100
    joined = pd.concat([nifty, vix], axis=1, join="inner").sort_index()
    joined["realized_vol_pct"] = realized
    joined["implied_minus_realized_pp"] = joined["india_vix_close"] - realized
    joined["drawdown_pct"] = drawdown
    joined.index.name = "date"
    return joined


def load_risk_premium(root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    """Combine the audited NIFTY price-index history with daily India VIX reports."""
    from data.processors.nse_indices import ROOT as NSE_INDEX_ROOT, read_sources

    vix_reports, metadata = load_history(root)
    index_manifest = json.loads((NSE_INDEX_ROOT / "manifest.json").read_text())
    index_series = read_sources(NSE_INDEX_ROOT, index_manifest["sources"])["largecap"]
    daily_nifty = vix_reports["nifty50_close"].rename("nifty50_close")

    # Use the audited historical NIFTY calendar to detect missing daily VIX reports.
    expected_end = min(index_series.index[-1], vix_reports.index[-1])
    expected_sessions = index_series.loc[
        (index_series.index >= vix_reports.index[0]) & (index_series.index <= expected_end)
    ].index
    missing_vix = expected_sessions.difference(vix_reports.index)
    if len(missing_vix):
        missing_dates = ", ".join(str(day.date()) for day in missing_vix[:5])
        raise ValueError(f"NSE India VIX history misses observed NIFTY sessions: {missing_dates}")

    # The two official NSE sources should agree on every overlapping NIFTY 50 close.
    common = index_series.index.intersection(daily_nifty.index)
    if len(common) and not np.allclose(
        index_series.loc[common].to_numpy(dtype=float),
        daily_nifty.loc[common].to_numpy(dtype=float), rtol=0, atol=0.011,
    ):
        raise ValueError("NSE daily report and historical NIFTY 50 closes disagree")
    nifty = pd.concat([index_series.rename("nifty50_close"), daily_nifty]).sort_index()
    if nifty.index.has_duplicates:
        # Overlapping observations were checked above; retain the historical-series value.
        nifty = nifty[~nifty.index.duplicated(keep="first")]
    panel = calculate_panel(nifty, vix_reports["india_vix_close"])
    return panel, metadata

