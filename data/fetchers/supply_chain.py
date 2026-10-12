"""Monthly New York Fed GSCPI, using the full-precision official workbook."""
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data.paths import DATA_CACHE, PROJECT_ROOT

PAGE = "https://www.newyorkfed.org/research/policy/gscpi"
URL = "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx"
STEM = "21_macro_supply_chain_pressure"


def parse_workbook(raw, today=None):
    today = today or date.today()
    frame = pd.read_excel(io.BytesIO(raw), sheet_name="GSCPI Monthly Data")
    if list(frame.columns[:2]) != ["Date", "GSCPI"]:
        raise ValueError("GSCPI: official workbook columns changed")
    frame = frame[["Date", "GSCPI"]].dropna(how="all")
    dates = pd.to_datetime(frame.Date, format="%d-%b-%Y", errors="raise")
    values = pd.to_numeric(frame.GSCPI, errors="raise")
    if dates.isna().any() or not np.isfinite(values).all():
        raise ValueError("GSCPI: missing or non-finite observation")
    months = dates.dt.to_period("M")
    if months.duplicated().any():
        raise ValueError("GSCPI: duplicate monthly observation")
    if (months > pd.Period(today, freq="M") - 1).any():
        raise ValueError("GSCPI: future or incomplete monthly observation")
    rows = sorted([{"month": str(month), "value": float(value)}
                   for month, value in zip(months, values)], key=lambda row: row["month"])
    if len(rows) < 120:
        raise ValueError("GSCPI: insufficient monthly history")
    latest = pd.Period(rows[-1]["month"], freq="M").end_time.date()
    if (today - latest).days > 90:
        raise ValueError("GSCPI: latest observation is stale")
    return {"title": "Global Supply Chain Pressure Index", "as_of": today.isoformat(),
            "units": "Standard deviations from historical average", "source_url": PAGE,
            "rows": rows}


def generate(output_dir, raw=None, today=None):
    from charts.world_charts.supply_chain import draw
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if raw is None:
            from data.processors.world_snapshot import _get
            raw = _get(URL).content
        report = parse_workbook(raw, today)
        digest = hashlib.sha256(raw).hexdigest()
        cache = DATA_CACHE / "supply_chain"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / (digest + ".xlsx")).write_bytes(raw)
        report["source"] = {"url": URL, "sha256": digest,
                            "retrieved_at": datetime.now(timezone.utc).isoformat()}
        draw(report, output_dir / (STEM + ".png"))
        (output_dir / (STEM + ".json")).write_text(json.dumps(report, indent=2) + "\n")
        return report
    except Exception:
        for extension in ("png", "json"):
            (output_dir / (STEM + "." + extension)).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    report = generate(PROJECT_ROOT / "output" / "macro" / date.today().strftime("%Y-%m"))
    print("GSCPI latest:", report["rows"][-1])
