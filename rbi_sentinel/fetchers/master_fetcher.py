"""
rbi_sentinel/fetchers/master_fetcher.py

Single master fetcher for all RBI MPC documents.

Strategy:
  1. Scrape the RBI search results page for MPC-related documents.
  2. Parse div#annual2 containers — each is one document link + date.
  3. Route to doc_type by h3 text keyword: "Governor", "Resolution", "Minutes".
  4. Handle ASP.NET ProcessPaging() pagination via form POST.
  5. Hard stop when any parsed date is earlier than MPC inception (Oct 2016).

For each discovered document URL (a BS_PressReleaseDisplay.aspx page),
fetch and cache the press release HTML so the cleaner can extract the text.
"""

import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from rbi_sentinel.config import (
    CACHE_DIR,
    DOC_GOVERNOR,
    DOC_MINUTES,
    DOC_RESOLUTION,
    FETCH_CACHED,
    FETCH_FAILED,
    FETCH_SUCCESS,
    MAX_RETRY_ATTEMPTS,
    MPC_INCEPTION_DATE,
    RATE_LIMIT_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_MAX_WAIT_SECONDS,
    RETRY_MIN_WAIT_SECONDS,
    USER_AGENT,
)

log = logging.getLogger("rbi_sentinel.fetcher.master")

# ── Constants ──────────────────────────────────────────────────────────────────

# Single search URL — returns Resolutions, Minutes, and Governor Statements
SEARCH_URL = (
    "https://www.rbi.org.in/scripts/SearchResults.aspx"
    "?search=Monetary+Policy+Committee"
)

# The MPC only exists from this date onward
MPC_CUTOFF = datetime.strptime(MPC_INCEPTION_DATE, "%Y-%m-%d").date()

# Keyword routing — checked against h3 text (case-insensitive)
_ROUTING: list[tuple[str, str]] = [
    ("minutes of the monetary policy committee", DOC_MINUTES),
    ("governor's statement", DOC_GOVERNOR),
    ("governor’s statement", DOC_GOVERNOR),  # Handles the smart quote
    ("resolution of the monetary policy committee", DOC_RESOLUTION),
    ("bi-monthly monetary policy statement", DOC_RESOLUTION),
]

# Months for date parsing
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Rate limiter ───────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self, delay: float = RATE_LIMIT_DELAY_SECONDS) -> None:
        self._delay = delay
        self._last: float = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last = time.monotonic()


_rate_limiter = _RateLimiter()


# ── Master Fetcher ─────────────────────────────────────────────────────────────

class MasterFetcher:
    """
    Discovers and fetches all RBI MPC documents from a single search results page.
    Handles ASP.NET ProcessPaging() pagination.
    """

    def __init__(self) -> None:
        self._session = self._build_session()
        # Cache directories
        for subdir in ("resolution", "minutes", "governor", "press_release"):
            (CACHE_DIR / subdir).mkdir(parents=True, exist_ok=True)

    # ── Session ────────────────────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return s

    # ── HTTP ───────────────────────────────────────────────────────────────────

    def _get(self, url: str) -> requests.Response:
        """GET with retry and rate limiting."""
        attempt = 0

        @retry(
            stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
            wait=wait_exponential(min=RETRY_MIN_WAIT_SECONDS, max=RETRY_MAX_WAIT_SECONDS),
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )
        def _do() -> requests.Response:
            _rate_limiter.wait()
            try:
                return self._session.get(
                    url, timeout=REQUEST_TIMEOUT_SECONDS, verify=True
                )
            except requests.exceptions.SSLError:
                log.warning("SSL error for %s — retrying without verify", url)
                _rate_limiter.wait()
                return self._session.get(
                    url, timeout=REQUEST_TIMEOUT_SECONDS, verify=False
                )

        return _do()

    def _post(self, url: str, data: dict) -> requests.Response:
        """POST for ASP.NET pagination with retry and rate limiting."""
        attempt = 0

        @retry(
            stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
            wait=wait_exponential(min=RETRY_MIN_WAIT_SECONDS, max=RETRY_MAX_WAIT_SECONDS),
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )
        def _do() -> requests.Response:
            _rate_limiter.wait()
            try:
                return self._session.post(
                    url, data=data,
                    timeout=REQUEST_TIMEOUT_SECONDS, verify=True
                )
            except requests.exceptions.SSLError:
                log.warning("SSL error on POST — retrying without verify")
                _rate_limiter.wait()
                return self._session.post(
                    url, data=data,
                    timeout=REQUEST_TIMEOUT_SECONDS, verify=False
                )

        return _do()

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_all_documents(self) -> list[dict]:
        """
        Paginate through the RBI search results and return all MPC document records
        published on or after October 1, 2016.

        Returns list of dicts:
        {
            "doc_type": str,          DOC_RESOLUTION / DOC_MINUTES / DOC_GOVERNOR
            "publication_date": str,  YYYY-MM-DD
            "meeting_date": str,      YYYY-MM-DD (same as pub date for resolution/governor)
            "source_url": str,        BS_PressReleaseDisplay.aspx?prid=XXXXX
            "title": str,             h3 text
        }
        """
        log.info("Starting discovery from: %s", SEARCH_URL)
        documents: list[dict] = []
        stop_pagination = False

        # ── Page 1: GET ────────────────────────────────────────────────────────
        try:
            resp = self._get(SEARCH_URL)
        except Exception as exc:
            log.error("Failed to load search page: %s", exc)
            return documents

        soup = BeautifulSoup(resp.text, "lxml")
        page_num = 1

        while True:
            log.info("Parsing search results page %d", page_num)
            page_docs, hit_cutoff = self._parse_search_page(soup)
            documents.extend(page_docs)

            log.info(
                "Page %d: found %d documents (cumulative: %d), hit_cutoff=%s",
                page_num, len(page_docs), len(documents), hit_cutoff
            )

            if hit_cutoff:
                log.info("Hit MPC cutoff date (Oct 2016) — stopping pagination")
                break

            # ── Find next page link ────────────────────────────────────────────
            next_page_num = self._find_next_page_number(soup)
            if next_page_num is None:
                log.info("No further pages found — pagination complete")
                break

            # ── POST to advance page ───────────────────────────────────────────
            form_data = self._build_pagination_post_data(soup, next_page_num)
            if form_data is None:
                log.warning("Could not build pagination POST data — stopping")
                break

            form_action = self._get_form_action(soup)
            post_url = urljoin(SEARCH_URL, form_action) if form_action else SEARCH_URL

            log.info("Posting to advance to page %d: %s", next_page_num, post_url)
            try:
                resp = self._post(post_url, form_data)
                soup = BeautifulSoup(resp.text, "lxml")
                page_num = next_page_num
            except Exception as exc:
                log.error("Pagination POST failed on page %d: %s", next_page_num, exc)
                break

        log.info("Discovery complete — %d documents found", len(documents))
        return documents

    # ── Page Parser ───────────────────────────────────────────────────────────

    def _parse_search_page(self, soup: BeautifulSoup) -> tuple[list[dict], bool]:
        """
        Parse one page of search results.

        Returns (documents_on_this_page, hit_cutoff_flag).
        hit_cutoff_flag = True if any document date is before MPC_CUTOFF.
        """
        documents: list[dict] = []
        hit_cutoff = False

        containers = soup.select("div#annual2")
        if not containers:
            # Fallback: try without id specificity (some pages use class instead)
            containers = soup.select("div.search_result") or soup.select("div.tabletext")
            log.debug("Primary selector 'div#annual2' found 0 — trying fallbacks (%d found)", len(containers))

        for container in containers:
            # ── Extract link and title ─────────────────────────────────────────
            link_tag = container.find("a")
            h3_tag = container.find("h3")

            if not link_tag or not h3_tag:
                continue

            href = link_tag.get("href", "")
            title = h3_tag.get_text(strip=True)

            if not href or not title:
                continue

            # Ensure absolute URL
            if href.startswith("http"):
                source_url = href
            else:
                source_url = urljoin("https://www.rbi.org.in", href)

            # ── Extract publication date ───────────────────────────────────────
            date_div = container.find("div", class_="sub_title2_detail")
            date_str = date_div.get_text(strip=True) if date_div else ""

            pub_date = _parse_date(date_str) or _parse_date_from_title(title)

            if pub_date is None:
                log.warning("Could not parse date from '%s' / '%s'", date_str, title)
                continue

            # ── Kill switch: stop if before MPC inception ─────────────────────
            if pub_date < MPC_CUTOFF:
                log.info(
                    "Date %s is before MPC cutoff %s — halting pagination",
                    pub_date, MPC_CUTOFF
                )
                hit_cutoff = True
                break

            # ── Route by document type ────────────────────────────────────────
            doc_type = _route_document(title)
            if doc_type is None:
                log.debug("Could not route document: '%s' — skipping", title)
                continue

            pub_date_str = pub_date.strftime("%Y-%m-%d")

            documents.append({
                "doc_type": doc_type,
                "publication_date": pub_date_str,
                "meeting_date": pub_date_str,   # Refined in pipeline for minutes
                "source_url": source_url,
                "title": title,
            })
            log.debug("Discovered: %s | %s | %s", doc_type, pub_date_str, title[:60])

        return documents, hit_cutoff

    # ── Pagination Helpers ────────────────────────────────────────────────────

    def _find_next_page_number(self, soup: BeautifulSoup) -> Optional[int]:
        """
        Find the next page number from the pagination div.
        Looks for:  <a href="javascript:ProcessPaging('N')">Next</a>
        """
        # Primary: look for div.next > a with ProcessPaging
        next_div = soup.find("div", class_="next")
        if next_div:
            link = next_div.find("a")
            if link:
                href = link.get("href", "")
                m = re.search(r"ProcessPaging\('?(\d+)'?\)", href)
                if m:
                    return int(m.group(1))

        # Fallback: scan all links for ProcessPaging in pagination context
        pagination = soup.find("div", class_="pagination")
        if pagination:
            for link in pagination.find_all("a"):
                href = link.get("href", "")
                text = link.get_text(strip=True).lower()
                if "next" in text or ">" in text:
                    m = re.search(r"ProcessPaging\('?(\d+)'?\)", href)
                    if m:
                        return int(m.group(1))

        return None

    def _build_pagination_post_data(
        self, soup: BeautifulSoup, page_num: int
    ) -> Optional[dict]:
        """
        Build the POST body for an ASP.NET ProcessPaging() call.

        ASP.NET pages require all hidden form fields (__VIEWSTATE etc.) to be
        re-submitted with each POST. The ProcessPaging function typically sets
        one of several possible hidden page-number fields.
        """
        form = soup.find("form")
        if not form:
            log.warning("No form element found on page — cannot paginate")
            return None

        # Collect all hidden inputs
        data: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name", "")
            value = inp.get("value", "")
            if name:
                data[name] = value

        # Set the page number field — try common ASP.NET field names in order
        page_field_candidates = [
            "hdnCurrentPage",
            "hdnPageNo",
            "hdnPage",
            "CurrentPageIndex",
            "PageNumber",
            "txtPageNo",
        ]

        page_field_set = False
        for candidate in page_field_candidates:
            if candidate in data:
                data[candidate] = str(page_num)
                log.debug("Set pagination field '%s' = %s", candidate, page_num)
                page_field_set = True
                break

        if not page_field_set:
            # No known field — add hdnCurrentPage (most common on RBI site)
            # and also try __EVENTTARGET/__EVENTARGUMENT approach
            log.warning(
                "No known page-number field found. "
                "Adding hdnCurrentPage and trying __doPostBack pattern."
            )
            data["hdnCurrentPage"] = str(page_num)
            data["__EVENTTARGET"] = data.get("__EVENTTARGET", "")
            data["__EVENTARGUMENT"] = str(page_num)

        # Also submit all select/textarea values
        for sel in form.find_all("select"):
            name = sel.get("name", "")
            selected = sel.find("option", selected=True)
            if name and selected:
                data[name] = selected.get("value", "")

        return data

    def _get_form_action(self, soup: BeautifulSoup) -> Optional[str]:
        form = soup.find("form")
        if form:
            action = form.get("action", "")
            return action if action else None
        return None

    # ── Document Content Fetcher ───────────────────────────────────────────────

    def fetch_press_release(self, doc_info: dict) -> tuple[Optional[bytes], str, str]:
        """
        Fetch a press release page and cache it.

        Returns (raw_bytes, cache_path_str, fetch_status).
        raw_bytes is None on failure.
        """
        source_url = doc_info["source_url"]
        doc_type = doc_info["doc_type"]
        pub_date = doc_info["publication_date"]

        # Cache key: doc_type/YYYY-MM-DD.html
        cache_path = CACHE_DIR / doc_type / f"{pub_date}.html"

        if cache_path.exists() and cache_path.stat().st_size > 100:
            log.info("Cache hit: %s %s", doc_type, pub_date)
            return cache_path.read_bytes(), str(cache_path), FETCH_CACHED

        log.info("Fetching press release: %s %s", doc_type, pub_date)
        try:
            resp = self._get(source_url)
            raw = resp.content

            # Validate: RBI returns HTTP 200 for error pages
            text_preview = raw[:2000].decode("utf-8", errors="replace")
            word_count = len(text_preview.split())
            if word_count < 20:
                log.warning(
                    "Suspiciously short response (%d words) for %s — possible error page",
                    word_count, source_url
                )

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw)
            log.info("Cached %s %s (%d bytes)", doc_type, pub_date, len(raw))
            return raw, str(cache_path), FETCH_SUCCESS

        except Exception as exc:
            log.error("Failed to fetch %s %s: %s", doc_type, pub_date, exc)
            return None, "", FETCH_FAILED


# ── Helpers ────────────────────────────────────────────────────────────────────

def _route_document(title: str) -> Optional[str]:
    """
    Route a document to a doc_type based on its h3 title text.
    Returns DOC_GOVERNOR, DOC_RESOLUTION, DOC_MINUTES, or None.
    """
    title_lower = title.lower()
    for keyword, doc_type in _ROUTING:
        if keyword in title_lower:
            return doc_type
    return None


def _parse_date(text: str) -> Optional[date]:
    """
    Parse a date from the sub_title2_detail div text.
    Handles formats like "Apr 08, 2026", "08 April 2026", "2026-04-08".
    """
    if not text:
        return None

    text = text.strip()

    # ISO format
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # "Apr 08, 2026" or "Apr 8, 2026"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        month_name = m.group(1).lower()
        month_num = _MONTHS.get(month_name)
        if month_num:
            try:
                return date(int(m.group(3)), month_num, int(m.group(2)))
            except ValueError:
                pass

    # "08 April 2026" or "08 Apr 2026"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m:
        month_name = m.group(2).lower()
        month_num = _MONTHS.get(month_name)
        if month_num:
            try:
                return date(int(m.group(3)), month_num, int(m.group(1)))
            except ValueError:
                pass

    return None


def _parse_date_from_title(title: str) -> Optional[date]:
    """
    Try to extract a date embedded in the document title.
    e.g. "Governor's Statement: April 08, 2026"
         "Minutes of the MPC Meeting held on June 6, 2024"
    """
    return _parse_date(title)
