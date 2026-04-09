"""
rbi_sentinel/sentiment/lexicon/dovish_terms.py

Curated dovish phrase list for RBI MPC documents.
Weights are on a [0.0, 1.0] scale — higher = stronger dovish signal.
All weights are returned as negative by the scorer.

IMPORTANT: This is NOT a generic finance sentiment lexicon.
Every entry has been chosen for RBI-specific vocabulary.
"""

# Format: (phrase, weight)
# Weights are POSITIVE here — the scorer negates them to produce negative scores.

DOVISH_TERMS: list[tuple[str, float]] = [

    # ── Stance / Posture (strongest signals) ─────────────────────────────────
    ("accommodative stance",                1.00),
    ("remain accommodative",                0.95),
    ("accommodative as long as necessary",  0.90),
    ("continue with accommodative",         0.90),
    ("supportive monetary policy",          0.85),
    ("policy will remain supportive",       0.85),
    ("focus on growth revival",             0.80),
    ("nurture the recovery",                0.75),
    ("support the economic recovery",       0.80),
    ("provide necessary support",           0.70),

    # ── Rate / Policy Action ──────────────────────────────────────────────────
    ("repo rate decrease",                  0.95),
    ("cut in the repo rate",                0.95),
    ("reduce the repo rate",                0.95),
    ("rate cut",                            0.90),
    ("ease monetary policy",                0.85),
    ("policy rate reduction",               0.90),
    ("lower interest rates",                0.85),
    ("further easing",                      0.80),
    ("scope for rate cuts",                 0.75),
    ("pivot to rate cuts",                  0.80),
    ("easing cycle",                        0.80),
    ("calibrated easing",                   0.75),

    # ── Inflation Comfort / Moderation ────────────────────────────────────────
    ("inflation is expected to moderate",   0.70),
    ("inflation to return to target",       0.65),
    ("inflation trajectory is favourable",  0.70),
    ("headline inflation softening",        0.65),
    ("benign inflation outlook",            0.70),
    ("inflation within tolerance band",     0.60),
    ("inflation risks are balanced",        0.55),
    ("inflation risks have receded",        0.65),
    ("downside risks to inflation",         0.55),
    ("food price pressures abating",        0.55),
    ("core inflation easing",               0.60),
    ("disinflation underway",               0.65),

    # ── Growth Concern ────────────────────────────────────────────────────────
    ("downside risks to growth",            0.65),
    ("growth concerns remain",              0.65),
    ("growth momentum has moderated",       0.60),
    ("slowdown in economic activity",       0.65),
    ("output gap remains negative",         0.70),
    ("below potential growth",              0.65),
    ("demand conditions are subdued",       0.60),
    ("private investment remains weak",     0.55),
    ("credit growth has moderated",         0.50),
    ("consumer confidence is weak",         0.50),

    # ── Liquidity Accommodation ───────────────────────────────────────────────
    ("inject liquidity",                    0.60),
    ("infuse durable liquidity",            0.65),
    ("durable liquidity",                   0.55),
    ("open market operations",              0.40),
    ("variable rate repo",                  0.40),   # VRR = liquidity injection
    ("system liquidity in surplus",         0.50),
    ("ensure adequate liquidity",           0.55),
    ("comfortable liquidity conditions",    0.55),
    ("monetary transmission",               0.35),   # Emphasis = wants rates to filter down

    # ── External / FX ─────────────────────────────────────────────────────────
    ("orderly depreciation",                0.45),
    ("rupee depreciation is manageable",    0.45),
    ("external sector is resilient",        0.35),

    # ── Forward Guidance (Dovish) ─────────────────────────────────────────────
    ("rates on hold for an extended period", 0.55),  # Hold after hiking = mildly dovish
    ("pause in rate action",                0.45),
    ("no immediate need for action",        0.55),
    ("wait and watch",                      0.40),
    ("data-dependent approach",             0.30),   # Neutral but slight dovish lean in RBI context
]


def get_dovish_terms() -> list[tuple[str, float]]:
    """Return the full dovish terms list."""
    return DOVISH_TERMS
