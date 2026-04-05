#!/usr/bin/env python3
"""
Economics Hub — Monthly Macro Pulse Generator
===============================================
Run on the 2nd Saturday of each month (after NFP + CPI release).
Generates 6 macro charts + summary table + DBnomics charts.
"""

import sys
import argparse
import warnings
from pathlib import Path
from datetime import datetime, timedelta

# Suppress harmless Matplotlib date locator warnings
warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.image as mpimg

from style.economics_hub_style import EconStyle
from data.fetchers.fred_fetcher import FredFetcher
from config.settings import FRED_API_KEY
from config.macro_settings import MACRO_INDICATORS, MACRO_TABLE_SECTIONS, MANUAL_DATA

import dbnomics

# ── DBNOMICS CONFIG & COLORS ──
COLOR_G7 = "#003366"
COLOR_EM = "#FF9933"
COLOR_POSITIVE = "#065F46"
COLOR_NEGATIVE = "#991B1B"
COLOR_NEUTRAL = "#666666"
COLOR_TARGET = "#CC0000"

G7 = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany",
    "FR": "France", "IT": "Italy", "JP": "Japan", "CA": "Canada",
}

EMERGING_MARKETS = {
    "IN": "India", "BR": "Brazil", "MX": "Mexico", "ID": "Indonesia",
    "ZA": "South Africa", "TR": "Turkey", "TH": "Thailand",
    "PH": "Philippines", "CL": "Chile", "PL": "Poland",
}

IMF_WEO_CODES = {
    "IN": "IND", "BR": "BRA", "MX": "MEX", "ID": "IDN",
    "ZA": "ZAF", "TR": "TUR", "TH": "THA", "PH": "PHL",
    "CL": "CHL", "PL": "POL",
}

OECD_CODES = {
    "US": "USA", "GB": "GBR", "DE": "DEU", "FR": "FRA",
    "IT": "ITA", "JP": "JPN", "CA": "CAN",
    "IN": "IND", "BR": "BRA", "MX": "MEX", "ID": "IDN",
    "ZA": "ZAF", "TR": "TUR",
}

# ═══════════════════════════════════════════════
# DATA ENGINES (FRED + DBNOMICS)
# ═══════════════════════════════════════════════

class MacroDataEngine:
    """Fetch and transform macro data from FRED."""
    def __init__(self, fred_fetcher):
        self.fred = fred_fetcher
        self.cache = {} 

    def fetch_raw(self, ind_id):
        if ind_id in self.cache: return self.cache[ind_id]
        ind = MACRO_INDICATORS[ind_id]
        years = ind.get("history_years", 3)
        try:
            # --- NEW: Yahoo Finance Interceptor ---
            if "ticker" in ind:
                start_date = datetime.now() - timedelta(days=int((years + 1) * 365.25))
                df = yf.download(ind["ticker"], start=start_date, progress=False)
                data = df["Close"]
                if isinstance(data, pd.DataFrame): data = data.iloc[:, 0]
            # --- ORIGINAL: FRED Fetcher ---
            else:
                data = self.fred.fetch_series(ind["series"], period_years=years + 1)
                
            data = data.astype(float)
            self.cache[ind_id] = data
            return data
        except Exception as e:
            print(f"   ⚠ Failed to fetch {ind['name']}: {e}")
            return pd.Series(dtype=float)

    def get_transformed(self, ind_id):
        ind = MACRO_INDICATORS[ind_id]
        raw = self.fetch_raw(ind_id)
        if raw.empty: return pd.Series(dtype=float)

        transform = ind["transform"]
        years = ind.get("history_years", 3)
        cutoff = datetime.now() - timedelta(days=int(years * 365.25))

        if transform == "level":
            result = raw[raw.index >= cutoff]
        elif transform == "yoy_pct":
            result = raw.pct_change(periods=12) * 100 
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
        series = self.get_transformed(ind_id)
        return float(series.iloc[-1]) if not series.empty else None

    def get_previous(self, ind_id, periods_ago=1):
        series = self.get_transformed(ind_id)
        return float(series.iloc[-(periods_ago + 1)]) if len(series) >= periods_ago + 1 else None

    def get_change(self, ind_id):
        latest = self.get_latest(ind_id)
        previous = self.get_previous(ind_id, 1)
        return latest - previous if latest is not None and previous is not None else None

def safe_fetch(provider, dataset, series_code, label=""):
    try:
        df = dbnomics.fetch_series(provider_code=provider, dataset_code=dataset, series_code=series_code)
        if df is not None and len(df) > 0:
            print(f"   ✓ Fetched: {label or series_code}")
            return df
        return None
    except Exception as e:
        print(f"   ⚠ Failed: {label or series_code} ({e})")
        return None

def extract_series(df, value_col="value", date_col="period"):
    if df is None: return pd.Series(dtype=float)
    out = df[[date_col, value_col]].copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    return out.dropna().set_index(date_col)[value_col]

def fetch_macro_oecd_cli(output_dir, years=5):
    print("\n   Fetching OECD Leading Indicators...")
    cutoff = datetime.now() - pd.Timedelta(days=years * 365)
    rows = []
    all_countries = {**G7, **EMERGING_MARKETS}

    for iso2, country_name in all_countries.items():
        if iso2 not in OECD_CODES: continue
        oecd_code = OECD_CODES[iso2]
        row = {"country": country_name, "iso": iso2, "group": "G7" if iso2 in G7 else "EM"}

        df = safe_fetch("OECD", "MEI", f"{oecd_code}.LOLITOAA.STSA.M", f"{iso2} CLI")
        series = extract_series(df)
        if len(series) > 0:
            f = series[series.index >= cutoff]
            if len(f) > 0:
                row["cli_latest"] = round(float(f.iloc[-1]), 2)
                row["cli_date"] = f.index[-1].strftime("%Y-%m")
                if len(f) >= 4:
                    row["cli_direction"] = "rising" if f.iloc[-1] > f.iloc[-4] else "falling"
                row["cli_zone"] = "expansion" if f.iloc[-1] > 100 else "contraction"
        rows.append(row)

    df_out = pd.DataFrame(rows)
    df_out.to_csv(output_dir / "oecd_cli.csv", index=False)
    return df_out

def fetch_macro_em_vulnerability(output_dir, years=5):
    print("\n   Fetching EM Vulnerability Data...")
    cutoff = datetime.now() - pd.Timedelta(days=years * 365)
    rows = []

    for iso2, name in EMERGING_MARKETS.items():
        weo_code = IMF_WEO_CODES[iso2]
        row = {"country": name, "iso": iso2, "group": "EM"}

        cpi_df = safe_fetch("IMF", "IFS", f"M.{iso2}.PCPI_PC_CP_A_PT", f"{iso2} CPI")
        cpi = extract_series(cpi_df)
        if len(cpi) > 0 and len(cpi[cpi.index >= cutoff]) > 0:
            row["cpi_yoy"] = round(float(cpi[cpi.index >= cutoff].iloc[-1]), 2)

        ca_df = safe_fetch("IMF", "WEO:latest", f"{weo_code}.BCA_NGDPD", f"{iso2} CA")
        ca = extract_series(ca_df)
        if len(ca) > 0 and len(ca[ca.index >= cutoff]) > 0:
            row["current_account_gdp"] = round(float(ca[ca.index >= cutoff].iloc[-1]), 2)

        debt_df = safe_fetch("IMF", "WEO:latest", f"{weo_code}.GGXWDG_NGDP", f"{iso2} Debt")
        debt = extract_series(debt_df)
        if len(debt) > 0 and len(debt[debt.index >= cutoff]) > 0:
            row["govt_debt_gdp"] = round(float(debt[debt.index >= cutoff].iloc[-1]), 2)

        rows.append(row)

    df_out = pd.DataFrame(rows)
    df_out.to_csv(output_dir / "em_macro.csv", index=False)
    return df_out

# ═══════════════════════════════════════════════
# CHART BUILDERS
# ═══════════════════════════════════════════════

def _style_axis(ax, ylabel=None):
    ax.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.35)
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=EconStyle.FONT_SIZE_TICK)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=EconStyle.FONT_SIZE_AXIS, color=EconStyle.TEXT_SECONDARY, labelpad=6)

def _add_end_label(ax, dates, values, name, color):
    if len(values) == 0: return
    last_val, last_date = float(values[-1]), dates[-1]
    
    if abs(last_val) >= 1000: vs = f"{last_val:,.0f}"
    elif abs(last_val) >= 10: vs = f"{last_val:.1f}"
    else: vs = f"{last_val:.2f}"

    label = f" {name}  {vs}"
    ax.annotate(
        label, xy=(last_date, last_val), xytext=(4, 0), textcoords="offset points",
        fontproperties=EconStyle._get_font("bold"), fontsize=EconStyle.FONT_SIZE_ANNOTATION - 0.5,
        color=color, va="center", ha="left",
        path_effects=[pe.withStroke(linewidth=2.5, foreground=EconStyle.BACKGROUND)],
    )

def chart_inflation(engine, output_dir):
    EconStyle.apply_global_style()
    # Use the standard wide template instead of the cramped 1x2 subplot
    fig, ax1 = EconStyle.create_figure(size="wide")
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    for ind_id in ["us_cpi_yoy", "us_core_pce", "us_inflation_exp"]:
        ind = MACRO_INDICATORS[ind_id]
        series = engine.get_transformed(ind_id)
        if series.empty: continue
        dates, vals = series.index.to_pydatetime().tolist(), series.values
        # Increased linewidth to 2.8 for better quality/visibility
        ax1.plot(dates, vals, color=ind["color"], linewidth=2.8, solid_capstyle="round", zorder=3)
        _add_end_label(ax1, dates, vals, ind["name"], ind["color"])

    # Target line styling
    ax1.axhline(y=2.0, color=EconStyle.NEGATIVE, linewidth=1.2, linestyle="--", alpha=0.6, zorder=1)
    ax1.text(ax1.get_xlim()[0], 2.05, " Fed 2% target", fontsize=9, fontweight="bold", color=EconStyle.NEGATIVE, alpha=0.8, va="bottom")
    
    _style_axis(ax1, ylabel="YoY Rate (%)")
    
    # Clean up spines
    for spine in ["top", "right", "left"]: 
        ax1.spines[spine].set_visible(False)
    ax1.spines["bottom"].set_visible(True)
    ax1.spines["bottom"].set_color(EconStyle.AXIS_COLOR)
    
    # Add padding to the right for labels
    ax1.set_xlim(ax1.get_xlim()[0], ax1.get_xlim()[1] + (ax1.get_xlim()[1] - ax1.get_xlim()[0]) * 0.15)

    # Elite Narrative Titles
    EconStyle.set_title(ax1, "US Inflation Metrics", "Headline CPI vs. Core PCE vs. 5-Year Inflation Expectations")
    EconStyle.add_top_rule(ax1)
    
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
    EconStyle.add_source(fig, "FRED")

    filepath = output_dir / "01_macro_inflation.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ US Inflation Dashboard")

def chart_labour(engine, output_dir):
    EconStyle.apply_global_style()
    fig, ax1 = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    unemp = engine.get_transformed("us_unemployment")
    if not unemp.empty:
        dates, vals = unemp.index.to_pydatetime().tolist(), unemp.values
        ax1.plot(dates, vals, color="#003366", linewidth=2, zorder=3, solid_capstyle="round")
        _add_end_label(ax1, dates, vals, "Unemployment", "#003366")

    ax1.set_ylabel("Unemployment Rate (%)", fontsize=EconStyle.FONT_SIZE_AXIS, color="#003366", labelpad=6)
    ax1.tick_params(axis="y", colors="#003366")

    ax2 = ax1.twinx()
    claims = engine.get_transformed("us_claims")
    if not claims.empty:
        claims_4w = (claims.rolling(4).mean() / 1000).dropna()
        dates_c, vals_c = claims_4w.index.to_pydatetime().tolist(), claims_4w.values
        ax2.plot(dates_c, vals_c, color="#d62728", linewidth=1.5, linestyle="-", alpha=0.85, zorder=2, solid_capstyle="round")
        _add_end_label(ax2, dates_c, vals_c, "Claims 4wk MA", "#d62728")

    ax2.set_ylabel("Initial Claims (K, 4wk MA)", fontsize=EconStyle.FONT_SIZE_AXIS, color="#d62728", labelpad=6)
    ax2.tick_params(axis="y", colors="#d62728")
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#d62728")

    nfp_latest = engine.get_latest("us_payrolls")
    if nfp_latest is not None:
        ax1.text(0.02, 0.95, f"Latest NFP: {nfp_latest:+,.0f}K", transform=ax1.transAxes, fontsize=10, fontweight="bold", color="#1f77b4", va="top", ha="left", bbox=dict(boxstyle="round,pad=0.3", facecolor="#E8F0FE", edgecolor="#1f77b4", linewidth=0.5))

    _style_axis(ax1)
    for spine in ["top", "left"]: ax1.spines[spine].set_visible(False)
    ax1.spines["bottom"].set_visible(True)
    ax2.spines["top"].set_visible(False)
    ax1.set_xlim(ax1.get_xlim()[0], ax1.get_xlim()[1] + (ax1.get_xlim()[1] - ax1.get_xlim()[0]) * 0.16)

    EconStyle.set_title(ax1, "Labour Market Pulse", "US Unemployment Rate vs. Initial Jobless Claims (4wk MA)")
    EconStyle.add_top_rule(ax1)
    EconStyle.add_source(fig, "FRED (BLS)")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "02_macro_labour.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Labour Market Pulse")

def chart_financial_conditions(engine, output_dir):
    EconStyle.apply_global_style()
    fig, ax1 = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    nfci = engine.get_transformed("nfci")
    if not nfci.empty:
        dates, vals = nfci.index.to_pydatetime().tolist(), nfci.values
        ax1.plot(dates, vals, color="#000000", linewidth=2, zorder=3, solid_capstyle="round")
        _add_end_label(ax1, dates, vals, "NFCI", "#000000")

        ax1.axhline(y=0, color="#A0A0A0", linewidth=0.8, linestyle="-", zorder=1)
        ax1.fill_between(dates, vals, 0, where=[v > 0 for v in vals], alpha=0.08, color=EconStyle.NEGATIVE, zorder=0)
        ax1.fill_between(dates, vals, 0, where=[v <= 0 for v in vals], alpha=0.05, color=EconStyle.POSITIVE, zorder=0)
        
        # Missing Glyph Fix: Removed Poppins incompatible arrow
        ax1.text(0.02, 0.92, "< Tighter", transform=ax1.transAxes, fontsize=7, color=EconStyle.NEGATIVE, alpha=0.6)
        ax1.text(0.02, 0.05, "< Looser", transform=ax1.transAxes, fontsize=7, color=EconStyle.POSITIVE, alpha=0.6)

    ax1.set_ylabel("NFCI (0 = avg conditions)", fontsize=EconStyle.FONT_SIZE_AXIS, color="#000000", labelpad=6)

    ax2 = ax1.twinx()
    hy = engine.get_transformed("hy_spread")
    if not hy.empty:
        dates_h, vals_h = hy.index.to_pydatetime().tolist(), hy.values * 100
        ax2.plot(dates_h, vals_h, color="#d62728", linewidth=1.5, alpha=0.85, zorder=2, solid_capstyle="round")
        _add_end_label(ax2, dates_h, vals_h, "HY Spread", "#d62728")

    ax2.set_ylabel("HY OAS (bps)", fontsize=EconStyle.FONT_SIZE_AXIS, color="#d62728", labelpad=6)
    ax2.tick_params(axis="y", colors="#d62728")
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#d62728")

    _style_axis(ax1)
    for spine in ["top", "left"]: ax1.spines[spine].set_visible(False)
    ax2.spines["top"].set_visible(False)
    ax1.set_xlim(ax1.get_xlim()[0], ax1.get_xlim()[1] + (ax1.get_xlim()[1] - ax1.get_xlim()[0]) * 0.16)

    EconStyle.set_title(ax1, "Financial Conditions & Credit Stress", "Chicago Fed NFCI vs. US High Yield Credit Spread")
    EconStyle.add_top_rule(ax1)
    EconStyle.add_source(fig, "FRED (Chicago Fed, ICE BofA)")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "03_macro_financial.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Financial Conditions")

def chart_emerging_markets(engine, output_dir):
    EconStyle.apply_global_style()
    fig, ax1 = plt.subplots(figsize=EconStyle.SIZE_WIDE)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    for ind_id in ["em_hy_spread", "em_corp_spread"]:
        if ind_id not in MACRO_INDICATORS: continue
        ind = MACRO_INDICATORS[ind_id]
        series = engine.get_transformed(ind_id)
        if series.empty: continue
        dates, vals = series.index.to_pydatetime().tolist(), series.values * 100
        ax1.plot(dates, vals, color=ind["color"], linewidth=2.2, solid_capstyle="round", zorder=3)
        _add_end_label(ax1, dates, vals, ind["name"], ind["color"])

    ax1.set_ylabel("Credit Spread (bps)", fontsize=EconStyle.FONT_SIZE_AXIS, color="#000000", labelpad=6)

    ax2 = ax1.twinx()
    if "em_usd_index" in MACRO_INDICATORS:
        usd = engine.get_transformed("em_usd_index")
        if not usd.empty:
            dates_u, vals_u = usd.index.to_pydatetime().tolist(), usd.values
            ax2.plot(dates_u, vals_u, color="#003366", linewidth=1.5, linestyle="--", alpha=0.85, zorder=2, solid_capstyle="round")
            _add_end_label(ax2, dates_u, vals_u, "USD vs EM", "#003366")

    ax2.set_ylabel("USD Index (vs EM)", fontsize=EconStyle.FONT_SIZE_AXIS, color="#003366", labelpad=6)
    ax2.tick_params(axis="y", colors="#003366")
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#003366")

    _style_axis(ax1)
    for spine in ["top", "left"]: ax1.spines[spine].set_visible(False)
    ax2.spines["top"].set_visible(False)
    ax1.set_xlim(ax1.get_xlim()[0], ax1.get_xlim()[1] + (ax1.get_xlim()[1] - ax1.get_xlim()[0]) * 0.18)

    EconStyle.set_title(ax1, "Emerging Markets Stress Monitor", "EM High Yield & Corporate Spreads vs. USD Strength")
    EconStyle.add_top_rule(ax1)
    EconStyle.add_source(fig, "FRED (ICE BofA, Federal Reserve)")
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "04_macro_em.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Emerging Markets Stress Monitor")
    
import matplotlib.pyplot as plt

# 1. Chart Data
regions = [
    'Latin America', 
    'Sub-Saharan Africa', 
    'Oceania', 
    'North America', 
    'Europe', 
    'Asia', 
    'Middle East & North Africa'
]
# Using 0.5 for <1% so it renders a tiny bar
percentages = [0.5, 1, 3, 3, 17, 37, 39] 
display_labels = ['<1%', '1%', '3%', '3%', '17%', '37%', '39%']

# 2. Canvas Setup (The Economics Hub standard)
fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
fig.patch.set_facecolor('#ffffff')
ax.set_facecolor('#ffffff')

# 3. Color Palette: Hub Red for MENA, muted greys for the rest
colors = ['#e0e0e0', '#cccccc', '#b3b3b3', '#999999', '#666666', '#333333', '#d62728']

# 4. Render Horizontal Bars
bars = ax.barh(regions, percentages, color=colors, height=0.65)

# 5. Clean Aesthetics (Remove all spines and axis ticks)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.xaxis.set_ticks([]) 
ax.tick_params(axis='y', length=0, labelsize=12, colors='#333333') 

# 6. Direct Data Labels (Bolding the MENA data point)
for bar, label in zip(bars, display_labels):
    width = bar.get_width()
    font_weight = 'bold' if label == '39%' else 'normal'
    color = '#d62728' if label == '39%' else '#333333'
    
    ax.text(width + 0.5, bar.get_y() + bar.get_height()/2, 
            label, 
            va='center', ha='left', fontsize=12, fontweight=font_weight, color=color)

# 7. Typography: Title & Subtitle
plt.text(-0.5, 7.4, "MENA's Absolute Dominance in Sovereign Wealth Funds", fontsize=18, fontweight='bold', color='#111111')
plt.text(-0.5, 6.9, "Proportion of global sovereign wealth fund assets by region (Total: $15.2 Trillion)", fontsize=12, color='#555555')

# 8. Footer / Source
plt.text(-0.5, -1.5, "Source: Global SWF (Dec 2025) | The Economics Hub", fontsize=10, color='#888888')

plt.tight_layout()

# Save output for the uploader
plt.savefig('TEH_SWF_Dominance.png', bbox_inches='tight', dpi=300)
plt.close()


def chart_macro_table(engine, output_dir):
    EconStyle.apply_global_style()
    rows = []
    
    for section in MACRO_TABLE_SECTIONS:
        for ind_id in section.get("rows", []):
            ind = MACRO_INDICATORS[ind_id]
            latest = engine.get_latest(ind_id)
            change = engine.get_change(ind_id)
            if latest is None: continue

            if ind["transform"] == "mom_abs": latest_str = f"{latest:+,.0f}K"
            elif "claims" in ind_id: latest_str = f"{latest/1000:,.0f}K"
            elif "spread" in ind_id or "hy" in ind_id: latest_str = f"{latest*100:.0f} bps"
            elif "usd_index" in ind_id: latest_str = f"{latest:.1f}"
            elif ind.get("unit") == "USD": latest_str = f"{latest:.2f}"  # <--- ADD THIS LINE
            elif abs(latest) > 100: latest_str = f"{latest:,.0f}"
            elif abs(latest) >= 1: latest_str = f"{latest:.2f}%"
            else: latest_str = f"{latest:.2f}"

            if change is not None:
                if "claims" in ind_id:
                    change_k = change / 1000
                    change_str = "0.0" if abs(change_k) < 0.1 else f"{change_k:+.1f}"
                elif "spread" in ind_id or "hy" in ind_id: change_str = f"{change*100:+.0f}"
                elif abs(change) < 0.005: change_str = "0.00"
                else: change_str = f"{change:+.2f}"
            else: change_str = "-"

            rows.append({
                "section": section["section"], "section_color": section["color"],
                "name": ind["name"], "latest": latest_str, "change": change_str, "unit": ind.get("unit", "")
            })

        for manual_key in section.get("manual_rows", []):
            if manual_key in MANUAL_DATA:
                m = MANUAL_DATA[manual_key]
                if "previous_value" in m and m["previous_value"] is not None:
                    change_str = f"{(m['value'] - m['previous_value']):+.2f}"
                else: change_str = "-"

                if m["unit"] == "index": val_str = f"{m['value']:.1f}"
                elif m["unit"] == "%": val_str = f"{m['value']:.1f}%"
                else: val_str = f"{m['value']}"

                rows.append({
                    "section": section["section"], "section_color": section["color"],
                    "name": m["name"], "latest": val_str, "change": change_str,
                    "unit": m["unit"], "manual_source": m["source"], "manual_date": m["as_of"]
                })

    n = len(rows)
    sections_seen = []
    for r in rows:
        if r["section"] not in sections_seen: sections_seen.append(r["section"])

    row_h, sec_gap, header_block, footer_space = 0.25, 0.45, 1.4, 0.95
    content_h = (0.65 * len(sections_seen)) + (row_h * n)
    fig_h = header_block + content_h + footer_space

    fig, ax = EconStyle.create_figure(size=(7.0, fig_h))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    cx = {"name": 0.5, "latest": 5.5, "change": 8.0, "unit": 9.5}
    y = fig_h - 0.4
    ax.text(0.5, y, "MACRO PULSE", fontsize=20, fontweight="bold", color="#000000", fontfamily="sans-serif", ha="left")
    y -= 0.25
    ax.text(0.5, y, datetime.now().strftime("%B %Y"), fontsize=10, color="#000000", ha="left")

    y -= 0.5
    for key, label in [("name", "INDICATOR"), ("latest", "LATEST"), ("change", "MoM CHG"), ("unit", "UNIT")]:
        ax.text(cx[key], y, label, fontsize=9, fontweight="bold", color="#000000", ha="left" if key == "name" else "right", fontfamily="sans-serif")
    y -= 0.15
    ax.plot([0.5, 9.5], [y, y], color="#000000", linewidth=1.2)

    cur_section = None
    for row in rows:
        if row["section"] != cur_section:
            cur_section = row["section"]
            y -= sec_gap
            ax.add_patch(plt.Rectangle((0, y - 0.125), 10, 0.25, facecolor="#F1F5F9", edgecolor="none", zorder=0))
            ax.text(cx["name"], y, cur_section, fontsize=9, fontweight="bold", color=row["section_color"], ha="left", va="center")
            y -= 0.20
        y -= row_h

        name_display = row["name"] + (f"  ({row['manual_source']})" if "manual_source" in row else "")
        ax.text(cx["name"], y, name_display, fontsize=10, fontweight="medium", color="#000000", ha="left", va="center")
        ax.text(cx["latest"], y, row["latest"], fontsize=10, color="#334155", ha="right", va="center")

        ch_col = "#065f46" if row["change"].startswith("+") else ("#991b1b" if row["change"].startswith("-") else "#64748b")
        ax.text(cx["change"], y, row["change"], fontsize=10, fontweight="bold", color=ch_col, ha="right", va="center")
        ax.text(cx["unit"], y, row["unit"], fontsize=9, color="#64748b", ha="right", va="center")
        ax.plot([0.5, 9.5], [y - row_h/2, y - row_h/2], color="#e2e8f0", linewidth=0.8, linestyle=":")

    footer_y = y - row_h/2 - 0.40
    ax.text(0.5, footer_y, f"Source: FRED, OECD, ICE BofA, S&P Global  |  {datetime.now().strftime('%d %b %Y')}", fontsize=8, color="#666666", ha="left", va="bottom")
    ax.text(9.5, footer_y, EconStyle.WATERMARK_TEXT, fontproperties=EconStyle._get_masthead_font(), fontsize=13, color="#1A1A1A", ha="right", va="bottom")

    EconStyle.finalize(fig, ax, source=None, tight=False)
    filepath = output_dir / "00_macro_table.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Macro Summary Table")

def chart_macro_cli(output_dir):
    fpath = output_dir / "oecd_cli.csv"
    if not fpath.exists(): return
    df = pd.read_csv(fpath).dropna(subset=["cli_latest"]).sort_values("cli_latest", ascending=True)

    fig, ax = EconStyle.create_figure(size=(10, 7))
    for i, (_, row) in enumerate(zip(range(len(df)), df.itertuples())):
        val, zone, direction = row.cli_latest, getattr(row, "cli_zone", ""), getattr(row, "cli_direction", "")
        
        if zone == "expansion" and direction == "rising": color, zone_label = COLOR_POSITIVE, "Expanding"
        elif zone == "expansion" and direction == "falling": color, zone_label = "#B8860B", "Peaking"
        elif zone == "contraction" and direction == "rising": color, zone_label = COLOR_G7, "Recovering"
        elif zone == "contraction" and direction == "falling": color, zone_label = COLOR_NEGATIVE, "Downturn"
        else: color, zone_label = COLOR_NEUTRAL, "N/A"

        ax.scatter(val, i, s=140, color=color, zorder=5, edgecolors="white", linewidth=0.8)
        arrow = " ^" if direction == "rising" else " v" if direction == "falling" else ""
        ax.text(val + 0.15, i, f"{val:.1f}{arrow}  {zone_label}", va="center", ha="left", fontsize=8.5, fontweight="bold", color=color, fontfamily=EconStyle.FONT_FAMILY)

    labels = [f"{r['country']} (EM)" if r.get("group") == "EM" else r['country'] for _, r in df.iterrows()]
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(labels, fontsize=9.5)
    
    ax.axvline(x=100, color="#000000", linewidth=1.5, zorder=2)
    xlim = ax.get_xlim()
    ax.axvspan(xlim[0], 100, color=COLOR_NEGATIVE, alpha=0.03, zorder=0)
    ax.axvspan(100, xlim[1], color=COLOR_POSITIVE, alpha=0.03, zorder=0)

    for spine in ["top", "right", "left"]: ax.spines[spine].set_visible(False)

    EconStyle.set_title(ax, "OECD Leading Indicators", "Composite Leading Indicator — Cycle Phase & Direction")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[0.02, 0.06, 0.98, 0.96])
    EconStyle.add_source(fig, "OECD Main Economic Indicators via DBnomics")
    EconStyle.save_chart(fig, output_dir / "07_macro_oecd_cli.png")
    print(f"   ✓ OECD Leading Indicators Dashboard")

def chart_macro_em_vulnerability(output_dir):
    fpath = output_dir / "em_macro.csv"
    if not fpath.exists(): return
    df = pd.read_csv(fpath)
    needed = ["current_account_gdp", "govt_debt_gdp", "cpi_yoy"]
    existing = [c for c in needed if c in df.columns]
    if not existing: return
    df = df.dropna(subset=existing, how="all")

    fig, axes = plt.subplots(1, 3, figsize=(15, 7.5), sharey=True)
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')
    EconStyle.apply_global_style()

    df["vuln_score"] = df.get("cpi_yoy", 0) + df.get("govt_debt_gdp", 0) - df.get("current_account_gdp", 0)
    df = df.sort_values("vuln_score", ascending=True)

    panels = [
        ("current_account_gdp", "Current Account (% GDP)", -4, "below", None),
        ("govt_debt_gdp", "Govt Debt (% GDP)", 60, "above", None),
        ("cpi_yoy", "CPI Inflation (YoY %)", 6, "above", 15),
    ]

    for ax, (col, title, thresh, bad_dir, clip_at) in zip(axes, panels):
        if col not in df.columns:
            ax.axis("off")
            continue
            
        vals = df[col].values
        for i, v in enumerate(vals):
            if pd.isna(v): continue
            is_bad = (v > thresh) if bad_dir == "above" else (v < thresh)
            color = COLOR_NEGATIVE if is_bad else COLOR_G7
            disp_v = min(v, clip_at) if clip_at and v > clip_at else v
            
            ax.scatter(disp_v, i, s=100, color=color, zorder=5, edgecolors="white")
            ax.plot([0 if col != "current_account_gdp" else min(0, disp_v), disp_v], [i, i], color=color, linewidth=0.6, alpha=0.3, zorder=2)
            
            label_x = v + (abs(ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.03) if v >= 0 else v - (abs(ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.03)
            ax.text(label_x if not (clip_at and v > clip_at) else disp_v - 0.3, i, f"{v:.1f}%" + (">>" if clip_at and v > clip_at else ""), va="center", ha="left" if v >= 0 and not (clip_at and v > clip_at) else "right", fontsize=8, fontweight="bold", color=color)

        ax.axvline(x=thresh, color=COLOR_TARGET, linewidth=1, linestyle="--", alpha=0.5, zorder=1)
        if clip_at: ax.set_xlim(right=clip_at + 1)
        ax.set_title(title, fontsize=10, fontweight="bold", loc="left", fontfamily=EconStyle.FONT_FAMILY)
        for spine in ["top", "right", "left"]: ax.spines[spine].set_visible(False)
        ax.plot([0, 1], [1, 1], color="#000000", linewidth=1.2, transform=ax.transAxes, clip_on=False, zorder=10)

    axes[0].set_yticks(range(len(df)))
    axes[0].set_yticklabels(df["country"].values, fontsize=9.5)
    
    fig.text(0.02, 0.97, "EM Vulnerability Scorecard", fontsize=18, fontweight="bold")
    fig.text(0.04, 0.02, f"Source: IMF WEO + CPI via DBnomics  |  {datetime.now().strftime('%d %b %Y')}", fontsize=8, color="#666666", ha="left", va="bottom")
    fig.tight_layout(rect=[0.01, 0.06, 0.99, 0.91])
    EconStyle.save_chart(fig, output_dir / "08_macro_em_vulnerability.png")
    print(f"   ✓ EM Vulnerability Scorecard")


def chart_agflation_pipeline(output_dir):
    """Deep Dive Chart: Energy to Food Pipeline (Smoothed, Base-100)."""
    EconStyle.apply_global_style()
    
    # 1. Load Manual Urea Data
    urea_path = PROJECT_ROOT / "data" / "urea_middle_east.csv"
    if not urea_path.exists():
        print("   ⚠ Missing Urea CSV. Please place urea_middle_east.csv in the data folder.")
        return

    # Parse Investing.com CSV (using our bulletproof date fix)
    urea_df = pd.read_csv(urea_path)
    urea_df['Date'] = pd.to_datetime(urea_df['Date'], dayfirst=True, format='mixed')
    urea_df = urea_df.sort_values('Date').set_index('Date')
    
    if urea_df['Price'].dtype == object:
        urea_df['Price'] = urea_df['Price'].str.replace(',', '').astype(float)

    # 2. Force start date to January 1, 2026 to show the pure "Hockey Stick"
    start_date = pd.to_datetime("2026-01-01")
    urea_df = urea_df[urea_df.index >= start_date]
    
    if urea_df.empty:
        print("   ⚠ Urea data doesn't contain 2026 dates. Please download a longer timeframe.")
        return
        
    end_date = urea_df.index[-1]

    # 3. Fetch Yahoo Finance Data
    tickers = {"Natural Gas (TTF)": "TTE=F", "Wheat Futures": "ZW=F"}
    yf_data = yf.download(list(tickers.values()), start=start_date, end=end_date + pd.Timedelta(days=1), progress=False)
    
    if yf_data.empty:
        print("   ⚠ Yahoo Finance data fetch failed.")
        return
        
    prices = yf_data['Close']
    
    # 4. Merge, Forward-Fill, and SMOOTH the data
    merged = pd.DataFrame(index=pd.date_range(start=start_date, end=end_date, freq='B'))
    merged["Urea Futures"] = urea_df["Price"]
    
    for name, ticker in tickers.items():
        if ticker in prices.columns:
            merged[name] = prices[ticker]
            
    # Forward-fill gaps (weekends/holidays), then backward fill the very first day if needed
    merged = merged.ffill().bfill()
    
    # Apply a 5-day Exponential Moving Average to kill the "staircase" look
    smoothed = merged.ewm(span=5, adjust=False).mean()
    
    # Normalize to 100 based on Jan 1st levels
    normalized = (smoothed / smoothed.iloc[0]) * 100

    # 5. Draw the Chart
    fig, ax = EconStyle.create_figure(size=(11, 6.5))
    fig.patch.set_linewidth(2)
    fig.patch.set_edgecolor('#000000')

    colors = {
        "Natural Gas (TTF)": "#BE185D",  # Energy Pink
        "Urea Futures": "#D97706", # Chemical Orange
        "Wheat Futures": "#003366"       # Agricultural Navy
    }
    
    dates = normalized.index.to_pydatetime()
    
    # Draw the main lines much thicker (3.8) for premium visibility
    for col in normalized.columns:
        vals = normalized[col].values
        ax.plot(dates, vals, label=col, color=colors[col], linewidth=3.8, solid_capstyle="round", zorder=3)
        
        # End Labels
        last_val = vals[-1]
        pct_change = last_val - 100
        sign = "+" if pct_change > 0 else ""
        ax.annotate(
            f"{col} ({sign}{pct_change:.1f}%)", xy=(dates[-1], last_val),
            xytext=(6, 0), textcoords="offset points",
            fontproperties=EconStyle._get_font("bold"),
            fontsize=10, color=colors[col], va="center", ha="left",
            path_effects=[pe.withStroke(linewidth=3, foreground=EconStyle.BACKGROUND)]
        )

    # NEW: Refined Vertical Event Marker
    event_date = pd.to_datetime("2026-02-27")
    if event_date >= dates[0] and event_date <= dates[-1]:
        # Thinner, dark red line that doesn't dominate the chart
        ax.axvline(x=event_date, color="#120000", linewidth=1.4, linestyle="--", alpha=0.6, zorder=2)
        
        y_max = normalized.max().max()
        
        # Shifted label to the left of the event line to preserve readability of the spike
        ax.text(event_date - pd.Timedelta(days=1), y_max * 0.98, "US-Israel Strike\non Iran", 
                fontsize=9.5, fontweight="bold", color="#CC0000", alpha=0.8, va="top", ha="right",
                fontfamily=EconStyle.FONT_FAMILY,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.7, pad=1))

    # Styling
    ax.axhline(100, color="#A0A0A0", linewidth=1.2, linestyle="--", zorder=2)
    
    # (Removed the redundant "Base = 100" text box here as requested)

    ax.set_ylabel("Indexed Price (Base = 100)", fontsize=10, color=EconStyle.TEXT_SECONDARY, labelpad=8)
    ax.grid(axis="y", visible=True, color=EconStyle.GRID_COLOR, linewidth=0.5, zorder=0)
    ax.grid(axis="x", visible=False)
    
    # Format X-axis for short timeframe
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=10))
    plt.setp(ax.get_xticklabels(), fontsize=10)

    for spine in ["top", "right", "left"]: 
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(EconStyle.AXIS_COLOR)

    # NEW: Tighten up the blank space on the right (leaves exactly 5 days of room for labels)
    ax.set_xlim(dates[0], dates[-1] + pd.Timedelta(days=5))

    # Elite Narrative Titles
    EconStyle.set_title(ax, 
                        "Futures Markets are Pricing the Agricultural Shock", 
                        "Rising European gas and fertilizer input futures are signaling a severe, lagged spike in global food costs")
    EconStyle.add_top_rule(ax)
    
    # Source Line
    EconStyle.add_source(fig, "Investing.com, Yahoo Finance. Note: Urea data is for Middle East region, not global")
    
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    filepath = output_dir / "11_agflation_pipeline.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Agflation Pipeline Chart (Smoothed & Refined)")
    return filepath

import matplotlib.pyplot as plt
import matplotlib.image as mpimg

def chart_bdti_branded_screenshot(output_dir):
    """Wraps a paywalled chart screenshot in the Economics Hub branding."""
    EconStyle.apply_global_style()
    
    # 1. Load the raw screenshot
    img_path = PROJECT_ROOT / "data" / "bdti_raw_chart.png"
    if not img_path.exists():
        print("   ⚠ Missing bdti_screenshot.png in the data folder.")
        return
        
    img = mpimg.imread(img_path)
    
    # 2. Create the standard EconStyle figure
    fig, ax = EconStyle.create_figure(size=(11, 7.5)) 
    
    # 3. Plot the image directly onto the matplotlib axis
    ax.imshow(img, aspect='auto', interpolation='lanczos')
    ax.axis('off')
    
    # ─── 100% ABSOLUTE MANUAL OVERRIDE ───────────────────────────────────────
    # Bypassing all EconStyle title functions to guarantee perfect spacing
    
    # 4. Main Title (Anchored at the very top)
    fig.text(0.02, 0.97, "Tanker Freight Rates Rise to Multi-Year Highs", 
             fontsize=20, fontweight="bold", ha="left", va="top", color="#000000")
             
    # 5. Subtitle (Anchored perfectly below the main title)
    fig.text(0.02, 0.92, "Baltic Dirty Tanker Index breaks above 3,000 for the first time since the 2022 energy crisis as Gulf shipping costs spike", 
             fontsize=12, color=EconStyle.TEXT_SECONDARY, ha="left", va="top")
             
    # 6. Top Rule (Draws the thick black line directly below the subtitle)
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.88, 0.88], color='black', linewidth=2.5, zorder=10, transform=fig.transFigure))
             
    # 7. Split Custom Footer
    fig.text(0.02, 0.02, "Source: Baltic Exchange and StockQ", 
             fontsize=12, color=EconStyle.TEXT_SECONDARY, ha="left", va="bottom", fontweight="bold")
    fig.text(0.98, 0.02, "The Economics Hub", 
             fontsize=14, color="#1C1C1E", ha="right", va="bottom", fontweight="bold")
    
    # 8. Lock the chart image exactly between the header line (0.88) and footer (0.02)
    fig.tight_layout(rect=[0.02, 0.06, 0.98, 0.86])
    # ─────────────────────────────────────────────────────────────────────────
    
    filepath = output_dir / "13_bdti_branded_screenshot.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ BDTI Branded Screenshot Wrapper Complete")
    return filepath

def chart_hormuz_exposure(output_dir):
    """Generates a horizontal bar chart showing Strait of Hormuz export exposure."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    EconStyle.apply_global_style()

    # 1. Extracted Data (Exports only, excluding Softs and Grains/Oilseeds)
    # Grouped into three distinct categories for specific color targeting
    data = [
        ("Methanol", 31.6, "Petrochemicals & Refined"),
        ("Crude Oil &\nCondensates", 30.9, "Crude & LNG"),
        ("Natural Gas \nLiquids (NGLs)", 23.3, "Petrochemicals & Refined"),
        ("Liquefied Natural \nGas (LNG)", 18.6, "Crude & LNG"),  
        ("Dirty Petroleum \nProducts (DPP)", 13.0, "Petrochemicals & Refined"),
        ("Clean Petroleum \nProducts (CPP)", 12.6, "Petrochemicals & Refined"),
        ("Petcoke", 6.1, "Petrochemicals & Refined")
    ]

    # Sort by value (ascending, so the largest bar renders at the very top of the chart)
    data.sort(key=lambda x: x[1])

    labels = [item[0] for item in data]
    values = [item[1] for item in data]
    categories = [item[2] for item in data]

    # 2. Institutional Color Mapping
    color_ag = "#1E3A8A"      # Deep Blue
    color_energy = "#D97706"  # Burnt Orange
    color_petro = "#C2185B"   # Deep Magenta/Pink for Petrochemicals

    colors = []
    for cat in categories:
        if cat == "Agriculture & Minerals":
            colors.append(color_ag)
        elif cat == "Petrochemicals & Refined":
            colors.append(color_petro)
        else:
            colors.append(color_energy)

    # 3. Create Figure
    fig, ax = EconStyle.create_figure(size=(10, 7))

    # 4. Plot Horizontal Bars
    bars = ax.barh(labels, values, color=colors, height=0.6, zorder=3)

    # 5. Add Data Labels directly to the end of the bars
    for bar, val in zip(bars, values):
        ax.text(
            val + 0.5,  # Offset slightly to the right of the bar
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%",
            va='center', ha='left',
            fontsize=11, fontweight='bold', color="#1C1C1E"
        )

    # 6. Clean and Style Axes
    ax.set_xlim(0, 40)
    ax.set_xlabel("Share of Global Exports (%)", fontsize=EconStyle.FONT_SIZE_AXIS, color=EconStyle.TEXT_SECONDARY)
    
    # Remove the bounding box
    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color(EconStyle.AXIS_COLOR)

    # 7. Gridlines (Force behind bars with correct transparency)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, linestyle='-', alpha=0.3, color='#9CA3AF', zorder=0)
    ax.yaxis.grid(False) 

    # 8. Custom 3-Part Categorical Legend
    energy_patch = mpatches.Patch(color=color_energy, label='Crude & LNG')
    petro_patch = mpatches.Patch(color=color_petro, label='Petrochemicals and Refined Products')
    
    ax.legend(handles=[petro_patch, energy_patch], loc='lower right', frameon=False, fontsize=11)

    # 9. Titles and Proprietary Branding
    EconStyle.set_title(
        ax,
        "The Gulf Is the World's Petrochemical Supplier",
        "Mideast Gulf exports as a share of global seaborne trade across commodity categories"
    )
    EconStyle.add_top_rule(ax)

    # Tight layout to prevent clipping
    fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])

    # Footer with source
    EconStyle.add_source(fig, "Kpler, S&P Global, U.S. EIA")

    # 10. Save
    filepath = output_dir / "15_hormuz_exposure.png"
    EconStyle.save_chart(fig, filepath)
    print(f"   ✓ Hormuz Petrochemical Exposure Chart Complete")
    
    return filepath

# ═══════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════

def generate_macro_dashboard():
    month_str = datetime.now().strftime("%Y-%m")
    output_dir = PROJECT_ROOT / "output" / "macro" / month_str
    output_dir.mkdir(parents=True, exist_ok=True)

    print("📊 Generating Economics Hub — Macro Pulse Dashboard")
    print(f"   Output: {output_dir}\n")

    if FRED_API_KEY == "YOUR_FRED_API_KEY":
        print("⚠  FRED API key not set! Open config/settings.py")
        return

    fred = FredFetcher(api_key=FRED_API_KEY)
    engine = MacroDataEngine(fred)

    print("   Fetching macro data from FRED...")
    success = 0
    for ind_id in MACRO_INDICATORS:
        try:
            data = engine.fetch_raw(ind_id)
            if not data.empty:
                success += 1
                print(f"   ✓ {MACRO_INDICATORS[ind_id]['name']}")
        except Exception: pass

    print(f"\n   Fetched {success}/{len(MACRO_INDICATORS)} FRED indicators\n")

    #print("   Fetching International Data via DBnomics...")
    #fetch_macro_oecd_cli(output_dir)
    #fetch_macro_em_vulnerability(output_dir)

    print("\n   Generating charts...")
    
    # 1. Generate Table First
    chart_macro_table(engine, output_dir)
    
    chart_inflation(engine, output_dir)
    chart_labour(engine, output_dir)
    chart_financial_conditions(engine, output_dir)
    chart_emerging_markets(engine, output_dir)
  
    
    #chart_macro_cli(output_dir)
    #chart_macro_em_vulnerability(output_dir)
    
    chart_agflation_pipeline(output_dir)
    chart_bdti_branded_screenshot(output_dir)
    chart_hormuz_exposure(output_dir)

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