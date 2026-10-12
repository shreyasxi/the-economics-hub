import unittest
from datetime import date
import numpy as np
import pandas as pd
from data.fetchers.portfolio_prices import freshness, snapshot_path, validate_history


class DataTests(unittest.TestCase):
    def test_adjustments_never_fall_back_to_close(self):
        index = pd.bdate_range("2020-01-01", periods=3)
        # $1 distribution against previous split-adjusted $100 Close.
        frame = pd.DataFrame({"Close": [100., 99., 101.], "Adj Close": [99., 99., 101.],
                              "Dividends": [0., 1., 0.], "Stock Splits": [0., 0., 0.]}, index=index)
        self.assertLess(validate_history("SPY", frame)[1], 1e-12)
        for broken in [frame.drop(columns="Adj Close"), frame.assign(**{"Adj Close": frame.Close}),
                       frame.assign(Dividends=np.nan)]:
            with self.assertRaises(ValueError): validate_history("SPY", broken)

    def test_freshness(self):
        self.assertTrue(freshness("2026-09-01", date(2026, 10, 11)).startswith("Stale"))
        self.assertFalse(freshness("2026-10-09", date(2026, 10, 11)).startswith("Stale"))
        self.assertTrue(freshness("2027-01-01", date(2026, 10, 11)).startswith("Invalid"))

    def test_missing_snapshot(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "No prepared"):
                snapshot_path(d)
            (Path(d)/"CURRENT").write_text("../../etc")
            with self.assertRaisesRegex(ValueError, "Invalid"):
                snapshot_path(d)


class SnapshotTests(unittest.TestCase):
    def test_atomic_snapshot_checksums_and_identity(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, Mock
        from data.fetchers.portfolio_prices import prepare, load_bundle
        index = pd.bdate_range("2020-01-01", periods=60)
        frame = pd.DataFrame({"Close": np.full(60,100.), "Adj Close": np.full(60,100.),
                              "Dividends": np.zeros(60), "Stock Splits": np.zeros(60), "Volume": np.full(60,200000.)}, index=index)
        def ticker(t):
            result = Mock()
            result.get_info.return_value = {}
            result.get_history_metadata.return_value = {"symbol": t, "currency": "USD", "instrumentType": "ETF"}
            return result
        with tempfile.TemporaryDirectory() as d:
            with patch("data.fetchers.yfinance_fetcher.YFinanceFetcher._download", return_value=frame), patch("yfinance.Ticker", side_effect=ticker), patch("data.fetchers.portfolio_bitcoin.fetch_bitcoin", return_value=pd.DataFrame({"asset":"btc", "time":pd.date_range("2019-12-31",periods=100,tz="UTC"), "PriceUSD":np.full(100,100.)})):
                bundle = prepare(d)
            self.assertEqual(snapshot_path(d), bundle)
            prices, manifest = load_bundle(bundle)
            self.assertEqual(prices.shape, (60, 28))
            with patch("data.fetchers.yfinance_fetcher.YFinanceFetcher._download", side_effect=ValueError("source failure")):
                with self.assertRaisesRegex(ValueError, "source failure"): prepare(d)
            self.assertEqual(snapshot_path(d), bundle)
            (bundle/"prices.csv").write_text("corrupt")
            with self.assertRaisesRegex(ValueError, "checksum"): load_bundle(bundle)

    def test_identity_mismatch_blocks_activation(self):
        import tempfile
        from unittest.mock import patch, Mock
        from data.fetchers.portfolio_prices import prepare
        tk = Mock()
        tk.get_history_metadata.return_value = {"symbol": "WRONG", "currency": "USD", "instrumentType": "ETF"}
        with tempfile.TemporaryDirectory() as d, patch("data.fetchers.yfinance_fetcher.YFinanceFetcher._download", return_value=pd.DataFrame()), patch("yfinance.Ticker", return_value=tk):
            with self.assertRaisesRegex(ValueError, "identity mismatch"): prepare(d)
            with self.assertRaisesRegex(ValueError, "No prepared"): snapshot_path(d)
