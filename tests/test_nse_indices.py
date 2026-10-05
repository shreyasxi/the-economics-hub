"""Offline NSE price-index import and failure-safe refresh tests."""
import tempfile
from pathlib import Path
import unittest
import pandas as pd
from data.nse_indices import parse_export, combine_exports, relative_performance, import_exports, load_risk_appetite
import json
import requests
from data.nse_indices import import_exports, load_risk_appetite, parse_daily, parse_export
from data.fetchers.nse_risk_appetite import refresh


def sample(name, rows):
    return ('Index Name,Date,Open,High,Low,Close\n' + ''.join(
        f'{name},{d},{v},{v+1},{v-1},{v}\n' for d, v in rows)).encode()


class IndexTests(unittest.TestCase):
    def test_inner_join_and_ratio_not_price_difference(self):
        a = pd.Series([100, 120, 150], index=pd.to_datetime(['2025-01-01','2025-01-02','2025-01-03']))
        b = pd.Series([50, 60], index=pd.to_datetime(['2025-01-01','2025-01-03']))
        out = relative_performance(a, b)
        self.assertEqual(out.relative_100.tolist(), [100, 125])
        self.assertNotIn(pd.Timestamp('2025-01-02'), out.index)

    def test_bad_denominator_rejected(self):
        a = pd.Series([100, 120], index=pd.date_range('2025-01-01', periods=2))
        with self.assertRaises(ValueError):
            relative_performance(a, a * 0)

    def test_wrong_index_rejected(self):
        with self.assertRaises(ValueError):
            parse_export(sample('NIFTY MIDCAP 100', [('01 Jan 2025', 100)]), 'NIFTY 50')

    def test_duplicates_within_file_rejected(self):
        with self.assertRaises(ValueError):
            parse_export(sample('NIFTY 50', [('01 Jan 2025',100)] * 2), 'NIFTY 50')

    def test_conflicting_overlap_rejected(self):
        a = pd.Series([100], index=pd.to_datetime(['2025-01-01']))
        with self.assertRaises(ValueError):
            combine_exports([a, a + 1])
        self.assertEqual(len(combine_exports([a, a])), 1)

    def test_roundtrip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small, large = root/'small.csv', root/'large.csv'
            small.write_bytes(sample('NIFTY SMALLCAP 250', [('01 Jan 2025',100),('02 Jan 2025',120),('03 Jan 2025',150)]))
            large.write_bytes(sample('NIFTY 50', [('01 Jan 2025',50),('03 Jan 2025',60)]))
            panel, meta = import_exports([small], [large], '2025-01-01', '2025-01-03', root/'store')
            self.assertEqual(meta['unmatched_dates'], ['2025-01-02'])
            loaded, _ = load_risk_appetite(root/'store')
            pd.testing.assert_frame_equal(panel, loaded)
            (root/'store'/meta['sources'][0]['path']).write_text('damaged')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_risk_appetite(root/'store')

    def test_tri_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            parse_export(b'Date,Total Returns Index\n01 Jan 2025,100\n', 'NIFTY 50')


def history(name, closes):
    return ('Index Name,Date,Open,High,Low,Close\n' + ''.join(
        f'{name},0{i} Jan 2025,-,-,-,{v}\n' for i, v in enumerate(closes, 1))).encode()


def daily(date='03-01-2025', small=150, large=60):
    return (f'Index Name,Index Date,Closing Index Value\n'
            f'Nifty Smallcap 250,{date},{small}\nNifty 50,{date},{large}\n').encode()


class Client:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        status, body = next(self.replies)
        response = requests.Response()
        response.status_code = status
        response._content = body
        response.url = url
        return response


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        small, large = base/'s.csv', base/'l.csv'
        small.write_bytes(history('NIFTY SMALLCAP 250', [100, 120]))
        large.write_bytes(history('NIFTY 50', [50, 60]))
        self.root = base/'store'
        import_exports([small], [large], '2025-01-01', '2025-01-02', self.root)

    def test_close_only_history_valid_but_missing_close_fails(self):
        self.assertEqual(len(parse_export(history('NIFTY 50', [50, 60]), 'NIFTY 50')), 2)
        with self.assertRaises(ValueError):
            parse_export(history('NIFTY 50', ['-']), 'NIFTY 50')

    def test_append_and_fixed_base(self):
        panel, meta = refresh(self.root, '2025-01-03', '2025-01-03', Client([(200, daily())]))
        self.assertEqual(meta['base_date'], '2025-01-01')
        self.assertEqual(panel.relative_100.tolist(), [100, 100, 125])
        loaded, _ = load_risk_appetite(self.root)
        self.assertEqual(loaded.relative_100.iloc[-1], 125)

    def test_identical_refresh_does_not_duplicate_sources_or_dates(self):
        _, first = refresh(self.root, '2025-01-03', '2025-01-03', Client([(200, daily())]))
        panel, second = refresh(self.root, '2025-01-03', '2025-01-03', Client([(200, daily())]))
        self.assertEqual(first['signal_sha256'], second['signal_sha256'])
        self.assertEqual(first['sources'], second['sources'])
        self.assertEqual(len(panel), 3)

    def test_unavailable_date_is_recorded_not_filled(self):
        client = Client([(404, b''), (200, daily('04-01-2025'))])
        panel, meta = refresh(self.root, '2025-01-04', '2025-01-03', client)
        self.assertNotIn('2025-01-03', panel.index.astype(str))
        self.assertEqual(meta['refresh']['unresolved_report_dates'], ['2025-01-03'])
        self.assertTrue(client.urls[-1].endswith('04012025.csv'))  # Saturdays are not assumed closed.

    def test_repaired_missing_report_clears_audit(self):
        refresh(self.root, '2025-01-04', '2025-01-03',
                Client([(404, b''), (200, daily('04-01-2025'))]))
        _, meta = refresh(self.root, '2025-01-03', '2025-01-03', Client([(200, daily())]))
        self.assertEqual(meta['refresh']['unresolved_report_dates'], [])

    def assert_retained(self, client, start='2025-01-03', end='2025-01-03'):
        manifest = self.root/'manifest.json'
        before = manifest.read_bytes()
        with self.assertRaises((ValueError, requests.HTTPError)):
            refresh(self.root, end, start, client)
        self.assertEqual(before, manifest.read_bytes())
        self.assertEqual(len(load_risk_appetite(self.root)[0]), 2)
        audit = json.loads(next((self.root/'runs').glob('*.json')).read_text())
        self.assertEqual(audit['status'], 'failed_previous_manifest_retained')

    def test_conflicting_revision_preserves_manifest(self):
        self.assert_retained(Client([(200, daily('02-01-2025', small=999))]), '2025-01-02', '2025-01-02')

    def test_http_failure_after_valid_report_preserves_manifest(self):
        self.assert_retained(Client([(200, daily()), (403, b'Forbidden')]), end='2025-01-04')

    def test_all_missing_preserves_manifest(self):
        self.assert_retained(Client([(404, b'')]))

    def test_html_instead_of_csv_preserves_manifest(self):
        self.assert_retained(Client([(200, b'<html>Access denied</html>')]))

    def test_wrong_date_preserves_manifest(self):
        self.assert_retained(Client([(200, daily('02-01-2025'))]))

    def test_wrong_variant_duplicate_and_invalid_close_rejected(self):
        bad = [daily().replace(b'Nifty Smallcap 250,', b'Nifty Smallcap 250 TRI,'),
               daily() + b'Nifty 50,03-01-2025,60\n',
               daily(large=0), daily(large='nan'), daily(small='inf')]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_daily(payload, '2025-01-03')


if __name__ == '__main__':
    unittest.main()
