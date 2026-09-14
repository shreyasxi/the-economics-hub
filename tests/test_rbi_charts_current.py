"""
RBI chart freshness test.

Exists because charts 05 and 06 were published in September 2026 without the
June and August 2026 holds: the rate data was seeded after the charts were
drawn, and nothing compared the two. Chart generation now stamps each
published folder with a fingerprint of the data it used; this test fails if
the database has changed since.

Fix a failure with:  python generate_rbi_sentinel.py --charts-only

Run:  python -m pytest tests/ -q      (or: python tests/test_rbi_charts_current.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rbi_sentinel.db.manager import chart_data_fingerprint
from rbi_sentinel.pipeline import FINGERPRINT_FILE, charts_are_current, latest_published_charts


def test_published_charts_have_a_fingerprint():
    folder = latest_published_charts()
    assert folder is not None, "No published RBI chart folder under assets/rbi_sentinel/"
    assert (folder / FINGERPRINT_FILE).exists(), (
        f"{folder} has no {FINGERPRINT_FILE}; regenerate with --charts-only"
    )


def test_published_charts_match_database():
    folder = latest_published_charts()
    stamp = (folder / FINGERPRINT_FILE).read_text().strip()
    assert charts_are_current(), (
        f"Charts in {folder} were drawn from different data "
        f"(stamp {stamp[:12]}, database {chart_data_fingerprint()[:12]}). "
        "Run: python generate_rbi_sentinel.py --charts-only"
    )


def test_exactly_the_current_charts_published():
    """All five current charts, and no retired one (06 was merged into 02 in Sep 2026)."""
    folder = latest_published_charts()
    expected = {
        "01_rbi_stance_meter.png", "02_rbi_sentiment_trajectory.png",
        "03_rbi_resolution_vs_minutes.png", "04_rbi_subdimension_radar.png",
        "05_rbi_rate_and_sentiment.png",
    }
    assert {p.name for p in folder.glob("*.png")} == expected


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
