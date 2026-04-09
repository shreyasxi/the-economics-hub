"""
rbi_sentinel/cleaners/pdf_extractor.py

Extracts text from RBI PDF documents (Governor's Statement, occasional resolution PDFs).
Primary: pdfplumber (better layout preservation)
Fallback: PyMuPDF / fitz (more robust on malformed PDFs)
Raises ValueError if the PDF appears to be a scanned image (no extractable text).
"""

import io
import logging
import re
from typing import Optional

log = logging.getLogger("rbi_sentinel.cleaner.pdf")

# Minimum characters per page to consider text extraction successful
# (scanned-image PDFs return near-zero characters)
_MIN_CHARS_PER_PAGE = 50

# RBI PDF boilerplate patterns
_BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*\d+\s*$", re.MULTILINE),              # Standalone page numbers
    re.compile(r"Reserve Bank of India\s*$", re.MULTILINE), # Running footer
    re.compile(r"RBI/\d{4}-\d{4}/\d+"),                    # Press release ref numbers
    re.compile(r"^\s*(Page|page)\s+\d+\s+of\s+\d+", re.MULTILINE),
]


def extract_text(pdf_bytes: bytes, source_url: str = "") -> Optional[str]:
    """
    Extract clean text from a PDF byte string.

    Returns the text string, or None if:
    - The PDF is a scanned image (no extractable text)
    - Both extraction libraries fail
    """
    text = _try_pdfplumber(pdf_bytes, source_url)

    if text is None:
        log.info("pdfplumber failed for %s — trying PyMuPDF", source_url or "unknown")
        text = _try_pymupdf(pdf_bytes, source_url)

    if text is None:
        log.error(
            "Both PDF extractors failed for %s", source_url or "unknown"
        )
        return None

    if _is_scanned_pdf(text):
        log.error(
            "PDF at %s appears to be a scanned image (extracted text too short). "
            "OCR would be required — skipping.",
            source_url or "unknown"
        )
        return None

    cleaned = _clean_text(text)
    log.info(
        "Extracted %d words from PDF %s",
        len(cleaned.split()), source_url or "unknown"
    )
    return cleaned


def _try_pdfplumber(pdf_bytes: bytes, source_url: str) -> Optional[str]:
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if len(page_text) < _MIN_CHARS_PER_PAGE and i < 3:
                    # First 3 pages with very little text → likely scanned
                    log.debug(
                        "Page %d has only %d chars — may be scanned",
                        i + 1, len(page_text)
                    )
                pages_text.append(page_text)
        return "\n\n".join(pages_text)
    except ImportError:
        log.warning("pdfplumber not installed — skipping")
        return None
    except Exception as exc:
        log.warning("pdfplumber failed for %s: %s", source_url or "unknown", exc)
        return None


def _try_pymupdf(pdf_bytes: bytes, source_url: str) -> Optional[str]:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text("text"))
        doc.close()
        return "\n\n".join(pages_text)
    except ImportError:
        log.warning("PyMuPDF (fitz) not installed — skipping")
        return None
    except Exception as exc:
        log.warning("PyMuPDF failed for %s: %s", source_url or "unknown", exc)
        return None


def _is_scanned_pdf(text: str) -> bool:
    """Return True if the extracted text is too short to be real content."""
    return len(text.strip()) < 200


def _clean_text(text: str) -> str:
    """Remove PDF boilerplate, normalize whitespace, remove hyphenation artifacts."""
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)

    # Fix PDF line-break hyphenation: "tighten-\ning" → "tightening"
    text = re.sub(r"-\n(\w)", lambda m: m.group(1), text)

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()

    return text
