"""
rbi_sentinel/sentiment/lexicon/negation_handler.py

Applies a 5-word negation window to lexicon phrase matching.
If a negation word appears within 5 tokens before a matched phrase,
the phrase's score is flipped (hawkish → dovish and vice versa).
"""

import re
from typing import Optional

# Negation triggers
NEGATION_WORDS = {
    "not", "no", "never", "neither", "without",
    "no longer", "rules out", "ruled out",
    "cannot", "can't", "won't", "does not", "do not",
    "did not", "is not", "are not", "was not", "were not",
    "reject", "rejects", "rejected",
    "dismiss", "dismisses", "dismissed",
}

# Window size (in tokens/words) before the matched phrase
NEGATION_WINDOW = 5


def is_negated(sentence: str, phrase_start_pos: int) -> bool:
    """
    Check whether the phrase starting at phrase_start_pos in sentence
    is preceded by a negation word within NEGATION_WINDOW tokens.

    Args:
        sentence: The full sentence text (lowercased)
        phrase_start_pos: Character index of the start of the matched phrase

    Returns:
        True if the phrase appears to be negated
    """
    # Extract the window of text before the phrase
    pre_text = sentence[:phrase_start_pos]
    pre_tokens = pre_text.split()

    # Take the last NEGATION_WINDOW tokens
    window_tokens = pre_tokens[-NEGATION_WINDOW:]
    window_text = " ".join(window_tokens)

    for neg in NEGATION_WORDS:
        if neg in window_text:
            return True

    return False


def apply_negation(
    text: str,
    phrase: str,
    base_score: float,
) -> tuple[float, list[dict]]:
    """
    Find all occurrences of phrase in text and compute the effective score
    after applying negation logic.

    Returns:
        (net_score, hits)
        net_score: sum of (±base_score) for each occurrence
        hits: list of {"phrase": str, "negated": bool, "score": float}
    """
    text_lower = text.lower()
    phrase_lower = phrase.lower()

    hits = []
    pos = 0

    while True:
        idx = text_lower.find(phrase_lower, pos)
        if idx == -1:
            break

        negated = is_negated(text_lower, idx)
        effective_score = -base_score if negated else base_score

        hits.append({
            "phrase": phrase,
            "position": idx,
            "negated": negated,
            "score": effective_score,
        })

        pos = idx + len(phrase_lower)

    net_score = sum(h["score"] for h in hits)
    return net_score, hits
