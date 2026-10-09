"""India GMD investment-rate snapshot; network access only on explicit refresh.

Refresh:
    python -m data.fetchers.gmd_investment

The chart generator reads the saved snapshot without calling GMD or MCP.
"""

from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd


COUNTRY = "IND"
COUNTRY_NAME = "India"
VINTAGE = "2026_09"
START_YEAR = 1990

from data.paths import GMD_INVESTMENT_CSV, GMD_INVESTMENT_META

CSV_PATH = GMD_INVESTMENT_CSV
META_PATH = GMD_INVESTMENT_META


def prepare(frame):
    """Validate India's annual GFCF/GDP series without interpolation."""
    data = frame[["ISO3", "year", "finv_GDP"]].copy()

    # India only
    data = data[data["ISO3"] == COUNTRY].copy()

    if data.empty:
        raise ValueError("GMD investment snapshot contains no India observations")

    years = pd.to_numeric(data["year"], errors="raise")
    if (
        years.isna().any()
        or not np.isfinite(years).all()
        or (years % 1 != 0).any()
    ):
        raise ValueError("Invalid annual dates in GMD investment data")

    data["year"] = years.astype(int)

    if data.duplicated(["ISO3", "year"]).any():
        raise ValueError("Duplicate GMD India/year observations")

    data["finv_GDP"] = pd.to_numeric(data["finv_GDP"], errors="raise")

    observed = data["finv_GDP"].dropna()
    if not np.isfinite(observed).all() or not observed.between(0, 100).all():
        raise ValueError("Invalid gross fixed investment / GDP percentage")

    # Do not publish the current calendar year, which may still be incomplete
    # or an extension rather than a completed annual observation.
    latest_complete_year = datetime.now(timezone.utc).year - 1

    data = data[
        (data["year"] >= START_YEAR)
        & (data["year"] <= latest_complete_year)
    ].copy()

    if data.empty:
        raise ValueError("No usable India investment observations")

    data = data.sort_values("year").set_index("year")

    if data["finv_GDP"].notna().sum() < 10:
        raise ValueError("Insufficient India investment history")

    return data["finv_GDP"].reindex(
        pd.Index(range(START_YEAR, int(data.index.max()) + 1), name="year")
    )


def save_snapshot(frame):
    series = prepare(frame)

    data = pd.DataFrame({
        "ISO3": COUNTRY,
        "year": series.index,
        "finv_GDP": series.values,
    })

    payload = data.to_csv(index=False)

    meta = {
        "package": "global_macro_data",
        "package_version": "2.0.0",
        "vintage": VINTAGE,
        "variable": "finv_GDP",
        "units": "% of GDP",
        "country": COUNTRY_NAME,
        "iso3": COUNTRY,
        "start_year": int(series.index.min()),
        "end_year": int(series.dropna().index.max()),
        "coverage_policy": (
            "India only; completed annual observations from 1990 through "
            "the latest available prior calendar year. No interpolation."
        ),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://www.globalmacrodata.com/data",
        "citation": (
            "Müller, Xu, Lehbib and Chen (2025), "
            "The Global Macro Database, NBER WP 33714."
        ),
        "sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "missing_years": [
            int(y) for y in series.index[series.isna()]
        ],
    }

    CSV_PATH.write_text(payload)
    META_PATH.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n"
    )

    return series, meta


def load_snapshot():
    meta = json.loads(META_PATH.read_text())

    if hashlib.sha256(CSV_PATH.read_bytes()).hexdigest() != meta["sha256"]:
        raise ValueError(
            "GMD investment snapshot checksum mismatch; refresh both snapshot files"
        )

    if meta["vintage"] != VINTAGE or meta["variable"] != "finv_GDP":
        raise ValueError("Unexpected GMD investment snapshot vintage or variable")

    series = prepare(pd.read_csv(CSV_PATH))
    return series, meta


def refresh():
    from global_macro_data import gmd

    frame = gmd(
        version=VINTAGE,
        country=[COUNTRY],
        variables=["finv_GDP"],
        fast=False,
    )

    return save_snapshot(frame)


if __name__ == "__main__":
    series, metadata = refresh()
    print(
        f"Saved GMD {metadata['vintage']}: "
        f"India {metadata['start_year']}–{metadata['end_year']}"
    )
