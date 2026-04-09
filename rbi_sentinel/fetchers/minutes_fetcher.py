"""
rbi_sentinel/fetchers/minutes_fetcher.py

Discovers and fetches MPC Minutes documents from rbi.org.in.
Minutes are published ~14 days after each MPC meeting.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from rbi_sentinel.config import (
    DOC_MINUTES,
    MINUTES_KEYWORDS,
    MINUTES_LAG_DAYS,
    RBI_BASE_URL,
    RBI_MINUTES_ARCHIVE,
)
from rbi_sentinel.fetchers.base_fetcher import BaseFetcher

log = logging.getLogger("rbi_sentinel.fetcher.minutes")

_MINUTES_PATTERN = re.compile(
    r"(minutes of the monetary policy committee|mpc minutes)",
    re.IGNORECASE,
)

_DATE_PATTERNS = [
    re.compile(r"(\w+ \d{1,2},?\s+\d{4})"),
    re.compile(r"(\d{1,2}[- /]\w+[- /]\d{4})"),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
]


def _parse_rbi_date(text: str) -> Optional[str]:
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


def _estimate_meeting_date_from_minutes_date(minutes_date: str) -> str:
    """
    Minutes are published ~14 days after the meeting.
    Estimate the meeting date by subtracting MINUTES_LAG_DAYS.
    This is approximate — the actual meeting date should be updated from mpc_meetings table.
    """
    d = datetime.strptime(minutes_date, "%Y-%m-%d")
    estimated = d - timedelta(days=MINUTES_LAG_DAYS)
    return estimated.strftime("%Y-%m-%d")


class MinutesFetcher(BaseFetcher):
    """Fetches MPC Minutes HTML documents."""

    def __init__(self) -> None:
        super().__init__(doc_type=DOC_MINUTES, cache_subdir="minutes")

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_documents(self) -> list[dict]:
        """Scrape the RBI minutes archive for all available minutes links."""
        log.info("Discovering MPC minutes documents from RBI archive")
        try:
            resp = self._get(RBI_MINUTES_ARCHIVE)
        except Exception as exc:
            log.error("Failed to fetch minutes archive: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        documents = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if not _MINUTES_PATTERN.search(text):
                continue

            full_url = urljoin(RBI_BASE_URL, href)
            pub_date = _parse_rbi_date(text)

            if not pub_date:
                parent_text = link.parent.get_text(strip=True) if link.parent else ""
                pub_date = _parse_rbi_date(parent_text)

            if not pub_date:
                log.warning("Could not parse date from minutes link: %s", text)
                continue

            # Estimate meeting date (will be reconciled against mpc_meetings table)
            meeting_date = _estimate_meeting_date_from_minutes_date(pub_date)

            documents.append({
                "meeting_date": meeting_date,
                "publication_date": pub_date,
                "url": full_url,
                "format": "html",
            })
            log.debug("Discovered minutes: pub=%s meeting~%s", pub_date, meeting_date)

        log.info("Discovered %d minutes documents", len(documents))
        return documents

    # ── Fetch & Cache ─────────────────────────────────────────────────────────

    def fetch_and_cache(self, doc_info: dict) -> tuple[bytes, str]:
        """
        Fetch minutes HTML, cache it. Cache key is publication_date (not meeting_date)
        because minutes lag the meeting.
        """
        pub_date = doc_info["publication_date"]
        url = doc_info["url"]

        if self._is_cached(pub_date, "html"):
            log.info("Cache hit for minutes %s", pub_date)
            raw = self._read_cache(pub_date, "html")
            return raw, str(self._cache_path(pub_date, "html"))

        log.info("Fetching minutes %s from %s", pub_date, url)
        try:
            resp = self._get(url)
            raw = resp.content
            cache_path = self._write_cache(pub_date, raw, "html")
            return raw, str(cache_path)
        except Exception as exc:
            log.error("Failed to fetch minutes %s: %s", pub_date, exc)
            raise
