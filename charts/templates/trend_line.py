"""
Economics Hub — Trend Line Chart v5 (FT/Bloomberg Quality)
============================================================
Key improvements over v4:
  - Anti-aliased rendering via rcParams (set in EconStyle v5)
  - Subtle line shadow for visual depth (like FT print edition)
  - Smoother line rendering with round caps/joins
  - Cleaner y-axis formatting (commas for large numbers)
  - Better end-label positioning with background pill
  - Optional reference lines (horizontal annotations)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import matplotlib.ticker as mticker
import numpy as np
from style.economics_hub_style import EconStyle


class TrendLineChart:

    def __init__(self):
        self.series = []
        self.ref_lines = []    # Horizontal reference lines (e.g., Fed target)
        self.fig = self.ax = None

    def add_series(self, name, dates, values, color_key=None, index=0,
                   show_area=True, linewidth=2.0, linestyle="-"):
        self.series.append({
            "name": name, "dates": dates, "values": values,
            "color_key": color_key, "index": index,
            "show_area": show_area, "linewidth": linewidth,
            "linestyle": linestyle,
        })

    def add_reference_line(self, y_value, label="", color="#999999",
                           linestyle="--", linewidth=0.8):
        """Add a horizontal reference line (e.g., '2% target')."""
        self.ref_lines.append({
            "y": y_value, "label": label, "color": color,
            "linestyle": linestyle, "linewidth": linewidth,
        })

    def render(self, title="Trailing 12 Months", subtitle=None,
               source="Yahoo Finance", ylabel=None, show_endpoints=True,
               size="wide", date_format="%b '%y", normalize=False):

        self.fig, self.ax = EconStyle.create_figure(size=size)
        ax = self.ax

        num_series = len(self.series)

        for i, s in enumerate(self.series):
            color = (EconStyle.get_color(s["color_key"]) if s["color_key"]
                     else EconStyle.SERIES_COLORS[s["index"] % len(EconStyle.SERIES_COLORS)])

            values = np.array(s["values"], dtype=float)
            if normalize and len(values) > 0 and values[0] != 0:
                values = (values / values[0]) * 100

            lw = s["linewidth"]

            # ── v5: SUBTLE SHADOW for visual depth ──
            # Light shadow slightly offset below the main line.
            # This gives the FT "printed on quality paper" feel.
            if num_series <= 3:
                ax.plot(s["dates"], values, color=color, linewidth=lw + 1.2,
                        linestyle=s["linestyle"], alpha=0.07, zorder=2 + i,
                        solid_capstyle="round", solid_joinstyle="round")

            # ── Main line ──
            ax.plot(s["dates"], values, color=color, linewidth=lw,
                    linestyle=s["linestyle"], alpha=1.0, zorder=3 + i,
                    solid_capstyle="round", solid_joinstyle="round",
                    antialiased=True)

            # ── Subtle area fill for single-series charts ──
            if s["show_area"] and num_series == 1:
                ax.fill_between(s["dates"], values, alpha=0.04, color=color, zorder=1)

            # ── End-label with background pill ──
            if show_endpoints and len(values) > 0:
                last_val, last_date = values[-1], s["dates"][-1]

                # Smart formatting
                if normalize:
                    vs = f"{last_val:.1f}"
                elif abs(last_val) > 10000:
                    vs = f"{last_val:,.0f}"
                elif abs(last_val) > 100:
                    vs = f"{last_val:,.0f}"
                elif abs(last_val) > 1:
                    vs = f"{last_val:.2f}"
                else:
                    vs = f"{last_val:.4f}"

                label = f" {s['name']}  {vs}" if num_series > 1 else f" {vs}"
                ax.annotate(
                    label, xy=(last_date, last_val),
                    xytext=(5, 0), textcoords="offset points",
                    fontproperties=EconStyle._get_font("bold"),
                    fontsize=EconStyle.FONT_SIZE_ANNOTATION - 0.5,
                    color=color, va="center", ha="left",
                    path_effects=[
                        pe.withStroke(linewidth=3.0, foreground=EconStyle.BACKGROUND),
                    ],
                )

        # ── Reference lines ──
        for ref in self.ref_lines:
            ax.axhline(y=ref["y"], color=ref["color"], linewidth=ref["linewidth"],
                       linestyle=ref["linestyle"], alpha=0.6, zorder=1)
            if ref["label"]:
                ax.text(ax.get_xlim()[0], ref["y"] + 0.05,
                        f" {ref['label']}", fontsize=7, color=ref["color"],
                        alpha=0.7, va="bottom")

        # ── X-axis formatting ──
        ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
        plt.setp(ax.get_xticklabels(), rotation=0, ha="center",
                 fontsize=EconStyle.FONT_SIZE_TICK)

        # ── Y-axis formatting (smart number formatting) ──
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=EconStyle.FONT_SIZE_AXIS,
                         color=EconStyle.TEXT_SECONDARY, labelpad=6)

        # Smart y-tick formatting: commas for large numbers
        ymin, ymax = ax.get_ylim()
        if ymax > 1000:
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(
                lambda x, p: f"{x:,.0f}"))
        elif ymax > 10:
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(
                lambda x, p: f"{x:.1f}"))
        else:
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(
                lambda x, p: f"{x:.2f}"))

        # ── Grid: horizontal only, subtle ──
        ax.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR,
                linewidth=0.35, linestyle="-")
        ax.grid(axis="x", visible=False)

        # ── Tight y-padding ──
        ymin, ymax = ax.get_ylim()
        pad = (ymax - ymin) * 0.06
        ax.set_ylim(ymin - pad * 0.2, ymax + pad)

        # ── Right margin for end-labels ──
        ax.margins(x=0.01)
        xmin, xmax = ax.get_xlim()
        ax.set_xlim(xmin, xmax + (xmax - xmin) * 0.14)

        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", length=0)

        EconStyle.set_title(ax, title, subtitle)
        EconStyle.add_top_rule(ax)
        EconStyle.finalize(self.fig, ax, source=source)
        return self.fig, self.ax

    def save(self, filepath):
        if self.fig is None: raise ValueError("Call render() first.")
        return EconStyle.save_chart(self.fig, filepath)
