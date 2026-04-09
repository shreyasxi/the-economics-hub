"""
rbi_sentinel/fetchers/governor_fetcher.py

Discovers and fetches Governor's Statement PDFs from rbi.org.in.
These are linked from the same press release pages as the Policy Resolutions.
PDF-primary format; falls back to HTML text if no PDF found.
"""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from rbi_sentinel.config import (
    DOC_GOVERNOR,
    GOVERNOR_KEYWORDS,
    RBI_BASE_URL,
    RBI_PRESS_RELEASE_URL,
)
from rbi_sentinel.fetchers.base_fetcher import BaseFetcher

log = logging.getLogger("rbi_sentinel.fetcher.governor")

_GOVERNOR_PATTERN = re.compile(
    r"(governor'?s? statement|statement by (the )?governor|"
    r"governor'?s? press|press conference)",
    re.IGNORECASE,
)

_PDF_PATTERN = re.compile(r"\.pdf(\?.*)?$", re.IGNORECASE)

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


class GovernorFetcher(BaseFetcher):
    """
    Fetches Governor's Statement PDFs (or HTML fallback).

    Strategy:
    1. Start from a press release page URL (usually discovered alongside the resolution)
    2. Scan all links on that page for PDF links matching governor statement patterns
    3. Fetch and cache the PDF
    """

    def __init__(self) -> None:
        super().__init__(doc_type=DOC_GOVERNOR, cache_subdir="governor")

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_documents(self) -> list[dict]:
        """
        Governor's statements don't have a standalone archive.
        This method is a stub — governor docs are discovered in the pipeline
        by scanning each resolution press release page for PDF links.
        Returns empty list; use discover_from_press_release_page() instead.
        """
        log.info(
            "Governor fetcher has no standalone archive. "
            "Use discover_from_press_release_page() per meeting."
        )
        return []

    def discover_from_press_release_page(
        self, press_release_url: str, meeting_date: str
    ) -> Optional[dict]:
        """
        Given a press release page URL (same page as the resolution),
        find and return the Governor's Statement PDF link if present.
        """
        log.info(
            "Searching for governor PDF on press release page: %s", press_release_url
        )
        try:
            resp = self._get(press_release_url)
        except Exception as exc:
            log.error(
                "Failed to fetch press release page %s: %s", press_release_url, exc
            )
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # First pass: look for explicit governor statement PDF links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if _GOVERNOR_PATTERN.search(text) and _PDF_PATTERN.search(href):
                full_url = urljoin(RBI_BASE_URL, href)
                log.info("Found governor PDF: %s", full_url)
                return {
                    "meeting_date": meeting_date,
                    "publication_date": meeting_date,
                    "url": full_url,
                    "format": "pdf",
                }

        # Second pass: any PDF on the page with governor-related text
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if _GOVERNOR_PATTERN.search(text):
                full_url = urljoin(RBI_BASE_URL, href)
                fmt = "pdf" if _PDF_PATTERN.search(href) else "html"
                log.info("Found governor statement (%s): %s", fmt, full_url)
                return {
                    "meeting_date": meeting_date,
                    "publication_date": meeting_date,
                    "url": full_url,
                    "format": fmt,
                }

        log.warning(
            "No governor statement found on press release page for %s", meeting_date
        )
        return None

    # ── Fetch & Cache ─────────────────────────────────────────────────────────

    def fetch_and_cache(self, doc_info: dict) -> tuple[bytes, str]:
        """
        Fetch governor statement (PDF or HTML), cache it locally.
        Extension is determined by doc_info["format"].
        """
        meeting_date = doc_info["meeting_date"]
        url = doc_info["url"]
        fmt = doc_info.get("format", "pdf")
        ext = "pdf" if fmt == "pdf" else "html"

        if self._is_cached(meeting_date, ext):
            log.info("Cache hit for governor statement %s", meeting_date)
            raw = self._read_cache(meeting_date, ext)
            return raw, str(self._cache_path(meeting_date, ext))

        log.info("Fetching governor statement %s from %s", meeting_date, url)
        try:
            resp = self._get(url)
            raw = resp.content
            cache_path = self._write_cache(meeting_date, raw, ext)
            return raw, str(cache_path)
        except Exception as exc:
            log.error(
                "Failed to fetch governor statement %s: %s", meeting_date, exc
            )
            raise
