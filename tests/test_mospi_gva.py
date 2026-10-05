"""Official workbook fixtures and failure-path tests for quarterly GVA."""
import copy
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

import openpyxl
from data.fetchers import mospi_gva as gva

FIXTURES = Path(__file__).parent / 'fixtures' / 'mospi_gva'


class GvaTests(unittest.TestCase):
    def setUp(self):
        self.history_blob = (FIXTURES / 'nas_2026_8.18.1.xlsx').read_bytes()
        self.latest_blob = (FIXTURES / 'quarterly_constant_2026-08-31.xlsx').read_bytes()
        self.entry = json.loads((FIXTURES / 'catalogue_entry.json').read_text())
        self.url = gva.DOWNLOAD_ROOT + quote(self.entry['file_path'].lstrip('/') + self.entry['file_name'], safe='/')
        self.history = gva.parse_history(self.history_blob)
        self.latest = gva.parse_latest(self.latest_blob, self.entry, self.url)
        self.rows = gva.combine(self.history, self.latest)

    def test_official_levels_and_calendar_comparisons(self):
        self.assertEqual(len(self.rows), 17)
        self.assertEqual(self.rows[0]['quarter'], '2022-06-30')
        self.assertEqual(self.rows[3]['quarter'], '2023-03-31')
        self.assertEqual(self.rows[7]['comparison_quarter'], '2023-03-31')
        self.assertTrue(all(r['headline_yoy'] is None for r in self.rows[:4]))
        for r in self.rows[4:]:
            self.assertLess(abs(sum(r[k+'_pp'] for k in gva.LEVEL_KEYS[:3])-r['headline_yoy']), 1e-8)
            self.assertEqual(r['base_year'], '2022-23')
        self.assertAlmostEqual(self.rows[-1]['headline_yoy'], 8.229320112314227)
        self.assertAlmostEqual(self.rows[-1]['tertiary_pp'], 5.447414095084943)
        self.assertEqual(self.rows[-1]['release_date'], '2026-08-31')

    def test_missing_quarter_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing quarter'):
            gva.calculate(self.rows[:6] + self.rows[7:])

    def test_mixed_base_and_nonreconciling_levels_rejected(self):
        for field, value, error in [('base_year', '2011-12', 'mixed base'),
                                    ('gva', 1, 'reconciliation')]:
            bad = copy.deepcopy(self.rows)
            bad[5][field] = value
            with self.assertRaisesRegex(ValueError, error):
                gva.calculate(bad)

    def test_changed_schema_and_missing_values_rejected(self):
        for cell, value in [('A11', '2. New Sector'), ('B8', None),
                            ('A2', 'Constant Prices, 2011-12 Series')]:
            book = openpyxl.load_workbook(BytesIO(self.history_blob))
            book.active[cell] = value
            out = BytesIO()
            book.save(out)
            with self.assertRaises(ValueError):
                gva.parse_history(out.getvalue())

    def test_inconsistent_revision_rejected(self):
        latest = copy.deepcopy(self.latest)
        latest[0]['gva'] += 50
        with self.assertRaisesRegex(ValueError, 'revises historical'):
            gva.combine(self.history, latest)

    def test_idempotent_storage_and_corruption_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'india.db'
            gva.store(self.rows, db)
            first = gva.load(db)
            gva.store(self.rows, db)
            second = gva.load(db)
            self.assertEqual([{k:v for k,v in r.items() if k!='fetched_at'} for r in first],
                             [{k:v for k,v in r.items() if k!='fetched_at'} for r in second])
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE india_gva_quarterly SET tertiary_pp=0 WHERE quarter='2026-06-30'")
            with self.assertRaisesRegex(ValueError, 'stored tertiary_pp'):
                gva.load(db)

    def test_fetch_uses_catalogue_and_dry_run_does_not_write(self):
        class Response:
            def __init__(self, content=b'', payload=None):
                self.content, self.payload = content, payload
            def raise_for_status(self):
                pass
            def json(self):
                return self.payload
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'absent.db'
            with patch('requests.Session.get', side_effect=[
                Response(payload={'statusCode':True,'data':[self.entry]}),
                Response(self.history_blob), Response(self.latest_blob),
            ]) as get:
                rows = gva.fetch(dry_run=True, db=db)
                self.assertEqual(len(rows), 17)
                self.assertEqual(get.call_args_list[-1].args[0], self.url)
                self.assertFalse(db.exists())


if __name__ == '__main__':
    unittest.main()
