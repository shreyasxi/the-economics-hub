"""
rbi_sentinel/charts/meeting_timeline.py

Chart 06: MPC Meeting History Timeline
One dot per MPC cycle (deduped by year-month), colored by rate action.
Score annotations removed — replaced by a thin sentiment strip above dots.
Only hike/cut events labeled.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np

from rbi_sentinel.config import RATE_CUT, RATE_HIKE, RATE_HOLD
from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.meeting_timeline")

_ACTION_COLORS = {
    RATE_CUT:  EconStyle.POSITIVE if hasattr(EconStyle, "POSITIVE") else "#008000",
    RATE_HIKE: EconStyle.NEGATIVE if hasattr(EconStyle, "NEGATIVE") else "#CC0000",
    RATE_HOLD: "#909090",
    None:      "#CCCCCC",
}
_ACTION_LABELS = {
    RATE_CUT:  "Rate Cut",
    RATE_HIKE: "Rate Hike",
}

# Action priority for deduplication (higher = more important)
_ACTION_PRIORITY = {RATE_HIKE: 3, RATE_CUT: 2, RATE_HOLD: 1, None: 0}


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    if not composites:
        log.warning("No data for meeting timeline chart")
        return

    EconStyle.apply_global_style()

    df = pd.DataFrame(composites)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.sort_values("meeting_date")

    # ── Deduplicate: one row per MPC cycle (YYYY-MM) ──────────────────────────
    df["ym"] = df["meeting_date"].dt.to_period("M")
    df["action_priority"] = df["rate_action"].map(lambda x: _ACTION_PRIORITY.get(x, 0))

    def best_action(group):
        """Pick highest-priority rate action in the group."""
        idx = group["action_priority"].idxmax()
        return group.loc[idx, "rate_action"]

    agg_rows = []
    for ym, group in df.groupby("ym", sort=True):
        agg_rows.append({
            "meeting_date": group["meeting_date"].min(),
            "rate_action": best_action(group),
            "composite_overall_score": group["composite_overall_score"].mean(),
        })
    grouped = pd.DataFrame(agg_rows)

    # ── Figure ─────────────────────────────────────────────────────────────────
    fig, (ax_score, ax_time) = plt.subplots(
        2, 1, figsize=(12, 5.0),
        sharex=True,  # Locks the top and bottom X-axes together perfectly
        gridspec_kw={"height_ratios": [2.5, 1], "hspace": 0.05}, # Flipped! Top gets more space
    )
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    for a in (ax_score, ax_time):
        a.set_facecolor(EconStyle.BACKGROUND)
        
    dates = grouped["meeting_date"].values
    scores = grouped["composite_overall_score"].fillna(0).values

    # ── Top panel: sentiment score strip (bar chart, coloured by sign) ────────
    bar_colors = [
        "#CC0000" if s > 0.15 else "#C9563C" if s > 0 else "#4472C4" if s > -0.15 else "#003366"
        for s in scores
    ]
    
    # Convert dates to matplotlib floats so width=30 actually draws 30 days wide
    dates_num = mdates.date2num(dates)
    ax_score.bar(dates_num, scores, width=30, color=bar_colors, alpha=0.90, zorder=3)
    
    ax_score.axhline(0, color="#000000", lw=0.7, alpha=0.6, zorder=2)
    ax_score.set_ylim(-1.2, 1.2) # Slightly expanded to give the bars headroom
    ax_score.set_yticks([-1, 0, 1])
    ax_score.set_yticklabels(["-1", "0", "+1"], fontsize=6.5, color="#606060")
    ax_score.set_ylabel("Score", fontsize=7, color="#606060")
    ax_score.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.4, alpha=0.5)
    ax_score.xaxis.grid(False)
    ax_score.tick_params(axis="x", labelbottom=False, length=0)
    ax_score.tick_params(axis="y", labelsize=6.5, length=0)
    for spine in ax_score.spines.values():
        spine.set_visible(False)

    # ── Bottom panel: timeline dots ────────────────────────────────────────────
    ax_time.axhline(0.0, color="#000000", lw=1.0, zorder=2)

    # Year gridlines (on both panels)
    years = pd.date_range(
        start=grouped["meeting_date"].min().replace(month=1, day=1),
        end=grouped["meeting_date"].max() + pd.DateOffset(years=1),
        freq="YS",
    )
    for yr in years:
        ax_score.axvline(yr, color="#D6D6D6", lw=0.5, ls=":", alpha=0.7, zorder=1)
        ax_time.axvline(yr, color="#D6D6D6", lw=0.5, ls=":", alpha=0.7, zorder=1)
        # Removed the floating year text to prevent duplication and overlap

    # Dots
    for _, row in grouped.iterrows():
        action = row.get("rate_action")
        color = _ACTION_COLORS.get(action, _ACTION_COLORS[None])
        dot_size = 100 if action in (RATE_CUT, RATE_HIKE) else 55
        ax_time.scatter(
            row["meeting_date"], 0.0,
            color=color, s=dot_size, zorder=4,
            edgecolors="#000000", linewidths=0.6,
        )

    # Rate action labels — only cuts/hikes, with minimum 150-day spacing
    # to avoid label pile-up in dense rate-cycle clusters.
    hike_cut_rows = grouped[grouped["rate_action"].isin([RATE_CUT, RATE_HIKE])].reset_index()
    _MIN_LABEL_GAP_DAYS = 150
    last_labeled_date = pd.Timestamp("2000-01-01")
    label_idx = 0  # alternating counter for above/below, only increments when label is drawn
    for _, row in hike_cut_rows.iterrows():
        dt = pd.Timestamp(row["meeting_date"])
        gap = (dt - last_labeled_date).days
        if gap < _MIN_LABEL_GAP_DAYS:
            continue  # too close to previous label — skip
        action = row["rate_action"]
        color = _ACTION_COLORS[action]
        label_text = _ACTION_LABELS[action]
        y_pos = 0.25 if label_idx % 2 == 0 else -0.32
        va = "bottom" if y_pos > 0 else "top"
        ax_time.text(
            dt, y_pos, label_text,
            ha="center", va=va,
            fontsize=6.5, color=color, fontweight="700",
            zorder=5,
        )
        ax_time.plot(
            [dt, dt],
            [0.07 if y_pos > 0 else -0.07, y_pos * 0.75],
            color=color, lw=0.6, alpha=0.55, zorder=3,
        )
        last_labeled_date = dt
        label_idx += 1

    # ── Axes formatting ────────────────────────────────────────────────────────
    x_min = grouped["meeting_date"].min() - pd.Timedelta(days=60)
    x_max = grouped["meeting_date"].max() + pd.Timedelta(days=90)

    ax_time.set_xlim(x_min, x_max)
    ax_score.set_xlim(x_min, x_max)

    ax_time.set_ylim(-0.55, 0.65)
    ax_time.set_yticks([])
    ax_time.yaxis.set_visible(False)

    ax_time.xaxis.set_major_locator(mdates.YearLocator())
    ax_time.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_time.tick_params(axis="x", labelsize=8, length=0)

    for spine in ax_time.spines.values():
        spine.set_visible(False)

    # ── Legend ─────────────────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(color=_ACTION_COLORS[RATE_CUT],  label="Rate Cut"),
        mpatches.Patch(color=_ACTION_COLORS[RATE_HIKE], label="Rate Hike"),
        mpatches.Patch(color=_ACTION_COLORS[RATE_HOLD], label="Hold"),
    ]
    
    # MOVED: Attached to ax_score instead of ax_time. 
    # bbox_to_anchor=(1.0, 1.02) places it perfectly aligned with the right edge,
    # floating exactly on the subtitle line.
    ax_score.legend(
        handles=legend_handles, loc="lower right",
        fontsize=9, frameon=False, ncol=3,
        bbox_to_anchor=(1.0, 1.02), 
    )

    # ── Title & branding ───────────────────────────────────────────────────────
    n_cycles = len(grouped)
    if mode == "newsletter":
        title = "Every RBI Decision Since the MPC Era"
        subtitle = f"Policy sentiment vs. rate decisions · {n_cycles} cycles (Oct 2016 – Present)"
    else:
        title = "Historical RBI Rate Actions and Policy Sentiment"
        # OPTIMIZED: Clean, executive summary style.
        subtitle = f"Policy sentiment trajectory vs. rate decisions | {n_cycles} cycles (Oct 2016 – Present)"

    EconStyle.add_top_rule(ax_score)
    EconStyle.set_title(ax_score, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents")

    # ADJUSTED: Since the legend is gone from the bottom, we can shrink the bottom 
    # margin from 0.20 to 0.12, giving the chart even more room to breathe.
    fig.subplots_adjust(top=0.88, bottom=0.12, left=0.05, right=0.96)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved meeting timeline to %s", output_path)
