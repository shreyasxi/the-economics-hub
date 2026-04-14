"""
rbi_sentinel/charts/09_tone_heatmap.py

Chart 09: Three-Document Tone Alignment Heatmap
A grid (rows = last N MPC meetings, columns = [Resolution, Minutes, Governor])
where each cell is colored by sentiment score and the numeric value is printed inside.
A consensus/divergence indicator is annotated in the row margin.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from style.economics_hub_style import EconStyle

log = logging.getLogger("rbi_sentinel.charts.tone_heatmap")

_HEATMAP_MEETINGS = 12  # number of recent meetings to display


def generate(
    composites: list[dict],
    output_path: Path,
    mode: str = "dashboard",
    n_meetings: int = _HEATMAP_MEETINGS,
) -> None:
    """
    Args:
        composites: List from db.manager.get_all_composites() or get_recent_composites(n)
                    Keys needed: meeting_date, resolution_score, minutes_score, governor_score
        output_path: Full path for output PNG
        mode: "dashboard" | "newsletter"
        n_meetings: Number of most recent meetings to display
    """
    if not composites:
        log.warning("No composites for tone heatmap")
        return

    EconStyle.apply_global_style()

    df = pd.DataFrame(composites)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.sort_values("meeting_date")

    # Deduplicate by YYYY-MM — keep first occurrence per cycle
    df["ym"] = df["meeting_date"].dt.to_period("M")
    df = (
        df.groupby("ym", sort=True)
        .agg(
            meeting_date=("meeting_date", "min"),
            resolution_score=("resolution_score", lambda s: next((v for v in s if pd.notna(v)), None)),
            minutes_score=("minutes_score",       lambda s: next((v for v in s if pd.notna(v)), None)),
            governor_score=("governor_score",     lambda s: next((v for v in s if pd.notna(v)), None)),
        )
        .reset_index(drop=True)
    )

    df = df.tail(n_meetings).reset_index(drop=True)

    if df.empty:
        log.warning("No meetings for tone heatmap after deduplication")
        return

    # Build score matrix: shape (n_meetings, 3)
    col_keys = ["resolution_score", "minutes_score", "governor_score"]
    col_labels = ["Policy\nResolution", "MPC\nMinutes", "Governor's\nStatement"]
    score_matrix = df[col_keys].values.astype(float)  # shape (n, 3)

    # Row labels: "MMM YYYY"
    row_labels = [pd.to_datetime(d).strftime("%b %Y") for d in df["meeting_date"]]

    # ── Figure setup ──────────────────────────────────────────────────────────
    n_rows, n_cols = score_matrix.shape
    fig_h = max(5.0, n_rows * 0.52 + 1.8)
    fig, ax = plt.subplots(figsize=(9, fig_h))
    fig.patch.set_facecolor(EconStyle.BACKGROUND)
    ax.set_facecolor(EconStyle.BACKGROUND)

    # ── Custom diverging colormap ─────────────────────────────────────────────
    # Deep navy (#003366) at -1.0  →  white at 0.0  →  deep red (#CC0000) at +1.0
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rbi_diverge",
        ["#003366", "#6699CC", "#FFFFFF", "#E07070", "#CC0000"],
        N=256
    )
    norm = mcolors.TwoSlopeNorm(vmin=-1.0, vcenter=0.0, vmax=1.0)

    # ── Draw cells ────────────────────────────────────────────────────────────
    for row_i in range(n_rows):
        for col_j in range(n_cols):
            val = score_matrix[row_i, col_j]
            if np.isnan(val):
                facecolor = "#E8E8E8"
                text = "N/A"
                text_color = "#888888"
            else:
                facecolor = cmap(norm(val))
                text = f"{val:+.2f}"
                # Dark text on light cells, light text on dark cells
                luminance = 0.299 * facecolor[0] + 0.587 * facecolor[1] + 0.114 * facecolor[2]
                text_color = "#FFFFFF" if luminance < 0.55 else "#111111"

            rect = mpatches.FancyBboxPatch(
                (col_j + 0.04, row_i + 0.04),
                0.92, 0.92,
                boxstyle="round,pad=0.02",
                facecolor=facecolor,
                edgecolor="#CCCCCC",
                linewidth=0.5,
                transform=ax.transData,
                zorder=2,
            )
            ax.add_patch(rect)
            ax.text(
                col_j + 0.5, row_i + 0.5, text,
                ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=text_color,
                zorder=3,
            )

    # ── Row consensus/divergence indicator in right margin ────────────────────
    for row_i in range(n_rows):
        row_vals = [score_matrix[row_i, j] for j in range(n_cols) if not np.isnan(score_matrix[row_i, j])]
        if len(row_vals) < 2:
            continue
        spread = max(row_vals) - min(row_vals)
        if spread < 0.15:
            marker_text = "ALIGNED"
            marker_color = "#2E7D32"
        elif spread > 0.30:
            marker_text = "DIVERGENT"
            marker_color = "#CC0000"
        else:
            marker_text = ""
            marker_color = "#888888"

        if marker_text:
            ax.text(
                n_cols + 0.12, row_i + 0.5, marker_text,
                ha="left", va="center",
                fontsize=6.5, color=marker_color, fontweight="bold",
                zorder=3,
            )

    # ── Axes setup ────────────────────────────────────────────────────────────
    ax.set_xlim(0, n_cols + 1.2)
    ax.set_ylim(0, n_rows)

    # X-axis: column labels at top
    ax.set_xticks([j + 0.5 for j in range(n_cols)])
    ax.set_xticklabels(col_labels, fontsize=9, fontweight="bold", va="bottom")
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    ax.tick_params(axis="x", which="both", length=0, pad=4)

    # Y-axis: meeting labels
    ax.set_yticks([i + 0.5 for i in range(n_rows)])
    ax.set_yticklabels(row_labels, fontsize=8)
    ax.tick_params(axis="y", which="both", length=0, pad=6)

    # Invert y so most recent meeting is at top
    ax.invert_yaxis()

    for spine in ax.spines.values():
        spine.set_visible(False)

    # ── Colorbar ──────────────────────────────────────────────────────────────
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="horizontal", pad=0.04,
                        fraction=0.03, aspect=40)
    cbar.set_label("Sentiment Score  (-1.0 Extremely Dovish  |  0 Neutral  |  +1.0 Extremely Hawkish)", fontsize=7.5, color="#444444")
    cbar.ax.tick_params(labelsize=7)
    cbar.outline.set_linewidth(0)

    # ── Title & branding ──────────────────────────────────────────────────────
    if mode == "newsletter":
        title = "When Does the Committee Speak With One Voice?"
        subtitle = "Tone alignment across all three MPC documents"
    else:
        title = "Three-Document Tone Alignment Matrix"
        subtitle = (
            f"Last {len(df)} MPC cycles | "
            "ALIGNED = spread < 0.15 | DIVERGENT = spread > 0.30"
        )

    EconStyle.add_top_rule(ax)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_source(fig, "RBI MPC Documents")

    fig.subplots_adjust(top=0.82, bottom=0.12, left=0.14, right=0.90)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    EconStyle.save_chart(fig, output_path)
    log.info("Saved tone heatmap to %s", output_path)
