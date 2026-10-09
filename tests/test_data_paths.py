"""Data-path contracts for manual inputs, isolated archives and workflow shells."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from data import paths


class DataPathTests(unittest.TestCase):
    def test_stores_inputs_and_caches_have_distinct_locations(self):
        self.assertEqual(paths.INDIA_DB.parent, paths.DATA_DIR/'stores/india')
        self.assertEqual(paths.RBI_SENTINEL_DB.parent, paths.DATA_DIR/'stores/rbi_sentinel')
        self.assertEqual(paths.WORLD_MANUAL_CSV.parent, paths.DATA_DIR/'stores/world')
        self.assertEqual(paths.CAG_WORKBOOK.parent, paths.DATA_DIR/'inputs/cag')
        self.assertEqual(paths.RBI_SENTINEL_CACHE.parent, paths.DATA_CACHE)
        self.assertEqual(paths.RBI_SOE_CACHE.parent, paths.DATA_CACHE)

    def test_owner_inputs_remain_at_data_top_level(self):
        self.assertEqual(paths.DBIE_WORKBOOK.parent, paths.DATA_DIR)
        self.assertEqual(paths.INDIA_MANUAL_CSV.parent, paths.DATA_DIR)
        self.assertEqual(paths.DBIE_WORKBOOK.name, '50 Macroeconomic Indicators.xlsx')
        self.assertEqual(paths.INDIA_MANUAL_CSV.name, 'india_manual.csv')

    def test_custom_sources_keep_archives_isolated_from_live_data(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertEqual(paths.archive_for_db(base/'copy.db', 'gva'), base/'gva')
            self.assertEqual(paths.archive_for_db(base/'copy.db', 'IIP'), base/'IIP')
            self.assertEqual(paths.mospi_sources_for(base/'copy.csv', 'iip'),
                             base/'mospi_activity_sources/iip')
            self.assertEqual(paths.mospi_sources_for(base/'copy.csv', 'plfs'),
                             base/'mospi_activity_sources/plfs')

    def test_canonical_archives_can_move_independently_of_database(self):
        with patch.object(paths, 'GVA_DIR', paths.DATA_DIR/'future/gva'), \
             patch.object(paths, 'MOSPI_SOURCES_DIR', paths.DATA_DIR/'future/evidence'):
            self.assertEqual(paths.archive_for_db(paths.INDIA_DB, 'gva'), paths.GVA_DIR)
            self.assertEqual(paths.mospi_sources_for(paths.MOSPI_IIP_CSV, 'iip'),
                             paths.MOSPI_SOURCES_DIR/'iip')

    def test_workflow_cli_preserves_spaces_and_ignores_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, PYTHONPATH=str(paths.PROJECT_ROOT))
            result = subprocess.run(
                [sys.executable, '-m', 'data.paths', '--relative',
                 'DBIE_WORKBOOK', 'INDIA_MANUAL_CSV', 'RBI_MONEY_MARKET_CSV'],
                cwd=directory, env=env, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.splitlines(),
                             ['data/50 Macroeconomic Indicators.xlsx', 'data/india_manual.csv',
                              'data/stores/india/rbi_money_market.csv'])
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
