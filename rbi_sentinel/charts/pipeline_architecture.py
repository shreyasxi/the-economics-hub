"""
rbi_sentinel/charts/pipeline_architecture.py

Generates a static PNG of the RBI Sentinel pipeline architecture diagram.
Saved to assets/rbi_sentinel/pipeline_architecture.png (not month-stamped —
this is a static architectural reference that does not change with data).
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

log = logging.getLogger("rbi_sentinel.charts.pipeline_architecture")

# ── Colours ────────────────────────────────────────────────────────────────────
NAVY    = "#003366"
BOX_BG  = "#D6E4F0"
DB_BG   = "#A8C8E8"
BAND_BG = "#F4F6F9"
ARROW   = "#444444"
WHITE   = "#FFFFFF"
TEXT_MN = "#111111"   # main text
TEXT_SB = "#444444"   # subtitle text


# ── Drawing helpers ────────────────────────────────────────────────────────────

def _band(ax, y_center: float, band_h: float, stage_label: str) -> None:
    """Draw a horizontal stage band with a navy label strip on the left."""
    ax.add_patch(FancyBboxPatch(
        (0.30, y_center - band_h / 2), 13.40, band_h,
        boxstyle="round,pad=0.05",
        facecolor=BAND_BG, edgecolor="#CCCCCC", linewidth=0.7, zorder=0,
    ))
    ax.add_patch(FancyBboxPatch(
        (0.30, y_center - band_h / 2), 1.35, band_h,
        boxstyle="round,pad=0.03",
        facecolor=NAVY, edgecolor=NAVY, linewidth=0, zorder=1,
    ))
    ax.text(0.975, y_center, stage_label,
            ha="center", va="center",
            fontsize=7.5, color=WHITE, fontweight="bold", zorder=2)


def _box(ax, cx: float, cy: float, w: float, h: float,
         title: str, subtitle: str = "",
         bg: str = BOX_BG, fc: str = TEXT_MN, border: str = NAVY) -> None:
    """Draw a rounded rectangle with a bold title and optional subtitle."""
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.07",
        facecolor=bg, edgecolor=border, linewidth=1.3, zorder=3,
    ))
    if subtitle:
        ax.text(cx, cy + 0.12, title, ha="center", va="center",
                fontsize=8.5, color=fc, fontweight="bold", zorder=4)
        ax.text(cx, cy - 0.15, subtitle, ha="center", va="center",
                fontsize=7.2, color=WHITE if bg == NAVY else TEXT_SB, zorder=4)
    else:
        ax.text(cx, cy, title, ha="center", va="center",
                fontsize=8.5, color=fc, fontweight="bold", zorder=4)


def _arrow(ax, x1: float, y1: float, x2: float, y2: float, rad: float = 0.0) -> None:
    """Draw a thin annotate-arrow from (x1,y1) to (x2,y2)."""
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="->", color=ARROW, lw=1.1,
            connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=2,
    )


# ── Main generator ─────────────────────────────────────────────────────────────

def generate(output_path: Path) -> None:
    """
    Render and save the pipeline architecture PNG.

    Args:
        output_path: Full path for output PNG.
                     Typically assets/rbi_sentinel/pipeline_architecture.png
    """
    fig, ax = plt.subplots(figsize=(14, 7.5))
    fig.patch.set_facecolor(WHITE)
    ax.set_facecolor(WHITE)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7.5)
    ax.axis("off")

    BW = 2.40   # standard box width
    BH = 0.60   # standard box height

    # ── Title ─────────────────────────────────────────────────────────────────
    ax.text(7.0, 7.25,
            "RBI SENTINEL — NLP PIPELINE ARCHITECTURE",
            ha="center", va="center",
            fontsize=10.5, color=NAVY, fontweight="bold")

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 1 — Fetch  (y = 6.45)
    # Flow: rbi.org.in  →  Master Fetcher  →  File Cache
    # ══════════════════════════════════════════════════════════════════════════
    S1 = 6.45
    _band(ax, S1, 0.90, "Fetch")
    _box(ax,  3.0, S1, BW,   BH, "rbi.org.in",     "MPC Catalogue")
    _box(ax,  6.5, S1, 2.70, BH, "Master Fetcher",  "HTTP + ASP.NET Pagination")
    _box(ax, 10.3, S1, BW,   BH, "File Cache",      "HTML / PDF")
    _arrow(ax, 4.20, S1,  5.15, S1)          # rbi → Fetcher
    _arrow(ax, 7.85, S1,  9.10, S1)          # Fetcher → Cache

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 2 — Extract & Clean  (y = 5.20)
    # Flow: Cache (diagonal down-left) → Document Extractor → Text Normalizer
    # ══════════════════════════════════════════════════════════════════════════
    S2 = 5.20
    _band(ax, S2, 0.90, "Extract")
    _box(ax,  4.80, S2, 2.70, BH, "Document Extractor", "HTML (CSS selectors) + PDF (pdfplumber)")
    _box(ax,  9.50, S2, 2.60, BH, "Text Normalizer",    "Dedup + sentence splitting")
    _arrow(ax, 10.30, S1 - 0.30, 4.80, S2 + 0.30)  # Cache → Extractor
    _arrow(ax,  6.15, S2,        8.20, S2)           # Extractor → Normalizer

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 3 — Hybrid Scoring  (y = 3.65 centre; taller band for two branches)
    # Lexicon at y=4.05 | LLM at y=3.25 | Fusion at y=3.65 (right side)
    # ══════════════════════════════════════════════════════════════════════════
    S3 = 3.65
    _band(ax, S3, 1.70, "Score")

    _box(ax, 4.30, 4.05, 3.00, BH,
         "Domain Lexicon — 25%",
         "30+ phrases, 5-token negation window")
    _box(ax, 4.30, 3.25, 3.00, BH,
         "LLM Semantic Parser — 75%",
         "Claude API  |  6 sub-dimensions  |  structured JSON")
    _box(ax, 10.30, S3, 3.00, BH,
         "Score Fusion",
         "0.25 \u00d7 lex + 0.75 \u00d7 llm  |  conflict flag: |\u0394| > 0.40")

    # Normalizer → Lexicon (diagonal down-left)
    _arrow(ax, 9.50, S2 - 0.30, 5.80, 4.05 + 0.30)
    # Normalizer → LLM (longer diagonal)
    _arrow(ax, 9.50, S2 - 0.30, 5.80, 3.25 + 0.30)
    # Lexicon → Fusion
    _arrow(ax, 5.80, 4.05, 8.80, 3.75)
    # LLM → Fusion
    _arrow(ax, 5.80, 3.25, 8.80, 3.55)

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 4 — Store  (y = 2.10)
    # Flow (right → left, snake pattern):
    #   Fusion (above) ↓ sentiment_scores  ←  Composite Engine  ←  meeting_composites
    # ══════════════════════════════════════════════════════════════════════════
    S4 = 2.10
    _band(ax, S4, 0.90, "Store")

    _box(ax, 10.30, S4, 2.60, BH, "sentiment_scores",   "SQLite — raw per-doc scores",  bg=DB_BG)
    _box(ax,  7.00, S4, 3.00, BH, "Composite Engine",   "Minutes 50%  ·  Res 35%  ·  Gov 15%")
    _box(ax,  3.30, S4, 2.60, BH, "meeting_composites", "SQLite — per-meeting aggregates", bg=DB_BG)

    # Fusion center-bottom → sentiment_scores top (short drop)
    _arrow(ax, 10.30, S3 - 0.30, 10.30, S4 + 0.30)
    # sentiment_scores → Composite (leftward)
    _arrow(ax,  9.00, S4,  8.50, S4)
    # Composite → meeting_composites (leftward)
    _arrow(ax,  5.50, S4,  4.60, S4)

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 5 — Visualise  (y = 0.80)
    # Flow: meeting_composites ↓ Chart Generator → Streamlit Dashboard
    # ══════════════════════════════════════════════════════════════════════════
    S5 = 0.80
    _band(ax, S5, 0.90, "Visualise")

    _box(ax, 4.50, S5, 2.80, BH, "Chart Generator",      "9 EconStyle matplotlib charts")
    _box(ax, 9.00, S5, 2.80, BH, "Streamlit Dashboard",  "The RBI Sentinel Tab",
         bg=NAVY, fc=WHITE, border=NAVY)

    # meeting_composites bottom → Chart Generator top (diagonal down-right)
    _arrow(ax, 3.30, S4 - 0.30, 4.50, S5 + 0.30)
    # Chart Generator → Dashboard
    _arrow(ax, 5.90, S5, 7.60, S5)

    # ── Source attribution ────────────────────────────────────────────────────
    ax.text(13.70, 0.10, "The Economics Hub",
            ha="right", va="center",
            fontsize=7.0, color="#888888")

    fig.subplots_adjust(top=0.98, bottom=0.02, left=0.01, right=0.99)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=WHITE, edgecolor="none")
    plt.close(fig)
    log.info("Saved pipeline architecture diagram to %s", output_path)
