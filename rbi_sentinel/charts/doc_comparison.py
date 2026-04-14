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
    MPC cycle. This function groups by YYYY-MM, merges resolution_score,
    minutes_score, and governor_score from their respective rows, and returns
    one row per cycle.
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
            minutes_score=("minutes_score",       lambda s: next((v for v in s if pd.notna(v)), None)),
            governor_score=("governor_score",     lambda s: next((v for v in s if pd.notna(v)), None)),
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
    bar_width = 0.25

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Bars ──────────────────────────────────────────────────────────────────
    res_scores_raw = pd.to_numeric(df["resolution_score"], errors="coerce").values
    min_scores_raw = pd.to_numeric(df["minutes_score"],    errors="coerce").values
    gov_scores_raw = pd.to_numeric(df["governor_score"],   errors="coerce").values

    has_res = ~np.isnan(res_scores_raw)
    has_min = ~np.isnan(min_scores_raw)
    has_gov = ~np.isnan(gov_scores_raw)

    # Use 0.0 so missing data sits flat on the axis
    res_scores = np.nan_to_num(res_scores_raw)
    min_scores = np.nan_to_num(min_scores_raw)
    gov_scores = np.nan_to_num(gov_scores_raw)

    res_color = EconStyle.get_color("pink") if hasattr(EconStyle, "get_color") else "#900C3F"
    min_color = EconStyle.get_color("us")   if hasattr(EconStyle, "get_color") else "#4472C4"
    gov_color = "#2E7D32"

    ax.bar(
        x - bar_width, res_scores,
        width=bar_width,
        color=[res_color if has_res[i] else "#CCCCCC" for i in range(len(res_scores))],
        alpha=0.90, zorder=3,
        edgecolor=["none" if has_res[i] else "#999999" for i in range(len(res_scores))],
        linewidth=1.0
    )
    ax.bar(
        x, min_scores,
        width=bar_width,
        color=[min_color if has_min[i] else "#CCCCCC" for i in range(len(min_scores))],
        alpha=0.90, zorder=3,
        edgecolor=["none" if has_min[i] else "#999999" for i in range(len(min_scores))],
        linewidth=1.0
    )
    ax.bar(
        x + bar_width, gov_scores,
        width=bar_width,
        color=[gov_color if has_gov[i] else "#CCCCCC" for i in range(len(gov_scores))],
        alpha=0.90, zorder=3,
        edgecolor=["none" if has_gov[i] else "#999999" for i in range(len(gov_scores))],
        linewidth=1.0
    )


    # ── Zero line ─────────────────────────────────────────────────────────────
    ax.axhline(0, color="#000000", lw=0.8, ls="-", alpha=0.6, zorder=2)

   # ── Axes ──────────────────────────────────────────────────────────────────
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(-1.05, 1.05)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.5))
    ax.tick_params(axis="y", labelsize=8)

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.5, alpha=0.7)
    ax.xaxis.grid(False)

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#000000")

    # ── Zone labels (Arrows) ──────────────────────────────────────────────────
    ax.annotate("More Hawkish", xy=(-0.045, 0.95), xytext=(-0.045, 0.75),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#CC0000", lw=1.5),
                ha="center", va="center", rotation=90, fontsize=8, color="#CC0000", fontweight="bold")

    ax.annotate("More Dovish", xy=(-0.045, 0.05), xytext=(-0.045, 0.25),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#003366", lw=1.5),
                ha="center", va="center", rotation=90, fontsize=8, color="#003366", fontweight="bold")
   
    # ── Legend ────────────────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(facecolor=res_color, alpha=0.90, label="Policy Statement"),
        mpatches.Patch(facecolor=min_color, alpha=0.90, label="Minutes"),
        mpatches.Patch(facecolor=gov_color, alpha=0.90, label="Governor's Statement"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8.5, frameon=False)

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "What the Documents Reveal"
        subtitle = "Resolution, MPC Minutes & Governor sentiment — three-document comparison"
    else:
        title = "Tripartite Sentiment — Resolution, Minutes & Governor"
        subtitle = f"Last {len(df)} MPC cycles | Sentiment score per document type"

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents")

    # CRITICAL FIX: left=0.10 gives the arrows physical space to exist outside the chart
    fig.subplots_adjust(top=0.85, bottom=0.15, left=0.08, right=0.95)

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
