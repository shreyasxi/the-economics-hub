"""
rbi_sentinel/charts/rate_and_sentiment.py

Chart 05: Repo Rate vs. Sentiment Score
Dual-axis: repo rate as stepped line (left, India saffron),
sentiment composite as smooth line (right, black).
Shows whether sentiment score leads rate decisions.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pandas as pd

from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.rate_and_sentiment")


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
) -> None:
    """
    Args:
        composites: List of dicts from get_all_composites()
                    Keys needed: meeting_date, repo_rate_pct, composite_overall_score
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
    """
    if not composites:
        log.warning("No composites for rate vs sentiment chart")
        return

    EconStyle.apply_global_style()

    df = pd.DataFrame(composites)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.sort_values("meeting_date")

    # Filter to rows with both rate and sentiment data
    df_rate = df.dropna(subset=["repo_rate_pct"])
    df_score = df.dropna(subset=["composite_overall_score"])

    if df_rate.empty or df_score.empty:
        log.warning("Insufficient data for rate vs sentiment chart")
        return

    fig, ax1 = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax1.set_facecolor(EconStyle.BACKGROUND)

    # ── Left axis: Repo Rate (step line) ─────────────────────────────────────
    india_color = EconStyle.get_color("india")  # Saffron
    ax1.step(
        df_rate["meeting_date"], df_rate["repo_rate_pct"],
        where="post",
        color=india_color, lw=2.2,
        label="Repo Rate (%)", zorder=4,
    )
    ax1.scatter(
        df_rate["meeting_date"], df_rate["repo_rate_pct"],
        color=india_color, s=30, zorder=5,
    )

    ax1.set_ylabel("RBI Repo Rate (%)", fontsize=8.5, color=india_color)
    ax1.tick_params(axis="y", colors=india_color, labelsize=8)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f%%"))

    # Rate axis range: pad above and below
    rate_min = df_rate["repo_rate_pct"].min()
    rate_max = df_rate["repo_rate_pct"].max()
    ax1.set_ylim(rate_min - 0.50, rate_max + 0.75)

    # ── Right axis: Sentiment Score ────────────────────────────────────────────
    ax2 = ax1.twinx()
    ax2.set_facecolor(EconStyle.BACKGROUND)

    ax2.plot(
        df_score["meeting_date"], df_score["composite_overall_score"],
        color="#000000", lw=1.8,
        label="Sentiment Score", zorder=4, ls="-",
    )
    ax2.scatter(
        df_score["meeting_date"], df_score["composite_overall_score"],
        color="#000000", s=22, zorder=5,
    )
    ax2.axhline(0, color="#000000", lw=0.6, ls="--", alpha=0.4, zorder=1)

    ax2.set_ylabel("Sentiment Score (−1 to +1)", fontsize=8.5, color="#404040")
    ax2.tick_params(axis="y", colors="#404040", labelsize=8)
    ax2.set_ylim(-1.25, 1.25)
    ax2.yaxis.set_ticks([-1.0, -0.5, 0.0, 0.5, 1.0])

    # ── Shared X axis ─────────────────────────────────────────────────────────
    x_min = df["meeting_date"].min()
    x_max = df["meeting_date"].max()
    ax1.set_xlim(
        x_min - pd.Timedelta(days=90),
        x_max + pd.Timedelta(days=90),
    )
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.tick_params(axis="x", labelsize=8.5)

    # ── Gridlines from ax1 only ───────────────────────────────────────────────
    ax1.set_axisbelow(True)
    ax1.yaxis.grid(True, color=EconStyle.GRID_COLOR, lw=0.5, alpha=0.5)
    ax1.xaxis.grid(False)
    ax2.yaxis.grid(False)

    for spine in ["top"]:
        ax1.spines[spine].set_visible(False)
        ax2.spines[spine].set_visible(False)
    ax1.spines["bottom"].set_color("#000000")

    # ── Combined legend ────────────────────────────────────────────────────────
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2, labels1 + labels2,
        loc="upper left", fontsize=7.5, frameon=False,
    )

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "Does Sentiment Lead Rate Decisions?"
        subtitle = "RBI Repo Rate (saffron, left) vs. MPC Sentiment Score (black, right)"
    else:
        title = "RBI Repo Rate vs. Composite Sentiment Score"
        subtitle = (
            "Step line = Repo Rate (%) · Line = Sentiment composite · "
            "Sentiment leading repo rate decisions by 1–2 meetings signals predictive value"
        )

    EconStyle.add_top_rule(ax1)
    EconStyle.set_title(ax1, title, subtitle)
    EconStyle.add_source(fig, "RBI  |  The Economics Hub RBI Sentinel")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved rate vs sentiment chart to %s", output_path)
