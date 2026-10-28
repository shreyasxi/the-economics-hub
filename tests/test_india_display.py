"""Publication gates and fast readers: archive work must stay off the app path."""
import copy
import ast
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config.emerging_opportunity import SECTORS, EQUITY_SECTORS
from data.processors import emerging_publication as research
from data.processors import cpi_items as items, cpi_contributions as cpi


FIXTURES = Path(__file__).parent/'fixtures'


class ResearchPublicationTests(unittest.TestCase):
    def datasets(self):
        fixture = json.loads((FIXTURES/'emerging_opportunity/snapshot.json').read_text())
        return {sector: dict(copy.deepcopy(fixture), sector=sector, digest='audited-fixture') for sector in SECTORS}

    def publish(self, root, datasets=None):
        with patch('data.fetchers.emerging_opportunity.validate_datasets', return_value=datasets or self.datasets()) as audit:
            release = research.publish(root)
            audit.assert_called_once_with(list(SECTORS))
        return release

    def test_ranking_and_selected_data_match_audited_inputs_without_archive_reads(self):
        from data.processors.emerging_opportunity import flow_metrics
        datasets = self.datasets()
        with tempfile.TemporaryDirectory() as d:
            self.publish(d, datasets)
            original_read = Path.read_bytes
            def read_only_publication(path):
                self.assertTrue(path.is_relative_to(Path(d)))
                return original_read(path)
            with patch.object(Path, 'read_bytes', read_only_publication), \
                 patch('data.processors.emerging_opportunity.load', side_effect=AssertionError('archive read')):
                folder, manifest = research.read_manifest(d)
                self.assertEqual([r['Sector'] for r in manifest['ranking']], EQUITY_SECTORS)
                self.assertEqual(manifest['ranking'][0]['Six-month net (₹ cr)'], flow_metrics(datasets[EQUITY_SECTORS[0]])['net_cr'])
                for sector in SECTORS:
                    self.assertEqual(research.load_sector(sector, folder, manifest), datasets[sector])

    def test_failed_audit_preserves_release_and_does_not_publish_partial_ranking(self):
        with tempfile.TemporaryDirectory() as d:
            self.publish(d)
            before = (Path(d)/'CURRENT').read_bytes()
            with patch('data.fetchers.emerging_opportunity.validate_datasets', side_effect=ValueError('Source checksum mismatch')):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    research.publish(d)
            self.assertEqual(before, (Path(d)/'CURRENT').read_bytes())
            research.read_manifest(d)

    def test_releases_are_content_addressed_and_do_not_mix_versions(self):
        with tempfile.TemporaryDirectory() as d:
            first = self.publish(d)
            folder, old_manifest = research.read_manifest(d)
            self.assertEqual(self.publish(d), first)
            changed = self.datasets()
            changed['Services']['companies'][0]['name'] = 'Updated verified name'
            changed['Services']['digest'] = 'new-source-digest'
            second = self.publish(d, changed)
            self.assertNotEqual(first, second)
            self.assertNotEqual(research.load_sector('Services', folder, old_manifest)['companies'][0]['name'], 'Updated verified name')
            folder, manifest = research.read_manifest(d)
            self.assertEqual(research.load_sector('Services', folder, manifest)['companies'][0]['name'], 'Updated verified name')

    def test_tampered_missing_and_cross_sector_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            self.publish(d)
            folder, manifest = research.read_manifest(d)
            file = folder/manifest['sectors']['Services']['file']
            original = file.read_bytes()
            file.write_bytes(original + b' ')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                research.load_sector('Services', folder, manifest)
            file.unlink()
            with self.assertRaises(OSError):
                research.load_sector('Services', folder, manifest)
            manifest['sectors']['Services']['file'] = '../outside.json'
            with self.assertRaisesRegex(ValueError, 'path'):
                research.load_sector('Services', folder, manifest)
            (folder/'manifest.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                research.read_manifest(d)
            (Path(d)/'CURRENT').write_text('../outside')
            with self.assertRaisesRegex(ValueError, 'identity'):
                research.read_manifest(d)


class CPIDisplayTests(unittest.TestCase):
    def test_renderer_recovers_previous_release_module_after_streamlit_rerun(self):
        source = (Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8')
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == '_render_cpi_items')
        for missing in ('DISPLAY_NAME', 'load_display'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as d:
                root, output, expected = self.prepare(d)
                ui = MagicMock()
                ui.columns.return_value = [MagicMock(), MagicMock()]
                namespace = {'Path': Path, 'st': ui}
                exec(compile(ast.Module(body=[function], type_ignores=[]), 'app.py', 'exec'), namespace)
                try:
                    # The dependency is already imported, as in a live Streamlit
                    # process; only app.py has picked up the new release.
                    delattr(items, missing)
                    with patch('data.paths.CPI_ITEMS_DIR', root):
                        namespace['_render_cpi_items'](output)
                    self.assertEqual(ui.image.call_count, 2)
                    self.assertTrue(any(expected['title'] in call.args[0]
                                        for call in ui.markdown.call_args_list))
                    ui.warning.assert_not_called()
                    ui.caption.assert_called_once_with(expected['source_line'])
                finally:
                    importlib.reload(items)

    def prepare(self, directory):
        root, output = Path(directory)/'source', Path(directory)/'edition'
        (root/'runs/fixture').mkdir(parents=True)
        output.mkdir()
        rows = json.loads((FIXTURES/'cpi/official_items.json').read_text())
        data = items.snapshot(rows)
        manifest = dict(run_id='fixture', latest_month=data['latest_month'], coverage_start='2025-08')
        blob = cpi.encoded(manifest)
        (root/'runs/fixture/manifest.json').write_bytes(blob)
        (root/'current.json').write_bytes(cpi.encoded(dict(run_id='fixture', manifest_sha256=cpi.sha(blob))))
        (root/'last_attempt.json').write_bytes(cpi.encoded(dict(run_id='fixture', status='success')))
        data.update(run_id='fixture', coverage_start='2025-08', base_year='2024', series='Current')
        (output/(items.DISPLAY_NAME+'.json')).write_bytes(cpi.encoded(data))
        for side in ('increases', 'declines'):
            (output/f'{items.DISPLAY_NAME}_{side}.png').write_bytes(b'fixture panel '+side.encode())
        with patch.object(items, 'load_current', return_value=(rows, manifest)) as audit:
            items.publish_existing_display(output, root)
            audit.assert_called_once_with(root)
        return root, output, data

    def test_runtime_reads_only_small_identity_and_display_files(self):
        with tempfile.TemporaryDirectory() as d:
            root, output, expected = self.prepare(d)
            allowed = {'current.json', 'last_attempt.json', 'manifest.json', items.DISPLAY_NAME+'.display.json',
                       items.DISPLAY_NAME+'.json', items.DISPLAY_NAME+'_increases.png', items.DISPLAY_NAME+'_declines.png'}
            read = Path.read_bytes
            def limited(path):
                self.assertIn(path.name, allowed)
                return read(path)
            with patch.object(Path, 'read_bytes', limited), \
                 patch.object(items, 'load_current', side_effect=AssertionError('archive replay')), \
                 patch.object(items, 'snapshot', side_effect=AssertionError('recalculation')):
                data, panels = items.load_display(output, root)
            self.assertEqual(data, expected)
            self.assertEqual(len(panels), 2)

    def test_modified_panel_or_metadata_and_missing_receipt_fail_closed(self):
        for name in (items.DISPLAY_NAME+'.json', items.DISPLAY_NAME+'_increases.png', items.DISPLAY_NAME+'.display.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root, output, _ = self.prepare(d)
                file = output/name
                if name.endswith('.display.json'):
                    file.unlink()
                    error = OSError
                else:
                    file.write_bytes(file.read_bytes()+b' ')
                    error = ValueError
                with self.assertRaises(error):
                    items.load_display(output, root)

    def test_failed_refresh_and_advanced_source_close_the_display_gate(self):
        for kind in ('failed', 'advanced', 'changed-manifest'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root, output, _ = self.prepare(d)
                if kind == 'failed':
                    (root/'last_attempt.json').write_text('{"status":"failed","run_id":"fixture"}')
                elif kind == 'advanced':
                    manifest = items._display_source(root)[1]
                    manifest['run_id'] = 'next'
                    (root/'runs/next').mkdir()
                    blob = cpi.encoded(manifest)
                    (root/'runs/next/manifest.json').write_bytes(blob)
                    (root/'current.json').write_bytes(cpi.encoded(dict(run_id='next',manifest_sha256=cpi.sha(blob))))
                    (root/'last_attempt.json').write_bytes(cpi.encoded(dict(status='success',run_id='next')))
                else:
                    (root/'runs/fixture/manifest.json').write_text('{}')
                with self.assertRaises(ValueError):
                    items.load_display(output, root)

    def test_bootstrap_rejects_metadata_from_another_edition(self):
        with tempfile.TemporaryDirectory() as d:
            root, output, _ = self.prepare(d)
            path = output/(items.DISPLAY_NAME+'.json')
            data = json.loads(path.read_text()); data['summary'] = 'Wrong edition'
            path.write_text(json.dumps(data))
            manifest = items._display_source(root)[1]
            with patch.object(items, 'load_current', return_value=(json.loads((FIXTURES/'cpi/official_items.json').read_text()), manifest)):
                with self.assertRaisesRegex(ValueError, 'different snapshot'):
                    items.publish_existing_display(output, root)


if __name__ == '__main__':
    unittest.main()
