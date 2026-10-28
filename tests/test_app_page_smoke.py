"""Render complete public dashboard pages against the checked-in artifacts."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize('page', ['weekly', 'world', 'india', 'rbi', 'research'])
def test_dashboard_page_renders_without_runtime_errors(page, tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = (root / 'app.py').read_text(encoding='utf-8')
    # Exercise each callable navigation destination with the real app shell.
    # AppTest writes its script to a temporary file, so preserve the asset root.
    source = source.replace('PROJECT_ROOT = Path(__file__).resolve().parent',
                            f'PROJECT_ROOT = Path({str(root)!r})')
    assert source.count('current.run()') == 1
    # The essay feed is external to these offline artifact/rendering checks.
    source = source.replace('current.run()',
                            f'_substack_posts = lambda *_: ([], None)\npage_{page}()')
    script = tmp_path / 'app.py'
    script.write_text(source, encoding='utf-8')
    app = AppTest.from_file(script, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    if page == 'india':
        assert any('cpi-items-heading' in item.value for item in app.markdown)
        assert not any('CPI item price pressures are unavailable' in item.value
                       for item in [*app.warning, *app.caption])
