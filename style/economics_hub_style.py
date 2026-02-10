"""
Economics Hub — Visual Style Library v5 (FT/Bloomberg Quality)
================================================================
Bloomberg/WSJ inspired. Anti-aliased rendering.
Jet black text. Distinct line colors.
Adds: yield curve support, format_pct_axis, rendering quality params.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as mticker
import matplotlib.patheffects as pe
import numpy as np
from pathlib import Path
from datetime import datetime


class EconStyle:

    # ─── BACKGROUND & BORDER ─────────────────
    BACKGROUND       = "#FFFFFF"
    CHART_BG         = "#FFFFFF"
    ROW_ALT          = "#F4F4F4"

    # ─── TEXT (High Contrast / Jet Black) ────
    TEXT_TITLE        = "#000000"
    TEXT_BODY         = "#000000"
    TEXT_SECONDARY    = "#000000"
    TEXT_MUTED        = "#404040"
    TEXT_FAINT        = "#E0E0E0"

    # ─── STRUCTURE ───────────────────────────
    GRID_COLOR        = "#D6D6D6"
    AXIS_COLOR        = "#000000"
    RULE_HEAVY        = "#000000"
    RULE_LIGHT        = "#A0A0A0"

    # ─── DATA COLOURS (Distinct) ─────────────
    POSITIVE          = "#008000"
    NEGATIVE          = "#CC0000"

    # High Contrast Palette for Lines
    SERIES_COLORS = [
        "#000000",  # Black (Primary/DXY)
        "#1f77b4",  # Blue
        "#ff7f0e",  # Orange/Gold
        "#2ca02c",  # Green
        "#d62728",  # Red
        "#9467bd",  # Purple
        "#8c564b",  # Brown
        "#e377c2",  # Pink
    ]

    # Specific Mappings
    REGION_COLORS = {
        "us":               "#003366",  # Navy
        "europe":           "#008080",  # Teal
        "india":            "#FF9933",  # Saffron/Orange
        "asia":             "#800080",  # Purple
        "commodity_energy": "#CC0000",  # Red
        "commodity_metals": "#B8860B",  # Dark Goldenrod (fallback)
        "commodity_gold":   "#B8860B",  # Dark Goldenrod
        "commodity_silver": "#708090",  # Slate Grey
        "commodity_copper": "#B87333",  # Copper
        "special_black":    "#000000",  # For DXY
    }

    # ─── YIELD CURVE COLOURS ────────────────
    YIELD_CURVE_COLORS = {
        "current": "#000000",       # Black — current curve
        "4w_ago":  "#1f77b4",       # Blue — 4 weeks ago
        "52w_ago": "#CC3333",       # Red — 52 weeks ago
    }

    # ─── TYPOGRAPHY ──────────────────────────
    FONT_FAMILY      = "sans-serif"
    FONT_FALLBACK    = "Arial"

    FONT_SIZE_TITLE      = 18
    FONT_SIZE_SUBTITLE   = 10
    FONT_SIZE_AXIS       = 9
    FONT_SIZE_TICK       = 9
    FONT_SIZE_ANNOTATION = 9
    FONT_SIZE_SOURCE     = 8
    FONT_SIZE_BAR_LABEL  = 9
    FONT_SIZE_CATEGORY   = 8

    # ─── DIMENSIONS ──────────────────────────
    SIZE_WIDE        = (9.5, 4.8)
    SIZE_STANDARD    = (8.5, 4.5)
    SIZE_COMPACT     = (8.5, 3.5)
    SIZE_YIELD       = (8.5, 4.5)    # Yield curve specific

    DPI              = 250
    DPI_PREVIEW      = 120
    WATERMARK_TEXT   = "The Economics Hub"

    # ── Masthead Typography ──
    # Clean bold serif — institutional style (IMF, BIS, Federal Reserve).
    # NOT italic, NOT blackletter. Just strong, authoritative roman serif.
    # Cambria (Microsoft institutional default) → Georgia → Palatino → Times
    MASTHEAD_FONTS = [
        "Cambria",                 # Microsoft's institutional serif (Win default)
        "Georgia",                 # Robust screen serif (Win/Mac)
        "Palatino Linotype",       # Classical humanist (Windows)
        "Garamond",                # Renaissance elegance (Windows)
        "Times New Roman",         # Universal fallback
        "DejaVu Serif",           # Linux fallback
        "serif",
    ]

    # ─── INTERNAL METHODS ────────────────────

    @classmethod
    def _get_font(cls, weight="regular"):
        return fm.FontProperties(family=cls.FONT_FAMILY, weight=weight)

    @classmethod
    def _get_masthead_font(cls):
        """Strong bold roman serif — institutional authority."""
        return fm.FontProperties(
            family=cls.MASTHEAD_FONTS,
            weight="bold",
            style="normal",
        )

    @classmethod
    def apply_global_style(cls):
        """Apply high-quality rendering defaults globally."""
        plt.rcParams.update({
            "figure.facecolor":     cls.BACKGROUND,
            "axes.facecolor":       cls.CHART_BG,
            "axes.edgecolor":       cls.AXIS_COLOR,
            "axes.linewidth":       1,
            "axes.labelsize":       cls.FONT_SIZE_AXIS,
            "axes.labelcolor":      cls.TEXT_SECONDARY,
            "axes.titlecolor":      cls.TEXT_TITLE,
            "axes.spines.top":      False,
            "axes.spines.right":    False,
            "axes.spines.left":     False,
            "axes.spines.bottom":   True,
            "axes.grid":            True,
            "grid.color":           cls.GRID_COLOR,
            "grid.linewidth":       0.5,
            "xtick.color":          cls.TEXT_SECONDARY,
            "ytick.color":          cls.TEXT_SECONDARY,
            "font.family":          "sans-serif",
            "font.sans-serif":      ["Poppins", "Arial", "Calibri", "sans-serif"],
            # ─── v5: RENDERING QUALITY ───
            "lines.antialiased":    True,
            "patch.antialiased":    True,
            "text.antialiased":     True,
            "savefig.dpi":          cls.DPI,
            "figure.dpi":           cls.DPI,
            "path.simplify":        True,
            "path.simplify_threshold": 0.111,  # Less aggressive simplification
            "lines.solid_capstyle": "round",
            "lines.solid_joinstyle": "round",
        })

    @classmethod
    def create_figure(cls, size="standard", nrows=1, ncols=1, **kwargs):
        cls.apply_global_style()
        size_map = {
            "wide": cls.SIZE_WIDE,
            "standard": cls.SIZE_STANDARD,
            "compact": cls.SIZE_COMPACT,
            "yield": cls.SIZE_YIELD,
        }
        figsize = size_map.get(size, size) if isinstance(size, str) else size

        fig, ax = plt.subplots(nrows=nrows, ncols=ncols, figsize=figsize, **kwargs)

        # Black border
        fig.patch.set_linewidth(2)
        fig.patch.set_edgecolor('#000000')

        return fig, ax

    @classmethod
    def set_title(cls, ax, title, subtitle=None):
        ax.set_title(
            title, fontproperties=cls._get_font("bold"),
            fontsize=cls.FONT_SIZE_TITLE, color=cls.TEXT_TITLE,
            loc="left", pad=20 if subtitle else 10,
        )
        if subtitle:
            ax.text(
                0.0, 1.02, subtitle, transform=ax.transAxes,
                fontproperties=cls._get_font("regular"),
                fontsize=cls.FONT_SIZE_SUBTITLE,
                color=cls.TEXT_SECONDARY, va="bottom", ha="left",
            )

    @classmethod
    def add_top_rule(cls, ax):
        ax.plot([0, 1], [1, 1], color=cls.RULE_HEAVY, linewidth=1.5,
                transform=ax.transAxes, clip_on=False, zorder=10)

    @classmethod
    def add_source(cls, fig, source_text, date_text=None):
        if date_text is None:
            date_text = datetime.now().strftime("%d %b %Y")

        # Source footnote (left) — sans-serif, muted
        fig.text(
            0.04, 0.02,
            f"Source: {source_text}  |  {date_text}",
            fontproperties=cls._get_font("regular"),
            fontsize=cls.FONT_SIZE_SOURCE, color=cls.TEXT_MUTED,
            ha="left", va="bottom",
        )

        # ── Masthead watermark (right) — bold roman serif ──
        fig.text(
            0.96, 0.025,
            cls.WATERMARK_TEXT,
            fontproperties=cls._get_masthead_font(),
            fontsize=cls.FONT_SIZE_SOURCE + 3,
            color="#1A1A1A",
            ha="right", va="bottom",
        )

    # ─── HELPERS ─────────────────────────────

    @classmethod
    def get_color(cls, key):
        return cls.REGION_COLORS.get(key, cls.SERIES_COLORS[1])

    @classmethod
    def get_bar_colors(cls, vals):
        return [cls.POSITIVE if v >= 0 else cls.NEGATIVE for v in vals]

    @classmethod
    def format_change_label(cls, value, change_type="pct"):
        if value is None: return "-"
        if change_type == "pct":
            return f"{'+' if value > 0 else ''}{value:.1f}%"
        elif change_type == "abs":
            bps = value * 100
            return f"{'+' if bps > 0 else ''}{bps:.0f} bps"
        return str(value)

    @classmethod
    def format_pct_axis(cls, ax, decimals=1):
        """Format y-axis as percentage with N decimal places."""
        fmt_str = f"%.{decimals}f%%"
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter(fmt_str))

    @classmethod
    def finalize(cls, fig, ax=None, source=None, tight=True):
        if source: cls.add_source(fig, source)
        if tight:
            fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    @classmethod
    def save_chart(cls, fig, filepath, dpi=None):
        fp = Path(filepath)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(fp, dpi=dpi or cls.DPI, bbox_inches="tight",
                   facecolor=cls.BACKGROUND, edgecolor='#000000', pad_inches=0.1)
        plt.close(fig)
        return fp
