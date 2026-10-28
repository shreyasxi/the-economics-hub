"""Official NSDL calendar-month totals and current-month daily FPI investment.

Run with ``python -m data.fetchers.nsdl_fpi``. A failed retrieval or validation
never replaces stored observations. All values are INR crore, all segments.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from data.paths import INDIA_DB, NSDL_FPI_DIR

YEAR_URL = "https://www.fpi.nsdl.co.in/web/Reports/Yearwise.aspx?RptType=6"
DAILY_URL = "https://www.fpi.nsdl.co.in/web/Reports/Monthly.aspx"
CATEGORIES = {"EQUITY", "DEBTGENERALLIMIT", "DEBTVRR", "DEBTFAR", "HYBRID", "MUTUALFUNDS", "AIFS"}


class SourceError(ValueError):
    """Response is not the requested, internally consistent official report."""


def money(value):
    value = value.strip().replace(",", "").replace("−", "-")
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        raise SourceError(f"Missing or malformed INR value: {value!r}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SourceError("Invalid INR value") from exc
    if not result.is_finite():
        raise SourceError("Non-finite INR value")
    return result


def _table(html, marker):
    soup = BeautifulSoup(html, "html.parser")
    tables = [t for t in soup.find_all("table") if not t.find("table") and marker in t.get_text(" ", strip=True)]
    if len(tables) != 1:
        raise SourceError(f"Expected one {marker!r} table, found {len(tables)}")
    return tables[0]


def _grid(table):
    """Expand source row/column spans before selecting totals (never sum twice)."""
    cells = {}
    rows = table.find_all("tr")
    if len(rows) > 5000:
        raise SourceError("Unexpected table size")
    for r, row in enumerate(rows):
        c = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while (r, c) in cells:
                c += 1
            rs, cs = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
            if not (1 <= rs <= 100 and 1 <= cs <= 32 and c + cs <= 32):
                raise SourceError("Unexpected table span")
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    if (rr, cc) in cells:
                        raise SourceError("Overlapping table cells")
                    cells[rr, cc] = cell.get_text(" ", strip=True)
            c += cs
    return [[cells.get((r, c), "") for c in range(max((cc for rr, cc in cells if rr == r), default=-1) + 1)] for r in range(len(rows))]


def parse_year(html, year, today):
    table = _table(html, "Monthly FPI Net Investments")
    text = table.get_text(" ", strip=True)
    heading = re.search(r"Calendar Year\s*-\s*(\d{4})", text)
    if not heading or int(heading[1]) != year or "INR Crores" not in text:
        raise SourceError("Year/currency does not match requested NSDL report")
    final, partial = {}, None
    for row in _grid(table):
        label = row[0].strip() if row else ""
        name = label.replace("*", "").strip()
        if name not in calendar.month_name[1:]:
            continue
        if len(row) != 13:
            raise SourceError("Monthly NSDL columns changed")
        month = date(year, list(calendar.month_name).index(name), 1)
        values = [money(v) for v in row[1:]]
        # Monthly components are independently rounded to whole crore by NSDL.
        if abs(sum(values[:-1]) - values[-1]) > Decimal(len(values)) / 2:
            raise SourceError(f"Monthly components do not reconcile: {month}")
        key = month.strftime("%Y-%m")
        if key in final or (partial and partial["month"] == key):
            raise SourceError("Duplicate NSDL month")
        if month > today.replace(day=1):
            raise SourceError("Future NSDL month")
        if "*" in label:
            if partial is not None:
                raise SourceError("Multiple partial months in NSDL calendar report")
            cutoff = re.search(r"\*\*\s*up to\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
            if not cutoff:
                raise SourceError("Partial month has no reporting cutoff")
            asof = datetime.strptime(cutoff[1], "%d %b %Y").date()
            if asof.strftime("%Y-%m") != key or asof > today:
                raise SourceError("Invalid partial-month cutoff")
            partial = {"month": key, "asof": asof.isoformat(), "value": values[-1]}
        elif month < today.replace(day=1):
            final[key] = values[-1]
        else:
            raise SourceError("Current month unexpectedly marked final")
    if not final and partial is None and not (year == today.year and today.month == 1):
        raise SourceError("No completed NSDL months")
    return final, partial


def parse_daily(html, today):
    table = _table(html, "Daily Trends in FPI Investments on")
    text = table.get_text(" ", strip=True)
    heading = re.search(r"Daily Trends in FPI Investments on\s*(\d{2}-[A-Za-z]{3}-\d{4})", text)
    if not heading or not re.search(r"Net Investment\s*\(Rs\.\s*Crore\)", text):
        raise SourceError("Daily NSDL heading/INR units changed")
    asof = datetime.strptime(heading[1], "%d-%b-%Y").date()
    if asof > today:
        raise SourceError("Future NSDL reporting date")
    if asof.replace(day=1) != today.replace(day=1):
        # First few days may still serve the previous month's final daily report.
        if today.day <= 6 and asof.replace(day=1) == (today.replace(day=1) - timedelta(days=1)).replace(day=1):
            return None
        raise SourceError("Daily NSDL report is not the current month")
    if (today - asof).days > 7:
        raise SourceError("Daily NSDL report is over seven days old")
    days = {}
    for row in _grid(table):
        if not row or not re.fullmatch(r"\d{2}-[A-Za-z]{3}-\d{4}", row[0]):
            continue
        if len(row) != 8:
            raise SourceError("Daily NSDL columns changed")
        day = datetime.strptime(row[0], "%d-%b-%Y").date()
        if day.replace(day=1) != asof.replace(day=1) or day > asof:
            raise SourceError("Daily rows disagree with report cutoff")
        category, route = (re.sub(r"[^A-Z]", "", v.upper()) for v in row[1:3])
        if category not in CATEGORIES:
            raise SourceError(f"Unknown NSDL category: {category}")
        purchases, sales, net = [money(v) for v in row[3:6]]
        if purchases < 0 or sales < 0 or abs(purchases - sales - net) > Decimal("0.02"):
            raise SourceError("Gross purchases/sales do not reconcile to net")
        group = days.setdefault(day, {"total": [], "categories": {}})
        if route == "TOTAL":
            group["total"].append(net)
        else:
            cat = group["categories"].setdefault(category, {"subtotal": [], "routes": {}})
            if route == "SUBTOTAL":
                cat["subtotal"].append(net)
            else:
                if route in cat["routes"]:
                    raise SourceError("Duplicate daily investment route")
                cat["routes"][route] = net
    if not days or max(days) != asof:
        raise SourceError("Daily report is missing its latest reporting day")
    totals = []
    for day, group in days.items():
        if len(group["total"]) != 1 or set(group["categories"]) != CATEGORIES:
            raise SourceError(f"Missing/duplicate daily totals: {day}")
        subtotals = []
        for category, cat in group["categories"].items():
            if len(cat["subtotal"]) != 1 or not cat["routes"]:
                raise SourceError("Missing/duplicate category subtotal")
            expected = {"EQUITYSCHEMES", "DEBTSCHEMES", "HYBRIDSCHEMES", "SOLUTIONORIENTEDSCHEMES", "OTHERSCHEMES"} if category == "MUTUALFUNDS" else {"STOCKEXCHANGE", "PRIMARYMARKETOTHERS"}
            if set(cat["routes"]) != expected:
                raise SourceError("Missing or unexpected investment route")
            if abs(sum(cat["routes"].values()) - cat["subtotal"][0]) > Decimal("0.10"):
                raise SourceError("Investment routes do not reconcile")
            subtotals.extend(cat["subtotal"])
        if abs(sum(subtotals) - group["total"][0]) > Decimal("0.10"):
            raise SourceError("Category subtotals do not reconcile to daily total")
        totals.extend(group["total"])
    return {"month": asof.strftime("%Y-%m"), "asof": asof.isoformat(), "value": sum(totals)}


class OfficialClient:
    def __init__(self):
        from curl_cffi import requests
        self.session = requests.Session(impersonate="chrome")

    def close(self):
        self.session.close()

    def request(self, method, url, **kwargs):
        for attempt in range(3):
            try:
                response = self.session.request(method, url, timeout=40, **kwargs)
                response.raise_for_status()
                if not response.url.startswith("https://www.fpi.nsdl.co.in/"):
                    raise SourceError("Unexpected NSDL redirect")
                return response.content
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def year(self, year):
        html = self.request("GET", YEAR_URL)
        soup = BeautifulSoup(html, "html.parser")
        selected = soup.select_one('select[name="ddl"] option[selected]')
        if selected and selected.get("value") == str(year):
            return html
        form = soup.find("form")
        if form is None or soup.select_one(f'select[name="ddl"] option[value="{year}"]') is None:
            raise SourceError("Requested NSDL year/form unavailable")
        payload = {i["name"]: i.get("value", "") for i in form.find_all("input", type="hidden") if i.get("name")}
        payload.update(ddl=str(year), __EVENTTARGET="ddl", __EVENTARGUMENT="", hdnCurr="INR")
        return self.request("POST", YEAR_URL, data=payload)

    def daily(self):
        return self.request("GET", DAILY_URL)


def collect(client, today):
    # Re-read three completed months, including across the year boundary.
    anchor = today.replace(day=1)
    months = []
    for _ in range(3):
        anchor = (anchor - timedelta(days=1)).replace(day=1)
        months.append(anchor.strftime("%Y-%m"))
    sources, finals, partial = [], {}, None
    for year in sorted({today.year, *(int(m[:4]) for m in months)}):
        raw = client.year(year)
        values, cutoff = parse_year(raw, year, today)
        sources.append((YEAR_URL, raw))
        finals.update({m: str(v) for m, v in values.items() if m in months})
        if year == today.year:
            partial = cutoff
    raw = client.daily()
    mtd = parse_daily(raw, today)
    sources.append((DAILY_URL, raw))
    if mtd and partial and partial["asof"] == mtd["asof"]:
        if abs(partial["value"] - mtd["value"]) > Decimal("1"):
            raise SourceError("Daily MTD and monthly report disagree at the same cutoff")
    if not finals:
        raise SourceError("No recent completed months available")
    if mtd:
        mtd = {**mtd, "value": str(mtd["value"])}
    return {"completed": finals, "mtd": mtd}, sources


def update(*, db=INDIA_DB, root=NSDL_FPI_DIR, today=None, client=None, dry_run=False):
    from data.processors.india_db_manager import apply_nsdl_fpi
    today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    own_client = client is None
    client = client or OfficialClient()
    try:
        observations, sources = collect(client, today)
    finally:
        if own_client:
            client.close()
    receipt = {"schema_version": 1, "checked_on": today.isoformat(), "retrieved_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
               "units": "INR crore", "scope": "all segments", **observations,
               "sources": [{"url": url, "sha256": hashlib.sha256(raw).hexdigest()} for url, raw in sources]}
    if dry_run:
        return receipt
    run_id = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    root = Path(root)
    for (_, raw), source in zip(sources, receipt["sources"]):
        target = root / "sources" / (source["sha256"] + ".html")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise SourceError("Existing source archive checksum mismatch")
        target.write_bytes(raw)
    manifest = root / "runs" / (run_id + ".json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    apply_nsdl_fpi(observations, run_id, receipt, db=db)
    pointer = root / "current.json.tmp"
    pointer.write_text(json.dumps({"run_id": run_id, **receipt}, indent=2) + "\n", encoding="utf-8", newline="\n")
    pointer.replace(root / "current.json")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=INDIA_DB)
    parser.add_argument("--root", type=Path, default=NSDL_FPI_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(update(db=args.db, root=args.root, dry_run=args.dry_run), indent=2))


if __name__ == "__main__":
    main()
