"""Essay shelf configuration for Research & About.

Pinned Substack essays and the window for featuring a recent post live here.
The signal board is computed separately from config/signals_settings.py.
"""

# ── The essay shelf ────────────────────────────────────────────────────────
SUBSTACK_URL = "https://economicshub.substack.com"

# Your best pieces, by the last part of their Substack address
# (economicshub.substack.com/p/<this>), in the order they should appear.
PINNED = [
    "iran-war-is-more-than-just-oil",
    "will-the-ai-boom-actually-hollow",
    "commodities-dominate-the-supreme",
    "the-takaichi-trade-indias-statistical",
]

# A new post leads the shelf, marked New, for this many days. After that it
# drops back among the pinned ones (or out, if it is not pinned), so a quiet
# spell never shows as a gap on the page.
NEW_FOR_DAYS = 30
