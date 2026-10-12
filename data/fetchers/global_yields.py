"""National yields take priority, with OECD historical backfill and dated fallback.

Retained observations keep their original retrieval time; source failures cannot
make them fresh. Source definitions remain available for every observation.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests

from config.global_yields import COUNTRIES, OECD_URL, STEM
from data.paths import DATA_CACHE, WORLD_STORE_DIR

STORE = WORLD_STORE_DIR / "global_yields.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (EconomicsHub official data monitor)"}


def parse_oecd(text, today):
    frame = pd.read_csv(io.StringIO(text), dtype={"TIME_PERIOD": str})
    expected = {"FREQ": "M", "MEASURE": "IRLT", "UNIT_MEASURE": "PA", "UNIT_MULT": 0,
                "ACTIVITY": "_Z", "ADJUSTMENT": "_Z", "TRANSFORMATION": "_Z",
                "TIME_HORIZ": "_Z", "METHODOLOGY": "N"}
    if not set(expected).union({"REF_AREA", "TIME_PERIOD", "OBS_VALUE"}) <= set(frame):
        raise ValueError("OECD yield schema changed")
    for column, value in expected.items():
        if not frame[column].eq(value).all():
            raise ValueError("Unexpected OECD yield dimension: " + column)
    if not frame.TIME_PERIOD.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError("Invalid monthly yield period")
    if frame.TIME_PERIOD.gt(today.strftime("%Y-%m")).any():
        raise ValueError("Future monthly yield")
    if frame.duplicated(["REF_AREA", "TIME_PERIOD"]).any():
        raise ValueError("Duplicate country/month yield")
    frame["OBS_VALUE"] = pd.to_numeric(frame.OBS_VALUE, errors="raise")
    frame = frame.dropna(subset=["OBS_VALUE"])
    if not np.isfinite(frame.OBS_VALUE).all():
        raise ValueError("Non-finite monthly yield")
    return {code: [{"date": row.TIME_PERIOD + "-01", "value": float(row.OBS_VALUE),
                    "status": str(getattr(row, "OBS_STATUS", ""))}
                   for row in group.sort_values("TIME_PERIOD").itertuples()]
            for code, group in frame.groupby("REF_AREA") if code in COUNTRIES}


def validate_daily(rows, today):
    seen = set()
    clean = []
    for row in rows:
        day = date.fromisoformat(row["date"])
        value = float(row["value"])
        if day > today or day in seen or not np.isfinite(value) or not -10 <= value <= 60:
            raise ValueError("Invalid, duplicate or future national yield")
        seen.add(day)
        clean.append({"date": day.isoformat(), "value": value})
    if not clean:
        raise ValueError("No national yield observations")
    return sorted(clean, key=lambda r: r["date"])


def parse_norges(text):
    frame = pd.read_csv(io.StringIO(text), sep=";", dtype={"TIME_PERIOD": str})
    required = {"FREQ", "TENOR", "INSTRUMENT_TYPE", "TIME_PERIOD", "OBS_VALUE"}
    if not required <= set(frame):
        raise ValueError("Norges Bank yield schema changed")
    frame = frame[(frame.FREQ == "B") & (frame.TENOR == "10Y") & (frame.INSTRUMENT_TYPE == "GBON")]
    if frame.empty:
        raise ValueError("Norges Bank ten-year daily government yield missing")
    return [{"date": r.TIME_PERIOD, "value": float(r.OBS_VALUE)} for r in frame.itertuples()]


def parse_rba(text):
    import csv
    records = list(csv.reader(io.StringIO(text)))
    ids = next(r for r in records if r and r[0] == "Series ID")
    index = ids.index("FCMYGBAG10D")
    metadata = {r[0]: r for r in records if r and r[0] in {"Title", "Frequency", "Units"}}
    if (metadata["Title"][index] != "Australian Government 10 year bond"
            or metadata["Frequency"][index] != "Daily"
            or metadata["Units"][index] != "Per cent per annum"):
        raise ValueError("RBA ten-year nominal yield definition changed")
    return [{"date": datetime.strptime(r[0], "%d-%b-%Y").date().isoformat(), "value": float(r[index])}
            for r in records if len(r) > index and re.fullmatch(r"\d{2}-[A-Za-z]{3}-\d{4}", r[0]) and r[index].strip()]


def national_fetcher(code, today, get):
    start = (today - timedelta(days=45)).isoformat()
    url, kind, rows = None, None, None
    if code == "USA":
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
        df = pd.read_csv(io.StringIO(get(url, {"id": "DGS10", "cosd": start}).text))
        values = pd.to_numeric(df.iloc[:, 1].replace(".", np.nan), errors="raise")
        rows = [{"date": str(day), "value": value} for day, value in zip(df.iloc[:, 0], values) if pd.notna(value)]
        kind = "10-year constant-maturity par"
    elif code == "CAN":
        url = "https://www.bankofcanada.ca/valet/observations/BD.CDN.10YR.DQ.YLD/json"
        j = get(url, {"start_date": start}).json()
        rows = [{"date": r["d"], "value": r["BD.CDN.10YR.DQ.YLD"]["v"]} for r in j["observations"] if "BD.CDN.10YR.DQ.YLD" in r]
        kind = "10-year benchmark"
    elif code in {"GBR", "DEU", "JPN"}:
        # Existing official-source collectors already used in the World scoreboard.
        from data.processors.world_snapshot import fetch_boe, fetch_bundesbank_10y, fetch_jgb_10y
        if code == "GBR":
            series = fetch_boe("IUDMNPY", date.fromisoformat(start))
            url, kind = "https://www.bankofengland.co.uk/statistics/yield-curves", "10-year fitted nominal par"
        elif code == "DEU":
            series = fetch_bundesbank_10y(start)
            url, kind = "https://api.statistiken.bundesbank.de/rest/data/BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A", "10-year fitted par"
        else:
            series = fetch_jgb_10y().loc[start:]
            url, kind = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv", "10-year JGB"
        rows = [{"date": day.date().isoformat(), "value": value} for day, value in series.items()]
    elif code == "SWE":
        url = "https://api.riksbank.se/swea/v1/Observations/SEGVB10YC/" + start
        rows = [{"date": r["date"], "value": r["value"]} for r in get(url).json()]
        kind = "10-year government benchmark"
    elif code == "KOR":
        key = os.environ.get("BOK_API_KEY", "sample")
        begin = (today - timedelta(days=9)).strftime("%Y%m%d")
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/en/1/10/817Y002/D/{begin}/{today:%Y%m%d}/010210000"
        j = get(url).json()["StatisticSearch"]
        if any(r["ITEM_NAME1"] != "Treasury Bonds (10-year)" for r in j["row"]):
            raise ValueError("ECOS instrument changed")
        rows = [{"date": datetime.strptime(r["TIME"], "%Y%m%d").date().isoformat(), "value": r["DATA_VALUE"]} for r in j["row"]]
        url, kind = "https://ecos.bok.or.kr/api/", "10-year Treasury benchmark"
    elif code == "ESP":
        url = "https://www.bde.es/webbe/es/estadisticas/compartido/datos/csv/uoi_sindi.csv"
        import csv
        data = list(csv.reader(io.StringIO(get(url).content.decode("latin1"))))
        index = data[0].index("DPUG0B1F0ZP")
        months = dict(zip("ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC".split(), range(1, 13)))
        rows = []
        for row in data[6:]:
            if len(row) <= index or row[index] in {"_", "", "."}:
                continue
            d, m, y = row[0].split()
            day = date(int(y), months[m], int(d)).isoformat()
            if day >= start:
                rows.append({"date": day, "value": row[index]})
        kind = "10-year secondary-market government yield"
    elif code == "NOR":
        url = "https://data.norges-bank.no/api/data/GOVT_GENERIC_RATES/all"
        rows = parse_norges(get(url, {"format": "csv", "startPeriod": start}).text)
        kind = "10-year generic government bond mid-yield"
    elif code == "IND":
        from data.paths import DBIE_WORKBOOK
        from data.processors.world_snapshot import read_dbie_ten_year
        series = read_dbie_ten_year(DBIE_WORKBOOK)
        rows = [{"date": day.date().isoformat(), "value": value} for day, value in series.items()]
        url, kind = "https://data.rbi.org.in/DBIE/", "10-year G-Sec yield (FBIL), DBIE Weekly sheet"
    elif code == "AUS":
        url = "https://www.rba.gov.au/statistics/tables/csv/f2-data.csv"
        rows = [r for r in parse_rba(get(url).text) if r["date"] >= start]
        kind = "10-year nominal government yield, interpolated maturity"
    elif code == "CHE":
        url = "https://www.snb.ch/en/the-snb/mandates-goals/statistics/statistics-pub/current_interest_exchange_rates"
        text = BeautifulSoup(get(url).text, "html.parser").get_text(" ", strip=True)
        m = re.search(r"Yield on Swiss Confederation bonds\s+([-\d.]+)%\s+(\d{2}\.\d{2}\.\d{4})", text)
        if not m:
            raise ValueError("SNB ten-year spot quote missing")
        rows = [{"date": datetime.strptime(m[2], "%d.%m.%Y").date().isoformat(), "value": m[1]}]
        kind = "10-year fitted spot"
    else:
        raise ValueError("No enabled national collector")
    result = {"source": code + " national official source", "url": url, "yield_type": kind,
              "observations": validate_daily(rows, today)}
    if code == "IND":
        result.update(source="RBI DBIE workbook / FBIL", collection_mode="Manually refreshed DBIE workbook",
                      workbook=DBIE_WORKBOOK.name, sha256=hashlib.sha256(DBIE_WORKBOOK.read_bytes()).hexdigest())
    return result


def prepare(monthly, national, today):
    start = date(today.year - 5, today.month, 1).isoformat()
    countries = []
    for code, (label, region) in COUNTRIES.items():
        history = [r for r in monthly.get(code, []) if r["date"] >= start]
        native = national.get(code, {})
        daily = validate_daily(native["observations"], today) if native.get("observations") else []
        # Each plotted national point is the last actual observation of its
        # ISO week; do not invent a Friday close when only Thursday is published.
        weeks = {}
        for row in daily:
            if row["date"] >= start:
                weeks[date.fromisoformat(row["date"]).isocalendar()[:2]] = row
        weekly = list(weeks.values())
        current = weekly[-1] if weekly else None
        latest_month = history[-1] if history else None
        usable_national = current and (not latest_month or current["date"] >= latest_month["date"])
        latest = current if usable_national else latest_month or current
        if not latest:
            raise ValueError(f"No data for required country {label}")
        frequency = "National weekly observation" if usable_national or not latest_month else "OECD monthly average"
        stale = (today - date.fromisoformat(latest["date"])).days > (10 if frequency.startswith("National") else 110)
        countries.append({"code": code, "label": label, "region": region, "monthly": history,
                          "weekly": weekly, "national": {k: v for k, v in native.items() if k != "observations"},
                          "latest": latest, "latest_frequency": frequency, "stale": stale,
                          "national_issue": native.get("error"),
                          "monthly_note": "OECD long-term rate; monthly average, country definitions vary" if history else "OECD history unavailable for this country"})
    return {"as_of": today.isoformat(), "start_date": start, "countries": countries,
            "methodology": "National observations take priority, sampled weekly at actual observation dates; "
                           "OECD supplies historical backfill and fallback. Definitions can differ at joins. "
                           "No interpolation or holiday filling."}


def collect(today=None, store_path=STORE):
    today = today or date.today()
    previous = json.loads(Path(store_path).read_text()) if Path(store_path).exists() else {}
    manifests, issues = [], []
    archive = DATA_CACHE / "global_yields"
    archive.mkdir(parents=True, exist_ok=True)

    def get(url, params=None):
        request_headers = {"User-Agent": requests.utils.default_user_agent()} if url.startswith("https://www.rba.gov.au/") else HEADERS
        r = requests.get(url, params=params, headers=request_headers, timeout=35)
        r.raise_for_status()
        digest = hashlib.sha256(r.content).hexdigest()
        (archive / digest).write_bytes(r.content)
        manifests.append({"url": r.url if "ecos.bok" not in url else "https://ecos.bok.or.kr/api/",
                          "sha256": digest, "retrieved_at": datetime.now(timezone.utc).isoformat()})
        return r

    try:
        monthly = parse_oecd(get(OECD_URL, {"startPeriod": f"{today.year-5}-{today.month:02}",
                                            "format": "csvfile"}).text, today)
        required = set(COUNTRIES)
        if not required <= set(monthly):
            raise ValueError("Missing required OECD countries: " + str(required - set(monthly)))
        monthly_retrieved_at = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        if not previous.get("monthly"):
            raise
        monthly = previous["monthly"]
        monthly_retrieved_at = previous.get("monthly_retrieved_at")
        issues.append("OECD refresh failed; retained dated history: " + type(exc).__name__)
    national = {code: dict(item) for code, item in previous.get("national", {}).items() if code in COUNTRIES}

    def fetch(code):
        try:
            return code, national_fetcher(code, today, get), None
        except Exception as exc:
            # Avoid credential-bearing request URLs in the published report.
            return code, None, type(exc).__name__

    codes = "USA CAN GBR DEU JPN SWE KOR ESP NOR CHE AUS IND".split()
    with ThreadPoolExecutor(max_workers=6) as pool:
        for code, fresh, error in pool.map(fetch, codes):
            if error:
                national.setdefault(code, {})["error"] = "National refresh failed: " + error
                issues.append(code + ": " + national[code]["error"])
                continue
            old = national.get(code, {})
            merged = {r["date"]: r for r in old.get("observations", [])}
            merged.update({r["date"]: r for r in fresh["observations"]})
            cutoff = f"{today.year-5}-{today.month:02}-01"
            fresh["observations"] = [merged[d] for d in sorted(merged) if d >= cutoff]
            fresh["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            national[code] = fresh
    report = prepare(monthly, national, today)
    report.update(sources=manifests, issues=issues, monthly_retrieved_at=monthly_retrieved_at)
    store = {"monthly": monthly, "national": national, "monthly_retrieved_at": monthly_retrieved_at}
    return report, store


def generate(output_dir, today=None, store_path=STORE):
    from charts.world_charts.global_yields import draw
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report, store = collect(today, store_path)
    draw(report, output_dir / (STEM + ".png"))
    (output_dir / (STEM + ".json")).write_text(json.dumps(report, indent=2) + "\n")
    store_path = Path(store_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = store_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2) + "\n")
    temporary.replace(store_path)
    return report


def main():
    import argparse
    from data.paths import PROJECT_ROOT
    parser = argparse.ArgumentParser(description="Refresh only global government yields")
    parser.add_argument("--published", action="store_true", help="Refresh the newest published World edition")
    args = parser.parse_args()
    if args.published:
        folders = sorted((PROJECT_ROOT / "assets/macro").glob("*/world_snapshot.json"))
        if not folders:
            raise ValueError("No published World snapshot")
        folder = folders[-1].parent
    else:
        folder = PROJECT_ROOT / "output/macro" / date.today().strftime("%Y-%m")
    report = generate(folder)
    if args.published:
        path = folder / "world_snapshot.json"
        snapshot = json.loads(path.read_text())
        snapshot["global_yields"] = report
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
        tmp.replace(path)
    print(f"Global yields: {len(report['countries'])} countries; {len(report['issues'])} source issues")


if __name__ == "__main__":
    main()
