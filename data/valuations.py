"""
US equity valuations for the World tab.

  * Robert J. Shiller's CAPE (price over ten-year average real earnings) and
    excess CAPE yield (earnings yield 1/CAPE minus the real ten-year bond
    yield), monthly since 1881, from ie_data.xls on shillerdata.com.
  * Aswath Damodaran's implied equity risk premium for the S&P 500, at the
    start of each month since September 2008, from ERPbymonth.xlsx (NYU Stern).
  * Damodaran's country risk premiums (January and July updates): total equity
    risk premium and country risk premium for every rated country, from the
    Moody's rating and from sovereign CDS, plus GDP-weighted regional averages.

Both files are downloaded on every run. A failed download, a changed layout or
a file that has stopped updating raises ValueError, and the World run fails.
Values are used exactly as published. Shiller's latest row is left out while
his notes say its price is a single day's close (a provisional month).
"""

from __future__ import annotations

import io
import re
from datetime import date

import numpy as np
import pandas as pd

from data.world_snapshot import _get

SHILLER_PAGE = "https://shillerdata.com/"
DAMODARAN_ERP_URL = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
DAMODARAN_DATA_PAGE = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html"

# Days from the start of the latest month (or update) before a file counts as
# no longer updated. Shiller and the monthly ERP: one missed month tolerated.
# Country risk premiums are updated in January and July.
SHILLER_MAX_AGE = 100
ERP_MAX_AGE = 70
COUNTRY_RISK_MAX_AGE = 260


def shiller_file_url(page_html: str) -> str:
    """The ie_data.xls download link on shillerdata.com (its path changes with each upload)."""
    m = re.search(r"(?:https?:)?//[^\"'\s<>]+/ie_data\.xls[^\"'\s<>]*", page_html)
    if not m:
        raise ValueError("shillerdata.com: no ie_data.xls link on the page — the site layout changed")
    url = m.group(0)
    return url if url.startswith("http") else "https:" + url


def _single_column(labels: list[str], test, what: str) -> int:
    matches = [i for i, label in enumerate(labels) if test(label)]
    if len(matches) != 1:
        raise ValueError(f"Shiller ie_data.xls: expected one '{what}' column, found {len(matches)} — the layout changed")
    return matches[0]


def parse_shiller(raw: pd.DataFrame, today: date) -> pd.DataFrame:
    """
    Shiller's 'Data' sheet, read with header=None, as a monthly frame with
    columns cape and excess_cape_yield (per cent). Dates in the file are
    decimals: 1871.01 is January, 1871.1 October.
    """
    first_col = raw.iloc[:, 0].astype(str).str.strip()
    header_rows = first_col.index[first_col == "Date"]
    if len(header_rows) == 0:
        raise ValueError("Shiller ie_data.xls: no 'Date' header row — the layout changed")
    header = header_rows[0]
    labels = [" ".join(str(v).strip() for v in raw.iloc[: header + 1, c] if str(v).strip() not in ("", "nan"))
              for c in range(raw.shape[1])]
    cape_col = _single_column(labels, lambda s: "P/E10" in s and "TR" not in s, "P/E10 or CAPE")
    ecy_col = _single_column(labels, lambda s: "Excess CAPE Yield" in s, "Excess CAPE Yield")

    body = raw.iloc[header + 1:]
    all_dates = pd.to_numeric(body.iloc[:, 0], errors="coerce")
    if all_dates.notna().sum() == 0:
        raise ValueError("Shiller ie_data.xls: no dated rows — the layout changed")
    notes_rows = body.iloc[np.flatnonzero(all_dates.notna())[-1] + 1:]   # Shiller's notes sit below the data
    data = body[all_dates.notna()]
    decimal_dates = all_dates[all_dates.notna()]
    years = np.floor(decimal_dates).astype(int)
    months = ((decimal_dates - years) * 100).round().astype(int)
    if not months.between(1, 12).all():
        raise ValueError("Shiller ie_data.xls: a date column value is not year.month — the layout changed")
    index = pd.to_datetime({"year": years.values, "month": months.values, "day": 1})

    out = pd.DataFrame({
        "cape": pd.to_numeric(data.iloc[:, cape_col], errors="coerce").values,
        "excess_cape_yield": pd.to_numeric(data.iloc[:, ecy_col], errors="coerce").values * 100,
    }, index=index).dropna(how="all")
    if out.empty:
        raise ValueError("Shiller ie_data.xls: no CAPE values")

    notes = " ".join(str(v) for v in notes_rows.to_numpy().ravel() if str(v).strip() not in ("", "nan"))
    if re.search(r"price is .*close", notes, flags=re.I):
        out = out.iloc[:-1]                                   # latest month priced off one day's close
    return out[out.index < pd.Timestamp(today.replace(day=1))]  # never a month still in progress


def _fraction(value) -> float:
    """A Damodaran cell as a fraction: 0.0409, or the occasional text entry '4.06%' / '6,36%'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if text.endswith("%"):
        return float(text[:-1]) / 100
    return float(text)   # anything else raises: the layout changed


def parse_damodaran_erp(sheet: pd.DataFrame) -> pd.DataFrame:
    """Damodaran's 'Historical ERP' sheet as start-of-month implied ERP and T-bond rate, in per cent."""
    missing = {"Start of month", "ERP (T12m)", "T.Bond Rate"} - set(sheet.columns)
    if missing:
        raise ValueError(f"Damodaran ERPbymonth.xlsx: missing columns {sorted(missing)} — the layout changed")
    dates = pd.to_datetime(sheet["Start of month"], errors="coerce")
    rows = sheet[dates.notna()]
    out = pd.DataFrame({
        "erp": rows["ERP (T12m)"].map(_fraction).values * 100,   # his headline series ("Last 12 months data")
        "tbond": rows["T.Bond Rate"].map(_fraction).values * 100,
    }, index=pd.DatetimeIndex(dates[dates.notna()])).dropna(subset=["erp"])
    if out.empty:
        raise ValueError("Damodaran ERPbymonth.xlsx: no ERP values")
    return out.sort_index()


def country_risk_links(page_html: str, today: date) -> list[str]:
    """
    Damodaran's country risk premium workbooks linked from his data page: the
    current file (ctryprem.xlsx) and dated updates such as ctrypremJuly25.xlsx.
    Dated files more than two years old are skipped (older layouts differ).
    """
    links = sorted(set(re.findall(r"https?://[^\"'\s<>]*/ctryprem[A-Za-z]*\d*\.xlsx?", page_html)))
    if not links:
        raise ValueError("Damodaran data page: no ctryprem links — the page layout changed")
    recent = []
    for url in links:
        m = re.search(r"ctryprem[A-Za-z]+(\d{2})\.xlsx?$", url)
        if m is None or 2000 + int(m.group(1)) >= today.year - 2:
            recent.append(url)
    return recent


def parse_update_date(sheet: pd.DataFrame) -> pd.Timestamp:
    """The 'Date of update' at the top of the 'ERPs by country' sheet."""
    for i in range(min(len(sheet), 12)):
        if str(sheet.iat[i, 0]).strip().lower().startswith("date of update"):
            return pd.Timestamp(sheet.iat[i, 1]).normalize()
    raise ValueError("Damodaran country risk file: no 'Date of update' row — the layout changed")


def parse_country_erps(sheet: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """
    The rated-country table of 'ERPs by country' (read with header=None) in per
    cent — total equity risk premium (erp), country risk premium from the
    Moody's rating (crp) and from sovereign CDS (crp_cds, blank without a CDS
    market) — and the mature-market premium the table is built on. The table
    ends where the region column stops being text: below it, unrated countries
    are scored on PRS risk scores, a different method, and are left out.
    """
    first = sheet.iloc[:, 0].astype(str).str.strip()
    header_rows = first.index[first == "Country"]
    if len(header_rows) == 0:
        raise ValueError("Damodaran country risk file: no 'Country' header — the layout changed")
    h = header_rows[0]
    header = [str(v) for v in sheet.iloc[h, :9]]
    expected = {2: "moody", 3: "default spread", 4: "total equity risk premium", 5: "country risk premium",
                6: "cds", 7: "total equity risk premium", 8: "country risk premium"}
    for col, text in expected.items():
        if text not in header[col].lower():
            raise ValueError(f"Damodaran country risk file: column {col} is '{header[col]}', expected '{text}'"
                             " — the layout changed")
    records = []
    for i in range(h + 1, len(sheet)):
        country, region = sheet.iat[i, 0], sheet.iat[i, 1]
        if not (isinstance(country, str) and isinstance(region, str) and region.strip()):
            break
        records.append({"country": country.strip(), "region": region.strip(), "rating": str(sheet.iat[i, 2]).strip(),
                        "erp": _fraction(sheet.iat[i, 4]) * 100, "crp": _fraction(sheet.iat[i, 5]) * 100,
                        "crp_cds": _fraction(sheet.iat[i, 8]) * 100})
    table = pd.DataFrame(records).set_index("country")
    if len(table) < 100:
        raise ValueError(f"Damodaran country risk file: only {len(table)} rated countries — the layout changed")
    base = table["erp"] - table["crp"]
    mature = float(base.median())
    if (base - mature).abs().max() > 0.05:
        raise ValueError("Damodaran country risk file: total premium minus country premium differs across countries")
    return table, mature


def parse_regional_erps(sheet: pd.DataFrame) -> pd.Series:
    """GDP-weighted average total equity risk premium by region, in per cent, ending with 'Global'."""
    first = sheet.iloc[:, 0].astype(str).str.strip()
    header_rows = first.index[first == "Region"]
    if len(header_rows) == 0 or "erp" not in str(sheet.iat[header_rows[0], 1]).lower():
        raise ValueError("Damodaran 'Regional Weighted Averages': no Region / ERP header — the layout changed")
    out = {}
    for i in range(header_rows[0] + 1, len(sheet)):
        name = str(sheet.iat[i, 0]).strip()
        if name in ("", "nan"):
            break
        out[name] = _fraction(sheet.iat[i, 1]) * 100
        if name == "Global":
            break
    regions = pd.Series(out, dtype=float)
    if "Global" not in regions or len(regions) < 6:
        raise ValueError("Damodaran 'Regional Weighted Averages': region rows not found — the layout changed")
    return regions


def pick_year_ago(dates, latest: pd.Timestamp) -> pd.Timestamp:
    """The update closest to twelve months before the latest one, from nine to fifteen months earlier."""
    candidates = [d for d in dates if 270 <= (latest - d).days <= 460]
    if not candidates:
        raise ValueError(f"Damodaran country risk: no update from about a year before {latest:%b %Y} on the data page")
    return min(candidates, key=lambda d: abs((latest - d).days - 365))


def fetch_country_risk(today: date | None = None) -> dict:
    """
    The latest country risk update and the one a year earlier, each as
    {date, countries, mature, regions}. Every recent workbook on the data page
    is opened to read its update date, so a renamed file is still found.
    """
    today = today or date.today()
    books = {}
    for url in country_risk_links(_get(DAMODARAN_DATA_PAGE).text, today):
        book = pd.ExcelFile(io.BytesIO(_get(url).content))
        sheet = pd.read_excel(book, sheet_name="ERPs by country", header=None)
        books[parse_update_date(sheet)] = (book, sheet)
    latest = max(books)
    check_fresh(latest, COUNTRY_RISK_MAX_AGE, "Damodaran country risk premiums", today)

    def load(update: pd.Timestamp) -> dict:
        book, sheet = books[update]
        countries, mature = parse_country_erps(sheet)
        regions = parse_regional_erps(pd.read_excel(book, sheet_name="Regional Weighted Averages", header=None))
        return {"date": update, "countries": countries, "mature": mature, "regions": regions}

    return {"latest": load(latest), "year_ago": load(pick_year_ago(list(books), latest))}


def check_fresh(latest: pd.Timestamp, max_age: int, label: str, today: date) -> None:
    age = (today - latest.date()).days
    if age > max_age:
        raise ValueError(f"{label}: latest month {latest:%b %Y} is {age} days old (limit {max_age}) "
                         f"— the file may have stopped updating")


def fetch_shiller(today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    content = _get(shiller_file_url(_get(SHILLER_PAGE).text)).content
    raw = pd.read_excel(io.BytesIO(content), sheet_name="Data", header=None)
    frame = parse_shiller(raw, today)
    check_fresh(frame["cape"].dropna().index[-1], SHILLER_MAX_AGE, "Shiller CAPE", today)
    return frame


def fetch_damodaran_erp(today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    sheet = pd.read_excel(io.BytesIO(_get(DAMODARAN_ERP_URL).content), sheet_name="Historical ERP")
    frame = parse_damodaran_erp(sheet)
    check_fresh(frame.index[-1], ERP_MAX_AGE, "Damodaran implied ERP", today)
    return frame
