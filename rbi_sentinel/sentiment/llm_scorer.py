"""
rbi_sentinel/sentiment/llm_scorer.py

Scores RBI MPC documents using the Anthropic API (Claude).
Returns structured JSON — never prose.
"""

import json
import logging
import os
from typing import Optional

from rbi_sentinel.config import (
    LLM_DEFAULT_MODEL,
    LLM_FALLBACK_MODEL,
    LLM_MAX_OUTPUT_TOKENS,
    SCORING_MODEL_VERSION,
)

log = logging.getLogger("rbi_sentinel.sentiment.llm")

# ── JSON Schema the LLM must return ───────────────────────────────────────────
_REQUIRED_KEYS = {
    "overall_score",
    "score_confidence",
    "inflation_stance",
    "growth_stance",
    "liquidity_stance",
    "rate_guidance",
    "fx_external_stance",
    "key_phrases",
    "narrative_para_1",
    "narrative_para_2",
}

_SYSTEM_PROMPT = """\
You are a quantitative analyst specializing in Reserve Bank of India monetary policy. \
You analyze MPC documents and return structured JSON scores. \
All scores are on a continuous scale from -1.0 (extremely dovish) to +1.0 (extremely hawkish). \
A score of 0.0 is neutral.

Never return prose. Return only valid JSON matching the schema provided. \
Do not include markdown code fences, comments, or any text outside the JSON object."""

_USER_PROMPT_TEMPLATE = """\
Analyze the following {doc_type} from the {meeting_date} MPC meeting.

Return this exact JSON structure with no additional text:
{{
  "overall_score": <float: composite hawkish/dovish score [-1.0 to +1.0]>,
  "score_confidence": <float: your confidence [0.0 to 1.0]>,
  "inflation_stance": <float: how alarmed is the committee about inflation? [-1.0 to +1.0]>,
  "growth_stance": <float: how optimistic about growth? [-1.0 to +1.0]>,
  "liquidity_stance": <float: tightening vs accommodating liquidity? [-1.0 to +1.0]>,
  "rate_guidance": <float: forward guidance — cuts ahead vs hikes ahead? [-1.0 to +1.0]>,
  "fx_external_stance": <float: defensive vs tolerant of rupee depreciation? [-1.0 to +1.0]>,
  "key_phrases": ["phrase 1", "phrase 2", "phrase 3"],
  "narrative_para_1": "<paragraph 1: 'How to read this document' — objective, institutional tone>",
  "narrative_para_2": "<paragraph 2: 'Practical takeaway / Investment implication' — Bloomberg/FT analyst level>"
}}

SCORING GUIDANCE:
- "Withdrawal of accommodation" = strongly hawkish (+0.7 to +0.9)
- "Remain accommodative" = strongly dovish (-0.7 to -0.9)
- Unanimous votes for hold after a hiking cycle = mildly dovish (-0.1 to -0.3)
- Vote splits toward cuts = moderately dovish (-0.4 to -0.6)
- Explicit rate cuts = strongly dovish (-0.7 to -1.0)
- Explicit rate hikes = strongly hawkish (+0.7 to +1.0)
- "Remain focused on inflation" with no growth concerns = moderately hawkish (+0.3 to +0.6)
- Balanced language (inflation concerns + growth support) = near neutral (-0.2 to +0.2)
- Pauses in hiking cycles are mildly dovish, not neutral
- key_phrases: 3–5 pivotal sentences or phrases that most influenced your score
- narrative_para_1 must begin with "**How to read this document:**"
- narrative_para_2 must begin with "**Practical takeaway:**"

DOCUMENT TEXT:
{text}"""


class LLMScorer:
    """Scores a single document text via Claude API."""

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or LLM_DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. Run: pip install anthropic"
                )
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                # Try dotenv
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    api_key = os.environ.get("ANTHROPIC_API_KEY")
                except ImportError:
                    pass
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not found in environment or .env file"
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def score(
        self,
        text: str,
        doc_type: str,
        meeting_date: str,
        *,
        use_fallback_model: bool = False,
    ) -> Optional[dict]:
        """
        Score a document. Returns parsed dict or None on failure.
        Attempts re-prompt once if JSON is invalid.
        """
        model = LLM_FALLBACK_MODEL if use_fallback_model else self.model
        prompt = _USER_PROMPT_TEMPLATE.format(
            doc_type=_format_doc_type(doc_type),
            meeting_date=meeting_date,
            text=text,
        )

        log.info(
            "Scoring %s %s with %s (~%d words)",
            doc_type, meeting_date, model, len(text.split())
        )

        client = self._get_client()

        # First attempt
        result = self._call_api(client, model, prompt)
        if result is not None:
            return result

        # Re-prompt once with explicit JSON reminder
        log.warning(
            "First LLM attempt returned invalid JSON for %s %s — re-prompting",
            doc_type, meeting_date
        )
        retry_prompt = (
            prompt + "\n\nIMPORTANT: Your previous response was not valid JSON. "
            "Return ONLY the JSON object, with no text before or after it."
        )
        result = self._call_api(client, model, retry_prompt)
        if result is not None:
            return result

        log.error(
            "LLM scoring failed after 2 attempts for %s %s",
            doc_type, meeting_date
        )
        return None

    def _call_api(self, client, model: str, prompt: str) -> Optional[dict]:
        try:
            message = client.messages.create(
                model=model,
                max_tokens=LLM_MAX_OUTPUT_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = message.content[0].text.strip()
            return self._parse_and_validate(raw_text)
        except Exception as exc:
            log.error("Anthropic API call failed: %s", exc)
            return None

    def _parse_and_validate(self, raw_text: str) -> Optional[dict]:
        """Parse JSON response and validate required keys."""
        # Strip markdown code fences if present
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("JSON parse error: %s | raw: %s...", exc, raw_text[:200])
            return None

        # Validate required keys
        missing = _REQUIRED_KEYS - set(data.keys())
        if missing:
            log.warning("LLM response missing keys: %s", missing)
            return None

        # Validate score ranges
        score_keys = [
            "overall_score", "inflation_stance", "growth_stance",
            "liquidity_stance", "rate_guidance", "fx_external_stance",
        ]
        for key in score_keys:
            val = data.get(key)
            if val is not None and not (-1.0 <= float(val) <= 1.0):
                log.warning("Score %s=%s out of range [-1, 1]", key, val)
                data[key] = max(-1.0, min(1.0, float(val)))

        # Ensure key_phrases is a list
        if not isinstance(data.get("key_phrases"), list):
            data["key_phrases"] = []

        return data


def _format_doc_type(doc_type: str) -> str:
    """Convert internal doc_type code to human-readable label for the prompt."""
    return {
        "resolution": "Monetary Policy Committee Resolution (Policy Statement)",
        "minutes": "Monetary Policy Committee Minutes",
        "governor_statement": "Governor's Statement / Press Conference Remarks",
    }.get(doc_type, doc_type)
