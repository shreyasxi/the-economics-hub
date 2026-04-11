"""
rbi_sentinel/charts/subdimension_radar.py

Chart 04: Sub-Dimension Radar (Spider Chart)
Five axes: Inflation Stance, Growth Stance, Liquidity Stance, Rate Guidance, FX Stance.
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
# We will dynamically set these angles inside the function based on a top-aligned, clockwise polar projection
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

    # --- FIX 1: Clean Architecture ---
    # Use standard subplots so we can control margins predictably
    fig, ax = plt.subplots(figsize=(7.5, 7.5), subplot_kw=dict(projection="polar"))
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # --- FIX 3: Rotate to Clockwise ---
    # Forces the first dimension (Inflation) to 12 o'clock and reads like a clock
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)

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
                color="#000000" if is_neutral else "#999999",  # Darker grey
                lw=1.2 if is_neutral else 0.8,                 # Thicker lines
                ls="-" if is_neutral else "--",
                alpha=0.85 if is_neutral else 0.75, zorder=1)  # Higher opacity
        if rl and rv > 0:
            ax.text(0.0, rv + 0.08, rl,
                    ha="center", va="bottom", fontsize=7, color="#555555", zorder=6)

    # ── Axis spokes ───────────────────────────────────────────────────────────
    for angle in _ANGLES[:-1]:
        # Darkened and thickened the spoke lines
        ax.plot([angle, angle], [0, 2.0], color="#999999", lw=0.8, zorder=1)

    # ── Current meeting polygon ────────────────────────────────────────────────
    curr_vals = _extract_values(current_scores)
    curr_vals_closed = curr_vals + [curr_vals[0]]

    ax.fill(_ANGLES, curr_vals_closed,
            color=EconStyle.get_color("us"), alpha=0.25, zorder=3)
    ax.plot(_ANGLES, curr_vals_closed,
            color=EconStyle.get_color("us"), lw=2.5, zorder=4)
    ax.scatter(_ANGLES[:-1], curr_vals,
               color=EconStyle.get_color("us"), s=60, zorder=5)

    # ── Previous meeting overlay ───────────────────────────────────────────────
    if previous_scores and previous_date:
        prev_vals = _extract_values(previous_scores)
        prev_vals_closed = prev_vals + [prev_vals[0]]
        ax.plot(_ANGLES, prev_vals_closed,
                color=EconStyle.get_color("pink"), lw=2.0, ls="--",
                zorder=3, alpha=0.9)
        ax.scatter(_ANGLES[:-1], prev_vals,
                   color=EconStyle.get_color("pink"), s=40, zorder=4, alpha=0.9)

    # ── Axis labels ───────────────────────────────────────────────────────────
    ax.set_xticks(_ANGLES[:-1])
    ax.set_xticklabels(
        [label for _, label in _DIMENSIONS],
        fontsize=14, fontweight="800", color="#1A1A1A",
    )
    # Pushes the labels outward so they don't clip the polygon
    ax.tick_params(pad=0.001)

    # --- FIX 4: Expand the invisible ceiling ---
    # Raising ylim to 2.50 shrinks the chart inward, creating perfect margins
    ax.set_yticks([])
    ax.set_ylim(0, 2.50)
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    # --- FIX 2: Empower the Legend & Declutter Title ---
    curr_handle = mlines.Line2D([], [], color=EconStyle.get_color("us"),
                                lw=2.5, label=f"Current ({current_date})")
    handles = [curr_handle]
    if previous_scores and previous_date:
        prev_handle = mlines.Line2D([], [], color=EconStyle.get_color("pink"),
                                    lw=2.0, ls="--",
                                    label=f"Previous ({previous_date})")
        handles.append(prev_handle)

    # Center the legend horizontally above the radar chart
    # Place legend at the top right corner of the chart body
    ax.legend(
        handles=handles,
        loc="upper right",
        bbox_to_anchor=(1.05, 1.0), 
        ncol=1, 
        fontsize=11, frameon=False,
    )
 
    if mode == "newsletter":
        title = "Breaking Down the RBI's Stance"
        subtitle = "Five-dimension policy breakdown"
    else:
        title = "RBI's Policy Stance Breakdown"
        subtitle = "Comparing current vs. previous policy sentiment across five key dimensions."

    # 1. Fix distance between Title and Subtitle
    # We move the subtitle up from 0.91 to 0.92, and the line up from 0.88 to 0.89.
    fig.text(0.05, 0.95, title, fontsize=18, fontweight="bold", color="#1A1A1A", ha="left")
    fig.text(0.05, 0.92, subtitle, fontsize=11, color="#1A1A1A", ha="left")
    fig.add_artist(mlines.Line2D([0.05, 0.95], [0.89, 0.89], color="#000000", lw=1.5))
    
    EconStyle.add_source(fig, "RBI MPC Documents")

    # 2. Fix the huge gap between the header and the chart
    # By increasing the chart height from 0.65 to 0.75, the chart reaches further up 
    # the page, closing the empty space between the "Inflation Stance" label and the black line.
    ax.set_position([0.05, 0.05, 0.90, 0.75])
   

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