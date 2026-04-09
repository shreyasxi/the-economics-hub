"""
rbi_sentinel/sentiment/hybrid_scorer.py

Orchestrates the two-stage hybrid scoring pipeline:
  Stage 1: Lexicon pre-score (deterministic, auditable)
  Stage 2: LLM score (contextual, generates narrative)
  Stage 3: Fusion (0.25 × lexicon + 0.75 × LLM)
  Conflict detection: |lexicon - llm| > threshold → WARNING + low confidence
"""

import logging
import math
from typing import Optional

from rbi_sentinel.config import (
    CONFLICT_THRESHOLD,
    LEXICON_WEIGHT,
    LOW_CONFIDENCE_THRESHOLD,
    LLM_WEIGHT,
    SCORING_MODEL_VERSION,
)
from rbi_sentinel.sentiment.lexicon.hawkish_terms import get_hawkish_terms
from rbi_sentinel.sentiment.lexicon.dovish_terms import get_dovish_terms
from rbi_sentinel.sentiment.lexicon.negation_handler import apply_negation
from rbi_sentinel.sentiment.llm_scorer import LLMScorer
from rbi_sentinel.sentiment.score_normalizer import clamp, normalize_lexicon_score

log = logging.getLogger("rbi_sentinel.sentiment.hybrid")


class HybridScorer:
    """
    Scores a single RBI document using the hybrid lexicon + LLM approach.

    Usage:
        scorer = HybridScorer()
        result = scorer.score(text, doc_type="resolution", meeting_date="2024-10-09")
    """

    def __init__(self) -> None:
        self._llm = LLMScorer()
        self._hawkish = get_hawkish_terms()
        self._dovish = get_dovish_terms()

    # ── Public Interface ───────────────────────────────────────────────────────

    def score(
        self,
        text: str,
        doc_type: str,
        meeting_date: str,
        sentences: Optional[list[str]] = None,
    ) -> dict:
        """
        Score a document. Always returns a result dict — never raises.
        Falls back to lexicon-only if LLM fails.

        Returns a dict matching the sentiment_scores table schema.
        """
        # Stage 1: Lexicon
        lexicon_result = self._lexicon_score(text)
        lexicon_score = lexicon_result["score"]
        hawkish_hits = lexicon_result["hawkish_hits"]
        dovish_hits = lexicon_result["dovish_hits"]

        log.info(
            "Lexicon score for %s %s: %.3f (hawk=%d, dove=%d)",
            doc_type, meeting_date, lexicon_score, hawkish_hits, dovish_hits
        )

        # Stage 2: LLM
        llm_result = self._llm.score(text, doc_type, meeting_date)

        if llm_result is None:
            # LLM failed — use lexicon-only with low confidence
            log.warning(
                "LLM failed for %s %s — using lexicon score only (low confidence)",
                doc_type, meeting_date
            )
            return self._build_result(
                overall_score=lexicon_score,
                score_confidence=0.30,
                lexicon_raw_score=lexicon_score,
                lexicon_hawkish_hits=hawkish_hits,
                lexicon_dovish_hits=dovish_hits,
                llm_raw_response=None,
                llm_result=None,
            )

        llm_score = float(llm_result["overall_score"])
        llm_confidence = float(llm_result.get("score_confidence", 0.70))

        # Stage 3: Conflict check
        divergence = abs(lexicon_score - llm_score)
        if divergence > CONFLICT_THRESHOLD:
            log.warning(
                "Score conflict for %s %s: lexicon=%.3f llm=%.3f divergence=%.3f — "
                "flagging as low confidence. Review key_phrases: %s",
                doc_type, meeting_date, lexicon_score, llm_score, divergence,
                llm_result.get("key_phrases", [])
            )
            llm_confidence = min(llm_confidence, 0.45)

        # Stage 3: Fusion
        final_score = (LEXICON_WEIGHT * lexicon_score) + (LLM_WEIGHT * llm_score)
        final_score = clamp(final_score)
        final_confidence = llm_confidence

        log.info(
            "Hybrid score for %s %s: %.3f (lex=%.3f, llm=%.3f, conf=%.2f)",
            doc_type, meeting_date, final_score, lexicon_score, llm_score,
            final_confidence
        )

        import json
        return self._build_result(
            overall_score=final_score,
            score_confidence=final_confidence,
            lexicon_raw_score=lexicon_score,
            lexicon_hawkish_hits=hawkish_hits,
            lexicon_dovish_hits=dovish_hits,
            llm_raw_response=json.dumps(llm_result, ensure_ascii=False),
            llm_result=llm_result,
        )

    # ── Lexicon Scoring ────────────────────────────────────────────────────────

    def _lexicon_score(self, text: str) -> dict:
        """
        Run lexicon scoring over the full text.
        Longest-match wins on overlapping phrases.
        Returns: {"score": float, "hawkish_hits": int, "dovish_hits": int, "matches": list}
        """
        text_lower = text.lower()
        all_matches: list[dict] = []

        # Hawkish terms (positive scores)
        for phrase, weight in self._hawkish:
            net, hits = apply_negation(text_lower, phrase, weight)
            all_matches.extend(hits)

        # Dovish terms (negative scores — weight is negated)
        for phrase, weight in self._dovish:
            net, hits = apply_negation(text_lower, phrase, weight)
            # Negate: dovish hits produce negative scores
            for h in hits:
                h["score"] = -h["score"]
            all_matches.extend(hits)

        # Resolve overlapping matches: remove shorter matches that are substrings
        # of already-matched phrases at the same position
        resolved = _resolve_overlaps(all_matches)

        raw_score = sum(m["score"] for m in resolved)
        hawkish_hits = sum(1 for m in resolved if m["score"] > 0)
        dovish_hits = sum(1 for m in resolved if m["score"] < 0)

        # Normalize by document density
        normalized = normalize_lexicon_score(raw_score, len(text.split()))

        return {
            "score": normalized,
            "hawkish_hits": hawkish_hits,
            "dovish_hits": dovish_hits,
            "matches": resolved,
        }

    # ── Result Builder ────────────────────────────────────────────────────────

    def _build_result(
        self,
        overall_score: float,
        score_confidence: float,
        lexicon_raw_score: float,
        lexicon_hawkish_hits: int,
        lexicon_dovish_hits: int,
        llm_raw_response: Optional[str],
        llm_result: Optional[dict],
    ) -> dict:
        result = {
            "overall_score": overall_score,
            "score_confidence": score_confidence,
            "lexicon_raw_score": lexicon_raw_score,
            "lexicon_hawkish_hits": lexicon_hawkish_hits,
            "lexicon_dovish_hits": lexicon_dovish_hits,
            "llm_raw_response": llm_raw_response,
            "scoring_model_version": SCORING_MODEL_VERSION,
            # Sub-dimensions
            "inflation_stance": None,
            "growth_stance": None,
            "liquidity_stance": None,
            "rate_guidance": None,
            "fx_external_stance": None,
            # LLM narratives
            "narrative_summary": None,
            "key_phrases": None,
        }

        if llm_result:
            result["inflation_stance"] = clamp(float(llm_result.get("inflation_stance", 0)))
            result["growth_stance"] = clamp(float(llm_result.get("growth_stance", 0)))
            result["liquidity_stance"] = clamp(float(llm_result.get("liquidity_stance", 0)))
            result["rate_guidance"] = clamp(float(llm_result.get("rate_guidance", 0)))
            result["fx_external_stance"] = clamp(float(llm_result.get("fx_external_stance", 0)))

            # Combine narrative paragraphs into the 2-paragraph format for insights.py
            p1 = llm_result.get("narrative_para_1", "")
            p2 = llm_result.get("narrative_para_2", "")
            result["narrative_summary"] = f"{p1}\n\n{p2}" if p1 and p2 else (p1 or p2)
            result["key_phrases"] = llm_result.get("key_phrases", [])

        return result


def _resolve_overlaps(matches: list[dict]) -> list[dict]:
    """
    Remove duplicate/overlapping matches.
    When two matches overlap, keep the one with higher |score|.
    """
    if not matches:
        return []

    sorted_matches = sorted(matches, key=lambda m: -abs(m["score"]))
    occupied: set[int] = set()
    resolved: list[dict] = []

    for match in sorted_matches:
        pos = match["position"]
        phrase_len = len(match["phrase"])
        positions = range(pos, pos + phrase_len)

        if any(p in occupied for p in positions):
            continue  # Skip — overlaps with a higher-weight match

        occupied.update(positions)
        resolved.append(match)

    return resolved
