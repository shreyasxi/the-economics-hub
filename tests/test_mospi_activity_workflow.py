"""Offline workflow publication and independent MoSPI failure gates."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from charts.india_charts import india_mospi_activity as activity
from tests.test_mospi_activity import iip_rows, plfs_rows

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / '.github/workflows/india.yml'


def copy_script():
    text = WORKFLOW.read_text().split('      - name: Copy charts to assets/\n', 1)[1]
    block = text.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
    return '\n'.join(line[10:] for line in block.splitlines() if line.startswith('          '))


class ActivityWorkflowTests(unittest.TestCase):
    def test_failed_industry_refresh_removes_stale_artifact_without_loading_history(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / activity.HEATMAP
            destination.write_text('stale')
            with patch.dict(os.environ, {'IIP_INDUSTRIES_UPDATE_FAILED': 'true'}), \
                    patch.object(activity.iip, 'load') as load:
                with self.assertRaisesRegex(ValueError, 'refresh failed'):
                    activity.generate(directory)
            load.assert_not_called()
            self.assertFalse(destination.exists())

    def test_invalid_industry_history_cannot_leave_previous_edition_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / activity.HEATMAP
            destination.write_text('stale')
            with patch.dict(os.environ, {'IIP_INDUSTRIES_UPDATE_FAILED': 'false'}), \
                    patch.object(activity.iip, 'load', side_effect=ValueError('bad source')):
                with self.assertRaises(ValueError):
                    activity.generate(directory)
            self.assertFalse(destination.exists())

    def test_failed_plfs_refresh_omits_row_without_loading_old_history(self):
        with patch.dict(os.environ, {'PLFS_UPDATE_FAILED': 'true'}), \
                patch.object(activity.plfs, 'load') as load:
            with self.assertRaisesRegex(ValueError, 'refresh failed'):
                activity.load_youth_snapshot()
        load.assert_not_called()

    def test_industry_and_plfs_failure_gates_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'PLFS_UPDATE_FAILED': 'true', 'IIP_INDUSTRIES_UPDATE_FAILED': 'false'}), \
                    patch.object(activity.iip, 'load', return_value=iip_rows()):
                activity.generate(directory)
            self.assertEqual(len(json.loads((Path(directory) / activity.HEATMAP).read_text())['leaders']), 2)
        with patch.dict(os.environ, {'IIP_INDUSTRIES_UPDATE_FAILED': 'true', 'PLFS_UPDATE_FAILED': 'false'}), \
                patch.object(activity.plfs, 'load', return_value=plfs_rows()):
            self.assertEqual(activity.load_youth_snapshot()['value_str'], '18.7%')

    def test_assets_publication_copies_heatmap_and_clears_omitted_or_retired_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output/india/2026-10'
            assets = root / 'assets/india/2026-10'
            output.mkdir(parents=True)
            assets.mkdir(parents=True)
            (output / '00_india_table.png').write_bytes(b'new youth snapshot')
            (output / activity.HEATMAP).write_text('{"leaders": []}')
            (assets / activity.YOUTH).write_bytes(b'retired')
            (assets / activity.HEATMAP).write_text('stale')
            subprocess.run(['bash', '-e', '-c', copy_script()], cwd=root, check=True, capture_output=True)
            self.assertEqual((assets / activity.HEATMAP).read_bytes(), (output / activity.HEATMAP).read_bytes())
            self.assertEqual((assets / '00_india_table.png').read_bytes(), b'new youth snapshot')
            self.assertFalse((assets / activity.YOUTH).exists())
            (output / activity.HEATMAP).unlink()
            subprocess.run(['bash', '-e', '-c', copy_script()], cwd=root, check=True, capture_output=True)
            self.assertFalse((assets / activity.HEATMAP).exists())

    def test_workflow_fetch_skip_flags_and_source_persistence(self):
        text = WORKFLOW.read_text()
        for step, module in [('mospi-iip-industries', 'mospi_iip_industries'), ('mospi-plfs', 'mospi_plfs_monthly')]:
            block = text.split(f'        id: {step}\n', 1)[1].split('\n      - name:', 1)[0]
            self.assertIn("github.event.inputs.skip_fetch != 'true'", block)
            self.assertIn('continue-on-error: true', block)
            self.assertIn(f'python -m data.fetchers.{module}', block)
            self.assertIn(f"steps.{step}.outcome != 'success' && github.event.inputs.skip_fetch != 'true'", text)
        for source in ['MOSPI_IIP_CSV', 'MOSPI_PLFS_CSV', 'MOSPI_SOURCES_DIR']:
            self.assertIn(source, text.split('      - name: Commit and push charts', 1)[1])
        self.assertIn("test_mospi_activity*.py", text)


if __name__ == '__main__':
    unittest.main()
