"""
rbi_sentinel/charts/meeting_timeline.py

Chart 06: MPC Meeting History Timeline
Horizontal annotated timeline. Each meeting = colored dot (green=cut, red=hike, grey=hold).
Score annotated above each point. Year separators as vertical gridlines.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

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
    RATE_HOLD: "Hold",
    None:      "Unknown",
}


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    """
    Args:
        composites: List of dicts from get_all_composites()
                    Keys: meeting_date, rate_action, composite_overall_score
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
    """
    if not composites:
        log.warning("No data for meeting timeline chart")
        return

    EconStyle.apply_global_style()

    df = pd.DataFrame(composites)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.sort_values("meeting_date")

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Baseline (horizontal axis line) ───────────────────────────────────────
    ax.axhline(0.0, color="#000000", lw=1.0, zorder=2)

    # ── Year separator gridlines ──────────────────────────────────────────────
    years = df["meeting_date"].dt.year.unique()
    for year in years:
        year_start = pd.Timestamp(f"{year}-01-01")
        ax.axvline(year_start, color="#D6D6D6", lw=0.6, ls=":", alpha=0.8, zorder=1)
        ax.text(
            year_start, 1.15, str(year),
            ha="center", va="bottom",
            fontsize=7, color="#606060",
        )

    # ── Meeting dots and annotations ──────────────────────────────────────────
    # Alternate score labels above/below to reduce overlap
    for i, row in df.iterrows():
        action = row.get("rate_action")
        color = _ACTION_COLORS.get(action, _ACTION_COLORS[None])
        score = row.get("composite_overall_score")

        # Dot
        ax.scatter(
            row["meeting_date"], 0.0,
            color=color, s=70, zorder=4,
            edgecolors="#000000", linewidths=0.6,
        )

        # Score label — alternate above/below every other point
        if score is not None:
            y_offset = 0.18 if i % 2 == 0 else -0.25
            va = "bottom" if y_offset > 0 else "top"
            sign = "+" if score >= 0 else ""
            ax.text(
                row["meeting_date"], y_offset,
                f"{sign}{score:.2f}",
                ha="center", va=va,
                fontsize=6.5, color="#222222",
                rotation=0, zorder=5,
            )

        # Rate action label (small) below each dot for hike/cut
        if action in (RATE_CUT, RATE_HIKE):
            ax.text(
                row["meeting_date"], -0.08 if y_offset > 0 else -0.38,
                _ACTION_LABELS.get(action, ""),
                ha="center", va="top",
                fontsize=5.5, color=color, fontweight="600",
                zorder=5,
            )

    # ── Legend ────────────────────────────────────────────────────────────────
    import matplotlib.patches as mpatches
    legend_handles = [
        mpatches.Patch(color=_ACTION_COLORS[RATE_CUT], label="Rate Cut"),
        mpatches.Patch(color=_ACTION_COLORS[RATE_HIKE], label="Rate Hike"),
        mpatches.Patch(color=_ACTION_COLORS[RATE_HOLD], label="Hold"),
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper left",
        fontsize=7.5,
        frameon=False,
    )

    # ── Axes ──────────────────────────────────────────────────────────────────
    x_min = df["meeting_date"].min()
    x_max = df["meeting_date"].max()
    ax.set_xlim(
        x_min - pd.Timedelta(days=90),
        x_max + pd.Timedelta(days=90),
    )
    ax.set_ylim(-0.55, 1.3)

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", labelsize=8.5)

    ax.set_yticks([])
    ax.yaxis.set_visible(False)

    for spine in ["top", "right", "left", "bottom"]:
        ax.spines[spine].set_visible(False)

    # ── Title & branding ──────────────────────────────────────────────────────
    n_meetings = len(df)
    if mode == "newsletter":
        title = "Every RBI Decision Since the MPC Era"
        subtitle = "Meeting timeline with sentiment scores · Oct 2016 to present"
    else:
        title = "RBI MPC Meeting History — Rate Actions & Sentiment Scores"
        subtitle = (
            f"{n_meetings} meetings · Oct 2016 to present · "
            "Score shown above each meeting dot · Green = cut · Red = hike · Grey = hold"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved meeting timeline to %s", output_path)
