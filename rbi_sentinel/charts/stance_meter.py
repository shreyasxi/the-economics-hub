"""
rbi_sentinel/charts/stance_meter.py

Chart 01: RBI Policy Stance Gauge
Semicircular dial from -1.0 (Extremely Dovish) to +1.0 (Extremely Hawkish).
Custom matplotlib implementation — no external gauge library.
"""

import logging
import math
from pathlib import Path
from typing import Optional

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from rbi_sentinel.sentiment.score_normalizer import score_to_label
from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.stance_meter")

# Gauge zone definitions: (min_score, max_score, color, label)
_ZONES = [
    (-1.00, -0.60, "#003366", "Extremely\nDovish"),   # Deep navy
    (-0.60, -0.20, "#4472C4", "Dovish"),               # Medium blue
    (-0.20,  0.20, "#A6A6A6", "Neutral"),              # Grey
    ( 0.20,  0.60, "#C9563C", "Hawkish"),              # Orange-red
    ( 0.60,  1.00, "#CC0000", "Extremely\nHawkish"),   # Deep red
]

# Gauge spans 180 degrees (semicircle)
# -1.0 = 180° (left), +1.0 = 0° (right), 0.0 = 90° (top)
_GAUGE_MIN_ANGLE = 180.0
_GAUGE_MAX_ANGLE = 0.0


def _score_to_angle(score: float) -> float:
    """Convert score [-1, +1] to angle in degrees (180 → 0)."""
    normalized = (score + 1.0) / 2.0          # Map [-1,1] → [0,1]
    angle = _GAUGE_MIN_ANGLE - normalized * 180.0  # Map [0,1] → [180°,0°]
    return angle


def generate(
    composite_score: float,
    meeting_date: str,
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    """
    Generate the stance meter chart.

    Args:
        composite_score: [-1.0, +1.0]
        meeting_date: "YYYY-MM-DD"
        output_path: Full path for the output PNG
        mode: "dashboard" or "newsletter"
    """
    EconStyle.apply_global_style()

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_STANDARD)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    fig.patch.set_edgecolor("#000000")
    fig.patch.set_linewidth(1.5)

    ax.set_facecolor(EconStyle.BACKGROUND)
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-0.55, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Draw colour arc zones ─────────────────────────────────────────────────
    outer_r = 1.0
    inner_r = 0.55
    n_points = 100

    for zone_min, zone_max, color, label in _ZONES:
        angle_start = _score_to_angle(zone_max)   # reversed: higher score = lower angle
        angle_end   = _score_to_angle(zone_min)

        angles = np.linspace(
            math.radians(angle_start), math.radians(angle_end), n_points
        )

        outer_x = outer_r * np.cos(angles)
        outer_y = outer_r * np.sin(angles)
        inner_x = inner_r * np.cos(angles[::-1])
        inner_y = inner_r * np.sin(angles[::-1])

        xs = np.concatenate([outer_x, inner_x])
        ys = np.concatenate([outer_y, inner_y])

        ax.fill(xs, ys, color=color, alpha=0.90, zorder=2)

        # Zone label — positioned at midpoint angle, just outside the arc
        mid_angle = math.radians((angle_start + angle_end) / 2)
        lx = 1.18 * math.cos(mid_angle)
        ly = 1.18 * math.sin(mid_angle)
        ax.text(
            lx, ly, label,
            ha="center", va="center",
            fontsize=6.5, fontweight="600",
            color="#222222",
            linespacing=1.2,
            zorder=5,
        )

    # ── Tick marks at -1, -0.5, 0, +0.5, +1 ─────────────────────────────────
    tick_scores = [-1.0, -0.5, 0.0, 0.5, 1.0]
    tick_labels = ["-1.0", "-0.5", "0", "+0.5", "+1.0"]
    for ts, tl in zip(tick_scores, tick_labels):
        angle = math.radians(_score_to_angle(ts))
        tx_out = 1.03 * math.cos(angle)
        ty_out = 1.03 * math.sin(angle)
        tx_in  = 0.52 * math.cos(angle)
        ty_in  = 0.52 * math.sin(angle)
        ax.plot([tx_in, tx_out], [ty_in, ty_out], color="#000000", lw=1.0, zorder=4)

        # Label below the arc
        tx_label = 1.35 * math.cos(angle)
        ty_label = 1.35 * math.sin(angle)
        ax.text(
            tx_label, ty_label, tl,
            ha="center", va="center",
            fontsize=6.5, color="#404040", zorder=5,
        )

    # ── Needle ────────────────────────────────────────────────────────────────
    needle_angle = math.radians(_score_to_angle(composite_score))
    needle_length = 0.80
    nx = needle_length * math.cos(needle_angle)
    ny = needle_length * math.sin(needle_angle)

    # Needle shaft
    ax.annotate(
        "",
        xy=(nx, ny),
        xytext=(0, 0),
        arrowprops=dict(
            arrowstyle="-|>",
            color="#000000",
            lw=2.5,
            mutation_scale=12,
        ),
        zorder=7,
    )

    # Needle pivot circle
    pivot = plt.Circle((0, 0), 0.06, color="#000000", zorder=8)
    ax.add_patch(pivot)
    pivot_inner = plt.Circle((0, 0), 0.04, color="#FFFFFF", zorder=9)
    ax.add_patch(pivot_inner)

    # ── Score annotation ──────────────────────────────────────────────────────
    label = score_to_label(composite_score)
    sign = "+" if composite_score >= 0 else ""
    score_text = f"{sign}{composite_score:.2f}"

    ax.text(
        0, -0.22, score_text,
        ha="center", va="center",
        fontsize=22, fontweight="800",
        color="#000000", zorder=6,
    )
    ax.text(
        0, -0.38, label.upper(),
        ha="center", va="center",
        fontsize=9, fontweight="700",
        color="#404040", zorder=6,
        letter_spacing=0.05,
    )
    ax.text(
        0, -0.49,
        f"As of {meeting_date} MPC Meeting",
        ha="center", va="center",
        fontsize=7.5, color="#606060", zorder=6,
    )

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "Where Does the RBI Stand?"
        subtitle = f"Composite policy stance score · {meeting_date}"
    else:
        title = "RBI MPC Policy Stance — Composite Sentiment Score"
        subtitle = (
            f"Hybrid lexicon + LLM model · Score: {sign}{composite_score:.2f} "
            f"({label}) · {meeting_date}"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved stance meter to %s", output_path)
