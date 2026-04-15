"""
rbi_sentinel/charts/07_governor_divergence.py

Chart 07: Governor vs. Committee Divergence Strip
Vertical bar chart showing (governor_score − composite_overall_score) per meeting.
Positive = Governor more hawkish than committee consensus.
Negative = Governor more dovish than committee consensus.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.governor_divergence")

_GOVERNOR_MEETINGS = 14  # default number of recent meetings to display


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
    n_meetings: int = _GOVERNOR_MEETINGS,
) -> None:
    """
    Args:
        composites: List from db.manager.get_recent_composites(n) or get_all_composites()
                    Keys needed: meeting_date, governor_score, composite_overall_score
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
        n_meetings: Number of most recent meetings to display
    """
    if not composites:
        log.warning("No composites for governor divergence chart")
        return

    EconStyle.apply_global_style()

    df = pd.DataFrame(composites)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.sort_values("meeting_date")

    # Deduplicate by YYYY-MM — keep latest row per cycle
    df["ym"] = df["meeting_date"].dt.to_period("M")
    df = (
        df.groupby("ym", sort=True)
        .agg(
            meeting_date=("meeting_date", "min"),
            governor_score=("governor_score", lambda s: next((v for v in s if pd.notna(v)), None)),
            composite_overall_score=("composite_overall_score", lambda s: next((v for v in s if pd.notna(v)), None)),
        )
        .reset_index(drop=True)
    )

    # Keep only rows where both scores are present
    df = df.dropna(subset=["governor_score", "composite_overall_score"])
    if df.empty:
        log.warning("No meetings with both governor_score and composite_overall_score")
        return

    df = df.tail(n_meetings).reset_index(drop=True)

    # Compute divergence
    df["divergence"] = df["governor_score"] - df["composite_overall_score"]

    labels = [pd.to_datetime(d).strftime("%b\n%Y") for d in df["meeting_date"]]
    x = np.arange(len(df))
    divergences = df["divergence"].values

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Color bars by sign ────────────────────────────────────────────────────
    hawk_color = "#CC0000"
    dove_color = "#003366"
    bar_colors = [hawk_color if v >= 0 else dove_color for v in divergences]

    bars = ax.bar(
        x, divergences,
        width=0.55,
        color=bar_colors,
        alpha=0.88,
        zorder=3,
        edgecolor="none",
    )

    # ── Annotate each bar with the divergence value ───────────────────────────
    for i, val in enumerate(divergences):
        if abs(val) < 0.005:
            continue
        sign = "+" if val > 0 else ""
        y_offset = 0.025 if val >= 0 else -0.025
        va = "bottom" if val >= 0 else "top"
        ax.text(
            i, val + y_offset,
            f"{sign}{val:.2f}",
            ha="center", va=va,
            fontsize=7.5, color="#111111", fontweight="bold",
            zorder=5,
        )

    # ── Zero line with label ──────────────────────────────────────────────────
    ax.axhline(0, color="#000000", lw=0.9, ls="-", alpha=0.7, zorder=2)

    # ── Axes ──────────────────────────────────────────────────────────────────
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)

    y_abs_max = max(abs(divergences).max() * 1.25, 0.25)
    ax.set_ylim(-y_abs_max, y_abs_max)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.1))
    ax.tick_params(axis="y", labelsize=8)

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.5, alpha=0.7)
    ax.xaxis.grid(False)

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#000000")

    # ── Zone arrows ───────────────────────────────────────────────────────────
    ax.annotate("Governor More Hawkish", xy=(-0.045, 0.92), xytext=(-0.045, 0.72),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#CC0000", lw=1.5),
                ha="center", va="center", rotation=90,
                fontsize=7.5, color="#CC0000", fontweight="bold")

    ax.annotate("Governor More Dovish", xy=(-0.045, 0.08), xytext=(-0.045, 0.28),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#003366", lw=1.5),
                ha="center", va="center", rotation=90,
                fontsize=7.5, color="#003366", fontweight="bold")

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "Is the Governor Signalling Ahead of the Committee?"
        subtitle = "Governor's Statement score minus composite meeting score"
    else:
        title = "MPC Consensus vs. Governor Stance Divergence"
        subtitle = (
            f"Last {len(df)} MPC cycles | "
            "Divergence = Governor's Statement score − composite score"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents")

    fig.subplots_adjust(top=0.85, bottom=0.15, left=0.10, right=0.95)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved governor divergence chart to %s", output_path)
