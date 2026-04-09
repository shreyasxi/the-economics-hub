"""
rbi_sentinel/charts/doc_comparison.py

Chart 03: Resolution vs. Minutes Comparison
Side-by-side grouped bars — one pair per MPC cycle (deduped by YYYY-MM).
Annotates the divergence (Minutes Premium) above each pair.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from rbi_sentinel.config import COMPARISON_CHART_MEETINGS
from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.doc_comparison")

_RESOLUTION_COLOR = EconStyle.get_color("us") if hasattr(EconStyle, "get_color") else "#003366"
_MINUTES_COLOR    = EconStyle.get_color("india") if hasattr(EconStyle, "get_color") else "#FF9933"


def _merge_by_cycle(composites: list[dict], n_meetings: int) -> pd.DataFrame:
    """
    The composites table has one row per *document publication date*, not per
    MPC cycle. This function groups by YYYY-MM, merges resolution_score and
    minutes_score from their respective rows, and returns one row per cycle.
    """
    df = pd.DataFrame(composites)
    if df.empty:
        return df

    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.sort_values("meeting_date")
    df["ym"] = df["meeting_date"].dt.to_period("M")

    merged = (
        df.groupby("ym", sort=True)
        .agg(
            meeting_date=("meeting_date", "min"),
            resolution_score=("resolution_score", lambda s: next((v for v in s if pd.notna(v)), None)),
            minutes_score=("minutes_score",    lambda s: next((v for v in s if pd.notna(v)), None)),
        )
        .reset_index(drop=True)
    )

    # Return the last n_meetings cycles
    return merged.tail(n_meetings).reset_index(drop=True)


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
    n_meetings: int = COMPARISON_CHART_MEETINGS,
) -> None:
    """
    Args:
        composites: List from get_recent_composites(n) or get_all_composites()
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
        n_meetings: Number of MPC cycles to display
    """
    if not composites:
        log.warning("No composites for resolution vs minutes comparison chart")
        return

    EconStyle.apply_global_style()

    # Merge to one row per MPC cycle
    df = _merge_by_cycle(composites, n_meetings)

    if df.empty:
        log.warning("No merged cycles for doc comparison chart")
        return

    # Format x-axis labels
    labels = [pd.to_datetime(d).strftime("%b\n%Y") for d in df["meeting_date"]]

    x = np.arange(len(df))
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Bars ──────────────────────────────────────────────────────────────────
    res_scores = pd.to_numeric(df["resolution_score"], errors="coerce").fillna(0).values
    min_scores = pd.to_numeric(df["minutes_score"],    errors="coerce").fillna(0).values

    # Track which cycles actually have each doc type
    has_res = pd.to_numeric(df["resolution_score"], errors="coerce").notna().values
    has_min = pd.to_numeric(df["minutes_score"],    errors="coerce").notna().values

    bars_res = ax.bar(
        x - bar_width / 2, res_scores,
        width=bar_width,
        color=[_score_color(s) if has_res[i] else "#E0E0E0" for i, s in enumerate(res_scores)],
        alpha=0.90, label="Resolution",
        zorder=3,
    )
    bars_min = ax.bar(
        x + bar_width / 2, min_scores,
        width=bar_width,
        color=[_score_color(s) if has_min[i] else "#E0E0E0" for i, s in enumerate(min_scores)],
        alpha=0.72, label="Minutes",
        zorder=3,
        edgecolor="#404040", linewidth=0.5,
    )

    # ── Divergence annotation ──────────────────────────────────────────────────
    for i, (rs, ms, hr, hm) in enumerate(zip(res_scores, min_scores, has_res, has_min)):
        if not (hr and hm):
            continue  # Only annotate when both scores are present
        divergence = ms - rs
        y_top = max(abs(rs), abs(ms)) + 0.07
        sign = "+" if divergence >= 0 else ""
        ax.text(
            i, y_top,
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
    ax.set_ylim(-1.15, 1.35)
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

    # ── Zone labels ───────────────────────────────────────────────────────────
    ax.text(-0.5, 0.90, "HAWKISH",
            fontsize=7, color="#CC000055", fontweight="700", va="center")
    ax.text(-0.5, -0.90, "DOVISH",
            fontsize=7, color="#00336655", fontweight="700", va="center")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(color="#4472C4", alpha=0.90, label="Resolution"),
        mpatches.Patch(color="#4472C4", alpha=0.72, label="Minutes", linewidth=0.5,
                       edgecolor="#404040"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=7.5, frameon=False)

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "What the Minutes Reveal"
        subtitle = (
            "Resolution vs. MPC Minutes sentiment · "
            "d = Minutes Premium (positive = Minutes more hawkish than Resolution)"
        )
    else:
        title = "Policy Resolution vs. MPC Minutes — Sentiment Divergence"
        subtitle = (
            f"Last {len(df)} MPC cycles · "
            "d = Minutes score minus Resolution score · Grey bars = data not yet available"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved doc comparison chart to %s", output_path)


def _score_color(score: float) -> str:
    """Color bar based on score: hawkish = red tones, dovish = blue tones."""
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
