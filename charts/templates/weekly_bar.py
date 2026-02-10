"""
Economics Hub — Weekly Bar Chart v5 (Dead-zone fix)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from style.economics_hub_style import EconStyle


class WeeklyBarChart:

    def __init__(self, names, values, change_type="pct", color_keys=None,
                 use_region_colors=False):
        self.names = list(names)
        self.values = list(values)
        self.change_type = change_type
        self.color_keys = color_keys
        self.use_region_colors = use_region_colors
        self.fig = self.ax = None

    def render(self, title="Weekly Change", subtitle=None, source="Yahoo Finance"):
        n = len(self.names)
        height = max(2.0, 0.35 * n + 0.9)
        self.fig, self.ax = EconStyle.create_figure(size=(7.5, height))
        ax = self.ax

        y_pos = np.arange(n)
        colors = (
            [EconStyle.get_color(k) for k in self.color_keys]
            if self.use_region_colors and self.color_keys
            else EconStyle.get_bar_colors(self.values)
        )

        # Dead-zone: suppress bars smaller than 2% of largest bar
        # so near-zero floats (e.g., -0.004) don't render a visible bar
        max_abs = max(abs(v) for v in self.values) if self.values else 1
        dead_zone = max_abs * 0.02
        display_vals = [v if abs(v) > dead_zone else 0 for v in self.values]

        ax.barh(y_pos, display_vals, height=0.45, color=colors,
                edgecolor="none", alpha=0.82, zorder=3)

        for i, val in enumerate(self.values):
            label = EconStyle.format_change_label(val, self.change_type)
            offset = 0.05 * max_abs
            # Position label relative to display bar, not raw value
            dv = display_vals[i]
            x = dv + (offset if val >= 0 else -offset)
            ha = "left" if val >= 0 else "right"
            ax.text(x, i, label, va="center", ha=ha,
                    fontsize=EconStyle.FONT_SIZE_BAR_LABEL,
                    fontweight="bold", color=colors[i],
                    fontfamily=EconStyle.FONT_FAMILY, zorder=4,
                    path_effects=[pe.withStroke(linewidth=2, foreground=EconStyle.BACKGROUND)])

        x_pad = max_abs * 0.18
        xmin, xmax = ax.get_xlim()
        ax.set_xlim(xmin - x_pad, xmax + x_pad)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(self.names, fontfamily=EconStyle.FONT_FAMILY,
                           fontsize=EconStyle.FONT_SIZE_AXIS,
                           color=EconStyle.TEXT_BODY)
        ax.invert_yaxis()
        ax.axvline(x=0, color=EconStyle.AXIS_COLOR, linewidth=0.5, zorder=2)
        ax.grid(visible=False)
        ax.set_xticklabels([])
        ax.tick_params(axis="x", length=0)
        ax.tick_params(axis="y", length=0)
        for s in ax.spines.values(): s.set_visible(False)

        EconStyle.set_title(ax, title, subtitle)
        EconStyle.add_top_rule(ax)
        EconStyle.finalize(self.fig, ax, source=source)
        return self.fig, self.ax

    def save(self, filepath):
        if self.fig is None: raise ValueError("Call render() first.")
        return EconStyle.save_chart(self.fig, filepath)
