"""Briefings survive table extraction, validation and history failures."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_soe as cli
from data.processors import rbi_soe as soe
from data.processors import rbi_soe_pdf as pdf

URL = 'https://rbidocs.rbi.org.in/rdocs/Bulletin/PDFs/01ARTICLE23102026026657A9D5FE49CA9595B3F593D46E4C.PDF'
EDITION = soe.Edition('2026-10', '', URL, URL)
PAYLOAD = Path(__file__).parent / 'fixtures/soe/2026-10.pdf'


class IndependentBriefingTests(unittest.TestCase):
    def test_october_real_table_and_prose(self):
        page = pdf.pdf_to_article(PAYLOAD.read_bytes(), EDITION.month, URL)
        table = soe.parse_transmission(page)
        cycle = table['cycles'][-1]
        self.assertEqual([cycle[k] for k in ['repo_bps', 'wadtdr_fresh_bps',
            'walr_fresh_bps', 'overall_bps', 'walr_outstanding_bps']], [-125, -95, -72, -76, -91])
        self.assertEqual(table['monthly'][-1]['walr_fresh_bps'], 9)
        self.assertEqual(table['monthly'][-1]['overall_bps'], -1)
        briefing = soe.parse_briefing(page, EDITION)
        self.assertEqual(len(briefing['conclusion']), 1)
        self.assertIn('trade tensions, alongside multi-decade-high', briefing['conclusion'][0])
        self.assertTrue(briefing['conclusion'][0].endswith('trade deficit narrowed in September.'))
        self.assertIn('5.5 per cent', soe.parse_topics(page)['Inflation'])

    def run_cli(self, extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root/'history.csv'
            history.write_text('invalid history must never be read by briefing-only')
            with patch.object(soe, 'CACHE_DIR', root/'cache'), \
                 patch.object(soe, '_request_pdf', return_value=PAYLOAD.read_bytes()), \
                 patch.object(cli, 'build_session', return_value=Mock()), \
                 patch.object(cli, 'find_latest', return_value=EDITION), \
                 patch.object(cli, 'read_changes', return_value=([{'topic': 'Inflation'}], '2026-09')), \
                 patch.object(cli, 'TRANSMISSION_CSV', history), \
                 patch.object(pdf, '_transmission_tables', side_effect=soe.SoeError('broken table')) as table, \
                 patch.object(cli, 'read_history', side_effect=AssertionError('history accessed')), \
                 patch('sys.argv', ['generate_soe.py', '--out', str(root), *extra]):
                code = cli.main()
            briefing = json.loads((root/'soe.json').read_text())
            self.assertEqual(briefing['month'], '2026-10')
            self.assertEqual(briefing['changes'], [{'topic': 'Inflation'}])
            self.assertEqual(briefing['compared_with'], '2026-09')
            self.assertEqual(history.read_text(), 'invalid history must never be read by briefing-only')
            return code, table.call_count

    def test_briefing_only_never_extracts_tables_or_reads_history(self):
        self.assertEqual(self.run_cli(['--briefing-only']), (0, 0))

    def test_default_run_saves_briefing_before_table_failure(self):
        code, calls = self.run_cli([])
        self.assertEqual(code, 1)
        self.assertGreater(calls, 0)

    def test_html_briefing_does_not_validate_broken_table(self):
        page = Path('tests/fixtures/soe/2026-08.html').read_text()
        edition = soe.Edition('2026-08', '1', 'https://rbi.org.in/?Id=1')
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(soe, 'CACHE_DIR', Path(directory)), \
             patch.object(soe, '_request', return_value=page), \
             patch.object(soe, 'parse_transmission', side_effect=soe.SoeError('bad header')) as table:
            self.assertEqual(soe.fetch_article(Mock(), edition, include_transmission=False), page)
            table.assert_not_called()


class MonthlyDetailTests(unittest.TestCase):
    def test_render_failure_omits_stale_chart_without_aborting_generation(self):
        import generate_india as charts
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            artifact = output/'18_india_rate_transmission.png'
            artifact.write_bytes(b'stale chart')
            with patch.object(charts, '_render_rate_transmission', side_effect=RuntimeError('render failed')):
                self.assertIsNone(charts.chart_rate_transmission(output))
            self.assertFalse(artifact.exists())

    def test_memo_requires_matching_vintage_and_never_uses_cumulative_differences(self):
        import pandas as pd
        from generate_india import transmission_monthly_detail
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'transmission.csv'
            path.write_bytes(Path('data/stores/india/rbi_transmission.csv').read_bytes())
            page = pdf.pdf_to_article(PAYLOAD.read_bytes(), EDITION.month, URL)
            detail = {"month": EDITION.month, "published": "2026-10-23", "url": URL,
                      **soe.parse_transmission(page)}
            # Select the October cycle directly so this test also works before a store refresh.
            latest = pd.Series({"month": EDITION.month, "published": "2026-10-23", "url": URL, **detail['cycles'][-1]})
            path.with_suffix('.json').write_text(json.dumps(detail))
            memo = transmission_monthly_detail(path, latest)
            self.assertEqual(memo['walr_fresh_bps'], 9)
            self.assertEqual(memo['overall_bps'], -1)
            detail['month'] = '2026-09'
            path.with_suffix('.json').write_text(json.dumps(detail))
            self.assertIsNone(transmission_monthly_detail(path, latest))
            detail['month'] = EDITION.month
            detail['cycles'][-1]['walr_fresh_bps'] = -999
            path.with_suffix('.json').write_text(json.dumps(detail))
            self.assertIsNone(transmission_monthly_detail(path, latest))


if __name__ == '__main__':
    unittest.main()
