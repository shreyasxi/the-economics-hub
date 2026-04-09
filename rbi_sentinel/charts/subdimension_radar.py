"""
rbi_sentinel/charts/subdimension_radar.py

Chart 04: Sub-Dimension Radar (Spider Chart)
Five axes: Inflation Stance, Growth Stance, Liquidity Stance, Rate Guidance, FX Stance.

Layout: polar axes occupy centre of figure; title header sits in a dedicated
top strip; legend anchored inside the axes (upper-right); source footnote stays
clear at the very bottom. All label positions are explicit so nothing collides.
"""

import logging
import math
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.lines as mlines
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
# Rotate so "Inflation Stance" is at the right (3 o'clock), not top
# Top axis will be Growth Stance — less cramped with header
_ANGLES = [n / float(_N) * 2 * math.pi for n in range(_N)]
_ANGLES += _ANGLES[:1]


def generate(
    current_scores: dict,
    previous_scores: Optional[dict],
    current_date: str,
    previous_date: Optional[str],
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    EconStyle.apply_global_style()

    # Wide figure — plenty of room for header + chart + source
    fig = plt.figure(figsize=(8.5, 7.2))
    fig.patch.set_facecolor(EconStyle.BACKGROUND)

    # ── Top rule + title strip (figure-level, not axes) ───────────────────────
    # Rule at 97%
    fig.add_artist(plt.Line2D(
        [0.06, 0.94], [0.965, 0.965],
        transform=fig.transFigure,
        color="#000000", lw=1.5, zorder=10,
    ))

    if mode == "newsletter":
        title   = "Breaking Down the RBI's Stance"
        subtitle = (
            f"Five-dimension policy breakdown · "
            f"Current ({current_date}) vs. Previous ({previous_date or 'n/a'})"
        )
    else:
        title   = "RBI Sentiment Sub-Dimensions — Policy Stance Breakdown"
        subtitle = (
            f"\u22121.0 = Dovish · +1.0 = Hawkish · "
            f"Navy = {current_date}   Orange = {previous_date or 'n/a'}"
        )

    fig.text(0.06, 0.945, title,
             fontsize=EconStyle.FONT_SIZE_TITLE, fontweight="800",
             color=EconStyle.TEXT_TITLE, transform=fig.transFigure, va="top")
    fig.text(0.06, 0.910, subtitle,
             fontsize=EconStyle.FONT_SIZE_SUBTITLE, color=EconStyle.TEXT_BODY,
             transform=fig.transFigure, va="top")

    # ── Polar axes — centred, clear of header and source ──────────────────────
    # [left, bottom, width, height] in figure fraction
    ax = fig.add_axes([0.08, 0.12, 0.84, 0.74], projection="polar")
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Reference rings ───────────────────────────────────────────────────────
    ring_angles = np.linspace(0, 2 * math.pi, 120)
    ring_specs = [
        (0.0,  None,   False),
        (0.5,  "−0.5", False),
        (1.0,  "0",    True),   # neutral ring — solid
        (1.5,  "+0.5", False),
        (2.0,  "+1.0", False),
    ]
    for rv, rl, is_neutral in ring_specs:
        ax.plot(ring_angles, [rv] * 120,
                color="#000000" if is_neutral else "#C8C8C8",
                lw=0.9 if is_neutral else 0.4,
                ls="-" if is_neutral else "--",
                alpha=0.75 if is_neutral else 0.55, zorder=1)
        if rl and rv > 0:
            # Place ring label at angle=0 (right side) to avoid top-axis collision
            ax.text(0.0, rv + 0.08, rl,
                    ha="center", va="bottom", fontsize=6, color="#888888")

    # ── Axis spokes ───────────────────────────────────────────────────────────
    for angle in _ANGLES[:-1]:
        ax.plot([angle, angle], [0, 2.0], color="#C8C8C8", lw=0.4, zorder=1)

    # ── Current meeting polygon ────────────────────────────────────────────────
    curr_vals = _extract_values(current_scores)
    curr_vals_closed = curr_vals + [curr_vals[0]]

    ax.fill(_ANGLES, curr_vals_closed,
            color=EconStyle.get_color("us"), alpha=0.22, zorder=3)
    ax.plot(_ANGLES, curr_vals_closed,
            color=EconStyle.get_color("us"), lw=2.5, zorder=4)
    ax.scatter(_ANGLES[:-1], curr_vals,
               color=EconStyle.get_color("us"), s=50, zorder=5)

    # ── Previous meeting overlay ───────────────────────────────────────────────
    if previous_scores and previous_date:
        prev_vals = _extract_values(previous_scores)
        prev_vals_closed = prev_vals + [prev_vals[0]]
        ax.plot(_ANGLES, prev_vals_closed,
                color=EconStyle.get_color("india"), lw=1.8, ls="--",
                zorder=3, alpha=0.85)
        ax.scatter(_ANGLES[:-1], prev_vals,
                   color=EconStyle.get_color("india"), s=30, zorder=4, alpha=0.85)

    # ── Axis labels — generous pad so FX/External clears the bottom ───────────
    ax.set_xticks(_ANGLES[:-1])
    ax.set_xticklabels(
        [label for _, label in _DIMENSIONS],
        fontsize=9, fontweight="600", color="#1A1A1A",
    )
    ax.tick_params(pad=18)

    ax.set_yticks([])
    ax.set_ylim(0, 2.30)
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    # ── Legend — inside axes, upper-right corner ───────────────────────────────
    curr_handle = mlines.Line2D([], [], color=EconStyle.get_color("us"),
                                lw=2.5, label=f"Current ({current_date})")
    handles = [curr_handle]
    if previous_scores and previous_date:
        prev_handle = mlines.Line2D([], [], color=EconStyle.get_color("india"),
                                    lw=1.8, ls="--",
                                    label=f"Previous ({previous_date})")
        handles.append(prev_handle)

    ax.legend(
        handles=handles,
        loc="upper right",
        bbox_to_anchor=(1.40, 1.22),   # anchored outside polar plot, upper-right
        fontsize=8.5, frameon=False,
    )

    # ── Source footnote (figure-level, stays clear of everything) ────────────
    EconStyle.add_source(fig, "RBI MPC Documents  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved subdimension radar to %s", output_path)


def _extract_values(scores: dict) -> list[float]:
    """Map sub-dimension scores [-1, +1] → [0, 2] for radar display."""
    values = []
    for key, _ in _DIMENSIONS:
        raw = scores.get(key)
        if raw is None:
            raw = 0.0
        mapped = float(raw) + 1.0
        values.append(max(0.05, mapped))
    return values
