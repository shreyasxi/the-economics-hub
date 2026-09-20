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
from matplotlib.lines import Line2D
from matplotlib.offsetbox import (AnchoredOffsetbox, DrawingArea, HPacker,
                                  TextArea, VPacker)
from pathlib import Path
from datetime import datetime


# ─── BUNDLED FONTS ───────────────────────────────────────────────────────────
# Faces the charts need that no machine can be assumed to have. They are
# committed to the repository, not installed, so a chart drawn here and the
# same chart drawn by GitHub Actions use the same letters. Drop a .ttf in and
# it is registered on import; nothing else has to change.
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _register_bundled_fonts() -> set:
    """Add assets/fonts/*.ttf to Matplotlib's font list. Returns the family names."""
    names = set()
    for ttf in sorted(FONT_DIR.glob("*.ttf")):
        try:
            fm.fontManager.addfont(str(ttf))
            names.add(fm.FontProperties(fname=str(ttf)).get_name())
        except Exception as exc:                      # a broken file must not stop a run
            print(f"   ⚠ could not load font {ttf.name}: {exc}")
    return names


_BUNDLED_FONTS = _register_bundled_fonts()


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

    # Line palette for the redesigned line charts (World tab). Checked with the
    # dataviz palette validator on white: lightness, chroma, colour-blind
    # separation and contrast pass. Fixed order, never cycled.
    LINE_BLUE        = "#1F5596"
    LINE_TEAL        = "#0B8F82"
    LINE_ORANGE      = "#C8620A"
    LINE_MAROON      = "#9B1C31"   # second panel of two-panel charts (claims, excess CAPE yield)
    LINE_RUPEE       = "#EA8412"   # India's saffron, deepened for a line; light on white, so always labelled
    INK              = "#1A1A1A"   # label values
    INK_MUTED        = "#4B5563"   # label names, reference lines

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
        "pink":             "#BE185D"
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

    # ── Credit line ──
    # The credit is a signature, not a second title. It used to be set three
    # points larger than the source line and in near-black, so on a dashboard
    # of forty charts the eye landed on the byline before the data.
    #
    # It is now a wordmark in two parts on one baseline: "The" in a script
    # face, then "ECONOMICS HUB" in letter-spaced caps. The script is set a
    # little larger because a cursive lower case is small for its point size —
    # at the same size it would look like a mistake rather than a contrast.
    # Matplotlib has no tracking control, so thin spaces stand in for it.
    #
    # To restyle it, change these constants — no drawing code anywhere calls
    # for the credit itself. WATERMARK_SCRIPT = "" gives the caps alone.
    WATERMARK_SCRIPT = "The"
    WATERMARK_TEXT   = "Economics Hub"
    WATERMARK_SIZE   = FONT_SIZE_SOURCE - 0.5    # the caps; the source line's size
    WATERMARK_SCRIPT_BOOST = 2.5                 # points added for the script word
    WATERMARK_GAP    = 3.5                       # points between the two parts
    WATERMARK_COLOR  = "#6B7280"                 # "#003366" for the house navy
    WATERMARK_CAPS   = True
    WATERMARK_TRACK  = " "       # "" for no letter-spacing

    # The rule or shape that closes the mark, so it reads as a logo rather than
    # a line of type. One of:
    #   "none"  the wordmark alone
    #   "under" a hairline the full width of the mark, beneath it
    #   "dash"  a short centred rule beneath, a masthead dash
    #   "band"  hairlines above and below, as the site's descriptor strip
    #   "lead"  a short rule before "The", on the same line
    #   "box"   a thin outline around the whole mark
    WATERMARK_RULE   = "under"
    WATERMARK_RULE_LW = 0.7          # points

    # Bundled (assets/fonts). The fallbacks are italics rather than romans: if
    # the script face is ever missing, a slanted "The" still reads as a
    # different voice from the caps beside it.
    SCRIPT_FONTS = ["Dancing Script", "Snell Roundhand", "Apple Chancery", "DejaVu Serif"]

    # ── Masthead Typography ──
    # Playfair Display is the face the site's own nameplate is set in, so the
    # credit at the foot of a chart is a small echo of the masthead at the top
    # of the page. It is bundled (assets/fonts) rather than assumed: the list
    # used to start with Cambria and Palatino, which exist on neither this
    # machine nor the CI runner, and the credit resolved to Georgia here and to
    # DejaVu Serif in Actions — two different wordmarks on the same site.
    #
    # The list still ends in DejaVu Serif, and that matters beyond insurance:
    # Matplotlib falls back family by family for a glyph the chosen face lacks,
    # and the thin spaces that letter-space the caps are exactly such a glyph
    # in several serifs. Playfair has U+2009; keep a font that does at the end.
    MASTHEAD_FONTS = [
        "Playfair Display",        # bundled — the site's masthead face
        "Georgia",                 # robust screen serif (Win/Mac)
        "Times New Roman",         # universal fallback
        "DejaVu Serif",            # ships with Matplotlib everywhere
        "serif",
    ]

    # ─── INTERNAL METHODS ────────────────────

    @classmethod
    def _get_font(cls, weight="regular"):
        return fm.FontProperties(family=cls.FONT_FAMILY, weight=weight)

    @classmethod
    def _watermark_label(cls):
        """The roman half of the credit as it is drawn: caps, with thin spaces for tracking."""
        text = cls.WATERMARK_TEXT.upper() if cls.WATERMARK_CAPS else cls.WATERMARK_TEXT
        return cls.WATERMARK_TRACK.join(text) if cls.WATERMARK_TRACK else text

    @classmethod
    def _get_script_font(cls):
        """The cursive face for the credit's first word."""
        return fm.FontProperties(family=cls.SCRIPT_FONTS, style="italic")

    @classmethod
    def _credit_row(cls, size):
        """Script word and caps packed on one baseline."""
        parts = []
        if cls.WATERMARK_SCRIPT:
            parts.append(TextArea(cls.WATERMARK_SCRIPT, textprops=dict(
                fontproperties=cls._get_script_font(),
                fontsize=size + cls.WATERMARK_SCRIPT_BOOST,
                color=cls.WATERMARK_COLOR)))
        parts.append(TextArea(cls._watermark_label(), textprops=dict(
            fontproperties=cls._get_masthead_font(),
            fontsize=size,
            color=cls.WATERMARK_COLOR)))
        return HPacker(children=parts, align="baseline", pad=0, sep=cls.WATERMARK_GAP)

    @classmethod
    def _rule(cls, width_pt):
        """A horizontal hairline `width_pt` long, as an offsetbox child."""
        lw = cls.WATERMARK_RULE_LW
        area = DrawingArea(width_pt, lw, 0, 0)
        area.add_artist(Line2D([0, width_pt], [lw / 2, lw / 2],
                               lw=lw, color=cls.WATERMARK_COLOR,
                               solid_capstyle="butt"))
        return area

    @classmethod
    def draw_credit(cls, fig, x=0.96, y=0.02, size=None, ax=None, transform=None):
        """
        Draw the wordmark with its lower-right corner at (x, y).

        The parts are packed rather than placed by hand: the script word's
        width changes with the face, and measuring it to position the caps
        would have to happen after the figure is laid out but before it is
        saved. A rule is sized the same way — from the row's measured width, so
        it always matches the mark it closes. Anchored to the figure by
        default; pass an Axes and its transform to place it inside one (the
        summary tables).
        """
        size = size or cls.WATERMARK_SIZE
        row = cls._credit_row(size)
        rule = cls.WATERMARK_RULE
        child, frame = row, False

        if rule in ("under", "dash", "band", "lead"):
            # Measure the mark so the rule is exactly as wide as it is. The
            # packer has to know its figure first — its Text children read the
            # figure's dpi to lay themselves out, and raise without one.
            try:
                renderer = fig.canvas.get_renderer()
                row.set_figure(fig)
                bbox = row.get_bbox(renderer)          # Matplotlib >= 3.7
                width_pt = bbox.width * 72.0 / fig.dpi
            except Exception as exc:    # never fail a chart over a rule
                print(f"   ⚠ credit rule skipped: {exc}")
                width_pt = 0
            if width_pt > 0:
                gap = max(1.6, size * 0.28)
                if rule == "under":
                    child = VPacker(children=[row, cls._rule(width_pt)],
                                    align="center", pad=0, sep=gap)
                elif rule == "dash":
                    child = VPacker(children=[row, cls._rule(width_pt * 0.3)],
                                    align="center", pad=0, sep=gap)
                elif rule == "band":
                    child = VPacker(children=[cls._rule(width_pt), row,
                                              cls._rule(width_pt)],
                                    align="center", pad=0, sep=gap)
                elif rule == "lead":
                    child = HPacker(children=[cls._rule(width_pt * 0.22), row],
                                    align="center", pad=0, sep=gap * 1.6)
        elif rule == "box":
            frame = True

        box = AnchoredOffsetbox(
            loc="lower right", child=child,
            pad=0.34 if frame else 0, borderpad=0, frameon=frame,
            bbox_to_anchor=(x, y),
            bbox_transform=transform if transform is not None else fig.transFigure,
        )
        if frame:
            box.patch.set(boxstyle="round,pad=0.3,rounding_size=0.18",
                          facecolor="none", edgecolor=cls.WATERMARK_COLOR,
                          linewidth=cls.WATERMARK_RULE_LW, alpha=0.75)
        (ax if ax is not None else fig).add_artist(box)
        return box

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
            # Arial and Calibri were removed: neither ships the Indian Rupee sign
            # (U+20B9), so every "₹" in the India charts rendered as a blank box
            # on macOS. They are also Windows/macOS-only, so local output never
            # matched what CI published. DejaVu Sans ships with matplotlib on
            # every platform and has the glyph, so local now matches CI exactly.
            # Drop a Poppins TTF into assets/fonts/ to get the intended face back.
            "font.sans-serif":      ["Poppins", "DejaVu Sans", "sans-serif"],
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

        # ── Credit (right) — the wordmark, on the source line's baseline ──
        cls.draw_credit(fig, x=0.96, y=0.02)

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
