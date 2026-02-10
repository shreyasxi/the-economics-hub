"""
Economics Hub — Yahoo Finance Data Fetcher
============================================
Fetches equity indices, FX rates, and commodity prices
from Yahoo Finance using the yfinance library.

Requirements:
    pip install yfinance

Usage:
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    fetcher = YFinanceFetcher()
    data = fetcher.fetch("^GSPC", period="1y")
    weekly_change = fetcher.weekly_change("^GSPC")
"""

import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("⚠ yfinance not installed. Run: pip install yfinance")


class YFinanceFetcher:
    """Fetch market data from Yahoo Finance."""

    def __init__(self, cache_dir=None):
        if not HAS_YFINANCE:
            raise ImportError("yfinance is required. Install with: pip install yfinance")
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def fetch(self, ticker, period="1y", interval="1d"):
        """
        Fetch historical data for a ticker.
        
        Parameters:
            ticker: Yahoo Finance ticker (e.g., "^GSPC")
            period: "1mo", "3mo", "6mo", "1y", "2y", "5y"
            interval: "1d", "1wk", "1mo"
        
        Returns:
            DataFrame with Date index and OHLCV columns
        """
        tk = yf.Ticker(ticker)
        df = tk.history(period=period, interval=interval)
        
        if df.empty:
            print(f"⚠ No data returned for {ticker}")
            return pd.DataFrame()
        
        # Cache if configured
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self.cache_dir / f"{ticker.replace('^', '').replace('=', '_')}_{period}.csv"
            df.to_csv(cache_file)
        
        return df

    def get_close_series(self, ticker, period="1y"):
        """Get just the closing prices as a Series."""
        df = self.fetch(ticker, period=period)
        if df.empty:
            return pd.Series(dtype=float)
        return df["Close"]

    def weekly_change(self, ticker):
        """
        Calculate the weekly percentage change (last close vs 5 trading days ago).
        
        Returns:
            dict with keys: current, previous, change_pct, change_abs
        """
        df = self.fetch(ticker, period="1mo", interval="1d")
        if len(df) < 6:
            return None
        
        current = df["Close"].iloc[-1]
        previous = df["Close"].iloc[-6]  # ~5 trading days
        change_pct = ((current / previous) - 1) * 100
        change_abs = current - previous
        
        return {
            "current": current,
            "previous": previous,
            "change_pct": round(change_pct, 2),
            "change_abs": round(change_abs, 4),
        }

    def fetch_multiple(self, tickers, period="1y"):
        """
        Fetch data for multiple tickers at once (more efficient).
        
        Returns:
            dict of {ticker: DataFrame}
        """
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = self.fetch(ticker, period=period)
            except Exception as e:
                print(f"⚠ Error fetching {ticker}: {e}")
                results[ticker] = pd.DataFrame()
        return results

    def weekly_changes_batch(self, ticker_map):
        """
        Get weekly changes for multiple indicators.
        
        Parameters:
            ticker_map: dict of {indicator_id: ticker} 
                        e.g., {"sp500": "^GSPC", "ftse100": "^FTSE"}
        
        Returns:
            dict of {indicator_id: {current, previous, change_pct, change_abs}}
        """
        results = {}
        for ind_id, ticker in ticker_map.items():
            try:
                results[ind_id] = self.weekly_change(ticker)
            except Exception as e:
                print(f"⚠ Error getting weekly change for {ind_id} ({ticker}): {e}")
                results[ind_id] = None
        return results
