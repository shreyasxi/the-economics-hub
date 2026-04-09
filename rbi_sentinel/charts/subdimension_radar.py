"""
rbi_sentinel/charts/subdimension_radar.py

Chart 04: Sub-Dimension Radar (Spider Chart)
Five axes: Inflation Stance, Growth Stance, Liquidity Stance, Rate Guidance, FX Stance.
Current meeting: filled navy polygon.
Previous meeting: dashed overlay for comparison.
"""

import logging
import math
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np

from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.subdimension_radar")

_DIMENSIONS = [
    ("inflation_stance",    "Inflation\nStance"),
    ("growth_stance",       "Growth\nStance"),
    ("liquidity_stance",    "Liquidity\nStance"),
    ("rate_guidance",       "Rate\nGuidance"),
    ("fx_external_stance",  "FX /\nExternal"),
]

_N = len(_DIMENSIONS)
_ANGLES = [n / float(_N) * 2 * math.pi for n in range(_N)]
_ANGLES += _ANGLES[:1]  # Close the polygon


def generate(
    current_scores: dict,
    previous_scores: Optional[dict],
    current_date: str,
    previous_date: Optional[str],
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    """
    Args:
        current_scores: Dict with dimension keys (from sentiment_scores table)
        previous_scores: Dict for previous meeting (optional overlay)
        current_date: Meeting date string for current meeting
        previous_date: Meeting date string for previous meeting
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
    """
    EconStyle.apply_global_style()

    fig, ax = plt.subplots(
        figsize=(7.0, 5.5),
        subplot_kw=dict(polar=True),
    )
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Radar rings (reference circles at -1, -0.5, 0, +0.5, +1) ─────────────
    # Radar uses [0, 2] scale internally: 0 = center, 1 = neutral (score 0), 2 = max
    ring_labels = ["-1.0", "-0.5", "0", "+0.5", "+1.0"]
    ring_values = [0.0, 0.5, 1.0, 1.5, 2.0]  # Mapped from [-1, +1] → [0, 2]

    for rv, rl in zip(ring_values, ring_labels):
        ring_angles = np.linspace(0, 2 * math.pi, 100)
        ax.plot(
            ring_angles, [rv] * 100,
            color="#D6D6D6" if rv != 1.0 else "#000000",
            lw=0.5 if rv != 1.0 else 0.8,
            ls="-" if rv == 1.0 else "--",
            alpha=0.5 if rv != 1.0 else 0.7,
            zorder=1,
        )
        if rv > 0:
            ax.text(
                0, rv + 0.05, rl,
                ha="center", va="bottom",
                fontsize=6.5, color="#606060",
            )

    # ── Axis lines ────────────────────────────────────────────────────────────
    for angle in _ANGLES[:-1]:
        ax.plot([angle, angle], [0, 2.0], color="#D6D6D6", lw=0.5, zorder=1)

    # ── Current meeting polygon ───────────────────────────────────────────────
    current_vals = _extract_values(current_scores)
    current_vals += current_vals[:1]

    ax.fill(
        _ANGLES, current_vals,
        color=EconStyle.get_color("us"),   # Navy
        alpha=0.30, zorder=3,
    )
    ax.plot(
        _ANGLES, current_vals,
        color=EconStyle.get_color("us"),
        lw=2.2, zorder=4, label=f"Current ({current_date})",
    )
    ax.scatter(
        _ANGLES[:-1], current_vals[:-1],
        color=EconStyle.get_color("us"),
        s=35, zorder=5,
    )

    # ── Previous meeting overlay ──────────────────────────────────────────────
    if previous_scores and previous_date:
        prev_vals = _extract_values(previous_scores)
        prev_vals += prev_vals[:1]
        ax.plot(
            _ANGLES, prev_vals,
            color=EconStyle.get_color("india"),   # Saffron
            lw=1.5, ls="--", zorder=3,
            label=f"Previous ({previous_date})", alpha=0.75,
        )
        ax.scatter(
            _ANGLES[:-1], prev_vals[:-1],
            color=EconStyle.get_color("india"),
            s=20, zorder=4, alpha=0.75,
        )

    # ── Axis labels ───────────────────────────────────────────────────────────
    ax.set_xticks(_ANGLES[:-1])
    ax.set_xticklabels(
        [label for _, label in _DIMENSIONS],
        fontsize=8, fontweight="600", color="#222222",
    )
    ax.tick_params(pad=10)

    ax.set_yticks([])
    ax.set_ylim(0, 2.05)

    # ── Legend ────────────────────────────────────────────────────────────────
    ax.legend(
        loc="upper right",
        bbox_to_anchor=(1.3, 1.1),
        fontsize=7.5, frameon=False,
    )

    # ── Spine / grid cleanup ──────────────────────────────────────────────────
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    # ── Title & branding ──────────────────────────────────────────────────────
    # For polar subplots, add_top_rule needs special handling — place as fig text
    fig.text(
        0.08, 0.93, "",
        transform=fig.transFigure,
    )

    if mode == "newsletter":
        title = "Breaking Down the RBI's Stance"
        subtitle = "Five-dimension policy sentiment breakdown · current vs. previous meeting"
    else:
        title = "RBI Sentiment Sub-Dimensions — Policy Stance Breakdown"
        subtitle = (
            "All dimensions: −1.0 = Extremely Dovish · +1.0 = Extremely Hawkish · "
            f"Blue = {current_date} · Orange dashed = {previous_date or 'n/a'}"
        )

    # Title via fig.text since polar ax doesn't support set_title() well
    fig.text(
        0.08, 0.96, title,
        fontsize=EconStyle.FONT_SIZE_TITLE,
        fontweight="800",
        color=EconStyle.TEXT_TITLE,
        transform=fig.transFigure,
    )
    fig.text(
        0.08, 0.915, subtitle,
        fontsize=EconStyle.FONT_SIZE_SUBTITLE,
        color=EconStyle.TEXT_BODY,
        transform=fig.transFigure,
    )

    # Top rule
    fig.add_artist(
        plt.Line2D(
            [0.08, 0.92], [0.97, 0.97],
            transform=fig.transFigure,
            color="#000000", lw=1.5,
        )
    )

    EconStyle.add_source(fig, "RBI MPC Documents  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved subdimension radar to %s", output_path)


def _extract_values(scores: dict) -> list[float]:
    """
    Extract sub-dimension values and convert from [-1, +1] to [0, 2] for radar display.
    0 = center (score -1), 1.0 = neutral (score 0), 2.0 = outer (score +1).
    """
    values = []
    for key, _ in _DIMENSIONS:
        raw = scores.get(key)
        if raw is None:
            raw = 0.0  # Default to neutral if missing
        # Map [-1, +1] → [0, 2]
        mapped = float(raw) + 1.0
        values.append(max(0.05, mapped))  # Minimum visible size
    return values
