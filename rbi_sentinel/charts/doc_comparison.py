"""
rbi_sentinel/charts/doc_comparison.py

Chart 03: Resolution vs. Minutes Comparison
Side-by-side grouped bars for the last N meetings.
Annotates the divergence (Minutes Premium) above each pair.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from rbi_sentinel.config import COMPARISON_CHART_MEETINGS
from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.doc_comparison")

_RESOLUTION_COLOR = EconStyle.get_color("us") if hasattr(EconStyle, "get_color") else "#003366"
_MINUTES_COLOR = EconStyle.get_color("india") if hasattr(EconStyle, "get_color") else "#FF9933"


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
    n_meetings: int = COMPARISON_CHART_MEETINGS,
) -> None:
    """
    Args:
        composites: List of dicts from get_recent_composites(n) — oldest first
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
        n_meetings: Number of meetings to display
    """
    if not composites:
        log.warning("No composites for resolution vs minutes comparison chart")
        return

    EconStyle.apply_global_style()

    df = pd.DataFrame(composites).tail(n_meetings).reset_index(drop=True)

    # Format x-axis labels: "Oct\n2024"
    labels = []
    for date_str in df["meeting_date"]:
        try:
            dt = pd.to_datetime(date_str)
            labels.append(dt.strftime("%b\n%Y"))
        except Exception:
            labels.append(str(date_str)[:7])

    x = np.arange(len(df))
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Bars ──────────────────────────────────────────────────────────────────
    res_scores = df["resolution_score"].fillna(0).values
    min_scores = df["minutes_score"].fillna(0).values

    bars_res = ax.bar(
        x - bar_width / 2, res_scores,
        width=bar_width,
        color=[_score_color(s) for s in res_scores],
        alpha=0.90, label="Resolution",
        zorder=3,
    )
    bars_min = ax.bar(
        x + bar_width / 2, min_scores,
        width=bar_width,
        color=[_score_color(s) for s in min_scores],
        alpha=0.72, label="Minutes",
        zorder=3,
        edgecolor="#404040", linewidth=0.5,
    )

    # ── Divergence annotation ─────────────────────────────────────────────────
    for i, (rs, ms) in enumerate(zip(res_scores, min_scores)):
        if df["resolution_score"].iloc[i] is not None and df["minutes_score"].iloc[i] is not None:
            divergence = ms - rs  # Positive = Minutes more hawkish than Resolution
            y_top = max(abs(rs), abs(ms)) + 0.05
            y_pos = y_top if y_top > 0 else -y_top - 0.12
            sign = "+" if divergence >= 0 else ""
            ax.text(
                i, y_pos,
                f"d{sign}{divergence:.2f}",
                ha="center", va="bottom",
                fontsize=7, color="#404040",
                zorder=5,
            )

    # ── Zero line ─────────────────────────────────────────────────────────────
    ax.axhline(0, color="#000000", lw=0.8, ls="-", alpha=0.6, zorder=2)

    # ── Axes ──────────────────────────────────────────────────────────────────
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(-1.15, 1.15)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.25))
    ax.tick_params(axis="y", labelsize=8)
    ax.set_ylabel("Sentiment Score", fontsize=8, color="#404040")

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.5, alpha=0.7)
    ax.xaxis.grid(False)

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#000000")

    # ── Hawkish / Dovish zone labels ──────────────────────────────────────────
    ax.text(
        -0.5, 0.90, "HAWKISH",
        fontsize=7, color="#CC000055", fontweight="700", va="center"
    )
    ax.text(
        -0.5, -0.90, "DOVISH",
        fontsize=7, color="#00336655", fontweight="700", va="center"
    )

    # ── Legend ────────────────────────────────────────────────────────────────
    import matplotlib.patches as mpatches
    legend_handles = [
        mpatches.Patch(color="#808080", alpha=0.90, label="Resolution (solid fill)"),
        mpatches.Patch(color="#808080", alpha=0.72, label="Minutes (hatched edge)"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=7.5, frameon=False)

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "What the Minutes Reveal"
        subtitle = (
            "Resolution vs. MPC Minutes sentiment · "
            "d = Minutes Premium (positive = Minutes more hawkish)"
        )
    else:
        title = "Policy Resolution vs. MPC Minutes — Sentiment Divergence"
        subtitle = (
            f"Last {n_meetings} MPC meetings · "
            "d = Minutes score minus Resolution score"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved doc comparison chart to %s", output_path)


def _score_color(score: float) -> str:
    """Color bar based on sign: hawkish = red tones, dovish = navy tones."""
    if score >= 0.40:
        return "#CC0000"
    elif score >= 0.10:
        return "#C9563C"
    elif score >= -0.10:
        return "#A6A6A6"
    elif score >= -0.40:
        return "#4472C4"
    else:
        return "#003366"
