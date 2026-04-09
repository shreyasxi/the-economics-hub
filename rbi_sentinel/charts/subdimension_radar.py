"""
rbi_sentinel/charts/subdimension_radar.py

Chart 04: Sub-Dimension Radar (Spider Chart)
Five axes: Inflation Stance, Growth Stance, Liquidity Stance, Rate Guidance, FX Stance.
Current meeting: filled navy polygon. Previous meeting: dashed overlay.

Layout fix: polar axes constrained to lower 70% of figure via subplots_adjust,
leaving a clean header zone for title, subtitle, and top rule.
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
_ANGLES += _ANGLES[:1]   # Close the polygon


def generate(
    current_scores: dict,
    previous_scores: Optional[dict],
    current_date: str,
    previous_date: Optional[str],
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    EconStyle.apply_global_style()

    # Square figure — leaves room for header at top
    fig = plt.figure(figsize=(7.5, 7.0))
    fig.patch.set_facecolor(EconStyle.BACKGROUND)

    # Polar axes occupy the lower 68% of the figure
    ax = fig.add_axes(
        [0.10, 0.04, 0.80, 0.62],   # [left, bottom, width, height]
        projection="polar",
    )
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Reference rings ────────────────────────────────────────────────────────
    ring_specs = [
        (0.0,  "-1.0", False),
        (0.5,  "-0.5", False),
        (1.0,  "0",    True),   # Neutral ring — solid black
        (1.5,  "+0.5", False),
        (2.0,  "+1.0", False),
    ]
    ring_angles = np.linspace(0, 2 * math.pi, 100)

    for rv, rl, is_neutral in ring_specs:
        ax.plot(
            ring_angles, [rv] * 100,
            color="#000000" if is_neutral else "#C0C0C0",
            lw=0.8 if is_neutral else 0.4,
            ls="-" if is_neutral else "--",
            alpha=0.7 if is_neutral else 0.5,
            zorder=1,
        )
        if rv > 0:
            ax.text(
                0, rv + 0.07, rl,
                ha="center", va="bottom",
                fontsize=6, color="#808080",
            )

    # ── Axis spokes ────────────────────────────────────────────────────────────
    for angle in _ANGLES[:-1]:
        ax.plot([angle, angle], [0, 2.0], color="#C0C0C0", lw=0.4, zorder=1)

    # ── Current meeting polygon ────────────────────────────────────────────────
    curr_vals = _extract_values(current_scores) + [0]
    curr_vals[-1] = curr_vals[0]   # Close

    ax.fill(
        _ANGLES, curr_vals,
        color=EconStyle.get_color("us"),
        alpha=0.25, zorder=3,
    )
    ax.plot(
        _ANGLES, curr_vals,
        color=EconStyle.get_color("us"),
        lw=2.5, zorder=4,
    )
    ax.scatter(
        _ANGLES[:-1], curr_vals[:-1],
        color=EconStyle.get_color("us"), s=45, zorder=5,
    )

    # ── Previous meeting overlay ───────────────────────────────────────────────
    if previous_scores and previous_date:
        prev_vals = _extract_values(previous_scores) + [0]
        prev_vals[-1] = prev_vals[0]
        ax.plot(
            _ANGLES, prev_vals,
            color=EconStyle.get_color("india"),
            lw=1.8, ls="--", zorder=3, alpha=0.80,
        )
        ax.scatter(
            _ANGLES[:-1], prev_vals[:-1],
            color=EconStyle.get_color("india"),
            s=28, zorder=4, alpha=0.80,
        )

    # ── Axis labels — padded outward ───────────────────────────────────────────
    ax.set_xticks(_ANGLES[:-1])
    ax.set_xticklabels(
        [label for _, label in _DIMENSIONS],
        fontsize=8.5, fontweight="600", color="#1A1A1A",
    )
    ax.tick_params(pad=16)   # Push labels further from polygon edge

    ax.set_yticks([])
    ax.set_ylim(0, 2.20)
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    # ── Legend — bottom of figure, below polar axes ────────────────────────────
    import matplotlib.lines as mlines
    curr_handle = mlines.Line2D([], [], color=EconStyle.get_color("us"),
                                lw=2.5, label=f"Current ({current_date})")
    prev_handle = mlines.Line2D([], [], color=EconStyle.get_color("india"),
                                lw=1.8, ls="--",
                                label=f"Previous ({previous_date or 'n/a'})")
    handles = [curr_handle] + ([prev_handle] if previous_scores else [])

    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.00),
        ncol=2,
        fontsize=8.5, frameon=False,
    )

    # ── Header zone: top rule + title + subtitle ───────────────────────────────
    # Top rule at 97%
    fig.add_artist(
        plt.Line2D(
            [0.06, 0.94], [0.965, 0.965],
            transform=fig.transFigure,
            color="#000000", lw=1.5, zorder=10,
        )
    )

    if mode == "newsletter":
        title = "Breaking Down the RBI's Stance"
        subtitle = f"5-dimension policy breakdown · Current ({current_date}) vs. Previous ({previous_date or 'n/a'})"
    else:
        title = "RBI Sentiment Sub-Dimensions — Policy Stance Breakdown"
        subtitle = (
            f"\u22121.0 = Extremely Dovish · +1.0 = Extremely Hawkish "
            f"· Navy = {current_date} · Orange = {previous_date or 'n/a'}"
        )

    fig.text(
        0.06, 0.945, title,
        fontsize=EconStyle.FONT_SIZE_TITLE,
        fontweight="800",
        color=EconStyle.TEXT_TITLE,
        transform=fig.transFigure,
        va="top",
    )
    fig.text(
        0.06, 0.910, subtitle,
        fontsize=EconStyle.FONT_SIZE_SUBTITLE,
        color=EconStyle.TEXT_BODY,
        transform=fig.transFigure,
        va="top",
        wrap=True,
    )

    EconStyle.add_source(fig, "RBI MPC Documents  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved subdimension radar to %s", output_path)


def _extract_values(scores: dict) -> list[float]:
    """Map sub-dimension scores from [-1, +1] → [0, 2] for radar display."""
    values = []
    for key, _ in _DIMENSIONS:
        raw = scores.get(key)
        if raw is None:
            raw = 0.0
        mapped = float(raw) + 1.0
        values.append(max(0.05, mapped))
    return values
