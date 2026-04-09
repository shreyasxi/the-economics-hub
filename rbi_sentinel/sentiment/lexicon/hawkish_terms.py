"""
rbi_sentinel/sentiment/lexicon/hawkish_terms.py

Curated hawkish phrase list for RBI MPC documents.
Weights are on a [0.0, 1.0] scale — higher = stronger hawkish signal.

IMPORTANT: This is NOT a generic finance sentiment lexicon.
Every entry has been chosen for RBI-specific vocabulary.
"""

# Format: (phrase, weight)
# Phrases are matched case-insensitively, longest match wins on overlap.

HAWKISH_TERMS: list[tuple[str, float]] = [

    # ── Stance / Posture (strongest signals) ─────────────────────────────────
    ("withdrawal of accommodation",         1.00),
    ("withdrawing accommodation",           1.00),
    ("unwavering commitment to price stability", 0.90),
    ("price stability as the cornerstone",  0.85),
    ("remain focused on withdrawal",        0.85),
    ("committed to bringing inflation",     0.80),
    ("keep inflation durably aligned",      0.80),
    ("unambiguously focused on inflation",  0.85),

    # ── Rate / Policy Action ──────────────────────────────────────────────────
    ("repo rate increase",                  0.90),
    ("increase in the repo rate",           0.90),
    ("hike in the policy rate",             0.90),
    ("raise the repo rate",                 0.90),
    ("further rate increases",              0.80),
    ("tightening of monetary policy",       0.80),
    ("policy rate increase",                0.85),
    ("further tightening cannot be ruled out", 0.70),
    ("keep rates elevated",                 0.75),
    ("rates will need to stay elevated",    0.75),
    ("not yet time to cut",                 0.65),
    ("pause does not mean pivot",           0.70),
    ("do not be misled by pause",           0.70),

    # ── Inflation Alarm ───────────────────────────────────────────────────────
    ("inflation remains elevated",          0.75),
    ("inflation is uncomfortably high",     0.80),
    ("inflation above target",              0.65),
    ("persistent inflationary pressures",   0.70),
    ("upside risks to inflation",           0.65),
    ("inflation risks are tilted to the upside", 0.70),
    ("stubborn inflation",                  0.75),
    ("inflation outlook remains uncertain", 0.55),
    ("food inflation pressures",            0.40),
    ("core inflation sticky",               0.65),
    ("inflation trajectory",                0.35),   # context-dependent, moderate weight
    ("inflationary impulses",               0.60),
    ("second round effects",                0.65),
    ("pass-through to core inflation",      0.60),

    # ── Vigilance / Monitoring ────────────────────────────────────────────────
    ("remain vigilant",                     0.55),
    ("be vigilant",                         0.55),
    ("heightened vigilance",                0.60),
    ("watchful",                            0.45),
    ("monitor closely",                     0.35),
    ("closely monitor",                     0.35),
    ("remain alert",                        0.50),
    ("readiness to act",                    0.60),
    ("prepared to act",                     0.60),
    ("act decisively",                      0.65),
    ("ready to deploy all instruments",     0.65),

    # ── Liquidity Tightening ──────────────────────────────────────────────────
    ("absorb liquidity",                    0.55),
    ("liquidity absorption",                0.55),
    ("draining liquidity",                  0.65),
    ("tighten liquidity conditions",        0.65),
    ("normalisation of liquidity",          0.50),
    ("standing deposit facility",           0.35),  # SDF = hawkish liquidity tool
    ("variable rate reverse repo",          0.35),

    # ── External / FX ─────────────────────────────────────────────────────────
    ("defend the rupee",                    0.60),
    ("rupee depreciation risks",            0.55),
    ("currency depreciation pressures",     0.55),
    ("intervene in forex markets",          0.50),
    ("forex reserve adequacy",              0.35),

    # ── Growth / Resilience (reduces urgency to ease) ─────────────────────────
    ("domestic growth remains robust",      0.45),
    ("growth impulses are strong",          0.45),
    ("economy is resilient",                0.40),
    ("economic activity is buoyant",        0.45),
]


def get_hawkish_terms() -> list[tuple[str, float]]:
    """Return the full hawkish terms list."""
    return HAWKISH_TERMS
