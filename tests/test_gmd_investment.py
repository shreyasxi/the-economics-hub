"""Guard the investment chart's coverage, units and missing-observation policy."""
import numpy as np
import pandas as pd
import unittest
from data.fetchers.gmd_investment import CSV_PATH, load_snapshot, prepare


class InvestmentTests(unittest.TestCase):
    def test_snapshot_coverage_and_percent_units(self):
        panel, meta = load_snapshot()
        assert panel.index.tolist() == list(range(meta["start_year"], meta["end_year"] + 1))
        assert panel.notna().all()
        self.assertAlmostEqual(panel.loc[2024], 31.643442, places=6)
        assert meta['variable'] == 'finv_GDP'


    def test_missing_year_stays_a_gap(self):
        raw = pd.read_csv(CSV_PATH)
        raw = raw[~((raw.ISO3 == 'IND') & (raw.year == 2000))]
        panel = prepare(raw)
        assert np.isnan(panel.loc[2000])
        assert panel.loc[1999] > 0
        assert panel.loc[2001] > 0


    def test_forecast_extension_excluded(self):
        raw = pd.read_csv(CSV_PATH)
        extended = pd.concat([raw, pd.DataFrame([{'ISO3': 'IND', 'year': 2027, 'finv_GDP': 35}])])
        pd.testing.assert_series_equal(prepare(raw), prepare(extended))


    def test_duplicate_observation_rejected(self):
        raw = pd.read_csv(CSV_PATH)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            prepare(pd.concat([raw, raw.iloc[:1]]))


    def test_missing_country_rejected(self):
        raw = pd.read_csv(CSV_PATH)
        with self.assertRaisesRegex(ValueError, 'no India observations'):
            prepare(raw[raw.ISO3 != 'IND'])

if __name__ == "__main__":
    unittest.main()
