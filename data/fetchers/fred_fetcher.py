"""
Economics Hub — FRED Data Fetcher
===================================
Fetches US macro data from the Federal Reserve Economic Data
(FRED) API. Covers treasury yields, credit spreads, inflation
expectations, unemployment, and more.

Requirements:
    pip install fredapi
    Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html

Usage:
    from data.fetchers.fred_fetcher import FredFetcher
    fetcher = FredFetcher(api_key="YOUR_KEY")
    data = fetcher.fetch_series("DGS10", period_years=1)
    curve = fetcher.fetch_yield_curve()
"""

import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

try:
    from fredapi import Fred
    HAS_FRED = True
except ImportError:
    HAS_FRED = False
    print("⚠ fredapi not installed. Run: pip install fredapi")


class FredFetcher:
    """Fetch macro data from FRED."""

    def __init__(self, api_key=None, cache_dir=None):
        if not HAS_FRED:
            raise ImportError("fredapi is required. Install with: pip install fredapi")
        
        if api_key is None:
            raise ValueError(
                "FRED API key required. Get one free at: "
                "https://fred.stlouisfed.org/docs/api/api_key.html"
            )
        
        self.fred = Fred(api_key=api_key)
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def fetch_series(self, series_id, period_years=1, end_date=None):
        """
        Fetch a single FRED series.
        
        Parameters:
            series_id: FRED series ID (e.g., "DGS10" for 10Y Treasury)
            period_years: how many years of history
            end_date: end date (defaults to today)
        
        Returns:
            pandas Series with date index
        """
        if end_date is None:
            end_date = datetime.now()
        start_date = end_date - timedelta(days=int(period_years * 365.25))
        
        data = self.fred.get_series(
            series_id,
            observation_start=start_date.strftime("%Y-%m-%d"),
            observation_end=end_date.strftime("%Y-%m-%d"),
        )
        
        # Drop NaN values (weekends/holidays for daily series)
        data = data.dropna()
        
        # Cache
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self.cache_dir / f"fred_{series_id}_{period_years}y.csv"
            data.to_csv(cache_file)
        
        return data

    def fetch_yield_curve(self, date=None):
        """
        Fetch the complete US Treasury yield curve for a given date.
        
        Returns:
            dict with tenor labels and yields (all plain Python floats)
        """
        tenor_series = {
            "1M":  "DGS1MO",
            "3M":  "DGS3MO",
            "6M":  "DGS6MO",
            "1Y":  "DGS1",
            "2Y":  "DGS2",
            "5Y":  "DGS5",
            "7Y":  "DGS7",
            "10Y": "DGS10",
            "20Y": "DGS20",
            "30Y": "DGS30",
        }
        
        tenors = list(tenor_series.keys())
        yields_list = []
        
        for tenor, series_id in tenor_series.items():
            data = self.fetch_series(series_id, period_years=0.1)
            if len(data) > 0:
                try:
                    yields_list.append(float(data.iloc[-1]))
                except (ValueError, TypeError):
                    yields_list.append(None)
            else:
                yields_list.append(None)
        
        # Filter out any tenor/yield pairs where yield is None
        clean_tenors = []
        clean_yields = []
        for t, y in zip(tenors, yields_list):
            if y is not None:
                clean_tenors.append(t)
                clean_yields.append(y)
        
        return {
            "tenors": clean_tenors,
            "yields": clean_yields,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

    def fetch_yield_curve_historical(self, weeks_ago=0):
        """
        Fetch yield curve from N weeks ago.
        Useful for overlay comparisons (current vs 4w vs 52w).
        """
        end_date = datetime.now() - timedelta(weeks=weeks_ago)
        
        tenor_series = {
            "1M": "DGS1MO", "3M": "DGS3MO", "6M": "DGS6MO",
            "1Y": "DGS1", "2Y": "DGS2", "5Y": "DGS5",
            "7Y": "DGS7", "10Y": "DGS10", "20Y": "DGS20", "30Y": "DGS30",
        }
        
        tenors = list(tenor_series.keys())
        yields_list = []
        
        for series_id in tenor_series.values():
            data = self.fred.get_series(
                series_id,
                observation_start=(end_date - timedelta(days=10)).strftime("%Y-%m-%d"),
                observation_end=end_date.strftime("%Y-%m-%d"),
            )
            data = data.dropna()
            if len(data) > 0:
                try:
                    yields_list.append(float(data.iloc[-1]))
                except (ValueError, TypeError):
                    yields_list.append(None)
            else:
                yields_list.append(None)
        
        # Filter out None pairs
        clean_tenors = []
        clean_yields = []
        for t, y in zip(tenors, yields_list):
            if y is not None:
                clean_tenors.append(t)
                clean_yields.append(y)
        
        return {"tenors": clean_tenors, "yields": clean_yields}

    def weekly_change(self, series_id):
        """
        Calculate weekly change for a FRED series.
        For yields, this returns absolute change (in percentage points).
        """
        data = self.fetch_series(series_id, period_years=0.1)
        if len(data) < 6:
            return None
        
        current = float(data.iloc[-1])
        previous = float(data.iloc[-6]) if len(data) >= 6 else float(data.iloc[0])
        change_abs = current - previous
        
        return {
            "current": round(current, 4),
            "previous": round(previous, 4),
            "change_abs": round(change_abs, 4),
            "change_bps": round(change_abs * 100, 1),
        }
