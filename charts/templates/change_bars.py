"""
Economics Hub — Weekly change bars (equities, commodities, FX)
==============================================================
One horizontal bar per market, sorted from the largest gain to the largest
loss, so each chart reads as a ranking of the week.

Design notes
- Colour carries only the sign: EconStyle.GAIN / EconStyle.LOSS, a blue↔red
  diverging pair checked with the dataviz palette validator on white (both
  pass lightness, chroma, colour-blind separation and contrast). Blue↔red
  rather than green↔red so a currency move doesn't read as "good" or "bad",
  and so red-green colour-blind readers can still tell the sides apart.
- The sign is never colour-alone: bars point left or right of the baseline,
  and every value is printed with its sign.
- Every bar is labelled at its tip, in ink rather than the bar colour, so the
  axis, gridlines and ticks are dropped — they would only repeat the labels.
- Bars are thin (capped in pixels, never filling the row), with a rounded
  data end and a square end on the zero baseline.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
from charts.style import EconStyle

BAR_MAX_PX = 52          # bar thickness cap at the chart's DPI (~24px on screen)
BAR_ROW_SHARE = 0.52     # bars never take more than this share of their row
CORNER_PX = 9            # rounding at the data end (~4px on screen)
LABEL_GAP_PX = 14        # space between a bar's tip and its value
NAME_GAP_PX = 36         # space between the name column and the bars
ROW_BAND = "#F4F4F2"     # alternate-row band, one step off the white surface
ZERO_EPS = 0.05         # |change| below this prints as 0.0% with no bar


def _format(v):
    if abs(v) < ZERO_EPS:
        return "0.0%"
    return f"{'+' if v > 0 else '−'}{abs(v):.1f}%"


def _bar_path(v, y, half_h, rx, ry):
    """A bar from 0 to v centred on y: square at the baseline, rounded at the tip."""
    s = 1 if v >= 0 else -1
    rx = min(rx, abs(v))
    ry = min(ry, half_h)
    top, bot = y - half_h, y + half_h
    tip = v
    verts = [
        (0, top),
        (tip - s * rx, top),
        (tip, top), (tip, top + ry),              # rounded corner
        (tip, bot - ry),
        (tip, bot), (tip - s * rx, bot),          # rounded corner
        (0, bot),
        (0, top),
    ]
    codes = [
        MplPath.MOVETO,
        MplPath.LINETO,
        MplPath.CURVE3, MplPath.CURVE3,
        MplPath.LINETO,
        MplPath.CURVE3, MplPath.CURVE3,
        MplPath.LINETO,
        MplPath.CLOSEPOLY,
    ]
    return MplPath(verts, codes)


def render_change_bars(names, values, title, subtitle, source, size="wide"):
    """Draw the ranked weekly-change bars. Returns the figure, or None if empty."""
    rows = sorted(zip(names, values), key=lambda r: r[1], reverse=True)
    if not rows:
        return None
    names = [r[0] for r in rows]
    values = [r[1] for r in rows]
    n = len(values)

    fig, ax = EconStyle.create_figure(size=size)
    ys = list(range(n))

    # Rows, largest gain at the top. Names are drawn inside the plot as a
    # left-aligned column (not tick labels), so they share one left edge with
    # the title and the source line whatever the names are.
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.grid(visible=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    name_texts = [
        ax.text(0, y, name, transform=ax.get_yaxis_transform(), va="center", ha="left",
                fontsize=EconStyle.FONT_SIZE_CATEGORY + 2, color=EconStyle.INK)
        for y, name in zip(ys, names)
    ]

    lo, hi = min(min(values), 0.0), max(max(values), 0.0)
    if hi - lo == 0:
        hi = 1.0
    ax.set_xlim(lo, hi)  # provisional; widened below once label sizes are known

    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, source)

    # Value labels, measured so the x-range leaves exactly enough room for them.
    labels = [
        ax.text(0, y, _format(v), va="center", ha="left" if v >= 0 else "right",
                fontsize=EconStyle.FONT_SIZE_BAR_LABEL + 1, fontweight="semibold",
                color=EconStyle.INK, zorder=5)
        for y, v in zip(ys, values)
    ]
    renderer = fig.canvas.get_renderer()
    widths = [t.get_window_extent(renderer).width for t in labels]
    name_col = max(t.get_window_extent(renderer).width for t in name_texts) + NAME_GAP_PX
    pad_right = max((w for w, v in zip(widths, values) if v >= 0), default=0) + LABEL_GAP_PX + 6
    neg_label = max((w for w, v in zip(widths, values) if v < 0), default=0)
    pad_left = name_col + (neg_label + LABEL_GAP_PX if neg_label else 0)

    box = ax.get_window_extent(renderer)
    span = (hi - lo) / (1 - (pad_left + pad_right) / box.width)
    px_per_x = box.width / span
    ax.set_xlim(lo - pad_left / px_per_x, hi + pad_right / px_per_x)
    px_per_y = box.height / n

    half_h = min(BAR_ROW_SHARE / 2, BAR_MAX_PX / 2 / px_per_y)
    rx, ry = CORNER_PX / px_per_x, CORNER_PX / px_per_y
    gap = LABEL_GAP_PX / px_per_x

    for y, v, label in zip(ys, values, labels):
        if abs(v) >= ZERO_EPS:
            color = EconStyle.GAIN if v > 0 else EconStyle.LOSS
            ax.add_patch(PathPatch(_bar_path(v, y, half_h, rx, ry),
                                   facecolor=color, edgecolor="none", zorder=3))
        label.set_x(v + gap if v >= 0 else v - gap)

    # Faint bands on alternate rows carry the eye from a name to its bar
    # across the empty stretch between them (short names, one-sided moves).
    for y in ys[1::2]:
        ax.axhspan(y - 0.5, y + 0.5, color=ROW_BAND, linewidth=0, zorder=0)

    # The one structural line: the zero baseline.
    ax.axvline(0, color=EconStyle.INK_MUTED, linewidth=0.9, zorder=4)
    return fig
