"""
rbi_sentinel/fetchers/base_fetcher.py

Abstract base fetcher with:
- Shared rate limiter (2.5s between requests to rbi.org.in)
- Tenacity retry (4 attempts, exponential backoff)
- Local document cache (HTML/PDF files)
- fetch_log DB writes on every attempt
"""

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from rbi_sentinel.config import (
    CACHE_DIR,
    FETCH_CACHED,
    FETCH_FAILED,
    FETCH_SUCCESS,
    MAX_RETRY_ATTEMPTS,
    MIN_VALID_WORD_COUNT,
    RATE_LIMIT_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_MAX_WAIT_SECONDS,
    RETRY_MIN_WAIT_SECONDS,
    USER_AGENT,
)
from rbi_sentinel.db import manager as db

log = logging.getLogger("rbi_sentinel.fetcher")


class _RateLimiter:
    """Shared rate limiter — one instance across all fetcher instances."""

    def __init__(self, min_delay: float = RATE_LIMIT_DELAY_SECONDS) -> None:
        self._delay = min_delay
        self._last_request: float = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_request = time.monotonic()


# Module-level singleton — shared across all fetcher instances
_rate_limiter = _RateLimiter()


class BaseFetcher(ABC):
    """
    Abstract base for all RBI document fetchers.

    Subclasses implement:
        discover_documents() -> list[dict]   # Find document URLs for all meetings
        fetch_document(url, doc_type, ...)   # Fetch + cache a single document
    """

    def __init__(self, doc_type: str, cache_subdir: str) -> None:
        self.doc_type = doc_type
        self.cache_dir = CACHE_DIR / cache_subdir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = self._build_session()

    # ── Session Setup ─────────────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return s

    # ── Core HTTP with retry ───────────────────────────────────────────────────

    def _get(self, url: str, *, allow_ssl_fallback: bool = True) -> requests.Response:
        """
        GET with tenacity retry. Rate-limited. Logs every attempt to fetch_log.
        Returns the response on success; raises on exhausted retries.
        """
        attempt_number = 0

        @retry(
            stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
            wait=wait_exponential(
                multiplier=1,
                min=RETRY_MIN_WAIT_SECONDS,
                max=RETRY_MAX_WAIT_SECONDS,
            ),
            retry=retry_if_exception_type(
                (requests.Timeout, requests.ConnectionError)
            ),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )
        def _attempt() -> requests.Response:
            nonlocal attempt_number
            attempt_number += 1
            _rate_limiter.wait()
            start = time.monotonic()
            try:
                resp = self._session.get(
                    url,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    verify=True,
                )
                duration_ms = int((time.monotonic() - start) * 1000)
                db.log_fetch(
                    url, attempt_number, success=True,
                    http_status=resp.status_code,
                    response_bytes=len(resp.content),
                    duration_ms=duration_ms,
                )
                return resp
            except (requests.Timeout, requests.ConnectionError) as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                db.log_fetch(
                    url, attempt_number, success=False,
                    error_message=str(exc),
                    duration_ms=duration_ms,
                )
                raise
            except requests.exceptions.SSLError:
                if allow_ssl_fallback:
                    log.warning("SSL error for %s — retrying without verification", url)
                    resp = self._session.get(
                        url,
                        timeout=REQUEST_TIMEOUT_SECONDS,
                        verify=False,
                    )
                    duration_ms = int((time.monotonic() - start) * 1000)
                    db.log_fetch(
                        url, attempt_number, success=True,
                        http_status=resp.status_code,
                        response_bytes=len(resp.content),
                        duration_ms=duration_ms,
                    )
                    return resp
                raise

        return _attempt()

    # ── Cache Helpers ─────────────────────────────────────────────────────────

    def _cache_path(self, meeting_date: str, extension: str = "html") -> Path:
        return self.cache_dir / f"{meeting_date}.{extension}"

    def _is_cached(self, meeting_date: str, extension: str = "html") -> bool:
        p = self._cache_path(meeting_date, extension)
        return p.exists() and p.stat().st_size > 0

    def _read_cache(self, meeting_date: str, extension: str = "html") -> bytes:
        return self._cache_path(meeting_date, extension).read_bytes()

    def _write_cache(
        self, meeting_date: str, data: bytes, extension: str = "html"
    ) -> Path:
        p = self._cache_path(meeting_date, extension)
        p.write_bytes(data)
        log.info("Cached %s.%s (%d bytes)", meeting_date, extension, len(data))
        return p

    # ── Content Validation ────────────────────────────────────────────────────

    def _is_valid_content(self, text: str) -> bool:
        """
        Reject RBI's HTTP-200-but-actually-an-error-page responses.
        A valid document should have at least MIN_VALID_WORD_COUNT words.
        """
        words = len(text.split())
        if words < MIN_VALID_WORD_COUNT:
            log.warning(
                "Content too short (%d words) — likely an error page", words
            )
            return False
        return True

    # ── Abstract Interface ────────────────────────────────────────────────────

    @abstractmethod
    def discover_documents(self) -> list[dict]:
        """
        Scrape the RBI archive to find all available documents of this type.

        Returns a list of dicts:
        {
            "meeting_date": str (YYYY-MM-DD),
            "publication_date": str (YYYY-MM-DD),
            "url": str,
            "format": str ("html" | "pdf"),
        }
        """

    @abstractmethod
    def fetch_and_cache(self, doc_info: dict) -> tuple[str, str]:
        """
        Fetch the document at doc_info["url"], cache it locally.

        Returns (raw_bytes_or_text, cache_path_str).
        """
