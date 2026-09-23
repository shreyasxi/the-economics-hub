"""
Analysis page: the essay shelf, the Substack readers, and the hand-written config.

The shelf must never show a gap: pinned essays in the owner's order, led by a
new post only while it is recent. The config checks catch a thread chart that
was renamed away, a saved image that is missing, or a link that is not a link.

Run:  python tests/test_analysis.py      (or: python -m pytest tests/test_analysis.py -q)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.analysis as analysis
import config.resources as resources
from charts.loader import chart_key, get_charts
from data.substack import cover_url, from_archive, from_rss, reading_minutes, shelf

ROOT = Path(__file__).resolve().parent.parent


def _post(slug: str, when: date) -> dict:
    return {"slug": slug, "title": slug.title(), "subtitle": "", "url": f"https://x.substack.com/p/{slug}",
            "date": when, "words": 1000, "cover": None}


POSTS = [_post("newest", date(2026, 9, 1)), _post("b", date(2026, 3, 1)), _post("a", date(2026, 2, 1))]


def test_shelf_keeps_the_pinned_order():
    cards = shelf(POSTS, ["a", "b"], today=date(2026, 12, 1), new_for_days=30)
    assert [c["slug"] for c in cards] == ["a", "b"]
    assert not any(c["is_new"] for c in cards)


def test_a_new_post_leads_while_it_is_recent():
    cards = shelf(POSTS, ["a", "b"], today=date(2026, 9, 20), new_for_days=30)
    assert [c["slug"] for c in cards] == ["newest", "a", "b"]
    assert cards[0]["is_new"]


def test_a_new_post_that_is_pinned_moves_up_once():
    cards = shelf(POSTS, ["a", "newest", "b"], today=date(2026, 9, 20), new_for_days=30)
    assert [c["slug"] for c in cards] == ["newest", "a", "b"]


def test_a_pinned_slug_that_does_not_exist_is_skipped():
    assert [c["slug"] for c in shelf(POSTS, ["gone", "b"], date(2026, 12, 1), 30)] == ["b"]


def test_no_posts_means_no_cards():
    assert shelf([], ["a"], date(2026, 12, 1), 30) == []


def test_archive_rows_keep_public_newsletters_only():
    rows = [
        {"slug": "p", "title": " A  title ", "subtitle": "Sub", "post_date": "2026-03-10T16:13:16.179Z",
         "canonical_url": "https://x.substack.com/p/p", "wordcount": 5296, "cover_image": None,
         "type": "newsletter", "audience": "everyone"},
        {"slug": "paid", "title": "Paid", "post_date": "2026-03-11T00:00:00Z", "canonical_url": "u",
         "type": "newsletter", "audience": "only_paid"},
        {"slug": "pod", "title": "Pod", "post_date": "2026-03-12T00:00:00Z", "canonical_url": "u",
         "type": "podcast", "audience": "everyone"},
    ]
    posts = from_archive(rows)
    assert [p["slug"] for p in posts] == ["p"]
    assert posts[0]["title"] == "A title" and posts[0]["date"] == date(2026, 3, 10) and posts[0]["words"] == 5296


def test_the_feed_is_read_when_the_archive_is_not():
    xml = b"""<?xml version="1.0"?><rss><channel>
      <item><title>Iran War is More Than Just Oil </title>
        <link>https://economicshub.substack.com/p/iran-war-is-more-than-just-oil</link>
        <description>Second-order shocks</description><pubDate>Tue, 10 Mar 2026 16:13:16 GMT</pubDate>
        <enclosure url="https://substack-post-media.s3.amazonaws.com/public/images/a.jpeg" type="image/jpeg"/></item>
    </channel></rss>"""
    [post] = from_rss(xml)
    assert post["slug"] == "iran-war-is-more-than-just-oil"
    assert post["date"] == date(2026, 3, 10) and post["words"] is None
    assert post["cover"].endswith("a.jpeg")


def test_covers_are_fetched_at_card_size():
    s3 = "https://substack-post-media.s3.amazonaws.com/public/images/big_5760x3840.jpeg"
    assert cover_url(s3).startswith("https://substackcdn.com/image/fetch/w_640,")
    assert cover_url(s3).endswith("https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fbig_5760x3840.jpeg")
    cdn = "https://substackcdn.com/image/fetch/$s_!f8Wb!,f_auto,q_auto:good/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fx.png"
    assert cover_url(cdn) == cover_url("https://substack-post-media.s3.amazonaws.com/x.png")
    assert cover_url(None) is None and cover_url("http://insecure/x.png") is None


def test_reading_time():
    assert reading_minutes(5296) == 22 and reading_minutes(100) == 1 and reading_minutes(None) is None


THREAD_KEYS = {"theme", "why", "charts", "links"}
DASHBOARD_CHART_KEYS = {"dashboard", "note"}
SAVED_CHART_KEYS = {"image", "title", "source", "note"}      # the source is named, not linked
LINK_KEYS = {"title", "source", "url", "date", "note", "paywall", "mine"}


def test_every_thread_is_complete():
    assert analysis.WATCHING, "no threads"
    for thread in analysis.WATCHING:
        assert thread.get("theme"), f"a thread has no theme: {thread}"
        # A misspelt field ("paywal", "tittle") is not an error in Python; the
        # page would just leave it out. Name it here instead.
        assert set(thread) <= THREAD_KEYS, f"{thread['theme']}: unknown field {sorted(set(thread) - THREAD_KEYS)}"
        for chart in thread.get("charts", []):
            allowed = DASHBOARD_CHART_KEYS if "dashboard" in chart else SAVED_CHART_KEYS
            assert set(chart) <= allowed, f"{thread['theme']}: unknown chart field {sorted(set(chart) - allowed)}"
            if "dashboard" in chart:
                continue
            assert (ROOT / "assets" / chart["image"]).exists(), f"missing saved chart: {chart['image']}"
            assert chart.get("source"), f"{thread['theme']}: a saved chart names no source: {chart['image']}"
        for link in thread.get("links", []):
            assert set(link) <= LINK_KEYS, f"{thread['theme']}: unknown link field {sorted(set(link) - LINK_KEYS)}"
            assert link["url"].startswith("https://"), link
            assert link["title"] and link["source"], link
            date.fromisoformat(link["date"])


def test_thread_dashboard_charts_exist():
    """Fails when a chart a thread borrows is renamed or dropped by its generator."""
    keys = set()
    for subdir in ("weekly", "macro", "india"):
        charts, _ = get_charts(subdir)
        keys |= {chart_key(c.name) for c in charts}
    if not keys:
        return   # nothing generated on this machine
    wanted = {c["dashboard"] for t in analysis.WATCHING for c in t.get("charts", []) if "dashboard" in c}
    assert wanted <= keys, f"thread charts not on the dashboard: {sorted(wanted - keys)}"


def test_pinned_essays_are_slugs():
    for slug in analysis.PINNED:
        assert slug == slug.strip().lower() and "/" not in slug and " " not in slug, slug


def test_footer_links_are_links():
    assert resources.FOOTER_COLUMNS
    for title, items in resources.FOOTER_COLUMNS:
        assert items, title
        for label, href in items:
            assert label and (href.startswith("/") or href.startswith("https://") or href.startswith("mailto:")), href


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  PASS  {name}"); passed += 1
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}"); failed += 1
            except Exception as e:     # a missing field is a KeyError: report it, don't stop
                print(f"  FAIL  {name}: {type(e).__name__} {e}"); failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
