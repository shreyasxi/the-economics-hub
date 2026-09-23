"""
Economics Hub — OECD monetary aggregates fetcher

Broad money for the largest economies, monthly and in national currency, from
the OECD's monetary aggregates dataset (DSD_STES@DF_MONAGG) through its free
SDMX API (no key). One request returns every economy asked for.

The OECD's broad money is each economy's broadest official measure as the
OECD compiles it: M2 for the United States and China, M3 or the nearest
national equivalent elsewhere. It is what "global M2" composites add up once
converted to dollars; the conversion is left to the caller.

Browse it: https://data-explorer.oecd.org ("Monetary aggregates").
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import pandas as pd
import requests

_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_MONAGG,4.0/"
        "{areas}.M.MABM.XDC._Z.N._Z._Z..")


def fetch_broad_money(areas: list[str], start: str = "2009-01",
                      max_age_days: int = 200) -> pd.DataFrame:
    """
    Month-end broad money in national currency units, one column per area
    (OECD codes: USA, CHN, EA20, JPN, GBR, CAN, AUS, ...), not seasonally
    adjusted, since `start` ("YYYY-MM").

    Economies publish a month or two apart, so the last row can be ragged.
    Raises if an area is missing altogether, or if its latest month is more
    than `max_age_days` old: a sum across economies with one of them frozen
    would drift without saying so.
    """
    url = _URL.format(areas="+".join(areas))
    resp = requests.get(url, params={"startPeriod": start, "format": "csvfilewithlabels"}, timeout=120)
    resp.raise_for_status()
    raw = pd.read_csv(io.StringIO(resp.text))
    if raw.empty:
        raise ValueError("OECD returned no broad money data")

    raw["value"] = pd.to_numeric(raw["OBS_VALUE"], errors="coerce") * 10.0 ** raw["UNIT_MULT"]
    table = raw.pivot_table(index="TIME_PERIOD", columns="REF_AREA", values="value", aggfunc="last")
    table.index = pd.PeriodIndex(table.index, freq="M").to_timestamp(how="end").normalize()
    absent = [a for a in areas if a not in table.columns]
    if absent:
        raise ValueError(f"OECD returned no broad money for {', '.join(absent)}")

    table = table[areas].sort_index()
    cutoff = datetime.now() - timedelta(days=max_age_days)
    stale = [a for a in areas if table[a].last_valid_index() < cutoff]
    if stale:
        raise ValueError(f"OECD broad money is stale for {', '.join(stale)}")
    return table
