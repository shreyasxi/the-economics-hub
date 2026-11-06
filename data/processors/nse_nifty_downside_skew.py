"""Audited NSE NIFTY options snapshots and 30-day downside skew calculations."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import date
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from data.paths import NSE_NIFTY_DOWNSIDE_SKEW_DIR

ROOT = NSE_NIFTY_DOWNSIDE_SKEW_DIR
VERSION = "nse_nifty50_30d_25delta_skew_v3"
SUPPORTED_VERSIONS = {"nse_nifty50_30d_25delta_skew_v2", VERSION}
HISTORY_MONTHS = 36
TARGET_TENOR_DAYS = 30
MIN_EXPIRY_DAYS = 7
MAX_EXPIRY_DAYS = 60
RISK_FREE_RATE = 0.06
DIVIDEND_YIELD = 0.012
OPTION_COLUMNS = [
    "date", "expiry_date", "option_type", "strike", "close_price",
    "volume", "open_interest", "underlying",
]


def load_nifty_close_history() -> pd.Series:
    """Load a long official NSE NIFTY 50 close series and append recent daily closes."""
    from data.processors.nse_indices import ROOT as NSE_INDEX_ROOT, read_sources
    from data.processors.nse_options_risk_premium import (
        ROOT as OPTIONS_RISK_ROOT,
        load_history as load_daily_index_reports,
    )

    index_manifest = json.loads((NSE_INDEX_ROOT / "manifest.json").read_text())
    long_series = read_sources(NSE_INDEX_ROOT, index_manifest["sources"])["largecap"]
    recent_reports, _ = load_daily_index_reports(OPTIONS_RISK_ROOT)
    recent = recent_reports["nifty50_close"].rename("nifty50_close")
    common = long_series.index.intersection(recent.index)
    if len(common) and not np.allclose(
        long_series.loc[common].to_numpy(float), recent.loc[common].to_numpy(float),
        rtol=0, atol=0.011,
    ):
        raise ValueError("NSE historical and daily NIFTY 50 closes disagree")
    combined = pd.concat([long_series.rename("nifty50_close"), recent]).sort_index()
    if combined.index.has_duplicates:
        combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.astype(float).sort_index()
    if (combined.empty or combined.index.has_duplicates or not combined.index.is_monotonic_increasing
            or not np.isfinite(combined.to_numpy()).all() or (combined <= 0).any()):
        raise ValueError("Official NSE NIFTY 50 closes are incomplete or invalid")
    return combined


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_day(value: str) -> date:
    return pd.Timestamp(value).date()


def extract_snapshot(archive: bytes, expected_date: str | date,
                     underlying_spot: float | None = None) -> tuple[bytes, int]:
    """Keep the NIFTY option chain from either NSE's legacy or UDiFF bhavcopy."""
    expected = pd.Timestamp(expected_date).date()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
            if len(names) != 1:
                raise ValueError("NSE UDiFF F&O archive must contain exactly one CSV")
            raw = zf.read(names[0])
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("NSE UDiFF F&O archive is not a valid zip file") from exc
    text = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    fields = set(reader.fieldnames or [])
    udiff_fields = {"TradDt", "Sgmt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric",
                    "OptnTp", "ClsPric", "UndrlygPric", "OpnIntrst", "TtlTradgVol"}
    legacy_fields = {"INSTRUMENT", "SYMBOL", "EXPIRY_DT", "STRIKE_PR", "OPTION_TYP",
                     "CLOSE", "CONTRACTS", "OPEN_INT", "TIMESTAMP"}
    if udiff_fields.issubset(fields):
        archive_format = "udiff"
    elif legacy_fields.issubset(fields):
        archive_format = "legacy"
        if underlying_spot is None or not math.isfinite(float(underlying_spot)) or underlying_spot <= 0:
            raise ValueError("Legacy NSE options need an official NIFTY 50 spot close")
    else:
        raise ValueError("Unexpected NSE F&O bhavcopy schema")
    selected = []

    def add_row(observed, expiry, option_type, strike, close_price, volume,
                open_interest, underlying):
        observed, expiry = _parse_day(observed), _parse_day(expiry)
        if observed != expected:
            raise ValueError("NSE bhavcopy trade date differs from the requested date")
        dte = (expiry - observed).days
        if not MIN_EXPIRY_DAYS <= dte <= MAX_EXPIRY_DAYS:
            return
        values = {
            "date": observed.isoformat(),
            "expiry_date": expiry.isoformat(),
            "option_type": option_type,
            "strike": float(strike),
            "close_price": float(close_price),
            "volume": float(volume),
            "open_interest": float(open_interest),
            "underlying": float(underlying),
        }
        if not all(math.isfinite(value) for key, value in values.items()
                   if key not in {"date", "expiry_date", "option_type"}):
            raise ValueError("NSE NIFTY option row contains a non-finite numeric value")
        if (values["strike"] <= 0 or values["close_price"] < 0 or values["volume"] < 0
                or values["open_interest"] < 0 or values["underlying"] <= 0):
            raise ValueError("NSE NIFTY option row contains an invalid numeric value")
        selected.append(values)

    for row in reader:
        if archive_format == "udiff":
            if (row.get("Sgmt") != "FO" or row.get("FinInstrmTp") != "IDO"
                    or row.get("TckrSymb") != "NIFTY" or row.get("OptnTp") not in {"CE", "PE"}):
                continue
            add_row(row["TradDt"], row["XpryDt"], row["OptnTp"], row["StrkPric"],
                    row["ClsPric"], row["TtlTradgVol"], row["OpnIntrst"], row["UndrlygPric"])
        else:
            if (row.get("INSTRUMENT") != "OPTIDX" or row.get("SYMBOL") != "NIFTY"
                    or row.get("OPTION_TYP") not in {"CE", "PE"}):
                continue
            add_row(row["TIMESTAMP"], row["EXPIRY_DT"], row["OPTION_TYP"], row["STRIKE_PR"],
                    row["CLOSE"], row["CONTRACTS"], row["OPEN_INT"], underlying_spot)
    frame = pd.DataFrame(selected, columns=OPTION_COLUMNS)
    if frame.empty:
        raise ValueError(f"NSE bhavcopy has no NIFTY options 7–60 days from expiry on {expected}")
    if frame.duplicated(["date", "expiry_date", "option_type", "strike"]).any():
        raise ValueError("NSE NIFTY option snapshot contains duplicate contracts")
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8"), len(frame)


def parse_snapshot(payload: bytes, expected_date: str | date) -> pd.DataFrame:
    expected = pd.Timestamp(expected_date).normalize()
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise ValueError("Stored NIFTY option snapshot is not UTF-8") from exc
    if reader.fieldnames != OPTION_COLUMNS:
        raise ValueError("Stored NIFTY option snapshot has an unexpected schema")
    rows = []
    for row in reader:
        day = pd.to_datetime(row["date"], errors="raise").normalize()
        expiry = pd.to_datetime(row["expiry_date"], errors="raise").normalize()
        option_type = row["option_type"]
        if day != expected or option_type not in {"CE", "PE"}:
            raise ValueError("Stored NIFTY option snapshot has an unexpected date or option side")
        dte = (expiry - day).days
        if not MIN_EXPIRY_DAYS <= dte <= MAX_EXPIRY_DAYS:
            raise ValueError("Stored NIFTY option snapshot includes an out-of-window expiry")
        values = {key: float(row[key]) for key in ("strike", "close_price", "volume", "open_interest", "underlying")}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("Stored NIFTY option snapshot contains a non-finite value")
        if (values["strike"] <= 0 or values["close_price"] < 0 or values["volume"] < 0
                or values["open_interest"] < 0 or values["underlying"] <= 0):
            raise ValueError("Stored NIFTY option snapshot contains an invalid value")
        rows.append({"date": day, "expiry_date": expiry, "option_type": option_type, **values})
    frame = pd.DataFrame(rows, columns=OPTION_COLUMNS)
    if frame.duplicated(["date", "expiry_date", "option_type", "strike"]).any():
        raise ValueError("Stored NIFTY option snapshot contains duplicate contracts")
    return frame


def _read_store(root: Path) -> tuple[pd.DataFrame, dict]:
    root = Path(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing NIFTY downside-skew store: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("calculation_version") not in SUPPORTED_VERSIONS:
        raise ValueError("Unrecognized NIFTY downside-skew store version")
    sources = manifest.get("sources", [])
    if not sources:
        raise ValueError("NIFTY downside-skew store has no official source snapshots")
    frames = []
    dates_seen = set()
    for source in sorted(sources, key=lambda item: item["date"]):
        if source["date"] in dates_seen:
            raise ValueError("NIFTY downside-skew manifest has duplicate weekly source dates")
        dates_seen.add(source["date"])
        payload = (root / source["subset_path"]).read_bytes()
        if digest(payload) != source.get("subset_sha256"):
            raise ValueError(f"NSE NIFTY option subset checksum mismatch for {source['date']}")
        frame = parse_snapshot(payload, source["date"])
        if len(frame) != int(source["rows"]):
            raise ValueError(f"NSE NIFTY option row count changed for {source['date']}")
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data = data.loc[data["date"] >= pd.Timestamp(manifest["retained_start"])].copy()
    data = data.sort_values(["date", "expiry_date", "option_type", "strike"]).reset_index(drop=True)

    observations_path = root / manifest.get("observations_path", "")
    published_bytes = observations_path.read_bytes()
    if digest(published_bytes) != manifest.get("observations_sha256"):
        raise ValueError("NIFTY downside-skew derived-data checksum mismatch")
    published = pd.read_csv(observations_path, parse_dates=["date", "expiry_date"])
    published = published.sort_values(["date", "expiry_date", "option_type", "strike"]).reset_index(drop=True)
    if list(published.columns) != OPTION_COLUMNS or len(published) != len(data):
        raise ValueError("NIFTY downside-skew derived data differs from its source manifest")
    for col in ("date", "expiry_date", "option_type"):
        if not published[col].equals(data[col]):
            raise ValueError("NIFTY downside-skew contract identities differ from source snapshots")
    numeric = ["strike", "close_price", "volume", "open_interest", "underlying"]
    if not np.allclose(published[numeric].to_numpy(float), data[numeric].to_numpy(float), rtol=0, atol=1e-8):
        raise ValueError("NIFTY downside-skew values differ from source snapshots")
    if data["date"].nunique() != len(sources):
        raise ValueError("NIFTY downside-skew observations do not cover each selected weekly date")
    return data, manifest


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def _bs_price(spot: float, strike: float, tenor: float, volatility: float,
              option_type: str) -> float:
    root_t = math.sqrt(tenor)
    d1 = (math.log(spot / strike) + (RISK_FREE_RATE - DIVIDEND_YIELD + 0.5 * volatility**2) * tenor) / (volatility * root_t)
    d2 = d1 - volatility * root_t
    if option_type == "CE":
        return spot * math.exp(-DIVIDEND_YIELD * tenor) * _normal_cdf(d1) - strike * math.exp(-RISK_FREE_RATE * tenor) * _normal_cdf(d2)
    return strike * math.exp(-RISK_FREE_RATE * tenor) * _normal_cdf(-d2) - spot * math.exp(-DIVIDEND_YIELD * tenor) * _normal_cdf(-d1)


def _implied_vol(price: float, spot: float, strike: float, tenor: float,
                 option_type: str) -> float | None:
    if price <= 0 or tenor <= 0:
        return None
    intrinsic = max(spot - strike, 0) if option_type == "CE" else max(strike - spot, 0)
    if price + 1e-7 < intrinsic:
        return None
    low, high = 0.005, 4.0
    if price < _bs_price(spot, strike, tenor, low, option_type) - 1e-6:
        return None
    if price > _bs_price(spot, strike, tenor, high, option_type):
        return None
    for _ in range(56):
        mid = (low + high) / 2
        if _bs_price(spot, strike, tenor, mid, option_type) < price:
            low = mid
        else:
            high = mid
    volatility = (low + high) / 2
    return volatility if 0.02 <= volatility <= 2.5 else None


def _delta25_smile(chain: pd.DataFrame, option_type: str) -> float | None:
    day = pd.Timestamp(chain["date"].iloc[0])
    expiry = pd.Timestamp(chain["expiry_date"].iloc[0])
    tenor = (expiry - day).days / 365.0
    if tenor <= 0:
        return None
    spot = float(chain["underlying"].median())
    if chain["underlying"].max() - chain["underlying"].min() > max(2.0, spot * .0002):
        return None
    otm = chain[(chain["option_type"] == option_type) & (chain["volume"] > 0) & (chain["close_price"] > 0)].copy()
    otm = otm.loc[otm["strike"] >= spot] if option_type == "CE" else otm.loc[otm["strike"] <= spot]
    points = []
    for row in otm.itertuples(index=False):
        strike = float(row.strike)
        iv = _implied_vol(float(row.close_price), spot, strike, tenor, option_type)
        if iv is None:
            continue
        d1 = (math.log(spot / strike) +
              (RISK_FREE_RATE - DIVIDEND_YIELD + .5 * iv**2) * tenor) / (iv * math.sqrt(tenor))
        delta = math.exp(-DIVIDEND_YIELD * tenor) * (
            _normal_cdf(d1) if option_type == "CE" else _normal_cdf(-d1)
        )
        if 0 < delta < 1:
            points.append((delta, iv))
    if len(points) < 2:
        return None
    points.sort(key=lambda item: item[0])
    deltas = np.asarray([item[0] for item in points])
    vols = np.asarray([item[1] for item in points])
    if deltas[0] > .25 or deltas[-1] < .25:
        return None
    return float(np.interp(.25, deltas, vols))


def calculate_daily(options: pd.DataFrame) -> pd.DataFrame:
    """Calculate 30-day constant-maturity 25-delta put IV minus call IV."""
    if options.empty or not set(OPTION_COLUMNS).issubset(options.columns):
        raise ValueError("NSE option snapshots are empty or missing required columns")
    per_expiry = []
    for (_, _), chain in options.groupby(["date", "expiry_date"], sort=True):
        day = pd.Timestamp(chain["date"].iloc[0])
        expiry = pd.Timestamp(chain["expiry_date"].iloc[0])
        days = (expiry - day).days
        if not MIN_EXPIRY_DAYS <= days <= MAX_EXPIRY_DAYS:
            continue
        put_iv = _delta25_smile(chain, "PE")
        call_iv = _delta25_smile(chain, "CE")
        if put_iv is not None and call_iv is not None:
            per_expiry.append({
                "date": day, "expiry_date": expiry, "tenor_years": days / 365.0,
                "put_iv_25_pct": put_iv * 100, "call_iv_25_pct": call_iv * 100,
            })
    if not per_expiry:
        raise ValueError("No weekly snapshot has a valid traded 25-delta call and put")
    smiles = pd.DataFrame(per_expiry).sort_values(["date", "tenor_years"])
    target_tenor = TARGET_TENOR_DAYS / 365.0
    output = []
    for day, group in smiles.groupby("date", sort=True):
        group = group.sort_values("tenor_years")
        below, above = group[group.tenor_years <= target_tenor], group[group.tenor_years >= target_tenor]
        if below.empty or above.empty:
            continue
        left, right = below.iloc[-1], above.iloc[0]
        if abs(float(left.tenor_years) - target_tenor) < 1e-9:
            put30, call30 = float(left.put_iv_25_pct), float(left.call_iv_25_pct)
        elif abs(float(right.tenor_years) - target_tenor) < 1e-9:
            put30, call30 = float(right.put_iv_25_pct), float(right.call_iv_25_pct)
        else:
            t0, t1 = float(left.tenor_years), float(right.tenor_years)
            if t1 - t0 > 30 / 365:
                continue
            weight = (target_tenor - t0) / (t1 - t0)
            def interpolate_variance(column: str) -> float:
                v0, v1 = float(left[column]) / 100, float(right[column]) / 100
                variance = (1 - weight) * v0**2 * t0 + weight * v1**2 * t1
                return math.sqrt(max(variance, 0) / target_tenor) * 100
            put30 = interpolate_variance("put_iv_25_pct")
            call30 = interpolate_variance("call_iv_25_pct")
        output.append({"date": day, "put_iv_25_30d_pct": put30,
                       "call_iv_25_30d_pct": call30, "downside_skew_pp": put30 - call30})
    if not output:
        raise ValueError("No weekly dates have valid expiry brackets around 30 calendar days")
    panel = pd.DataFrame(output).set_index("date").sort_index()
    panel.index = pd.DatetimeIndex(panel.index, name="date")
    if panel.index.has_duplicates or not np.isfinite(panel.to_numpy(float)).all():
        raise ValueError("Calculated NIFTY downside-skew observations are invalid")
    return panel


def load_history(root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    return _read_store(Path(root))


def load_skew(root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    options, manifest = load_history(root)
    return calculate_daily(options), manifest


def publish(options: pd.DataFrame, manifest: dict, root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    data = options[OPTION_COLUMNS].copy()
    data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")
    data["expiry_date"] = pd.to_datetime(data["expiry_date"]).dt.strftime("%Y-%m-%d")
    data = data.sort_values(["date", "expiry_date", "option_type", "strike"]).reset_index(drop=True)
    payload = data.to_csv(index=False, float_format="%.10g", lineterminator="\n").encode("utf-8")
    checksum = digest(payload)
    relative = f"derived/{checksum}.csv"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(payload)
    published_manifest = dict(manifest)
    published_manifest.update({
        "calculation_version": VERSION,
        "retained_start": str(pd.Timestamp(manifest["retained_start"]).date()),
        "source_dates": data["date"].drop_duplicates().tolist(),
        "last_option_date": data["date"].max(),
        "option_contract_rows": len(data),
        "observations_path": relative,
        "observations_sha256": checksum,
    })
    pending = root / "manifest.pending.json"
    pending.write_text(json.dumps(published_manifest, indent=2) + "\n")
    pending.replace(root / "manifest.json")
    return _read_store(root)

