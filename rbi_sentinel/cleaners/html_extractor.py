"""
rbi_sentinel/cleaners/html_extractor.py

Extracts main body text from RBI press release HTML.
Uses versioned CSS selectors with fallbacks to handle site restructures.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from rbi_sentinel.config import HTML_CONTENT_SELECTORS, MIN_VALID_WORD_COUNT

log = logging.getLogger("rbi_sentinel.cleaner.html")

# RBI boilerplate patterns to strip before returning text
_BOILERPLATE_PATTERNS = [
    re.compile(r"RBI/\d{4}-\d{4}/\d+"),          # Press release number e.g. RBI/2022-23/145
    re.compile(r"(Ref\.? No\.?|Ref No\.?).*"),
    re.compile(r"Jose J\. Kattoor.*Chief General Manager"),
    re.compile(r"Ajit Prasad.*Director"),
    re.compile(r"(Press Release|PRESS RELEASE)\s*:?\s*"),
    re.compile(r"Alpana Killawala.*"),
    re.compile(r"(Website|www\.rbi\.org\.in|rbi\.org\.in).*"),
]

# Patterns that confirm we're looking at a monetary policy document
_VALIDITY_KEYWORDS = [
    "monetary policy",
    "repo rate",
    "mpc",
    "monetary policy committee",
    "inflation",
    "basis points",
]


def extract_text(html_bytes: bytes, source_url: str = "") -> Optional[str]:
    """
    Extract clean body text from RBI HTML.

    Returns the text string, or None if the page appears to be an error or
    does not contain monetary policy content.
    """
    try:
        soup = BeautifulSoup(html_bytes, "lxml")
    except Exception as exc:
        log.error("Failed to parse HTML from %s: %s", source_url, exc)
        return None

    # Try each selector version in order
    content_element = None
    used_selector = None

    for version, selector in HTML_CONTENT_SELECTORS:
        elements = soup.select(selector)
        if elements:
            # Take the largest element (most likely to be the main content)
            candidate = max(elements, key=lambda el: len(el.get_text()))
            if len(candidate.get_text().split()) >= MIN_VALID_WORD_COUNT:
                content_element = candidate
                used_selector = version
                log.info(
                    "Selector '%s' (%s) succeeded for %s",
                    version, selector, source_url or "unknown"
                )
                break

    if content_element is None:
        log.warning(
            "All selectors failed for %s — falling back to full body",
            source_url or "unknown"
        )
        content_element = soup.find("body") or soup

    raw_text = content_element.get_text(separator="\n", strip=True)
    cleaned = _clean_text(raw_text)

    if not _is_valid_monetary_policy_text(cleaned):
        log.warning(
            "Content from %s does not appear to be a monetary policy document "
            "(missing key terms). Word count: %d",
            source_url or "unknown", len(cleaned.split())
        )
        return None

    log.info(
        "Extracted %d words from %s (selector: %s)",
        len(cleaned.split()), source_url or "unknown", used_selector
    )
    return cleaned


def _clean_text(text: str) -> str:
    """Strip boilerplate, normalize whitespace, remove navigation artifacts."""
    # Remove boilerplate patterns
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)

    # Collapse multiple blank lines to single
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove lines that are purely navigation artifacts (very short lines)
    lines = text.split("\n")
    filtered_lines = []
    for line in lines:
        stripped = line.strip()
        # Keep lines with meaningful content (>3 words or looks like a sentence)
        if len(stripped.split()) >= 3 or (len(stripped) > 20 and "." in stripped):
            filtered_lines.append(stripped)

    cleaned = "\n".join(filtered_lines)

    # Final whitespace normalization
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = cleaned.strip()

    return cleaned


def _is_valid_monetary_policy_text(text: str) -> bool:
    """
    Confirm the extracted text actually contains monetary policy content.
    Rejects error pages, navigation-only pages, etc.
    """
    text_lower = text.lower()
    hits = sum(1 for kw in _VALIDITY_KEYWORDS if kw in text_lower)
    return hits >= 2
