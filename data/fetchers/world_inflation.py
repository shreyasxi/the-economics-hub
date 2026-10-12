"""Official monthly OECD national CPI rates for the World small multiples.

Use published year-on-year rates, never quarterly substitutes or interpolation.
The two COICOP flows are needed during countries' classification transitions.
"""
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.paths import DATA_CACHE

FLOWS = {
    "1999": "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
    "2018": "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0",
}
KEY = ".M.N.CPI.PA._T+_TXCP01_NRG.N.GY"
STEM = "12_macro_global_inflation_breadth"
NAMES = {"CHN": "China", "KOR": "South Korea", "SVK": "Slovakia", "EA": "Euro area"}
DIMENSIONS = {"FREQ": "M", "METHODOLOGY": "N", "MEASURE": "CPI",
              "UNIT_MEASURE": "PA", "ADJUSTMENT": "N", "TRANSFORMATION": "GY"}


def parse_source(text, classification, today=None):
    """Reject ambiguous series and changed units instead of averaging rows."""
    today = today or date.today()
    frame = pd.read_csv(io.StringIO(text), dtype={"REF_AREA": str, "TIME_PERIOD": str})
    required = set(DIMENSIONS) | {"REF_AREA", "Reference area", "EXPENDITURE",
                                  "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "UNIT_MULT"}
    if not required.issubset(frame.columns):
        raise ValueError("OECD inflation: changed CSV schema")
    for column, expected in DIMENSIONS.items():
        if not frame[column].eq(expected).all():
            raise ValueError("OECD inflation: unexpected " + column)
    if not frame["EXPENDITURE"].isin(["_T", "_TXCP01_NRG"]).all():
        raise ValueError("OECD inflation: unexpected expenditure category")
    if not frame["TIME_PERIOD"].str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError("OECD inflation: invalid monthly period")
    if frame["TIME_PERIOD"].gt(today.strftime("%Y-%m")).any():
        raise ValueError("OECD inflation: future observations")
    if frame.duplicated(["REF_AREA", "EXPENDITURE", "TIME_PERIOD"]).any():
        raise ValueError("OECD inflation: duplicate country/category/month")
    multipliers = pd.to_numeric(frame["UNIT_MULT"], errors="raise").dropna()
    if not multipliers.eq(0).all():
        raise ValueError("OECD inflation: unexpected unit multiplier")
    frame["OBS_VALUE"] = pd.to_numeric(frame["OBS_VALUE"], errors="raise")
    frame = frame.dropna(subset=["OBS_VALUE"]).copy()
    if not np.isfinite(frame["OBS_VALUE"]).all():
        raise ValueError("OECD inflation: non-finite rates")
    if frame.empty:
        raise ValueError("OECD inflation: empty response")
    frame["classification"] = classification
    return frame


def prepare(sources, today=None, months=36):
    """Select freshest published series and retain per-observation provenance.

    Prefer COICOP 2018 on tied latest dates. Earlier 1999 observations may
    precede a short 2018 history; never overwrite overlapping 2018 rates.
    Joins are recorded explicitly. Rates are not recomputed from index levels.
    """
    today = today or date.today()
    frame = pd.concat([parse_source(text, key, today) for key, text in sources.items()], ignore_index=True)
    end = pd.Period(today, freq="M")
    start = end - (months - 1)
    countries, excluded = [], []
    codes = sorted(c for c in frame.REF_AREA.unique() if (len(c) == 3 and c.isalpha()) or c == "EA")
    for code in codes:
        country = frame[frame.REF_AREA == code]
        series, transitions = {}, {}
        for category, name in [("_T", "headline"), ("_TXCP01_NRG", "core")]:
            subset = country[country.EXPENDITURE == category]
            if subset.empty:
                series[name] = []
                continue
            latest = subset.groupby("classification").TIME_PERIOD.max()
            chosen = max(latest.index, key=lambda key: (latest[key], key))
            selected = subset[subset.classification == chosen].sort_values("TIME_PERIOD")
            first = selected.TIME_PERIOD.iloc[0]
            earlier = subset[(subset.classification != chosen) & (subset.TIME_PERIOD < first)]
            if not earlier.empty:
                selected = pd.concat([earlier, selected]).sort_values("TIME_PERIOD")
                transitions[name] = first
            series[name] = [{"month": row.TIME_PERIOD, "value": float(row.OBS_VALUE),
                             "classification": row.classification,
                             "status": None if pd.isna(row.OBS_STATUS) else row.OBS_STATUS}
                            for row in selected.itertuples() if row.TIME_PERIOD >= str(start)]
        headline = series["headline"]
        if not headline:
            excluded.append({"code": code, "reason": "no headline observations in display window"})
            continue
        last = date.fromisoformat(headline[-1]["month"] + "-01")
        if (today - last).days > 110 or len(headline) < 6:
            excluded.append({"code": code, "reason": "headline stale or fewer than six monthly observations",
                             "latest": headline[-1]["month"]})
            continue
        core = series["core"]
        core_note = None
        if core and (today - date.fromisoformat(core[-1]["month"] + "-01")).days > 110:
            core_note = "Core omitted: latest " + core[-1]["month"]
            series["core"] = []
        countries.append({"code": code, "label": NAMES.get(code, country["Reference area"].iloc[0]),
                          "series": series, "transitions": transitions, "core_note": core_note,
                          "aggregate": code == "EA"})
    present = {c["code"] for c in countries}
    if len(present) < 20 or not {"USA", "CHN", "IND", "GBR", "JPN"}.issubset(present):
        raise ValueError("OECD inflation: insufficient current country coverage")
    priority = ["USA", "CHN", "IND", "JPN", "GBR", "EA"]
    countries.sort(key=lambda c: (priority.index(c["code"]) if c["code"] in priority else len(priority), c["label"]))
    national = [c for c in countries if not c["aggregate"]]
    lookup = {c["code"]: {r["month"]: r["value"] for r in c["series"]["headline"]} for c in national}
    breadth = None
    for period in sorted({m for values in lookup.values() for m in values}, reverse=True):
        reporting = [values for values in lookup.values() if period in values]
        if len(reporting) / len(national) < .8:
            continue
        previous = str(pd.Period(period, freq="M") - 3)
        deltas = [v[period] - v[previous] for v in reporting if previous in v]
        breadth = {"month": period, "comparison_month": previous, "reporting": len(reporting),
                   "matched": len(deltas), "total_countries": len(national),
                   "easing": sum(d < -.05 for d in deltas), "rising": sum(d > .05 for d in deltas),
                   "little_changed": sum(-.05 <= d <= .05 for d in deltas)}
        break
    if breadth is None:
        raise ValueError("OECD inflation: no common month with 80% country coverage")
    return {"as_of": today.isoformat(), "start_month": str(start), "end_month": str(end),
            "units": "% year-on-year", "countries": countries, "excluded": excluded,
            "breadth": breadth,
            "methodology": "National CPI; published monthly YoY rates; core excludes food and energy. "
                           "No interpolation. Earlier COICOP 1999 history can precede a short COICOP 2018 series. "
                           "Breadth is an unweighted country count; euro area excluded. "
                           "Easing/rising compares the exact month three months earlier; +/-0.05 pp is little changed."}


def fetch_sources(cache_dir=None, start="2021-01"):
    from data.processors.world_snapshot import _get
    cache_dir = Path(cache_dir or DATA_CACHE / "world_inflation")
    cache_dir.mkdir(parents=True, exist_ok=True)
    sources, manifests = {}, []
    for classification, flow in FLOWS.items():
        url = "https://sdmx.oecd.org/public/rest/data/" + flow + "/" + KEY
        response = _get(url, {"startPeriod": start, "format": "csvfilewithlabels"})
        sources[classification] = response.text
        digest = hashlib.sha256(response.content).hexdigest()
        (cache_dir / (classification + "_" + digest + ".csv")).write_bytes(response.content)
        manifests.append({"classification": classification, "url": response.url,
                          "sha256": digest, "retrieved_at": datetime.now(timezone.utc).isoformat()})
    return sources, manifests


def generate(output_dir, sources=None, manifests=None, today=None):
    """Also usable independently, without refreshing unrelated World sources."""
    from charts.world_charts.world_inflation import draw
    output_dir = Path(output_dir)
    png, audit = output_dir / (STEM + ".png"), output_dir / (STEM + ".json")
    try:
        if sources is None:
            sources, manifests = fetch_sources()
        report = prepare(sources, today)
        report["sources"] = manifests or [{"classification": key, "flow": FLOWS[key],
                                          "sha256": hashlib.sha256(text.encode()).hexdigest()}
                                         for key, text in sources.items()]
        draw(report, png)
        # The existing publication workflow copies world_snapshot.json, so
        # embedding the vector preserves sharp rendering without a new
        # workflow file-copy rule. Keep the PNG for existing asset discovery.
        report["chart_svg"] = png.with_suffix(".svg").read_text()
        audit.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return report
    except Exception:
        png.unlink(missing_ok=True)
        png.with_suffix(".svg").unlink(missing_ok=True)
        audit.unlink(missing_ok=True)
        raise


def main():
    import argparse
    from data.paths import PROJECT_ROOT
    parser = argparse.ArgumentParser(description="Generate the World monthly inflation small multiples")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "output/macro" / date.today().strftime("%Y-%m"))
    args = parser.parse_args()
    report = generate(args.out)
    print("Generated inflation panels:", len(report["countries"]), "| breadth:", report["breadth"])


if __name__ == "__main__":
    main()
