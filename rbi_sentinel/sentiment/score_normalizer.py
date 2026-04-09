"""
rbi_sentinel/sentiment/score_normalizer.py

Utility functions for score normalization and composite computation.
"""

import math
import logging
from typing import Optional

from rbi_sentinel.config import DOC_GOVERNOR, DOC_MINUTES, DOC_RESOLUTION

log = logging.getLogger("rbi_sentinel.sentiment.normalizer")

# Document type weights for composite score
# Minutes are weighted highest — most text-rich and analytically revealing
_DOC_WEIGHTS = {
    DOC_RESOLUTION: 0.35,
    DOC_MINUTES: 0.50,
    DOC_GOVERNOR: 0.15,
}


def clamp(score: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """Clamp a score to [lo, hi]."""
    return max(lo, min(hi, score))


def normalize_lexicon_score(raw_score: float, word_count: int) -> float:
    """
    Normalize the raw lexicon score by document length.

    Strategy: use a sigmoid-like normalization so that:
    - A very short doc with 1 strong hit doesn't score ±1.0
    - A very long doc can accumulate strong scores but is bounded

    Returns a score in [-1.0, +1.0].
    """
    if word_count == 0:
        return 0.0

    # Scale factor: divide by sqrt of word count to reduce length bias
    # A 500-word doc with 3 hits vs an 1500-word doc with 9 hits
    # should produce comparable scores
    density = raw_score / math.sqrt(max(word_count, 100))

    # Apply tanh to squish into [-1, 1] — smooth and bounded
    # Multiplier 3.0 calibrated so that a dense hawkish doc hits ~0.8
    normalized = math.tanh(density * 3.0)

    return clamp(normalized)


def compute_composite(scores_by_doc_type: dict[str, Optional[float]]) -> Optional[float]:
    """
    Compute a weighted composite score across document types.

    Args:
        scores_by_doc_type: {"resolution": float|None, "minutes": float|None, ...}

    Returns:
        Weighted composite or None if no scores available.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for doc_type, weight in _DOC_WEIGHTS.items():
        score = scores_by_doc_type.get(doc_type)
        if score is not None:
            weighted_sum += score * weight
            total_weight += weight

    if total_weight == 0:
        return None

    # Re-normalize by actual weight available (in case some doc types are missing)
    composite = weighted_sum / total_weight
    return clamp(composite)


def compute_meeting_composite(scores: list[dict]) -> dict:
    """
    Compute the meeting-level composite from individual document scores.

    Args:
        scores: List of score dicts from sentiment_scores table (joined with doc_type)

    Returns:
        Dict ready for upsert_composite(): composite_overall_score, resolution_score,
        minutes_score, governor_score, score_divergence, composite_narrative
    """
    by_type: dict[str, dict] = {}
    for s in scores:
        doc_type = s.get("doc_type")
        if doc_type:
            by_type[doc_type] = s

    resolution_score = by_type.get(DOC_RESOLUTION, {}).get("overall_score")
    minutes_score = by_type.get(DOC_MINUTES, {}).get("overall_score")
    governor_score = by_type.get(DOC_GOVERNOR, {}).get("overall_score")

    composite = compute_composite({
        DOC_RESOLUTION: resolution_score,
        DOC_MINUTES: minutes_score,
        DOC_GOVERNOR: governor_score,
    })

    # Score divergence: primarily between resolution and minutes
    divergence = None
    if resolution_score is not None and minutes_score is not None:
        divergence = abs(resolution_score - minutes_score)

    # Composite narrative: prefer minutes narrative (richest), fall back to resolution
    narrative = None
    for preferred_type in [DOC_MINUTES, DOC_RESOLUTION, DOC_GOVERNOR]:
        candidate = by_type.get(preferred_type, {}).get("narrative_summary")
        if candidate:
            narrative = candidate
            break

    return {
        "composite_overall_score": composite,
        "resolution_score": resolution_score,
        "minutes_score": minutes_score,
        "governor_score": governor_score,
        "score_divergence": divergence,
        "composite_narrative": narrative,
    }


def score_to_label(score: float) -> str:
    """Convert a numeric score to a human-readable stance label."""
    if score >= 0.70:
        return "Extremely Hawkish"
    elif score >= 0.40:
        return "Hawkish"
    elif score >= 0.15:
        return "Mildly Hawkish"
    elif score >= -0.15:
        return "Neutral"
    elif score >= -0.40:
        return "Mildly Dovish"
    elif score >= -0.70:
        return "Dovish"
    else:
        return "Extremely Dovish"
