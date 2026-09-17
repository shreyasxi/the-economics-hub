"""
News strip: The Week in Headlines (Weekly Markets tab).

generate_news.py writes news.json into each weekly edition folder; the weekly
workflow runs it after the charts and publishes it with them.

The pipeline selects, it never writes: every line on the page is a publisher's
own headline, linked to the original.

Unlike chart data, news is optional (agreed Sep 2026): a feed that fails is
skipped and reported as a warning, and a column with too little left is dropped
from the page. Nothing is ever filled in.

The pure helpers are covered by tests/test_news.py.
"""

from __future__ import annotations

import html
import math
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from lxml import etree

from config.news_settings import BROWSER_UA_HOSTS

PIPELINE_UA = {"User-Agent": "Mozilla/5.0 (EconomicsHub data pipeline; +https://github.com/shreyasxi/the-economics-hub)"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


# ═══════════════════════════════════════════════
# PURE HELPERS — feeds
# ═══════════════════════════════════════════════

def clean_text(s: str | None) -> str:
    """Feed text as plain words: entities decoded (some feeds escape them twice), tags and footnote marks removed."""
    s = html.unescape(html.unescape(s or ""))
    s = re.sub(r"(?is)<sup\b.*?</sup>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s*[-–|:]$", "", s).strip()


def parse_date(text: str | None) -> datetime | None:
    """RFC 822 or ISO 8601 feed date as an aware datetime (UTC when the feed gives no zone)."""
    text = (text or "").strip().rstrip(":")      # some feeds end the time with a stray ':'
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _child_text(el, name: str) -> str:
    for child in el:
        if _local(child) == name:
            return "".join(child.itertext())
    return ""


def parse_feed(content: bytes) -> list[dict]:
    """
    Items of an RSS 2.0 or Atom feed as {'title', 'url', 'published'}. Malformed
    XML (an unescaped '&' in a title) is read as far as it parses; a page that is
    not a feed at all, such as an error page, raises ValueError.
    """
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    root = etree.fromstring(content, parser)
    if root is None or _local(root) not in ("rss", "feed", "RDF"):
        raise ValueError("not an RSS or Atom feed")
    items = []
    for el in root.iter():
        if _local(el) not in ("item", "entry"):
            continue
        url = _child_text(el, "link").strip()
        if not url:
            links = [c for c in el if _local(c) == "link" and c.get("rel", "alternate") == "alternate"]
            url = links[0].get("href", "") if links else ""
        published = None
        for name in ("pubDate", "date", "published", "updated"):
            published = parse_date(_child_text(el, name))
            if published:
                break
        items.append({"title": clean_text(_child_text(el, "title")), "url": url.strip(), "published": published})
    return items


def in_window(published: datetime | None, start: datetime, end: datetime) -> bool:
    return published is not None and start <= published <= end + timedelta(hours=1)


# ═══════════════════════════════════════════════
# PURE HELPERS — headlines
# ═══════════════════════════════════════════════

def headline_theme(title: str, themes: list[tuple[str, list[str]]]) -> str | None:
    """The first theme whose patterns the headline matches; None when it matches none."""
    t = title.replace("’", "'")
    for name, patterns in themes:
        if any(re.search(p, t, flags=re.I) for p in patterns):
            return name
    return None


def is_excluded(title: str, patterns: list[str]) -> bool:
    t = title.replace("’", "'")
    return any(re.search(p, t, flags=re.I) for p in patterns)


def story_tokens(title: str, stopwords: set[str], synonyms: list[tuple[str, str]] = ()) -> list[str]:
    """
    Words that identify a story: synonyms unified, crude singular, stopwords
    dropped, numbers kept ('3.1%'). Word pairs were tried and made matching
    worse: most pairs are unique, which dilutes the similarity of paraphrases.
    """
    t = title.lower().replace("’", "'")
    for pattern, word in synonyms:
        t = re.sub(pattern, word, t)
    words = []
    for w in re.findall(r"[a-z0-9][a-z0-9.%&'-]*", t):
        w = w.strip(".'-")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if w and w not in stopwords and (len(w) > 2 or w[0].isdigit()):
            words.append(w)
    return words


def _normalise(v: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {t: x / norm for t, x in v.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def cluster_stories(token_lists: list[list[str]], threshold: float,
                    labels: list[str] | None = None) -> list[list[tuple[int, float]]]:
    """
    Headlines grouped into stories, each as [(index, centrality)] with the most
    typical headline first. Similarity is TF-IDF cosine, so rare shared words
    ('3.1%', 'Warsh') count for more than common ones ('rate'). A headline joins
    the story whose centroid it is closest to, if close enough, which stops
    'Fed hikes' and 'Czechs hold rates' chaining together through 'rate'. With
    `labels`, headlines only join stories with the same label (their theme).
    """
    n = len(token_lists)
    df = Counter(t for toks in token_lists for t in set(toks))
    vectors = [_normalise({t: c * (math.log((1 + n) / (1 + df[t])) + 1) for t, c in Counter(toks).items()})
               for toks in token_lists]

    stories: list[dict] = []
    for i, v in enumerate(vectors):
        best, best_sim = None, 0.0
        for s in stories:
            if labels and labels[s["members"][0]] != labels[i]:
                continue
            sim = _cosine(v, s["centroid"])
            if sim > best_sim:
                best, best_sim = s, sim
        if best is not None and best_sim >= threshold:
            best["members"].append(i)
            for t, x in v.items():
                best["sum"][t] = best["sum"].get(t, 0.0) + x
            best["centroid"] = _normalise(best["sum"])
        else:
            stories.append({"members": [i], "sum": dict(v), "centroid": v})

    return [sorted(((i, _cosine(vectors[i], s["centroid"])) for i in s["members"]), key=lambda m: -m[1])
            for s in stories]


def is_foreign_story(titles: list[str], local: dict[str, list[str]] | None) -> bool:
    """True when a story names a foreign actor and none of its headlines has a local angle."""
    if not local:
        return False

    def mentions(patterns: list[str]) -> bool:
        return any(re.search(p, t, flags=re.I) for t in titles for p in patterns)

    return mentions(local["foreign"]) and not mentions(local["local"])


def lacks_local_angle(title: str, local: dict[str, list[str]] | None) -> bool:
    """A headline about a foreign actor with nothing local in it ('US Fed raises rates' in the India column)."""
    return bool(local) and is_foreign_story([title], local)


def select_headlines(items: list[dict], *, publishers: list[str], themes: list[tuple[str, list[str]]],
                     exclude: list[str], stopwords: set[str], synonyms: list[tuple[str, str]],
                     similarity: float, limit: int, per_publisher: int,
                     one_outlet_themes: set[str] | None = None,
                     local: dict[str, list[str]] | None = None) -> list[dict]:
    """
    The week's top stories from dated feed items ({'title', 'url', 'publisher', 'published'}).

    Headlines are sorted into themes and, within a theme, into stories. A story
    counts once however many outlets ran it and ranks by how many did, then by
    its theme's priority (the order of `themes`), then by how many headlines it
    drew, then by recency. Each theme offers its top story and the column takes
    the best `limit` of those, so one event cannot fill it. A story only one
    outlet carried qualifies only in `one_outlet_themes` (all themes if None).
    With `local`, foreign stories without a local angle are dropped first.

    A story's headline is its most typical one, or a close runner-up from a
    publisher listed earlier in `publishers` (free-to-read outlets). Once an
    outlet has `per_publisher` headlines in the column, another outlet's
    headline for the story is used if there is one; the story itself is never
    dropped for that. With `local`, a headline with a local angle is preferred.
    """
    seen, pool = set(), []
    for it in sorted(items, key=lambda i: i["published"], reverse=True):
        key = (it["url"].split("?")[0], it["title"].lower())
        if not it["title"] or key[0] in seen or key[1] in seen:
            continue
        seen.update(key)
        theme = headline_theme(it["title"], themes)
        if theme and not is_excluded(it["title"], exclude):
            pool.append({**it, "theme": theme})
    if not pool:
        return []

    rank = {p: i for i, p in enumerate(publishers)}
    stories = []
    tokens = [story_tokens(p["title"], stopwords, synonyms) for p in pool]
    for members in cluster_stories(tokens, similarity, labels=[p["theme"] for p in pool]):
        top = members[0][1]
        ordered = sorted(members, key=lambda m: (lacks_local_angle(pool[m[0]]["title"], local), m[1] < top - 0.1,
                                                 rank.get(pool[m[0]]["publisher"], 99), -m[1]))
        group = [pool[i] for i, _ in ordered]
        if is_foreign_story([g["title"] for g in group], local):
            continue
        stories.append({
            "items": group, "theme": group[0]["theme"],
            "outlets": sorted({g["publisher"] for g in group}, key=lambda p: rank.get(p, 99)),
            "latest": max(g["published"] for g in group),
        })
    priority = {name: i for i, (name, _) in enumerate(themes)}
    stories.sort(key=lambda s: (-len(s["outlets"]), priority[s["theme"]], -len(s["items"]), -s["latest"].timestamp()))

    chosen, themes_used, per = [], set(), Counter()
    for s in stories:
        if s["theme"] in themes_used:
            continue
        if len(s["outlets"]) < 2 and one_outlet_themes is not None and s["theme"] not in one_outlet_themes:
            continue
        pick = next((g for g in s["items"] if per[g["publisher"]] < per_publisher), s["items"][0])
        per[pick["publisher"]] += 1
        themes_used.add(s["theme"])
        chosen.append({
            "title": pick["title"], "url": pick["url"], "publisher": pick["publisher"],
            "date": pick["published"].date().isoformat(), "theme": s["theme"],
            "also": [o for o in s["outlets"] if o != pick["publisher"]],
        })
        if len(chosen) == limit:
            break
    return chosen


# ═══════════════════════════════════════════════
# FETCHERS — each raises on failure
# ═══════════════════════════════════════════════

def _get(url: str, attempts: int = 3) -> requests.Response:
    headers = BROWSER_UA if urlparse(url).hostname in BROWSER_UA_HOSTS else PIPELINE_UA
    for attempt in range(attempts):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == attempts - 1:
                raise
            time.sleep(3 * (attempt + 1))


def fetch_feed(url: str, attempts: int = 2) -> list[dict]:
    """A feed's items. A reply that is not a feed (an error page served with 200) is retried once."""
    for attempt in range(attempts):
        try:
            items = parse_feed(_get(url).content)
            if not items:
                raise ValueError("feed has no items")
            return items
        except ValueError:
            if attempt == attempts - 1:
                raise
            time.sleep(5)


# ═══════════════════════════════════════════════
# BUILD
# ═══════════════════════════════════════════════

class _Collector:
    """Runs fetches, keeping going after a failure but remembering it."""

    def __init__(self):
        self.problems: list[str] = []

    def run(self, label: str, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001 — every failure is reported, none hidden
            self.problems.append(f"{label}: {type(exc).__name__}: {str(exc)[:200]}")
            return None


def _headlines(cfg, c: _Collector, region: str, start: datetime, end: datetime) -> dict:
    feeds = cfg.HEADLINE_FEEDS[region]
    publishers = list(dict.fromkeys(p for p, _ in feeds))
    # Feeds are read in parallel, so one slow site costs its own timeout, not everyone's.
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(lambda f: c.run(f"{f[0]} feed ({f[1]})", fetch_feed, f[1]), feeds))
    items, failed = [], []
    for (publisher, _), got in zip(feeds, fetched):
        if got is None:
            failed.append(publisher)
            continue
        items += [{**it, "publisher": publisher} for it in got if in_window(it["published"], start, end)]
    working = [p for p in publishers if any(it["publisher"] == p for it in items)]
    chosen = select_headlines(
        items, publishers=publishers, themes=cfg.HEADLINE_THEMES, exclude=cfg.HEADLINE_EXCLUDE,
        stopwords=cfg.STORY_STOPWORDS, synonyms=cfg.STORY_SYNONYMS, similarity=cfg.STORY_SIMILARITY,
        limit=cfg.HEADLINES_PER_REGION, per_publisher=cfg.MAX_PER_PUBLISHER,
        one_outlet_themes=cfg.ONE_OUTLET_THEMES, local=cfg.HEADLINE_LOCAL.get(region),
    )
    if len(chosen) < cfg.MIN_HEADLINES:
        c.problems.append(f"{region.title()} headlines: only {len(chosen)} found, so the column is left out")
        chosen = []
    return {"items": chosen, "publishers": working,
            "unavailable": sorted({p for p in failed if p not in working})}


def build_news(cfg, now: datetime | None = None) -> tuple[dict, list[str]]:
    """(news.json content, problems). Problems are warnings: the strip is built from whatever worked."""
    now = now or datetime.now(timezone.utc)
    c = _Collector()
    start = now - timedelta(days=cfg.HEADLINE_WINDOW_DAYS)
    news = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "headlines": {
            "from": start.date().isoformat(), "to": now.date().isoformat(),
            **{region: _headlines(cfg, c, region, start, now) for region in cfg.HEADLINE_FEEDS},
        },
    }
    news["problems"] = c.problems
    return news, c.problems
