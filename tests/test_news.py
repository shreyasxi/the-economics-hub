"""
The Week in Headlines regression tests.

  * The Fed hike was split across the week's top five: outlets word one event
    differently, so each theme now shows one story, ranked by outlet count.
  * India's CPI story was dropped for having no "India" in its headline and,
    later, for coming from an outlet that had used its two slots.
  * Feeds arrive malformed (an unescaped '&') or with odd dates ('18:00:').
  * Bloomberg's feed holds about 15 hours of stories, so a Saturday read missed
    Monday's coverage: headlines are now pooled through the week.

No network: feeds and pages are canned strings.

Run:  python tests/test_news.py      (or: python -m pytest tests/test_news.py -q)
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.news_settings as cfg
import data.news as news

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _item(title: str, publisher: str, hours_ago: int = 5, url: str | None = None) -> dict:
    return {"title": title, "publisher": publisher, "published": NOW - timedelta(hours=hours_ago),
            "url": url or f"https://example.com/{publisher}/{abs(hash(title))}"}


def _select(items: list[dict], region: str = "world", **overrides) -> list[dict]:
    publishers = list(dict.fromkeys(p for p, _ in cfg.HEADLINE_FEEDS[region]))
    kwargs = dict(
        publishers=publishers, themes=cfg.HEADLINE_THEMES, exclude=cfg.HEADLINE_EXCLUDE,
        stopwords=cfg.STORY_STOPWORDS, synonyms=cfg.STORY_SYNONYMS, similarity=cfg.STORY_SIMILARITY,
        limit=cfg.HEADLINES_PER_REGION, per_publisher=cfg.MAX_PER_PUBLISHER,
        one_outlet_themes=cfg.ONE_OUTLET_THEMES, local=cfg.HEADLINE_LOCAL.get(region),
        explainers=cfg.HEADLINE_EXPLAINERS, min_words=cfg.MIN_HEADLINE_WORDS,
    )
    kwargs.update(overrides)
    return news.select_headlines(items, **kwargs)


# ── Feeds ───────────────────────────────────────────────────────────────────

def test_parse_feed_reads_malformed_rss_and_a_trailing_colon_in_the_date():
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Statement on Monetary Policy</title><link>https://www.boj.or.jp/a.pdf</link>
            <pubDate>Fri, 19 Sep 2026 12:00:00 +0900</pubDate></item>
      <item><title>Minutes of the Federal Open Market Committee, June 16-17, 2026</title>
            <link>https://www.federalreserve.gov/b.htm</link><pubDate>Wed, 8 Jul 2026 18:00:</pubDate></item>
      <item><title>Tankan & Outlook</title><link>https://www.boj.or.jp/c.htm</link></item>
    </channel></rss>"""
    items = news.parse_feed(rss)
    assert [i["title"] for i in items][:2] == ["Statement on Monetary Policy",
                                                "Minutes of the Federal Open Market Committee, June 16-17, 2026"]
    assert items[0]["published"] == datetime(2026, 9, 19, 3, 0, tzinfo=timezone.utc)
    assert items[1]["published"] == datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)


def test_parse_feed_reads_atom_and_rejects_an_html_page():
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Rates held</title>
      <link rel="alternate" href="https://example.com/held"/><updated>2026-09-17T11:00:00Z</updated></entry></feed>"""
    (entry,) = news.parse_feed(atom)
    assert entry["url"] == "https://example.com/held"
    assert entry["published"] == datetime(2026, 9, 17, 11, 0, tzinfo=timezone.utc)
    try:
        news.parse_feed(b"<!DOCTYPE html><html><body>Access denied</body></html>")
    except ValueError:
        pass
    else:
        raise AssertionError("an HTML error page was read as a feed")


def test_clean_text_decodes_double_escaping_and_drops_footnotes():
    assert news.clean_text("Auction for &amp;#8377;28,000 crore") == "Auction for ₹28,000 crore"
    assert news.clean_text("Next Decade<sup>1</sup> - Keynote Address -") == "Next Decade - Keynote Address"


# ── Headlines ───────────────────────────────────────────────────────────────

def test_theme_is_the_first_match_and_cooking_oil_is_not_energy():
    assert news.headline_theme("Fed hike lifts the dollar", cfg.HEADLINE_THEMES) == "Central banks"
    assert news.headline_theme("Brent crude slides", cfg.HEADLINE_THEMES) == "Energy & commodities"
    assert news.headline_theme("Cooking oil gets dearer", cfg.HEADLINE_THEMES) is None
    assert news.headline_theme("Onions and ginger: why food prices are rising", cfg.HEADLINE_THEMES) == "Inflation"


def test_exclusions_catch_live_blogs_questions_and_daily_market_reports():
    for title in ["UK economy grows – business live", "Will the BoE hike rates?",
                  "Sensex gains 282 pts; metal shares advance", "Rupee opens 3 paise lower at 96",
                  "Today’s Gold Rate in India September 17: prices down", "Five safe dividend stocks to beat inflation",
                  # Closing reports, previews and stock chatter (10-17 Sep 2026). Pooled over a week,
                  # they would look like stories that stayed in the news every day.
                  "Nifty holds above 23,250 mark; broader mkt outperforms",
                  "Barometers trade sideways; Nifty ends above 23,250",
                  "INR settles almost flat; Outflows of foreign funds keep rupee under pressure",
                  "Sensex today | Stock Market Highlights: Nifty, Sensex close flat as high crude price concerns offset",
                  "Stock Market prediction tomorrow: Sensex, Nifty outlook for Fri | Kospi, Nikkei cues to watch",
                  "Tata group stocks surge up to 14% as N Chandrasekaran gets 5-year extension",
                  "Gold, silver prices rise on bargain buying, dip in crude oil rates",
                  "Wall Street climbs as retreating oil prices boost investor sentiments"]:
        assert news.is_excluded(title, cfg.HEADLINE_EXCLUDE), title
    for title in ["Fed raises rates for the first time in three years", "RBI holds repo rate at 5.50%",
                  "Core inflation stays above 4.5% for a third month",
                  "Rupee falls 0.42% to 95.96, posts sharpest decline since July 14",
                  "US borrowing costs hit 5% for first time since 2023 amid bond sell-off",
                  "Oil prices fall as Saudi Arabia reportedly offers more crude via Hormuz after pipeline attack"]:
        assert not news.is_excluded(title, cfg.HEADLINE_EXCLUDE), title


def test_one_event_takes_one_slot_and_coverage_ranks_first():
    items = [
        _item("Fed raises interest rates for first time in three years", "BBC News"),
        _item("Federal Reserve raises rates, defying Trump", "Financial Times"),
        _item("Fed hikes rates for first time since 2023, defying Trump", "Bloomberg"),
        _item("A stronger dollar: how the Fed's rate hike hits global markets", "CNBC"),
        _item("UK inflation jumps to 3.1% in August", "CNBC", 20),
        _item("UK inflation rose to 3.1% in August", "Financial Times", 22),
        _item("Precision Wires begins trial production of copper cathodes", "Bloomberg"),
    ]
    picks = _select(items)
    assert [p["theme"] for p in picks] == ["Central banks", "Inflation"], picks
    assert len({p["theme"] for p in picks}) == len(picks)
    assert picks[0]["publisher"] == "BBC News"          # free-to-read outlet preferred for the headline
    assert set(picks[0]["also"]) == {"CNBC", "Financial Times", "Bloomberg"}   # the dollar angle joined the Fed story


def test_at_equal_coverage_the_story_that_stayed_in_the_news_longer_ranks_first():
    items = [
        _item("UK inflation rose to 3.1% in August", "Financial Times", 30),
        _item("UK inflation jumps to 3.1% as energy costs soar", "CNBC", 28),
        _item("US House passes Russia sanctions bill with 100% tariff threat", "Bloomberg", 100),
        _item("Russia sanctions bill: tariff threat hangs over importers", "BBC News", 50),
        _item("Senate takes up Russia sanctions bill and its tariff threat", "Bloomberg", 3),
    ]
    picks = _select(items)
    # Both carried by two outlets: the three-day story outranks the higher-priority theme's one-day story.
    assert [(p["theme"], p["days"]) for p in picks] == [("Trade & tariffs", 3), ("Inflation", 1)], picks


def test_a_story_is_shown_by_a_plain_report_not_an_explainer_or_a_title_too_short_to_say_what_happened():
    items = [
        _item("Why Trump's hand-picked Fed chair defied him by raising interest rates", "BBC News", 20),
        _item("Fed defies Trump with first rate rise since 2023", "Financial Times", 22),
        _item("Getting to know Mr Warsh", "Financial Times", 21),
        _item("Here are five key takeaways from Wednesday's Fed rate hike", "CNBC", 23),
    ]
    (fed,) = _select(items)
    assert fed["title"] == "Fed defies Trump with first rate rise since 2023", fed
    assert set(fed["also"]) == {"BBC News", "CNBC"}, "explainers still count as coverage"


def test_india_keeps_domestic_stories_and_drops_foreign_ones_without_an_india_angle():
    items = [
        _item("Retail inflation rises to 4.82% in August as food inflation climbs", "Business Standard", 70),
        _item("US Fed raises interest rates as Warsh bucks Trump", "Mint"),
        _item("Chinese oil prices hit record highs after attacks on Saudi pipeline", "Mint"),
        _item("Brent oil prices climb after Saudi pipeline attacks", "BusinessLine"),
    ]
    picks = _select(items, "india")
    assert [p["title"] for p in picks] == ["Retail inflation rises to 4.82% in August as food inflation climbs"]

    items.append(_item("Fed raises interest rates: what the hike means for FII flows into India", "BusinessLine"))
    picks = _select(items, "india")
    fed = next(p for p in picks if p["theme"] == "Central banks")
    assert "FII" in fed["title"], "the headline with an India angle should represent the story"


def test_an_outlet_at_its_cap_never_drops_a_story():
    items = [
        _item("RBI keeps repo rate unchanged at 5.50%", "Business Standard", 3),
        _item("Retail inflation rises to 4.82% in August", "Business Standard", 70),
        _item("India's exports to US rise 21.83% in August", "Business Standard", 50),
    ]
    picks = _select(items, "india")
    assert len(picks) == 3 and {p["publisher"] for p in picks} == {"Business Standard"}


def test_headlines_column_is_left_out_when_too_few_and_failed_outlets_are_named():
    def fake_fetch(url):
        if "bbc" in url:
            raise ConnectionError("down")
        return [{"title": "Fed raises interest rates", "url": url + "/a", "published": NOW - timedelta(hours=2)}]

    real, news.fetch_feed = news.fetch_feed, fake_fetch
    try:
        c = news._Collector()
        out, answered = news._headlines(cfg, c, "world", NOW - timedelta(days=7), NOW, stored=[])
    finally:
        news.fetch_feed = real
    assert answered
    assert out["items"] == [], "one story is below MIN_HEADLINES, so the column must be left out"
    assert out["unavailable"] == ["BBC News"]
    assert any("BBC News feed" in p for p in c.problems)
    assert any("column is left out" in p for p in c.problems)


def test_headlines_go_into_the_newest_edition_that_has_charts():
    """A folder holding only news.json would become the 'newest edition' and hide every Weekly chart."""
    import tempfile
    from generate_news import latest_edition

    with tempfile.TemporaryDirectory() as tmp:
        weekly = Path(tmp)
        assert latest_edition(weekly) is None
        for name, files in (("2026-09-13", ["00_summary_table.png"]), ("2026-09-19", ["01_equities_weekly.png"]),
                            ("2026-09-20", ["news.json"])):
            (weekly / name).mkdir()
            for f in files:
                (weekly / name / f).write_bytes(b"")
        assert latest_edition(weekly).name == "2026-09-19"


# ── The week's pool ────────────────────────────────────────────────────────

def _down(url):
    raise ConnectionError("down")


def test_the_pool_keeps_each_article_once_as_last_seen_and_forgets_it_after_eight_days():
    start = NOW - timedelta(days=cfg.POOL_KEEP_DAYS)
    stored = [_item("Fed holds rates", "Bloomberg", 24 * 9, url="https://www.bloomberg.com/news/old"),
              _item("Fed set to raise rates", "Bloomberg", 30, url="https://www.bloomberg.com/news/fed")]
    fresh = [_item("Fed raises rates for the first time since 2023", "Bloomberg", 30,
                   url="https://www.bloomberg.com/news/fed?srnd=economics"),         # the same article, retitled
             _item("UK inflation rose to 3.1% in August", "Financial Times", 2, url="https://www.ft.com/content/cpi")]
    merged = news.merge_pool(stored, fresh, start=start, end=NOW, cap=10)
    assert [m["title"] for m in merged] == ["UK inflation rose to 3.1% in August",
                                            "Fed raises rates for the first time since 2023"]
    assert [m["title"] for m in news.merge_pool(stored, fresh, start=start, end=NOW, cap=1)] == \
        ["UK inflation rose to 3.1% in August"]


def test_the_pool_round_trips_through_json_in_the_publishers_time_zone_and_rejects_anything_else():
    ist = timezone(timedelta(hours=5, minutes=30))
    pool = {"reads": [NOW], "headlines": {"india": [
        {"title": "RBI keeps repo rate unchanged", "url": "https://www.livemint.com/a", "publisher": "Mint",
         "published": datetime(2026, 9, 17, 1, 30, tzinfo=ist)}]}}
    back = news.pool_from_json(json.loads(json.dumps(news.pool_to_json(pool))))
    assert back == pool
    assert back["headlines"]["india"][0]["published"].date() == date(2026, 9, 17)   # Mint's day, not UTC's 16th
    for bad in ([], {"version": 0}, {"version": news.POOL_VERSION, "reads": ["yesterday"], "headlines": {}},
                {"version": news.POOL_VERSION, "reads": [], "headlines": {"world": [{"title": "x"}]}}):
        try:
            news.pool_from_json(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_collecting_keeps_only_choosable_headlines_and_a_read_nobody_answered_is_not_counted():
    def fake_fetch(url):
        if "bbc" not in url:
            raise ConnectionError("down")
        return [{"title": "Fed raises rates", "url": "https://www.bbc.co.uk/news/fed", "published": NOW - timedelta(hours=2)},
                {"title": "Five safe dividend stocks to beat inflation", "url": "https://www.bbc.co.uk/news/tips",
                 "published": NOW - timedelta(hours=2)},                                          # excluded
                {"title": "Royal Mail stamps go up again", "url": "https://www.bbc.co.uk/news/stamps",
                 "published": NOW - timedelta(hours=2)},                                          # no theme
                {"title": "Oil jumps", "url": "javascript:alert(1)", "published": NOW - timedelta(hours=2)},
                {"title": "Fed holds rates", "url": "https://www.bbc.co.uk/news/old", "published": NOW - timedelta(days=9)}]

    real, news.fetch_feed = news.fetch_feed, fake_fetch
    try:
        pool, added, _ = news.collect_headlines(cfg, None, now=NOW)
        assert [i["title"] for i in pool["headlines"]["world"]] == ["Fed raises rates"]
        assert added == {"world": 1, "india": None} and pool["reads"] == [NOW]

        again, added, _ = news.collect_headlines(cfg, pool, now=NOW + timedelta(hours=4))
        assert added["world"] == 0 and len(again["headlines"]["world"]) == 1 and len(again["reads"]) == 2

        news.fetch_feed = _down
        same, added, problems = news.collect_headlines(cfg, again, now=NOW + timedelta(hours=8))
        assert added == {"world": None, "india": None} and same["reads"] == again["reads"] and problems
        assert same["headlines"]["world"] == again["headlines"]["world"]
    finally:
        news.fetch_feed = real


def test_the_week_is_ranked_from_the_pool_and_a_saturday_read_together():
    """Bloomberg and the FT no longer hold these stories on Saturday; the pool still counts them."""
    pool = {"reads": [NOW - timedelta(hours=80), NOW - timedelta(hours=8)], "headlines": {"world": [
        _item("Fed raises interest rates for first time in three years", "Bloomberg", 70, url="https://www.bloomberg.com/fed"),
        _item("UK inflation rose to 3.1% in August", "Financial Times", 50, url="https://www.ft.com/uk-cpi"),
    ]}}

    def fake_fetch(url):
        def it(title, path, hours):
            return {"title": title, "url": f"https://{url.split('/')[2]}/{path}", "published": NOW - timedelta(hours=hours)}
        if "bbc" in url:
            return [it("Fed raises rates, defying Trump", "fed", 60), it("UK inflation jumps to 3.1% in August", "cpi", 40),
                    it("Oil prices surge after Saudi pipeline attacks", "oil", 5)]
        if "cnbc" in url:
            return [it("Brent crude jumps as Saudi pipeline is attacked", "oil", 4)]
        raise ConnectionError("down")

    real, news.fetch_feed = news.fetch_feed, fake_fetch
    try:
        out, _ = news.build_news(cfg, now=NOW, pool=pool)
    finally:
        news.fetch_feed = real
    world = out["headlines"]["world"]
    assert [(i["theme"], {i["publisher"], *i["also"]}, i["days"]) for i in world["items"]] == [
        ("Central banks", {"BBC News", "Bloomberg"}, 2),
        ("Inflation", {"BBC News", "Financial Times"}, 1),
        ("Energy & commodities", {"BBC News", "CNBC"}, 1),
    ]
    assert world["publishers"] == ["BBC News", "CNBC", "Financial Times", "Bloomberg"]
    assert world["unavailable"] == ["The Guardian"]
    assert out["reads"] == {"count": 3, "first": "2026-09-14 04:00 UTC"}


def test_an_unreadable_pool_is_set_aside_not_a_crash():
    import tempfile
    from generate_news import load_pool, save_pool

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "headline_pool" / "pool.json"
        assert load_pool(path) == (None, None)
        pool = {"reads": [NOW], "headlines": {"world": []}}
        save_pool(pool, path)
        assert load_pool(path) == (pool, None)
        path.write_text('{"version": 1, "reads": [')          # a copy cut short
        broken, reason = load_pool(path)
        assert broken is None and "could not be read" in reason


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  PASS  {name}"); passed += 1
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}"); failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
