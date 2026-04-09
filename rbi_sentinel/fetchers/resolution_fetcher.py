"""
rbi_sentinel/fetchers/resolution_fetcher.py

Discovers and fetches RBI MPC Policy Resolution documents from rbi.org.in.
"""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from rbi_sentinel.config import (
    DOC_RESOLUTION,
    FETCH_CACHED,
    FETCH_FAILED,
    FETCH_SUCCESS,
    RBI_BASE_URL,
    RBI_RESOLUTION_ARCHIVE,
    RESOLUTION_KEYWORDS,
)
from rbi_sentinel.fetchers.base_fetcher import BaseFetcher

log = logging.getLogger("rbi_sentinel.fetcher.resolution")

# Pattern to identify a monetary policy resolution link
_RESOLUTION_PATTERN = re.compile(
    r"(monetary policy statement|resolution of the monetary policy committee"
    r"|mpc resolution)",
    re.IGNORECASE,
)

# Date patterns in RBI press release titles: e.g. "October 4, 2016" or "04-10-2016"
_DATE_PATTERNS = [
    re.compile(r"(\w+ \d{1,2},?\s+\d{4})"),           # "October 4, 2016"
    re.compile(r"(\d{1,2}[- /]\w+[- /]\d{4})"),       # "04-Oct-2016"
    re.compile(r"(\d{4}-\d{2}-\d{2})"),                # "2016-10-04"
]


def _parse_rbi_date(text: str) -> Optional[str]:
    """Try to parse a date string from RBI text into YYYY-MM-DD format."""
    formats = [
        "%B %d, %Y", "%B %d %Y", "%d %B %Y",
        "%d-%b-%Y", "%d/%b/%Y", "%d %b %Y",
        "%Y-%m-%d",
    ]
    for pattern in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).strip().rstrip(",")
            for fmt in formats:
                try:
                    return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return None


class ResolutionFetcher(BaseFetcher):
    """Fetches MPC Policy Resolution HTML documents."""

    def __init__(self) -> None:
        super().__init__(doc_type=DOC_RESOLUTION, cache_subdir="resolution")

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_documents(self) -> list[dict]:
        """
        Scrape the RBI publications archive for Policy Resolution links.
        Returns a list of document info dicts.
        """
        log.info("Discovering resolution documents from RBI archive")
        try:
            resp = self._get(RBI_RESOLUTION_ARCHIVE)
        except Exception as exc:
            log.error("Failed to fetch resolution archive: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        documents = []

        # RBI archive pages list links in tables or definition lists
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if not _RESOLUTION_PATTERN.search(text):
                continue

            full_url = urljoin(RBI_BASE_URL, href)
            pub_date = _parse_rbi_date(text)

            # Try to extract date from surrounding context if not in link text
            if not pub_date:
                parent_text = ""
                if link.parent:
                    parent_text = link.parent.get_text(strip=True)
                pub_date = _parse_rbi_date(parent_text)

            if not pub_date:
                log.warning("Could not parse date from resolution link: %s", text)
                continue

            documents.append({
                "meeting_date": pub_date,     # Resolution date = meeting date
                "publication_date": pub_date,
                "url": full_url,
                "format": "html",
            })
            log.debug("Discovered resolution: %s at %s", pub_date, full_url)

        log.info("Discovered %d resolution documents", len(documents))
        return documents

    def discover_from_press_releases(self, year: Optional[int] = None) -> list[dict]:
        """
        Alternative discovery: search press releases page by keyword.
        Used as a fallback if the archive page changes structure.
        """
        from rbi_sentinel.config import RBI_PRESS_RELEASE_URL
        log.info("Discovering resolutions via press release search")
        documents = []

        # RBI press releases use prid= query params; we search by keyword
        search_url = f"{RBI_PRESS_RELEASE_URL}?prid="
        try:
            resp = self._get(RBI_PRESS_RELEASE_URL)
        except Exception as exc:
            log.error("Failed to fetch press release page: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            if not any(kw.lower() in text.lower() for kw in RESOLUTION_KEYWORDS):
                continue
            href = link["href"]
            full_url = urljoin(RBI_BASE_URL, href)
            pub_date = _parse_rbi_date(text)
            if not pub_date:
                continue
            documents.append({
                "meeting_date": pub_date,
                "publication_date": pub_date,
                "url": full_url,
                "format": "html",
            })

        return documents

    # ── Fetch & Cache ─────────────────────────────────────────────────────────

    def fetch_and_cache(self, doc_info: dict) -> tuple[bytes, str]:
        """
        Fetch the resolution HTML, cache it, return (raw_bytes, cache_path_str).
        Uses cache if already available.
        """
        meeting_date = doc_info["meeting_date"]
        url = doc_info["url"]

        if self._is_cached(meeting_date, "html"):
            log.info("Cache hit for resolution %s", meeting_date)
            raw = self._read_cache(meeting_date, "html")
            return raw, str(self._cache_path(meeting_date, "html"))

        log.info("Fetching resolution %s from %s", meeting_date, url)
        try:
            resp = self._get(url)
            raw = resp.content
            cache_path = self._write_cache(meeting_date, raw, "html")
            return raw, str(cache_path)
        except Exception as exc:
            log.error("Failed to fetch resolution %s: %s", meeting_date, exc)
            raise
