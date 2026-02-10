"""
Economics Hub — India Macro Dashboard
========================================
Generates India-specific charts from manually maintained CSV data.

Data sources (all manual — no API available):
  - Manufacturing PMI:   tradingeconomics.com/india/manufacturing-pmi (1st biz day)
  - Services PMI:        tradingeconomics.com/india/services-pmi (3rd biz day)
  - GST Revenue:         pib.gov.in (1st of month, ₹ Lakh Cr)
  - Bank Credit Growth:  RBI monthly bulletin (YoY %)
  - Unemployment:        CMIE (monthly)
  - FPI Flows:           fpi.nsdl.co.in (net monthly, $B)

Usage:
  python generate_india.py                    # Generate all charts
  python generate_india.py --csv path.csv     # Use custom CSV path
  python generate_india.py --months 18        # Last 18 months only

Monthly workflow:
  1. Open data/india_manual.csv
  2. Add a new row: date (YYYY-MM), fill each column
  3. Save → run this script
  4. Charts appear in output/india/YYYY-MM/
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

# ── Project imports ──
sys.path.insert(0, str(Path(__file__).parent))
from style.economics_hub_style import EconStyle


# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════

DEFAULT_CSV = Path(__file__).parent / "data" / "india_manual.csv"
OUTPUT_BASE = Path(__file__).parent / "output" / "india"

# Colors
C_MFG_PMI       = "#003366"     # Navy — manufacturing
C_SVC_PMI       = "#CC0066"     # Magenta — services
C_COMPOSITE     = "#FF9933"     # Saffron — composite/India
C_GST           = "#2ca02c"     # Green — revenue
C_CREDIT        = "#003366"     # Navy — credit
C_UNEMPLOYMENT  = "#CC0000"     # Red — unemployment
C_FPI_POS       = "#065F46"     # Dark green — inflows
C_FPI_NEG       = "#991B1B"     # Dark red — outflows
C_PMI_50        = "#999999"     # Grey — expansion/contraction line


# ═══════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════

def load_india_data(csv_path=DEFAULT_CSV, months=None):
    """Load and validate the India manual CSV."""
    if not csv_path.exists():
        print(f"❌ CSV not found: {csv_path}")
        print(f"   Create it with columns: date,india_mfg_pmi,india_svc_pmi,...")
        sys.exit(1)

    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if months:
        cutoff = df["date"].max() - pd.DateOffset(months=months)
        df = df[df["date"] >= cutoff].reset_index(drop=True)

    print(f"   Loaded {len(df)} months from {csv_path.name}")
    print(f"   Range: {df['date'].min():%b %Y} → {df['date'].max():%b %Y}")
    return df


# ═══════════════════════════════════════════
# CHART HELPERS
# ═══════════════════════════════════════════

def _add_end_label(ax, dates, vals, label, color, offset_x=8, offset_y=0):
    """Add end-of-line label with value."""
    if len(dates) == 0 or len(vals) == 0:
        return
    last_val = float(vals[-1]) if hasattr(vals[-1], 'item') else float(vals[-1])
    ax.annotate(
        f"{label}  {last_val:.1f}",
        xy=(dates[-1], last_val),
        xytext=(offset_x, offset_y), textcoords="offset points",
        fontsize=9, fontweight="bold", color=color,
        fontfamily=EconStyle.FONT_FAMILY,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                  edgecolor="none", alpha=0.85),
        zorder=10,
    )


def _format_date_axis(ax):
    """Clean date formatting for monthly data."""
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=8)


# ═══════════════════════════════════════════
# CHART 1: PMI DASHBOARD
# ═══════════════════════════════════════════

def chart_pmi(df, output_dir):
    """Manufacturing + Services PMI with expansion/contraction zones."""
    fig, ax = EconStyle.create_figure(size="wide")

    dates = df["date"].tolist()

    # Manufacturing PMI
    if "india_mfg_pmi" in df.columns:
        vals = df["india_mfg_pmi"].values
        ax.plot(dates, vals, color=C_MFG_PMI, linewidth=2.5,
                label="Manufacturing", zorder=5, solid_capstyle="round")
        # Shadow for depth
        ax.plot(dates, vals, color=C_MFG_PMI, linewidth=3.7,
                alpha=0.07, zorder=4, solid_capstyle="round")
        _add_end_label(ax, dates, vals, "Mfg", C_MFG_PMI)

    # Services PMI
    if "india_svc_pmi" in df.columns:
        vals = df["india_svc_pmi"].values
        ax.plot(dates, vals, color=C_SVC_PMI, linewidth=2.2,
                label="Services", zorder=5, solid_capstyle="round")
        ax.plot(dates, vals, color=C_SVC_PMI, linewidth=3.4,
                alpha=0.07, zorder=4, solid_capstyle="round")
        _add_end_label(ax, dates, vals, "Svc", C_SVC_PMI, offset_y=-14)

    # Expansion/contraction line at 50
    ax.axhline(y=50, color=C_PMI_50, linewidth=1.2, linestyle="--", zorder=1)
    ax.text(dates[0], 50.3, "< Contraction  |  Expansion >",
            fontsize=7.5, color="#888888", va="bottom",
            fontfamily=EconStyle.FONT_FAMILY)

    # Light fill: green above 50, red below 50 for manufacturing
    if "india_mfg_pmi" in df.columns:
        mfg = df["india_mfg_pmi"].values
        ax.fill_between(dates, 50, mfg, where=(mfg >= 50),
                        color=C_FPI_POS, alpha=0.04, interpolate=True)
        ax.fill_between(dates, 50, mfg, where=(mfg < 50),
                        color=C_FPI_NEG, alpha=0.04, interpolate=True)

    _format_date_axis(ax)
    ax.set_ylabel("PMI Index", fontsize=EconStyle.FONT_SIZE_AXIS)
    ax.legend(loc="lower left", frameon=True, facecolor="white",
              edgecolor="#E0E0E0", fontsize=9)

    EconStyle.set_title(ax, "India PMI Dashboard",
                        "S&P Global Manufacturing & Services PMI")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "S&P Global (IHS Markit)")

    fp = output_dir / "01_india_pmi.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ PMI Dashboard")
    return fp


# ═══════════════════════════════════════════
# CHART 2: GST REVENUE
# ═══════════════════════════════════════════

def chart_gst(df, output_dir):
    """Monthly GST collection bar chart with trend line."""
    if "india_gst_revenue" not in df.columns:
        print("   ⚠ Skipping GST — column not found")
        return None

    fig, ax = EconStyle.create_figure(size="wide")

    dates = df["date"].tolist()
    vals = df["india_gst_revenue"].values

    # Bar chart
    colors = [C_GST if v >= df["india_gst_revenue"].median() else "#7CB342"
              for v in vals]
    bar_width = 20  # days
    ax.bar(dates, vals, width=bar_width, color=colors, alpha=0.75,
           edgecolor="none", zorder=3)

    # 3-month moving average trend
    if len(vals) >= 3:
        ma3 = pd.Series(vals).rolling(3).mean().values
        ax.plot(dates, ma3, color="#000000", linewidth=2, linestyle="-",
                label="3M Avg", zorder=5, solid_capstyle="round")
        # End label for MA
        valid_ma = [(d, v) for d, v in zip(dates, ma3) if not np.isnan(v)]
        if valid_ma:
            _add_end_label(ax, [d for d, _ in valid_ma],
                          [v for _, v in valid_ma], "3M Avg", "#000000")

    # ₹2 Lakh Cr reference
    ax.axhline(y=2.0, color="#FF9933", linewidth=1, linestyle="--",
               alpha=0.6, zorder=1)
    ax.text(dates[-1], 2.02, "₹2L Cr", fontsize=7.5, color="#FF9933",
            ha="right", va="bottom", fontfamily=EconStyle.FONT_FAMILY)

    _format_date_axis(ax)
    ax.set_ylabel("₹ Lakh Crore", fontsize=EconStyle.FONT_SIZE_AXIS)
    ax.legend(loc="upper left", frameon=True, facecolor="white",
              edgecolor="#E0E0E0", fontsize=9)

    EconStyle.set_title(ax, "GST Revenue Collections",
                        "Monthly Gross GST Revenue (₹ Lakh Crore)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "PIB / GST Council")

    fp = output_dir / "02_india_gst.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ GST Revenue")
    return fp


# ═══════════════════════════════════════════
# CHART 3: BANK CREDIT GROWTH
# ═══════════════════════════════════════════

def chart_credit(df, output_dir):
    """Bank credit growth YoY trend."""
    if "india_bank_credit_yoy" not in df.columns:
        print("   ⚠ Skipping Bank Credit — column not found")
        return None

    fig, ax = EconStyle.create_figure(size="wide")

    dates = df["date"].tolist()
    vals = df["india_bank_credit_yoy"].values

    # Area fill + line
    ax.fill_between(dates, 0, vals, color=C_CREDIT, alpha=0.08)
    ax.plot(dates, vals, color=C_CREDIT, linewidth=2.5, zorder=5,
            solid_capstyle="round")
    ax.plot(dates, vals, color=C_CREDIT, linewidth=3.7, alpha=0.07,
            zorder=4, solid_capstyle="round")
    _add_end_label(ax, dates, vals, "Credit Growth", C_CREDIT)

    # Reference lines
    ax.axhline(y=15, color="#999999", linewidth=0.8, linestyle="--", zorder=1)
    ax.text(dates[0], 15.2, "15% (strong growth)", fontsize=7.5,
            color="#888888", va="bottom", fontfamily=EconStyle.FONT_FAMILY)

    _format_date_axis(ax)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax.set_ylabel("YoY Growth (%)", fontsize=EconStyle.FONT_SIZE_AXIS)

    EconStyle.set_title(ax, "Bank Credit Growth",
                        "Scheduled Commercial Banks — YoY Credit Growth")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "RBI Monthly Bulletin")

    fp = output_dir / "03_india_credit.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ Bank Credit Growth")
    return fp


# ═══════════════════════════════════════════
# CHART 4: FPI FLOWS
# ═══════════════════════════════════════════

def chart_fpi(df, output_dir):
    """FPI net flows — green/red bar chart."""
    if "india_fpi_flows" not in df.columns:
        print("   ⚠ Skipping FPI — column not found")
        return None

    fig, ax = EconStyle.create_figure(size="wide")

    dates = df["date"].tolist()
    vals = df["india_fpi_flows"].values
    colors = [C_FPI_POS if v >= 0 else C_FPI_NEG for v in vals]

    bar_width = 20
    ax.bar(dates, vals, width=bar_width, color=colors, alpha=0.8,
           edgecolor="none", zorder=3)

    # Zero line
    ax.axhline(y=0, color="#000000", linewidth=0.8, zorder=2)

    # Cumulative annotation
    cumulative = vals.sum()
    cum_color = C_FPI_POS if cumulative >= 0 else C_FPI_NEG
    ax.text(0.98, 0.95, f"Cumulative: ${cumulative:+.1f}B",
            transform=ax.transAxes, fontsize=10, fontweight="bold",
            color=cum_color, ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=cum_color, alpha=0.9))

    _format_date_axis(ax)
    ax.set_ylabel("Net FPI Flows ($B)", fontsize=EconStyle.FONT_SIZE_AXIS)

    EconStyle.set_title(ax, "Foreign Portfolio Flows",
                        "Monthly Net FPI Flows into India ($B)")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "NSDL / CDSL")

    fp = output_dir / "04_india_fpi.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ FPI Flows")
    return fp


# ═══════════════════════════════════════════
# CHART 5: INDIA MACRO SUMMARY TABLE
# ═══════════════════════════════════════════

def chart_table(df, output_dir):
    """India macro pulse table — latest values + MoM change."""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None

    # Define rows
    indicators = [
        ("PMI", [
            ("Mfg PMI", "india_mfg_pmi", "index"),
            ("Services PMI", "india_svc_pmi", "index"),
        ]),
        ("FISCAL", [
            ("GST Revenue", "india_gst_revenue", "₹L Cr"),
        ]),
        ("CREDIT & FLOWS", [
            ("Bank Credit Growth", "india_bank_credit_yoy", "% YoY"),
            ("FPI Net Flows", "india_fpi_flows", "$B"),
        ]),
        ("LABOUR", [
            ("Unemployment (CMIE)", "india_unemployment", "%"),
        ]),
    ]

    # Build rows
    rows = []
    for section_name, items in indicators:
        for name, col, unit in items:
            if col in df.columns and pd.notna(latest.get(col)):
                val = latest[col]
                if prev is not None and col in df.columns and pd.notna(prev.get(col)):
                    chg = val - prev[col]
                    chg_str = f"{chg:+.2f}"
                else:
                    chg = None
                    chg_str = "-"
                rows.append({
                    "section": section_name,
                    "name": name,
                    "value": val,
                    "change": chg,
                    "change_str": chg_str,
                    "unit": unit,
                })

    # ── Render ──
    row_h = 0.28
    sections = list(dict.fromkeys(r["section"] for r in rows))
    sec_gap = 0.50
    header_h = 1.4
    content_h = (sec_gap * len(sections)) + (row_h * len(rows))
    footer_h = 0.95
    fig_h = header_h + content_h + footer_h

    fig, ax = EconStyle.create_figure(size=(7.0, fig_h))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    # Title block
    ax.text(0.3, fig_h - 0.25, "INDIA MACRO PULSE",
            fontsize=18, fontweight="bold", color="#000000",
            fontfamily=EconStyle.FONT_FAMILY, va="top")
    ax.text(0.3, fig_h - 0.60, latest["date"].strftime("%B %Y"),
            fontsize=11, color="#666666",
            fontfamily=EconStyle.FONT_FAMILY, va="top")

    # Header rule
    hdr_y = fig_h - 0.80
    ax.plot([0.3, 9.7], [hdr_y, hdr_y], color="#000000", linewidth=2,
            clip_on=False, zorder=10)

    # Column headers
    hy = hdr_y - 0.28
    ax.text(0.5, hy, "INDICATOR", fontsize=8, fontweight="bold", color="#666666",
            fontfamily=EconStyle.FONT_FAMILY)
    ax.text(5.0, hy, "LATEST", fontsize=8, fontweight="bold", color="#666666",
            ha="center", fontfamily=EconStyle.FONT_FAMILY)
    ax.text(7.0, hy, "MoM CHG", fontsize=8, fontweight="bold", color="#666666",
            ha="center", fontfamily=EconStyle.FONT_FAMILY)
    ax.text(9.0, hy, "UNIT", fontsize=8, fontweight="bold", color="#666666",
            ha="center", fontfamily=EconStyle.FONT_FAMILY)

    ax.plot([0.3, 9.7], [hy - 0.10, hy - 0.10], color="#CCCCCC",
            linewidth=0.5, clip_on=False)

    y = hy - 0.35
    current_section = None

    for i, r in enumerate(rows):
        # Section header
        if r["section"] != current_section:
            current_section = r["section"]
            ax.text(0.5, y, current_section, fontsize=9, fontweight="bold",
                    color="#FF9933", fontfamily=EconStyle.FONT_FAMILY)
            y -= sec_gap * 0.6

        # Alternating row background
        if i % 2 == 0:
            ax.fill_between([0.3, 9.7], y - 0.05, y + 0.20,
                           color="#F8F8F8", zorder=0)

        # Name
        ax.text(0.5, y, r["name"], fontsize=10, color="#000000",
                fontfamily=EconStyle.FONT_FAMILY, va="center")

        # Value
        if r["unit"] == "₹L Cr":
            val_str = f"₹{r['value']:.2f}L Cr"
        elif r["unit"] == "$B":
            val_str = f"${r['value']:+.1f}B"
        elif r["unit"] == "% YoY":
            val_str = f"{r['value']:.1f}%"
        elif r["unit"] == "%":
            val_str = f"{r['value']:.1f}%"
        else:
            val_str = f"{r['value']:.1f}"
        ax.text(5.0, y, val_str, fontsize=10, fontweight="bold",
                color="#000000", ha="center", va="center",
                fontfamily=EconStyle.FONT_FAMILY)

        # Change
        chg_color = "#000000"
        if r["change"] is not None:
            # For unemployment: down is good. For everything else: up is good.
            if "unemployment" in r["name"].lower():
                chg_color = EconStyle.POSITIVE if r["change"] <= 0 else EconStyle.NEGATIVE
            else:
                chg_color = EconStyle.POSITIVE if r["change"] >= 0 else EconStyle.NEGATIVE
        ax.text(7.0, y, r["change_str"], fontsize=10, fontweight="bold",
                color=chg_color, ha="center", va="center",
                fontfamily=EconStyle.FONT_FAMILY)

        # Unit
        ax.text(9.0, y, r["unit"], fontsize=9, color="#999999",
                ha="center", va="center", fontfamily=EconStyle.FONT_FAMILY)

        y -= row_h

    # Footer
    footer_y = y - row_h
    ax.text(0.5, footer_y,
            f"Source: S&P Global, RBI, PIB, CMIE, NSDL  |  {datetime.now().strftime('%d %b %Y')}",
            fontsize=8, color="#666666", ha="left", va="bottom")
    ax.text(9.5, footer_y, EconStyle.WATERMARK_TEXT,
            fontproperties=EconStyle._get_masthead_font(),
            fontsize=13, color="#1A1A1A", ha="right", va="bottom")

    EconStyle.finalize(fig, ax, source=None, tight=False)

    fp = output_dir / "05_india_table.png"
    EconStyle.save_chart(fig, fp)
    print(f"   ✓ India Macro Table")
    return fp


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generate Economics Hub India Macro Dashboard"
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                        help="Path to india_manual.csv")
    parser.add_argument("--months", type=int, default=None,
                        help="Limit to last N months (default: all)")
    args = parser.parse_args()

    now = datetime.now()
    output_dir = OUTPUT_BASE / now.strftime("%Y-%m")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🇮🇳 Generating Economics Hub — India Macro Dashboard")
    print(f"   Output: {output_dir}")

    # Load data
    df = load_india_data(args.csv, args.months)

    # Generate charts
    print(f"   Generating charts...")
    chart_pmi(df, output_dir)
    chart_gst(df, output_dir)
    chart_credit(df, output_dir)
    chart_fpi(df, output_dir)
    chart_table(df, output_dir)

    print(f"\n✅ India Dashboard complete! 5 charts saved to:")
    print(f"   {output_dir}")


if __name__ == "__main__":
    main()
