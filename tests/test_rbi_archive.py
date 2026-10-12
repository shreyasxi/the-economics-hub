"""Archive browsing is read-only, complete and independent of paid scoring."""
import sqlite3
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from rbi_sentinel.archive import narrative_html
from rbi_sentinel.db.manager import get_summary_archive


def test_archive_filters_version_and_blank_summaries_without_writes(tmp_path):
    path = tmp_path / "archive.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE mpc_meetings (meeting_id INTEGER, policy_cycle TEXT,
                meeting_date TEXT, repo_rate_pct REAL, rate_action TEXT, rate_change_bps INTEGER);
            CREATE TABLE meeting_composites (meeting_id INTEGER, scoring_model_version TEXT,
                composite_narrative TEXT, computed_at TEXT, composite_overall_score REAL);
            CREATE TABLE rbi_documents (meeting_id INTEGER, doc_type TEXT, publication_date TEXT,
                source_url TEXT, raw_text TEXT, source_kind TEXT, word_count INTEGER);
            INSERT INTO mpc_meetings VALUES
                (1,'2025-12-05','2025-12-05',5.25,'cut',-25),
                (2,'2026-10-07','2026-10-07',5.50,'hike',25),
                (3,'2026-08-05','2026-08-05',5.25,'hold',0);
            INSERT INTO meeting_composites VALUES
                (1,'hybrid_v2','Earlier summary','2026-10-07 06:47:08',-.3),
                (2,'hybrid_v2','Latest summary','2026-10-07 06:47:08',.5),
                (2,'hybrid_v1','Old version','2026-09-12 12:00:00',.4),
                (3,'hybrid_v2','   ','2026-10-07 06:47:08',0);
        """)
    before = path.read_bytes()
    rows = get_summary_archive(db_path=path)
    assert [r["composite_narrative"] for r in rows] == ["Latest summary", "Earlier summary"]
    assert [r['composite_overall_score'] for r in rows] == [.5, -.3]
    assert path.read_bytes() == before
    assert not path.with_name(path.name + '-wal').exists()


def test_narrative_retains_paragraphs_and_escapes_html():
    result = narrative_html('**How to read this document:** First <script>bad()</script>.\n\n'
                            '**Practical takeaway:** Second **emphasis** & third.')
    assert result.count('<p>') == 2
    assert '<script>' not in result and '&lt;script&gt;' in result
    assert '<strong>emphasis</strong>' in result and '&amp; third.' in result


def test_browse_oldest_year_then_return_to_latest():
    app = AppTest.from_string('from rbi_sentinel.archive import render\nrender()').run()
    assert not app.exception
    assert app.selectbox[0].value == '2026'
    assert '7 October 2026' in app.markdown[-1].value
    app.selectbox[0].select('2016').run()
    assert not app.exception
    assert len(app.selectbox[1].options) == 2
    app.selectbox[1].select('2016-10-04').run()
    assert '4 October 2016' in app.markdown[-1].value
    app.selectbox[0].select('2026').run()
    assert '7 October 2026' in app.markdown[-1].value


def test_empty_and_unavailable_archive_are_graceful():
    with patch('rbi_sentinel.db.manager.get_summary_archive', return_value=[]):
        app = AppTest.from_string('from rbi_sentinel.archive import render\nrender()').run()
        assert not app.exception and app.info
    with patch('rbi_sentinel.db.manager.get_summary_archive', side_effect=sqlite3.OperationalError('offline')):
        app = AppTest.from_string('from rbi_sentinel.archive import render\nrender()').run()
        assert not app.exception and app.warning


def test_archive_metadata_coverage_and_rate_vote_semantics():
    rows = get_summary_archive()
    assert len(rows) >= 62
    assert all(r['stated_stance'] and r['voting_split'] and r['documents'] for r in rows)
    by_date = {r['policy_cycle']: r for r in rows}
    assert by_date['2026-10-07']['stated_stance'] == 'calibrated tightening'
    assert by_date['2026-10-07']['voting_split'] == '6–0'  # Stance dissent is separate.
    assert by_date['2025-06-06']['voting_split'] == '5–1'  # Both groups wanted cuts, of different sizes.
    assert by_date['2019-10-04']['voting_split'] == '5–1'  # Unanimous direction, split on size.
    assert by_date['2024-12-06']['voting_split'] == '4–2'
    assert by_date['2018-12-05']['voting_split'] == '6–0'  # Stance dissent alongside unanimous hold.
    assert by_date['2022-04-08']['stated_stance'] == 'accommodative while focusing on withdrawal of accommodation'


def test_stance_votes_alone_are_not_reported_as_rate_votes():
    from rbi_sentinel.cleaners.archive_facts import rate_vote, stated_stance
    assert rate_vote('Six members voted to continue with the neutral stance.', 'hold', 0) is None
    assert stated_stance('Dr. A voted to change the stance to neutral.') is None
