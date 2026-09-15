"""
rbi_sentinel/charts/sentiment_trajectory.py

Chart 02: RBI Sentiment Over Time
Three lines — Resolution, Minutes and Governor's Statement scores per MPC
meeting from 2016 — over hawkish/dovish zone fills, with a decision strip
beneath on the same time axis: one dot per meeting, coloured hike / cut / hold.
The strip replaces the former chart 06 (Meeting History), whose bar panel
repeated this chart's data.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from matplotlib.lines import Line2D

from charts.style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.sentiment_trajectory")

# Decision strip. Blue for cuts and red for hikes follow the dovish/hawkish zone
# fills above; the blue is lighter than the navy Policy Statement line so the
# two never read as the same series.
_DECISION_STYLE = {
    "hike": dict(color="#CC0000", s=46, label="Rate hike"),
    "cut":  dict(color="#4472C4", s=46, label="Rate cut"),
    "hold": dict(color="#B4BAC3", s=20, label="Hold"),
}


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

    # Drop rows where all three scores are missing
    df = df.dropna(subset=["resolution_score", "minutes_score", "governor_score"], how="all")
    if df.empty:
        log.warning("No scored meetings for trajectory chart")
        return

    fig, (ax, ax_dec) = plt.subplots(
        2, 1, figsize=(EconStyle.SIZE_WIDE[0], EconStyle.SIZE_WIDE[1] + 0.75),
        sharex=True, gridspec_kw={"height_ratios": [6.2, 0.75], "hspace": 0.16},
    )
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)
    ax_dec.set_facecolor(EconStyle.BACKGROUND)

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

    # Governor's Statement score — Forest green (distinct personal signal channel)
    gov_mask = df["governor_score"].notna()
    if gov_mask.any():
        ax.plot(
            dates[gov_mask], df["governor_score"][gov_mask],
            color="#2E7D32",
            lw=1.4, marker="D", markersize=3.5,
            label="Governor's Statement", zorder=4, ls="-",
        )

    # ── Meeting date vertical hairlines (through both panels) ────────────────
    for dt in dates:
        ax.axvline(dt, color="#D6D6D6", lw=0.4, alpha=0.7, zorder=1)
        ax_dec.axvline(dt, color="#D6D6D6", lw=0.4, alpha=0.7, zorder=1)

    # ── Decision strip ────────────────────────────────────────────────────────
    actions = df["rate_action"].fillna("hold").str.lower() if "rate_action" in df else pd.Series("hold", index=df.index)
    ax_dec.axhline(0, color="#000000", lw=0.8, zorder=2)
    for action, style in _DECISION_STYLE.items():
        mask = actions == action
        if mask.any():
            ax_dec.scatter(dates[mask], [0] * int(mask.sum()), s=style["s"], color=style["color"],
                           edgecolors="white", linewidths=0.6, zorder=4)
    ax_dec.set_ylim(-1, 1)
    ax_dec.set_yticks([0])
    ax_dec.set_yticklabels(["MPC\ndecision"], fontsize=7.5)
    ax_dec.tick_params(axis="y", length=0)
    ax_dec.grid(False)
    for spine in ["top", "right", "left", "bottom"]:
        ax_dec.spines[spine].set_visible(False)
    decision_handles = [
        Line2D([], [], marker="o", ls="", color=st["color"], markeredgecolor="white",
               markersize=6.5 if a != "hold" else 5, label=st["label"])
        for a, st in _DECISION_STYLE.items()
    ]
    # Key in the gap between the two panels, right-aligned directly above the
    # strip, so it reads as the strip's key and never covers a decision dot.
    ax_dec.legend(handles=decision_handles, loc="lower right", bbox_to_anchor=(1.0, 1.02),
                  ncol=3, fontsize=7.5, frameon=True, facecolor=EconStyle.BACKGROUND,
                  edgecolor="none", framealpha=1.0, handletextpad=0.2, columnspacing=1.1,
                  borderpad=0.15, borderaxespad=0.0)

    # ── Axes ──────────────────────────────────────────────────────────────────
    ax.set_xlim(x_min - pd.Timedelta(days=60), x_max + pd.Timedelta(days=60))
    ax.set_ylim(-1.1, 1.1)
    ax.yaxis.set_ticks([-1.0, -0.5, 0.0, 0.5, 1.0])
    ax.yaxis.set_ticklabels(["−1.0\nExtr. Dovish", "−0.5", "0\nNeutral", "+0.5", "+1.0\nExtr. Hawkish"])
    ax.tick_params(axis="y", labelsize=7.5)

    ax_dec.xaxis.set_major_locator(mdates.YearLocator())
    ax_dec.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_dec.tick_params(axis="x", labelsize=8.5, length=0)
    ax.tick_params(axis="x", length=0, labelbottom=False)

    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.5, alpha=0.7)
    ax.xaxis.grid(False)

    for spine in ["top", "right", "left", "bottom"]:
        ax.spines[spine].set_visible(False)

    # ── Legend ────────────────────────────────────────────────────────────────
    ax.legend(
        loc="upper left",
        fontsize=8,
        frameon=False,
    )

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "The RBI's Mood Over Time"
        subtitle = "Policy Statement, MPC Minutes & Governor sentiment score, with each rate decision · Oct 2016 to present"
    else:
        title = "RBI Sentiment Trajectory — MPS, Minutes & Governor"
        subtitle = (
            "Hybrid lexicon + LLM composite score per meeting, with each rate decision below | Oct 2016 to present"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved sentiment trajectory to %s", output_path)
