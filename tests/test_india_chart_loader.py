"""India edition selection preserves current local source-validation omissions."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from charts import loader


class IndiaLoaderTests(unittest.TestCase):
    def test_local_matching_edition_wins_without_stale_chart_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            assets=root/'assets/india/2026-10';output=root/'output/india/2026-10'
            assets.mkdir(parents=True);output.mkdir(parents=True)
            (assets/'06_india_inflation_bar.png').write_bytes(b'old')
            (output/'15_india_iip.png').write_bytes(b'new')
            # Precedence is explicit even if discovery order changes.
            for bases in ([root/'assets',root/'output'],[root/'output',root/'assets']):
                with patch.object(loader,'_get_base_dirs',return_value=bases):
                    paths,edition=loader.get_charts('india')
                self.assertEqual(paths,[output/'15_india_iip.png'])
                self.assertEqual(edition,'2026-10')

    def test_newer_published_edition_wins_over_older_local_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);assets=root/'assets/india/2026-11';output=root/'output/india/2026-10'
            assets.mkdir(parents=True);output.mkdir(parents=True)
            with patch.object(loader,'_get_base_dirs',return_value=[root/'assets',root/'output']):
                self.assertEqual(loader._latest_folder('india'),(assets,'2026-11'))
