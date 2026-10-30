"""Saturday source failures must not publish previous charts or mismatched audits."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from charts.india_charts import india_cpi_items as cpi_chart
from charts.india_charts import india_external as external
from tests.test_mospi_activity_workflow import copy_script

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/india.yml'
CPI_FILES = ('06b_india_cpi_items.json', '06b_india_cpi_items_increases.png',
             '06b_india_cpi_items_declines.png', '06b_india_cpi_items.display.json')
EXTERNAL_FILES = ('30_india_reer.png', '31_india_external_vulnerability.png')


class SaturdaySources(unittest.TestCase):
    def test_cpi_timeout_clears_both_panels_and_audit_without_reading_old_store(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in CPI_FILES:
                (Path(directory) / name).write_bytes(b'old')
            with patch.dict(os.environ, {'CPI_ITEMS_UPDATE_FAILED': 'true'}), \
                    patch.object(cpi_chart.items, 'load_current') as load:
                self.assertEqual(cpi_chart.generate(directory), [])
            load.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def assert_external_refresh_fallback(self, failed_flag, fallback_chart, independent_chart,
                                         fallback_name, independent_name):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name in EXTERNAL_FILES:
                (output / name).write_bytes(b'old chart')

            def render(folder, name, content):
                path = folder / name
                path.write_bytes(content)
                return path

            flags = dict(REER_UPDATE_FAILED='false', EXTERNAL_VULNERABILITY_UPDATE_FAILED='false')
            flags[failed_flag] = 'true'
            with patch.dict(os.environ, flags), \
                    patch.object(external, fallback_chart, side_effect=lambda folder: render(
                        folder, fallback_name, b'validated stored data')) as fallback, \
                    patch.object(external, independent_chart, side_effect=lambda folder: render(
                        folder, independent_name, b'fresh independent data')) as independent:
                self.assertEqual(set(external.generate(output)), {output / name for name in EXTERNAL_FILES})
            fallback.assert_called_once_with(output)
            independent.assert_called_once_with(output)
            self.assertEqual((output / fallback_name).read_bytes(), b'validated stored data')
            self.assertEqual((output / independent_name).read_bytes(), b'fresh independent data')

    def test_failed_reer_renders_validated_store_and_does_not_block_vulnerability(self):
        self.assert_external_refresh_fallback('REER_UPDATE_FAILED', 'chart_reer',
            'chart_vulnerability', EXTERNAL_FILES[0], EXTERNAL_FILES[1])

    def test_failed_vulnerability_renders_validated_store_and_does_not_block_reer(self):
        self.assert_external_refresh_fallback('EXTERNAL_VULNERABILITY_UPDATE_FAILED',
            'chart_vulnerability', 'chart_reer', EXTERNAL_FILES[1], EXTERNAL_FILES[0])
        self.assertIn('::warning title=External vulnerability refresh failed', WORKFLOW.read_text())

    def test_failed_external_refresh_with_invalid_store_omits_only_affected_chart(self):
        for flag, failed_chart, good_chart, missing, retained in (
            ('REER_UPDATE_FAILED', 'chart_reer', 'chart_vulnerability', *EXTERNAL_FILES),
            ('EXTERNAL_VULNERABILITY_UPDATE_FAILED', 'chart_vulnerability', 'chart_reer',
             EXTERNAL_FILES[1], EXTERNAL_FILES[0]),
        ):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                for name in EXTERNAL_FILES:
                    (output / name).write_bytes(b'old chart')

                def render(folder):
                    path = folder / retained
                    path.write_bytes(b'fresh independent data')
                    return path

                flags = dict(REER_UPDATE_FAILED='false', EXTERNAL_VULNERABILITY_UPDATE_FAILED='false')
                flags[flag] = 'true'
                with patch.dict(os.environ, flags), \
                        patch.object(external, failed_chart, side_effect=ValueError('invalid stored data')), \
                        patch.object(external, good_chart, side_effect=render) as independent:
                    self.assertEqual(external.generate(output), [output / retained])
                independent.assert_called_once_with(output)
                self.assertFalse((output / missing).exists())
                self.assertEqual((output / retained).read_bytes(), b'fresh independent data')

    def test_invalid_external_store_cannot_abort_independent_charts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name in EXTERNAL_FILES:
                (output / name).write_bytes(b'old')
            with patch.dict(os.environ, dict(REER_UPDATE_FAILED='false', EXTERNAL_VULNERABILITY_UPDATE_FAILED='false')), \
                    patch.object(external, 'chart_reer', side_effect=ValueError('invalid source')), \
                    patch.object(external, 'chart_vulnerability', return_value=None) as independent:
                self.assertEqual(external.generate(output), [])
            independent.assert_called_once()
            self.assertEqual(list(output.iterdir()), [])

    def test_publication_replaces_panels_and_audit_then_removes_omitted_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output/india/2026-10'
            assets = root / 'assets/india/2026-10'
            output.mkdir(parents=True)
            assets.mkdir(parents=True)
            (output / '00_india_table.png').write_bytes(b'independent chart')
            for name in CPI_FILES + EXTERNAL_FILES:
                (output / name).write_bytes(b'new ' + name.encode())
                (assets / name).write_bytes(b'old')
            subprocess.run(['bash', '-e', '-c', copy_script()], cwd=root, check=True, capture_output=True)
            for name in CPI_FILES + EXTERNAL_FILES:
                self.assertEqual((assets / name).read_bytes(), (output / name).read_bytes())
                (output / name).unlink()
            subprocess.run(['bash', '-e', '-c', copy_script()], cwd=root, check=True, capture_output=True)
            for name in CPI_FILES + EXTERNAL_FILES:
                self.assertFalse((assets / name).exists())
            self.assertTrue((assets / '00_india_table.png').exists())

    def test_incomplete_cpi_panels_are_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output/india/2026-10'
            assets = root / 'assets/india/2026-10'
            output.mkdir(parents=True)
            assets.mkdir(parents=True)
            (output / '00_india_table.png').write_bytes(b'independent')
            for name in CPI_FILES[:-1]:
                (output / name).write_bytes(b'incomplete')
            for name in CPI_FILES:
                (assets / name).write_bytes(b'old')
            subprocess.run(['bash', '-e', '-c', copy_script()], cwd=root, check=True, capture_output=True)
            self.assertFalse(any((assets / name).exists() for name in CPI_FILES))

    def test_collectors_precede_generation_and_skipped_fetches_do_not_close_gates(self):
        workflow = WORKFLOW.read_text()
        generation = workflow.index('run: python generate_india.py --mode dashboard')
        for command, step, flag in (
            ('python -m data.fetchers.mospi_cpi_items --update', 'mospi-cpi-items', 'CPI_ITEMS_UPDATE_FAILED'),
            ('python -m data.fetchers.rbi_external --series reer', 'rbi-reer', 'REER_UPDATE_FAILED'),
            ('python -m data.fetchers.rbi_external --series vulnerability', 'rbi-vulnerability', 'EXTERNAL_VULNERABILITY_UPDATE_FAILED'),
        ):
            block = workflow.split('        id: ' + step + '\n', 1)[1].split('\n      - name:', 1)[0]
            self.assertIn("if: ${{ github.event.inputs.skip_fetch != 'true' }}", block)
            self.assertIn('continue-on-error: true', block)
            self.assertIn('timeout-minutes:', block)
            self.assertLess(workflow.index('run: ' + command), generation)
            self.assertIn(flag + ": ${{ steps." + step + ".outcome != 'success' && github.event.inputs.skip_fetch != 'true' }}", workflow)
        publication = workflow.split('      - name: Commit and push charts', 1)[1]
        for name in ('CPI_ITEMS_DIR', 'RBI_REER_CSV', 'INDIA_EXTERNAL_CSV', 'RBI_WSS_CSV'):
            self.assertIn(name, publication)


if __name__ == '__main__':
    unittest.main()
