"""
rbi_sentinel/cleaners/text_normalizer.py

Final normalization pass applied to all documents regardless of source format.
- Deduplicates repeated paragraphs (common in PDFs)
- Tokenizes into sentences for the lexicon scorer
- Produces word count
- Truncates to LLM token budget while preserving intro + conclusion
"""

import logging
import re
from typing import Optional

from rbi_sentinel.config import LLM_MAX_INPUT_TOKENS

log = logging.getLogger("rbi_sentinel.cleaner.normalizer")

# Approximate: 1 token ≈ 4 characters (conservative for Claude)
_CHARS_PER_TOKEN = 4
_MAX_CHARS = LLM_MAX_INPUT_TOKENS * _CHARS_PER_TOKEN


def normalize(text: str) -> dict:
    """
    Apply final normalization to extracted text.

    Returns:
        {
            "text": str,              # Cleaned, deduplicated text
            "word_count": int,
            "sentences": list[str],   # For lexicon scorer
            "truncated": bool,        # True if text was truncated for LLM
        }
    """
    # Step 1: Basic cleanup
    text = _basic_cleanup(text)

    # Step 2: Deduplicate paragraphs
    text = _dedup_paragraphs(text)

    # Step 3: Sentence tokenization
    sentences = _tokenize_sentences(text)

    word_count = len(text.split())
    truncated = False

    # Step 4: Truncate for LLM if needed (preserve intro + conclusion)
    llm_text = text
    if len(text) > _MAX_CHARS:
        llm_text = _truncate_for_llm(text, _MAX_CHARS)
        truncated = True
        log.info(
            "Text truncated from %d to ~%d chars for LLM",
            len(text), len(llm_text)
        )

    return {
        "text": llm_text,
        "full_text": text,          # Full text stored in DB; llm_text passed to scorer
        "word_count": word_count,
        "sentences": sentences,
        "truncated": truncated,
    }


def _basic_cleanup(text: str) -> str:
    """Remove null bytes, normalize unicode, collapse excessive whitespace."""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _dedup_paragraphs(text: str) -> str:
    """
    Remove duplicate paragraphs. PDFs often repeat section headers on every page.
    Two paragraphs are considered duplicates if they are identical after stripping.
    """
    paragraphs = text.split("\n\n")
    seen: set[str] = set()
    unique: list[str] = []
    for para in paragraphs:
        key = re.sub(r"\s+", " ", para.strip().lower())
        if key and key not in seen:
            seen.add(key)
            unique.append(para.strip())
    return "\n\n".join(unique)


def _tokenize_sentences(text: str) -> list[str]:
    """
    Simple rule-based sentence tokenizer.
    Splits on ". " followed by a capital letter, or on ".\n".
    Good enough for lexicon scoring — no need for NLTK/spaCy.
    """
    # Split on sentence boundaries
    raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    sentences = []
    for s in raw_sentences:
        s = s.strip()
        if len(s.split()) >= 4:  # Skip fragments shorter than 4 words
            sentences.append(s)
    return sentences


def _truncate_for_llm(text: str, max_chars: int) -> str:
    """
    Truncate text while preserving the opening and closing sections.
    Strategy: keep first 60% + last 40% of budget.
    This ensures the document's stance setup (intro) and conclusion are both included.
    """
    if len(text) <= max_chars:
        return text

    intro_budget = int(max_chars * 0.60)
    outro_budget = max_chars - intro_budget

    intro = text[:intro_budget]
    outro = text[-outro_budget:]

    # Try to break at paragraph boundaries
    intro_break = intro.rfind("\n\n")
    if intro_break > intro_budget * 0.7:
        intro = intro[:intro_break]

    outro_break = outro.find("\n\n")
    if outro_break > 0 and outro_break < outro_budget * 0.3:
        outro = outro[outro_break:]

    separator = "\n\n[... content truncated for length ...]\n\n"
    return intro + separator + outro
