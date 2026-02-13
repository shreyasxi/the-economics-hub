#!/usr/bin/env python3
"""
Economics Hub — Monthly Macro Pulse Generator
===============================================
Run on the 2nd Saturday of each month (after NFP + CPI release).
Generates 6 macro charts + summary table + newsletter section.

Usage:
    python generate_macro.py                # Live FRED data
    python generate_macro.py --preview      # Lower DPI for quick preview

Before running:
    1. Update MANUAL_DATA in config/macro_settings.py
       (EM PMI Composite, etc.)
    2. Ensure fredapi is installed: pip install fredapi

Output: output/macro/YYYY-MM/
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from style.economics_hub_style import EconStyle
from data.fetchers.fred_fetcher import FredFetcher
from config.settings import FRED_API_KEY
from config.macro_settings import MACRO_INDICATORS, MACRO_CHARTS, MACRO_TABLE_SECTIONS, MANUAL_DATA


# ═══════════════════════════════════════════════
# DATA ENGINE
# ═══════════════════════════════════════════════

class MacroDataEngine:
    """Fetch and transform macro data from FRED."""

    def __init__(self, fred_fetcher):
        self.fred = fred_fetcher
        self.cache = {}  # {indicator_id: pd.Series}

    def fetch_raw(self, ind_id):
        """Fetch raw FRED series for an indicator."""
        if ind_id in self.cache:
            return self.cache[ind_id]

        ind = MACRO_INDICATORS[ind_id]
        years = ind.get("history_years", 3)
        try:
            data = self.fred.fetch_series(ind["series"], period_years=years + 1)
            # Cast to float
            data = data.astype(float)
            self.cache[ind_id] = data
            return data
        except Exception as e:
            print(f"   ⚠ Failed to fetch {ind['name']}: {e}")
            return pd.Series(dtype=float)

    def get_transformed(self, ind_id):
        """Get transformed series (YoY %, level, etc.) ready for plotting."""
        ind = MACRO_INDICATORS[ind_id]
        raw = self.fetch_raw(ind_id)
        if raw.empty:
            return pd.Series(dtype=float)

        transform = ind["transform"]
        years = ind.get("history_years", 3)
        cutoff = datetime.now() - timedelta(days=int(years * 365.25))

        if transform == "level":
            result = raw[raw.index >= cutoff]
        elif transform == "yoy_pct":
            # Year-over-year percentage change
            result = raw.pct_change(periods=12) * 100  # 12 months
            result = result[result.index >= cutoff]
        elif transform == "mom_pct":
            result = raw.pct_change(periods=1) * 100
            result = result[result.index >= cutoff]
        elif transform == "mom_abs":
            result = raw.diff(periods=1)
            result = result[result.index >= cutoff]
        else:
            result = raw[raw.index >= cutoff]

        return result.dropna()

    def get_latest(self, ind_id):
        """Get the most recent value (transformed)."""
        series = self.get_transformed(ind_id)
        if series.empty:
            return None
        return float(series.iloc[-1])

    def get_previous(self, ind_id, periods_ago=1):
        """Get value from N periods ago."""
        series = self.get_transformed(ind_id)
        if len(series) < periods_ago + 1:
            return None
        return float(series.iloc[-(periods_ago + 1)])

    def get_change(self, ind_id):
        """Get change from previous period."""
        latest = self.get_latest(ind_id)
        previous = self.get_previous(ind_id, 1)
        if latest is None or previous is None:
            return None
        return latest - previous


# ═══════════════════════════════════════════════
# CHART BUILDERS (using EconStyle theme)
# ═══════════════════════════════════════════════

def _style_axis(ax, ylabel=None):
    """Apply consistent styling to an axis (matches weekly charts)."""
    ax.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.35)
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center",
             fontsize=EconStyle.FONT_SIZE_TICK)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=EconStyle.FONT_SIZE_AXIS,
                      color=EconStyle.TEXT_SECONDARY, labelpad=6)


def _add_end_label(ax, dates, values, name, color):
    """Add Bloomberg-style end label to a line."""
    if len(values) == 0:
        return
    last_val = float(values[-1])
    last_date = dates[-1]

    if abs(last_val) >= 1000:
        vs = f"{last_val:,.0f}"
    elif abs(last_val) >= 10:
        vs = f"{last_val:.1f}"
    else:
        vs = f"{last_val:.2f}"

    label = f" {name}  {vs}"
    ax.annotate(
        label, xy=(last_date, last_val),
        xytext=(4, 0), textcoords="offset points",
        fontproperties=EconStyle._get_font("bold"),
        fontsize=EconStyle.FONT_SIZE_ANNOTATION - 0.5,
        color=color, va="center", ha="left",
        path_effects=[pe.withStroke(linewidth=2.5, foreground=EconStyle.BACKGROUND)],
    )


def chart_inflation(engine, output_dir):
    """Chart 1: Inflation Dashboard — 2-panel (US | International)."""
    EconStyle.apply_global_style()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    # ── Left Panel: US Inflation ──
    for ind_id in ["us_cpi_yoy", "us_core_pce", "us_inflation_exp"]:
        ind = MACRO_INDICATORS[ind_id]
        series = engine.get_transformed(ind_id)
        if series.empty:
            continue
        dates = series.index.to_pydatetime().tolist()
        vals = series.values
        ax1.plot(dates, vals, color=ind["color"], linewidth=2.2,
                 solid_capstyle="round", zorder=3)
        _add_end_label(ax1, dates, vals, ind["name"], ind["color"])

    # Fed 2% target line
    ax1.axhline(y=2.0, color=EconStyle.NEGATIVE, linewidth=0.8,
                linestyle="--", alpha=0.6, zorder=1)
    ax1.text(ax1.get_xlim()[0], 2.05, " Fed 2% target", fontsize=7,
             color=EconStyle.NEGATIVE, alpha=0.7, va="bottom")

    _style_axis(ax1, ylabel="Rate (%)")
    ax1.set_title("United States", fontsize=12, fontweight="bold",
                  color=EconStyle.TEXT_TITLE, loc="left", pad=8)

    # Spines
    for spine in ["top", "right", "left"]:
        ax1.spines[spine].set_visible(False)
    ax1.spines["bottom"].set_visible(True)
    ax1.spines["bottom"].set_color(EconStyle.AXIS_COLOR)

    # Right margin for labels
    xmin, xmax = ax1.get_xlim()
    ax1.set_xlim(xmin, xmax + (xmax - xmin) * 0.22)

    # ── Right Panel: International (Eurozone, UK) ──
    for ind_id in ["ez_cpi_yoy", "uk_cpi_yoy"]:
        ind = MACRO_INDICATORS[ind_id]
        series = engine.get_transformed(ind_id)
        if series.empty:
            continue
        dates = series.index.to_pydatetime().tolist()
        vals = series.values
        ax2.plot(dates, vals, color=ind["color"], linewidth=2.2,
                 solid_capstyle="round", zorder=3)
        _add_end_label(ax2, dates, vals, ind["name"], ind["color"])

    _style_axis(ax2, ylabel="CPI YoY (%)")
    ax2.set_title("Eurozone · UK", fontsize=12, fontweight="bold",
                  color=EconStyle.TEXT_TITLE, loc="left", pad=8)

    for spine in ["top", "right", "left"]:
        ax2.spines[spine].set_visible(False)
    ax2.spines["bottom"].set_visible(True)
    ax2.spines["bottom"].set_color(EconStyle.AXIS_COLOR)

    xmin, xmax = ax2.get_xlim()
    ax2.set_xlim(xmin, xmax + (xmax - xmin) * 0.22)

    # ── Layout: Title + Rule (manual positioning, no suptitle) ──
    fig.subplots_adjust(left=0.06, right=0.96, top=0.85, bottom=0.12, wspace=0.25)

    fig.text(0.06, 0.94, "Inflation Dashboard",
             fontsize=EconStyle.FONT_SIZE_TITLE, fontweight="bold",
             color=EconStyle.TEXT_TITLE, ha="left", va="bottom",
             fontfamily="sans-serif")

    fig.add_artist(plt.Line2D([0.06, 0.96], [0.92, 0.92],
                              color=EconStyle.RULE_HEAVY, linewidth=1.5,
                              transform=fig.transFigure, clip_on=False))

    EconStyle.add_source(fig, "FRED, OECD")

    filepath = output_dir / "01_macro_inflation.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Inflation Dashboard")
    return filepath


def chart_labour(engine, output_dir):
    """Chart 2: Labour Market — Dual axis (Unemployment + Claims 4wk MA)."""
    EconStyle.apply_global_style()

    fig, ax1 = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    # ── Primary: Unemployment Rate ──
    unemp = engine.get_transformed("us_unemployment")
    if not unemp.empty:
        dates = unemp.index.to_pydatetime().tolist()
        vals = unemp.values
        ax1.plot(dates, vals, color="#003366", linewidth=2, zorder=3,
                 solid_capstyle="round")
        _add_end_label(ax1, dates, vals, "Unemployment", "#003366")

    ax1.set_ylabel("Unemployment Rate (%)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color="#003366", labelpad=6)
    ax1.tick_params(axis="y", colors="#003366")

    # ── Secondary: Initial Claims (4-week MA) ──
    ax2 = ax1.twinx()
    claims = engine.get_transformed("us_claims")
    if not claims.empty:
        # 4-week moving average, convert to thousands
        claims_4w = claims.rolling(4).mean() / 1000
        claims_4w = claims_4w.dropna()
        dates_c = claims_4w.index.to_pydatetime().tolist()
        vals_c = claims_4w.values
        ax2.plot(dates_c, vals_c, color="#d62728", linewidth=1.5,
                 linestyle="-", alpha=0.85, zorder=2, solid_capstyle="round")
        _add_end_label(ax2, dates_c, vals_c, "Claims 4wk MA", "#d62728")

    ax2.set_ylabel("Initial Claims (K, 4wk MA)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color="#d62728", labelpad=6)
    ax2.tick_params(axis="y", colors="#d62728")
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#d62728")
    ax2.spines["right"].set_linewidth(0.5)

    # ── Payrolls annotation (latest figure) ──
    nfp_latest = engine.get_latest("us_payrolls")
    if nfp_latest is not None:
        nfp_str = f"Latest NFP: {nfp_latest:+,.0f}K"
        ax1.text(0.02, 0.95, nfp_str, transform=ax1.transAxes,
                 fontsize=10, fontweight="bold", color="#1f77b4",
                 va="top", ha="left",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#E8F0FE",
                           edgecolor="#1f77b4", linewidth=0.5))

    _style_axis(ax1)
    ax1.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.35)

    for spine in ["top", "left"]:
        ax1.spines[spine].set_visible(False)
    ax1.spines["bottom"].set_visible(True)
    ax2.spines["top"].set_visible(False)

    # Right margin for end labels
    xmin, xmax = ax1.get_xlim()
    margin = (xmax - xmin) * 0.16
    ax1.set_xlim(xmin, xmax + margin)

    EconStyle.set_title(ax1, "Labour Market Pulse",
                        "US Unemployment Rate vs. Initial Jobless Claims (4wk MA)")
    EconStyle.add_top_rule(ax1)
    EconStyle.add_source(fig, "FRED (BLS)")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "02_macro_labour.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Labour Market Pulse")
    return filepath


def chart_financial_conditions(engine, output_dir):
    """Chart 3: Financial Conditions — NFCI + HY Spread (dual axis)."""
    EconStyle.apply_global_style()

    fig, ax1 = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    # ── Primary: NFCI ──
    nfci = engine.get_transformed("nfci")
    if not nfci.empty:
        dates = nfci.index.to_pydatetime().tolist()
        vals = nfci.values
        ax1.plot(dates, vals, color="#000000", linewidth=2, zorder=3,
                 solid_capstyle="round")
        _add_end_label(ax1, dates, vals, "NFCI", "#000000")

        # Shade loose (below 0) vs tight (above 0) zones
        ax1.axhline(y=0, color="#A0A0A0", linewidth=0.8, linestyle="-", zorder=1)
        ax1.fill_between(dates, vals, 0, where=[v > 0 for v in vals],
                         alpha=0.08, color=EconStyle.NEGATIVE, zorder=0)
        ax1.fill_between(dates, vals, 0, where=[v <= 0 for v in vals],
                         alpha=0.05, color=EconStyle.POSITIVE, zorder=0)

        # Zone labels
        ax1.text(0.02, 0.92, "← Tighter", transform=ax1.transAxes,
                 fontsize=7, color=EconStyle.NEGATIVE, alpha=0.6)
        ax1.text(0.02, 0.05, "← Looser", transform=ax1.transAxes,
                 fontsize=7, color=EconStyle.POSITIVE, alpha=0.6)

    ax1.set_ylabel("NFCI (0 = avg conditions)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color="#000000", labelpad=6)

    # ── Secondary: HY Spread ──
    ax2 = ax1.twinx()
    hy = engine.get_transformed("hy_spread")
    if not hy.empty:
        dates_h = hy.index.to_pydatetime().tolist()
        # Convert to bps (* 100) — FRED HY OAS is already in percentage points
        vals_h = hy.values * 100
        ax2.plot(dates_h, vals_h, color="#d62728", linewidth=1.5,
                 alpha=0.85, zorder=2, solid_capstyle="round")
        _add_end_label(ax2, dates_h, vals_h, "HY Spread", "#d62728")

    ax2.set_ylabel("HY OAS (bps)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color="#d62728", labelpad=6)
    ax2.tick_params(axis="y", colors="#d62728")
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#d62728")
    ax2.spines["right"].set_linewidth(0.5)

    _style_axis(ax1)
    for spine in ["top", "left"]:
        ax1.spines[spine].set_visible(False)
    ax2.spines["top"].set_visible(False)

    xmin, xmax = ax1.get_xlim()
    ax1.set_xlim(xmin, xmax + (xmax - xmin) * 0.16)

    EconStyle.set_title(ax1, "Financial Conditions & Credit Stress",
                        "Chicago Fed NFCI vs. US High Yield Credit Spread")
    EconStyle.add_top_rule(ax1)
    EconStyle.add_source(fig, "FRED (Chicago Fed, ICE BofA)")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "03_macro_financial.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Financial Conditions")
    return filepath


def chart_emerging_markets(engine, output_dir):
    """Chart 4: Emerging Markets Stress Monitor — EM HY + Corp Spread + USD Index."""
    EconStyle.apply_global_style()

    fig, ax1 = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    # ── Primary: EM Credit Spreads ──
    for ind_id in ["em_hy_spread", "em_corp_spread"]:
        if ind_id not in MACRO_INDICATORS:
            continue
        ind = MACRO_INDICATORS[ind_id]
        series = engine.get_transformed(ind_id)
        if series.empty:
            continue
        dates = series.index.to_pydatetime().tolist()
        # Convert to bps (* 100)
        vals = series.values * 100
        ax1.plot(dates, vals, color=ind["color"], linewidth=2.2,
                 solid_capstyle="round", zorder=3)
        _add_end_label(ax1, dates, vals, ind["name"], ind["color"])

    ax1.set_ylabel("Credit Spread (bps)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color="#000000", labelpad=6)

    # ── Secondary: USD Index vs EM ──
    ax2 = ax1.twinx()
    if "em_usd_index" in MACRO_INDICATORS:
        usd = engine.get_transformed("em_usd_index")
        if not usd.empty:
            dates_u = usd.index.to_pydatetime().tolist()
            vals_u = usd.values
            ax2.plot(dates_u, vals_u, color="#003366", linewidth=1.5,
                     linestyle="--", alpha=0.85, zorder=2, solid_capstyle="round")
            _add_end_label(ax2, dates_u, vals_u, "USD vs EM", "#003366")

    ax2.set_ylabel("USD Index (vs EM)", fontsize=EconStyle.FONT_SIZE_AXIS,
                   color="#003366", labelpad=6)
    ax2.tick_params(axis="y", colors="#003366")
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#003366")
    ax2.spines["right"].set_linewidth(0.5)

    _style_axis(ax1)
    for spine in ["top", "left"]:
        ax1.spines[spine].set_visible(False)
    ax2.spines["top"].set_visible(False)

    xmin, xmax = ax1.get_xlim()
    ax1.set_xlim(xmin, xmax + (xmax - xmin) * 0.18)

    EconStyle.set_title(ax1, "Emerging Markets Stress Monitor",
                        "EM High Yield & Corporate Spreads vs. USD Strength")
    EconStyle.add_top_rule(ax1)
    EconStyle.add_source(fig, "FRED (ICE BofA, Federal Reserve)")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "04_macro_em.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Emerging Markets Stress Monitor")
    return filepath


def chart_money_rates(engine, output_dir):
    """Chart 5: Money & Rates — M2 YoY, 2s10s, Real Yield (triple line)."""
    EconStyle.apply_global_style()

    fig, ax = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    for ind_id in ["m2_yoy", "spread_2s10s", "real_yield_10y"]:
        ind = MACRO_INDICATORS[ind_id]
        series = engine.get_transformed(ind_id)
        if series.empty:
            continue
        dates = series.index.to_pydatetime().tolist()
        vals = series.values
        ax.plot(dates, vals, color=ind["color"], linewidth=2.2,
                solid_capstyle="round", zorder=3)
        _add_end_label(ax, dates, vals, ind["name"], ind["color"])

    # Zero line
    ax.axhline(y=0, color="#A0A0A0", linewidth=0.8, linestyle="-", zorder=1)

    _style_axis(ax, ylabel="Rate / Spread (%)")

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(True)

    # Right margin
    xmin, xmax = ax.get_xlim()
    ax.set_xlim(xmin, xmax + (xmax - xmin) * 0.22)

    # Y-axis padding
    ymin, ymax = ax.get_ylim()
    pad = (ymax - ymin) * 0.06
    ax.set_ylim(ymin - pad, ymax + pad)

    EconStyle.set_title(ax, "Money, Rates & the Yield Curve Signal",
                        "M2 Money Supply YoY · 2s10s Spread · 10Y Real Yield (TIPS)")
    EconStyle.add_top_rule(ax)
    EconStyle.add_source(fig, "FRED")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "05_macro_money.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Money & Rates")
    return filepath


def chart_macro_table(engine, output_dir):
    """Chart 6: Macro Summary Table — matching Market Snapshot style."""
    EconStyle.apply_global_style()

    # ── Build row data ──
    rows = []
    for section in MACRO_TABLE_SECTIONS:
        # FRED-sourced rows
        for ind_id in section.get("rows", []):
            ind = MACRO_INDICATORS[ind_id]
            latest = engine.get_latest(ind_id)
            change = engine.get_change(ind_id)

            if latest is None:
                continue

            # Format latest value
            if ind["transform"] == "mom_abs":
                latest_str = f"{latest:+,.0f}K"
            elif "claims" in ind_id:
                latest_str = f"{latest/1000:,.0f}K"
            elif "spread" in ind_id or "hy" in ind_id:
                # Credit spreads: multiply by 100 for bps display
                latest_str = f"{latest*100:.0f} bps"
            elif "usd_index" in ind_id:
                latest_str = f"{latest:.1f}"
            elif abs(latest) > 100:
                latest_str = f"{latest:,.0f}"
            elif abs(latest) >= 1:
                latest_str = f"{latest:.2f}%"
            else:
                latest_str = f"{latest:.2f}"

            # Format change
            if change is not None:
                if "claims" in ind_id:
                    # Claims are in raw units — show change in K
                    change_k = change / 1000
                    if abs(change_k) < 0.1:
                        change_str = "0.0"
                    else:
                        change_str = f"{change_k:+.1f}"
                elif "spread" in ind_id or "hy" in ind_id:
                    # Credit spreads change in bps
                    change_bps = change * 100
                    change_str = f"{change_bps:+.0f}"
                elif abs(change) < 0.005:
                    change_str = "0.00"
                else:
                    change_str = f"{change:+.2f}"
            else:
                change_str = "-"

            rows.append({
                "section": section["section"],
                "section_color": section["color"],
                "name": ind["name"],
                "latest": latest_str,
                "change": change_str,
                "unit": ind.get("unit", ""),
            })

        # Manual rows (EM PMI etc.)
        for manual_key in section.get("manual_rows", []):
            if manual_key in MANUAL_DATA:
                m = MANUAL_DATA[manual_key]

                # Compute MoM change if previous_value exists
                if "previous_value" in m and m["previous_value"] is not None:
                    change_val = m["value"] - m["previous_value"]
                    change_str = f"{change_val:+.2f}"
                else:
                    change_str = "-"

                # Format value based on unit
                if m["unit"] == "index":
                    val_str = f"{m['value']:.1f}"
                elif m["unit"] == "%":
                    val_str = f"{m['value']:.1f}%"
                else:
                    val_str = f"{m['value']}"

                rows.append({
                    "section": section["section"],
                    "section_color": section["color"],
                    "name": m["name"],
                    "latest": val_str,
                    "change": change_str,
                    "unit": m["unit"],
                    "manual_source": m["source"],
                    "manual_date": m["as_of"],
                })

    # ── Render table ──
    n = len(rows)
    sections_seen = []
    for r in rows:
        if r["section"] not in sections_seen:
            sections_seen.append(r["section"])

    row_h = 0.25
    sec_gap = 0.45
    header_block = 1.4
    content_h = (0.65 * len(sections_seen)) + (row_h * n)
    footer_space = 0.95
    fig_h = header_block + content_h + footer_space

    fig, ax = EconStyle.create_figure(size=(7.0, fig_h))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    cx = {"name": 0.5, "latest": 5.5, "change": 8.0, "unit": 9.5}

    # ── Title ──
    y = fig_h - 0.4
    ax.text(0.5, y, "MACRO PULSE", fontsize=20, fontweight="bold",
            color="#000000", fontfamily="sans-serif", ha="left")
    y -= 0.25
    month_str = datetime.now().strftime("%B %Y")
    ax.text(0.5, y, month_str, fontsize=10, color="#000000", ha="left")

    # ── Headers ──
    y -= 0.5
    for key, label in [("name", "INDICATOR"), ("latest", "LATEST"),
                       ("change", "MoM CHG"), ("unit", "UNIT")]:
        ha = "left" if key == "name" else "right"
        ax.text(cx[key], y, label, fontsize=9, fontweight="bold",
                color="#000000", ha=ha, fontfamily="sans-serif")

    y -= 0.15
    ax.plot([0.5, 9.5], [y, y], color="#000000", linewidth=1.2)

    # ── Rows ──
    cur_section = None
    SECTION_BG = "#F1F5F9"

    for row in rows:
        if row["section"] != cur_section:
            cur_section = row["section"]
            y -= sec_gap
            rect = plt.Rectangle((0, y - 0.125), 10, 0.25,
                                 facecolor=SECTION_BG, edgecolor="none", zorder=0)
            ax.add_patch(rect)
            ax.text(cx["name"], y, cur_section, fontsize=9, fontweight="bold",
                    color=row["section_color"], ha="left", va="center")
            y -= 0.20

        y -= row_h

        # Name
        name_display = row["name"]
        if "manual_source" in row:
            name_display += f"  ({row['manual_source']})"
        ax.text(cx["name"], y, name_display, fontsize=10, fontweight="medium",
                color="#000000", ha="left", va="center")

        # Latest value
        ax.text(cx["latest"], y, row["latest"], fontsize=10,
                color="#334155", ha="right", va="center")

        # Change
        ch_str = row["change"]
        if ch_str != "-":
            is_pos = ch_str.startswith("+")
            is_neg = ch_str.startswith("-")
            ch_col = "#065f46" if is_pos else ("#991b1b" if is_neg else "#000000")
        else:
            ch_col = "#64748b"
        ax.text(cx["change"], y, ch_str, fontsize=10, fontweight="bold",
                color=ch_col, ha="right", va="center")

        # Unit
        ax.text(cx["unit"], y, row["unit"], fontsize=9,
                color="#64748b", ha="right", va="center")

        # Dotted separator
        ax.plot([0.5, 9.5], [y - row_h/2, y - row_h/2],
                color="#e2e8f0", linewidth=0.8, linestyle=":")

    # ── Footer ──
    footer_y = y - row_h/2 - 0.40
    ax.text(0.5, footer_y, f"Source: FRED, OECD, ICE BofA, S&P Global  |  {datetime.now().strftime('%d %b %Y')}",
            fontsize=8, color="#666666", ha="left", va="bottom")
    ax.text(9.5, footer_y, EconStyle.WATERMARK_TEXT,
            fontproperties=EconStyle._get_masthead_font(),
            fontsize=13, color="#1A1A1A", ha="right", va="bottom")

    EconStyle.finalize(fig, ax, source=None, tight=False)

    filepath = output_dir / "06_macro_table.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Macro Summary Table")
    return filepath


# ═══════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════

def generate_macro_dashboard():
    """Main entry point — generates the complete Macro Pulse dashboard."""
    # Output directory: output/macro/YYYY-MM/
    month_str = datetime.now().strftime("%Y-%m")
    output_dir = PROJECT_ROOT / "output" / "macro" / month_str
    output_dir.mkdir(parents=True, exist_ok=True)

    print("📊 Generating Economics Hub — Macro Pulse Dashboard")
    print(f"   Output: {output_dir}\n")

    # Initialize FRED connection
    if FRED_API_KEY == "YOUR_FRED_API_KEY":
        print("⚠  FRED API key not set! Open config/settings.py")
        return

    fred = FredFetcher(api_key=FRED_API_KEY)
    engine = MacroDataEngine(fred)

    # ── Pre-fetch all data ──
    print("   Fetching macro data from FRED...")
    success = 0
    for ind_id in MACRO_INDICATORS:
        try:
            data = engine.fetch_raw(ind_id)
            if not data.empty:
                success += 1
                print(f"   ✓ {MACRO_INDICATORS[ind_id]['name']}")
            else:
                print(f"   ✗ {MACRO_INDICATORS[ind_id]['name']} (no data)")
        except Exception as e:
            print(f"   ✗ {MACRO_INDICATORS[ind_id]['name']} ({e})")

    print(f"\n   Fetched {success}/{len(MACRO_INDICATORS)} indicators\n")

    # ── Generate charts ──
    print("   Generating charts...")
    chart_inflation(engine, output_dir)
    chart_labour(engine, output_dir)
    chart_financial_conditions(engine, output_dir)
    chart_emerging_markets(engine, output_dir)
    chart_money_rates(engine, output_dir)
    chart_macro_table(engine, output_dir)

    
    print(f"\n✅ Macro Pulse complete! {len(list(output_dir.glob('*.png')))} charts saved to:")
    print(f"   {output_dir}")
    


def main():
    parser = argparse.ArgumentParser(description="Generate Economics Hub Macro Pulse Dashboard")
    parser.add_argument("--preview", action="store_true", help="Lower DPI for quick test")
    args = parser.parse_args()

    if args.preview:
        EconStyle.DPI = 120

    generate_macro_dashboard()


if __name__ == "__main__":
    main()
