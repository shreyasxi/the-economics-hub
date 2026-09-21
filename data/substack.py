"""
Essays from the Substack newsletter, for the Analysis page's shelf.

Read when the page is opened (the app keeps a copy for a few hours). The
archive API lists every post with its word count; the RSS feed, which holds
only the latest twenty, is the fallback. When both fail nothing is made up:
the shelf says where the essays are instead.

Feed text is untrusted. The app escapes every title and keeps only http(s)
links; this module only reads and tidies.
"""

from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote, unquote

USER_AGENT = "Mozilla/5.0 (compatible; EconomicsHub/1.0; +https://shreyasxi.github.io/)"
WORDS_PER_MINUTE = 238
# The archive API returns fewer posts than asked for (23 when asked for 50, in
# Sep 2026), so it is read page after page until a page comes back empty.
ARCHIVE_PAGE = 25
ARCHIVE_MAX_PAGES = 12


def _get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _post(slug: str, title: str, subtitle: str, url: str, when: date,
          words: int | None, cover: str | None) -> dict:
    return {
        "slug": slug,
        "title": " ".join((title or "").split()),
        "subtitle": " ".join((subtitle or "").split()),
        "url": url,
        "date": when,
        "words": words,
        "cover": cover or None,
    }


def from_archive(rows: list[dict]) -> list[dict]:
    """Public newsletter posts from the archive API's JSON."""
    posts = []
    for row in rows:
        if row.get("type", "newsletter") != "newsletter" or row.get("audience", "everyone") != "everyone":
            continue
        posted = datetime.fromisoformat(row["post_date"].replace("Z", "+00:00")).date()
        posts.append(_post(row["slug"], row.get("title", ""), row.get("subtitle") or row.get("description", ""),
                           row["canonical_url"], posted, row.get("wordcount"), row.get("cover_image")))
    return posts


def from_rss(xml_bytes: bytes) -> list[dict]:
    """Posts from the RSS feed: no word counts, latest twenty only."""
    posts = []
    for item in ET.fromstring(xml_bytes).findall("./channel/item"):
        link = (item.findtext("link") or "").strip()
        enclosure = item.find("enclosure")
        posts.append(_post(link.rstrip("/").rsplit("/p/", 1)[-1], item.findtext("title", ""),
                           item.findtext("description", ""), link,
                           parsedate_to_datetime(item.findtext("pubDate")).date(), None,
                           enclosure.get("url") if enclosure is not None else None))
    return posts


def fetch_posts(base_url: str, timeout: float = 6.0) -> tuple[list[dict], str | None]:
    """(posts newest first, None), or ([], what went wrong)."""
    base = base_url.rstrip("/")
    problems = []
    try:
        rows: dict[str, dict] = {}
        for _ in range(ARCHIVE_MAX_PAGES):
            batch = json.loads(_get(f"{base}/api/v1/archive?sort=new&limit={ARCHIVE_PAGE}"
                                    f"&offset={len(rows)}", timeout))
            new = {row["slug"]: row for row in batch if row.get("slug") not in rows}
            if not new:
                break
            rows.update(new)
        posts = from_archive(list(rows.values()))
        if posts:
            return sorted(posts, key=lambda p: p["date"], reverse=True), None
        problems.append("the archive listed no posts")
    except Exception as exc:  # any failure falls through to the feed
        problems.append(f"archive: {exc}")
    try:
        posts = from_rss(_get(f"{base}/feed", timeout))
        if posts:
            return sorted(posts, key=lambda p: p["date"], reverse=True), None
        problems.append("the feed listed no posts")
    except Exception as exc:
        problems.append(f"feed: {exc}")
    return [], "; ".join(problems)


def shelf(posts: list[dict], pinned: list[str], today: date, new_for_days: int) -> list[dict]:
    """
    The pinned essays in the order given, led by the newest post for as long
    as it is recent. Once it is older than `new_for_days` it simply drops back
    (or out, if it was never pinned), so a quiet spell never shows as a gap.
    """
    by_slug = {p["slug"]: p for p in posts}
    cards = [dict(by_slug[slug], is_new=False) for slug in pinned if slug in by_slug]
    if posts:
        newest = max(posts, key=lambda p: p["date"])
        if (today - newest["date"]).days <= new_for_days:
            cards = [c for c in cards if c["slug"] != newest["slug"]]
            cards.insert(0, dict(newest, is_new=True))
    return cards


def reading_minutes(words: int | None) -> int | None:
    return max(1, round(words / WORDS_PER_MINUTE)) if words else None


def cover_url(url: str | None, width: int = 640) -> str | None:
    """
    A cover image through Substack's image CDN at card size: the originals run
    to several megabytes (one is 5,760 px wide). Links already on the CDN are
    re-sized the same way.
    """
    if not url or not url.startswith("https://"):
        return None
    marker = "/https%3A"
    if url.startswith("https://substackcdn.com/image/fetch/") and marker in url:
        url = unquote(url[url.index(marker) + 1:])
    return ("https://substackcdn.com/image/fetch/"
            f"w_{width},c_limit,f_auto,q_auto:good,fl_progressive:steep/{quote(url, safe='')}")
