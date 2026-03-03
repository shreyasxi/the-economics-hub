"""
Economics Hub — Yield Curve Chart v5 (Bulletproof)
====================================================
Key fixes:
  - Forces ALL yield values to plain Python float (fixes isfinite crash)
  - Uses EconStyle.YIELD_CURVE_COLORS (now defined in v5 style)
  - Uses EconStyle.format_pct_axis (now defined in v5 style)
  - size="yield" now mapped in EconStyle v5
  - Fallback defaults if any style attribute is missing
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from style.economics_hub_style import EconStyle


class YieldCurveChart:

    def __init__(self):
        self.curves = []
        self.fig = self.ax = None

    def add_curve(self, name, tenors, yields, style="current"):
        """
        Add a curve to the chart.
        CRITICAL: Forces all yields to plain Python float to prevent
        the 'isfinite' numpy type error.
        """
        # ── BULLETPROOF FLOAT CONVERSION ──
        clean_tenors = []
        clean_yields = []
        for t, y in zip(tenors, yields):
            try:
                val = float(y)
                # Check for NaN
                if val != val:
                    continue
                clean_tenors.append(str(t))
                clean_yields.append(val)
            except (ValueError, TypeError):
                continue

        self.curves.append({
            "name": name,
            "tenors": clean_tenors,
            "yields": clean_yields,
            "style": style,
        })

    def render(self, title="US Treasury Yield Curve", subtitle=None, source="FRED"):
        # ── Figure ──
        try:
            self.fig, self.ax = EconStyle.create_figure(size="yield")
        except Exception:
            # Fallback if "yield" size not in style
            self.fig, self.ax = EconStyle.create_figure(size="standard")
        ax = self.ax

        # ── Curve styling (with fallbacks) ──
        try:
            yc_colors = EconStyle.YIELD_CURVE_COLORS
        except AttributeError:
            yc_colors = {"current": "#000000", "4w_ago": "#1f77b4", "52w_ago": "#B0B0B0"}

        # ── BULLETPROOF Y-AXIS SCALING (The "Zoom" Fix) ──
        # Find the absolute min and max yields across ALL curves
        all_yields = [y for curve in self.curves for y in curve["yields"]]
        if all_yields:
            y_min, y_max = min(all_yields), max(all_yields)
            y_range = y_max - y_min if y_max != y_min else 1.0
            
            # Pad the top and bottom by 15% so it breathes perfectly
            y_bottom = y_min - (y_range * 0.15)
            y_top = y_max + (y_range * 0.15)
        else:
            y_bottom, y_top = 0, 5

        # ── Upgraded Institutional Styling ──
        cfg = {
            "current": {"color": "#1C1C1E", 
                        "lw": 3.5, "ls": "-", "marker": "o", "ms": 7, "z": 10, "a": 1.0},
            "4w_ago":  {"color": "#2563EB", 
                        "lw": 2.5, "ls": "--", "marker": None, "ms": 0, "z": 8, "a": 1.0},
            "52w_ago": {"color": "#DC2626", 
                        "lw": 2.0, "ls": "-", "marker": None, "ms": 0, "z": 7, "a": 0.85},
        }

        for curve in self.curves:
            if len(curve["yields"]) == 0:
                continue

            c = cfg.get(curve["style"], cfg["current"])
            x = list(range(len(curve["tenors"])))
            y = curve["yields"]  # Already plain Python floats from add_curve()

            # ── Draw the lines ──
            ax.plot(x, y, color=c["color"], linewidth=c["lw"],
                    linestyle=c["ls"], marker=c["marker"], markersize=c["ms"],
                    markerfacecolor="white", markeredgecolor=c["color"],
                    markeredgewidth=1.8, label=curve["name"],
                    alpha=c["a"], zorder=c["z"],
                    solid_capstyle="round", antialiased=True)

            # ── NEW: Shaded fill now anchors to y_bottom, NOT zero ──
            if curve["style"] == "current":
                ax.fill_between(x, y, y2=y_bottom, color=c["color"], alpha=0.06, zorder=1)

            # ── LOCK THE Y-AXIS ZOOM ──
            ax.set_ylim(y_bottom, y_top)

            # Annotate key tenors on current curve
            if curve["style"] == "current":
                for i, (t, yv) in enumerate(zip(curve["tenors"], y)):
                    if t in {"2Y", "10Y", "30Y"}:
                        ax.annotate(
                            f"{yv:.2f}%", xy=(i, yv), xytext=(0, 10),
                            textcoords="offset points",
                            fontsize=EconStyle.FONT_SIZE_ANNOTATION,
                            fontweight="bold", color=c["color"],
                            ha="center", va="bottom",
                            fontfamily=EconStyle.FONT_FAMILY,
                            path_effects=[
                                pe.withStroke(linewidth=2.5,
                                              foreground=EconStyle.BACKGROUND)
                            ],
                        )

        # ── X-axis: tenor labels ──
        if self.curves:
            # Use the curve with the most tenors for x-ticks
            longest = max(self.curves, key=lambda c: len(c["tenors"]))
            ax.set_xticks(list(range(len(longest["tenors"]))))
            ax.set_xticklabels(longest["tenors"],
                               fontfamily=EconStyle.FONT_FAMILY,
                               color=EconStyle.TEXT_SECONDARY)

        # ── Y-axis formatting ──
        ax.set_ylabel("Yield (%)", fontsize=EconStyle.FONT_SIZE_AXIS,
                      color=EconStyle.TEXT_SECONDARY, labelpad=6)
        try:
            EconStyle.format_pct_axis(ax, decimals=1)
        except AttributeError:
            pass  # Graceful fallback if format_pct_axis missing

        # ── Grid ──
        ax.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.35)
        ax.grid(axis="x", visible=False)

        # ── Inversion shading ──
        if self.curves:
            cur = [c for c in self.curves if c["style"] == "current"]
            if cur:
                ylds = cur[0]["yields"]
                tnrs = cur[0]["tenors"]
                if "2Y" in tnrs and "10Y" in tnrs:
                    i2 = tnrs.index("2Y")
                    i10 = tnrs.index("10Y")
                    if ylds[i2] > ylds[i10]:
                        ax.axhspan(ylds[i10], ylds[i2], alpha=0.04,
                                   color=EconStyle.NEGATIVE, zorder=0)

        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", length=0)
        for spine in ["top", "right", "left"]:
            ax.spines[spine].set_visible(False)

        ax.legend(loc="lower right", frameon=False,
                  fontsize=EconStyle.FONT_SIZE_TICK,
                  labelcolor=EconStyle.TEXT_BODY)

        EconStyle.set_title(ax, title, subtitle)
        EconStyle.add_top_rule(ax)
        EconStyle.finalize(self.fig, ax, source=source)
        return self.fig, self.ax

    def save(self, filepath):
        if self.fig is None: raise ValueError("Call render() first.")
        return EconStyle.save_chart(self.fig, filepath)
