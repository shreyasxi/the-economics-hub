"""
rbi_sentinel/charts/sentiment_trajectory.py

Chart 02: RBI Sentiment Over Time
Two lines: Resolution score + Minutes score per MPC meeting from 2016 to present.
Horizontal zero line. Background zone fills (hawkish territory / dovish territory).
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.sentiment_trajectory")


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    """
    Args:
        composites: List of dicts from db.manager.get_all_composites()
                    Keys needed: meeting_date, resolution_score, minutes_score
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
    """
    if not composites:
        log.warning("No composites available for sentiment trajectory chart")
        return

    EconStyle.apply_global_style()

    df = pd.DataFrame(composites)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.sort_values("meeting_date")

    # Drop rows where both scores are missing
    df = df.dropna(subset=["resolution_score", "minutes_score"], how="all")
    if df.empty:
        log.warning("No scored meetings for trajectory chart")
        return

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    dates = df["meeting_date"]
    x_min, x_max = dates.min(), dates.max()

    # ── Background zone fills ─────────────────────────────────────────────────
    ax.axhspan(0.0, 1.05, alpha=0.06, color="#CC0000", zorder=0)   # Hawkish zone (light red)
    ax.axhspan(-1.05, 0.0, alpha=0.06, color="#003366", zorder=0)  # Dovish zone (light navy)

    # ── Zero line (Neutral) ───────────────────────────────────────────────────
    ax.axhline(0, color="#000000", lw=0.8, ls="--", alpha=0.5, zorder=2)
    ax.text(
        x_max, 0.02, "NEUTRAL",
        ha="right", va="bottom",
        fontsize=6.5, color="#404040", alpha=0.7,
    )

    # ── Lines ─────────────────────────────────────────────────────────────────
    # Resolution score — Navy
    res_mask = df["resolution_score"].notna()
    if res_mask.any():
        ax.plot(
            dates[res_mask], df["resolution_score"][res_mask],
            color=EconStyle.get_color("us"),       # Navy
            lw=1.8, marker="o", markersize=4.5,
            label="Policy Statement", zorder=4,
        )

    # Minutes score — Saffron (India color — RBI is an Indian institution)
    min_mask = df["minutes_score"].notna()
    if min_mask.any():
        ax.plot(
            dates[min_mask], df["minutes_score"][min_mask],
            color=EconStyle.get_color("india"),    # Saffron
            lw=1.8, marker="s", markersize=4.0,
            label="MPC Minutes", zorder=4, ls="--",
        )

    # ── Meeting date vertical hairlines ──────────────────────────────────────
    for dt in dates:
        ax.axvline(dt, color="#D6D6D6", lw=0.4, alpha=0.7, zorder=1)

    # ── Axes ──────────────────────────────────────────────────────────────────
    ax.set_xlim(x_min - pd.Timedelta(days=60), x_max + pd.Timedelta(days=60))
    ax.set_ylim(-1.1, 1.1)
    ax.yaxis.set_ticks([-1.0, -0.5, 0.0, 0.5, 1.0])
    ax.yaxis.set_ticklabels(["−1.0\nExtr. Dovish", "−0.5", "0\nNeutral", "+0.5", "+1.0\nExtr. Hawkish"])
    ax.tick_params(axis="y", labelsize=7.5)

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", labelsize=8.5)

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.5, alpha=0.7)
    ax.xaxis.grid(False)

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#000000")

    # ── Legend ────────────────────────────────────────────────────────────────
    ax.legend(
        loc="upper left",
        fontsize=8,
        frameon=False,
    )

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "The RBI's Mood Over Time"
        subtitle = "Policy Statement vs. MPC Minutes sentiment score · Oct 2016 to present"
    else:
        title = "RBI Sentiment Trajectory — MPS vs. Minutes"
        subtitle = (
            "Hybrid lexicon + LLM composite score per meeting | Oct 2016 to present"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved sentiment trajectory to %s", output_path)
