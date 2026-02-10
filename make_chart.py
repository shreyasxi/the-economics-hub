#!/usr/bin/env python3
"""
Economics Hub — Custom Chart Pipeline (The Ultimate Version)
================================================================
Turn any CSV/Excel dataset into a publication-ready chart.

location: python make_chart.py data/external/mydata.xlsx (followerd by customisations)

USAGE CHEAT SHEET:
------------------
1. LINE CHART (Default)
   python make_chart.py data/external/data.xlsx --title "Inflation Trend"

2. BAR CHART (For categories like Sectors or Countries)
   python make_chart.py data/external/sectors.xlsx --type bar --title "Sector Returns"

3. COMPARISON CHART (Rebases all series to 100 at start)
   python make_chart.py data/external/stocks.xlsx --type comparison --title "S&P 500 vs Gold"

4. DUAL AXIS (Left vs Right scale)
   python make_chart.py data/external/rates.xlsx --type dual --title "Rates vs GDP"

5. SCATTER PLOT
   python make_chart.py data/external/risk.xlsx --type scatter --title "Risk vs Reward"

6. CUSTOM COLORS & HEIGHT
   python make_chart.py data.xlsx --title "My Chart" --colors "us,europe" --height 6.0
   python make_chart.py data.xlsx --title "My Chart" --colors "#FF0000,#0000FF"

OPTIONS:
  --type       line | bar | dual | comparison | scatter  (default: auto)
  --height        Chart height in inches (default ~4.5)
  --colors        Comma-separated list (e.g., "red,blue" or "#F00,#00F")
  --title      Chart title (required)
  --subtitle   Chart subtitle
  --source     Data source label (default: "The Economics Hub")
  --ylabel     Y-axis label
  --date-format   Format for x-axis dates (e.g., "%Y" for just year)
  --output     Output filename (default: auto-generated)
  --edition    "weekly" or "macro" → saves to appropriate folder
  --normalize  Index all series to 100 at start
  --preview    Lower DPI for quick preview

CSV FORMAT:
  - First column: dates (any parseable format) OR category labels
  - Remaining columns: numeric series (column headers become series names)
  - Example:
      Date,S&P 500,FTSE 100,Nifty 50
      2025-01-01,4800,7500,21000
      2025-02-01,4900,7600,21500
      ...
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import matplotlib.patheffects as pe

from style.economics_hub_style import EconStyle

# ═══════════════════════════════════════════════
# DATA LOADING & PREP
# ═══════════════════════════════════════════════

def load_data(filepath):
    fp = Path(filepath)
    if fp.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(fp)
    elif fp.suffix == ".tsv":
        df = pd.read_csv(fp, sep="\t")
    else:
        df = pd.read_csv(fp)

    # Try parse dates
    first_col = df.columns[0]
    try:
        df[first_col] = pd.to_datetime(df[first_col])
        df = df.set_index(first_col)
        df = df.sort_index()
        has_dates = True
    except (ValueError, TypeError):
        df = df.set_index(first_col) # Use as category labels
        has_dates = False

    # Clean numeric data
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    return df, has_dates

def auto_detect_type(df, has_dates):
    n_series = len(df.columns)
    if not has_dates: return "bar"
    if n_series >= 2:
        mins = [df[c].min() for c in df.columns]
        maxs = [df[c].max() for c in df.columns]
        if len(maxs) == 2 and max(maxs) / (min(maxs) + 1e-9) > 10:
            return "dual"
    return "line"

def parse_colors(color_arg):
    if not color_arg: return None
    raw_list = color_arg.split(",")
    final_colors = []
    for c in raw_list:
        c = c.strip()
        if c in EconStyle.REGION_COLORS:
            final_colors.append(EconStyle.REGION_COLORS[c])
        elif c in ["positive", "green"]:
            final_colors.append(EconStyle.POSITIVE)
        elif c in ["negative", "red"]:
            final_colors.append(EconStyle.NEGATIVE)
        else:
            final_colors.append(c)
    return final_colors

# ═══════════════════════════════════════════════
# CHART BUILDERS
# ═══════════════════════════════════════════════

def _end_label(ax, dates, values, name, color, num_series):
    vals_clean = values.dropna()
    if len(vals_clean) == 0: return
    last_val = float(vals_clean.iloc[-1])
    last_date = vals_clean.index[-1]

    if abs(last_val) > 1000: vs = f"{last_val:,.0f}"
    elif abs(last_val) < 1:  vs = f"{last_val:.3f}"
    else:                    vs = f"{last_val:.2f}"

    label = f" {name}  {vs}" if num_series > 1 else f" {vs}"
    
    ax.annotate(
        label, xy=(last_date, last_val),
        xytext=(5, 0), textcoords="offset points",
        fontproperties=EconStyle._get_font("bold"),
        fontsize=EconStyle.FONT_SIZE_ANNOTATION,
        color=color, va="center", ha="left",
        path_effects=[pe.withStroke(linewidth=3.0, foreground=EconStyle.BACKGROUND)],
    )

def make_line_chart(df, title, subtitle=None, source="The Economics Hub", 
                   ylabel=None, normalize=False, colors=None, height=None, date_fmt="%b '%y", **kwargs):
    
    size = (9.5, float(height)) if height else "wide"
    fig, ax = EconStyle.create_figure(size=size)
    palette = colors if colors else EconStyle.SERIES_COLORS
    
    for i, col in enumerate(df.columns):
        c = palette[i % len(palette)]
        vals = df[col].dropna()
        if vals.empty: continue

        if normalize and vals.iloc[0] != 0:
            vals = (vals / vals.iloc[0]) * 100

        if len(df.columns) <= 3:
            ax.plot(vals.index, vals, color=c, linewidth=4, alpha=0.1, zorder=2)
            
        ax.plot(vals.index, vals, color=c, linewidth=2.0, zorder=3+i)
        _end_label(ax, vals.index, vals, col, c, len(df.columns))

    ax.xaxis.set_major_formatter(mdates.DateFormatter(date_fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    if ylabel: ax.set_ylabel(ylabel, color=EconStyle.TEXT_SECONDARY)
    
    xmin, xmax = ax.get_xlim()
    ax.set_xlim(xmin, xmax + (xmax - xmin) * 0.15)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig

def make_bar_chart(df, title, subtitle=None, source="The Economics Hub", 
                  colors=None, height=None, **kwargs):
    
    col = df.columns[0]
    vals = df[col].fillna(0)
    cats = df.index.astype(str)
    
    h = float(height) if height else max(2.5, 0.4 * len(cats) + 1.0)
    fig, ax = EconStyle.create_figure(size=(7.5, h))
    
    if colors:
        bar_colors = [colors[i % len(colors)] for i in range(len(vals))]
    else:
        bar_colors = EconStyle.get_bar_colors(vals)
        
    y_pos = np.arange(len(cats))
    ax.barh(y_pos, vals, height=0.5, color=bar_colors, zorder=3)
    
    max_val = max(abs(vals)) if len(vals) > 0 else 1
    for i, v in enumerate(vals):
        label = f"{v:+.1f}%" if abs(v) < 100 else f"{v:,.0f}"
        offset = max_val * 0.02
        x = v + (offset if v >= 0 else -offset)
        ha = "left" if v >= 0 else "right"
        ax.text(x, i, label, va="center", ha=ha, 
                color=bar_colors[i], fontweight="bold", fontsize=9,
                path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats)
    ax.invert_yaxis()
    ax.grid(visible=False)
    ax.axvline(0, color="black", linewidth=0.5)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig

def make_dual_axis_chart(df, title, subtitle=None, source="The Economics Hub", 
                   colors=None, height=None, **kwargs):
    
    if len(df.columns) < 2: return make_line_chart(df, title, subtitle, source, colors=colors, height=height)
    
    size = (9.5, float(height)) if height else "wide"
    fig, ax1 = EconStyle.create_figure(size=size)
    ax2 = ax1.twinx()
    
    c1 = colors[0] if colors and len(colors) > 0 else "#003366"
    c2 = colors[1] if colors and len(colors) > 1 else "#d62728"
    
    s1 = df.iloc[:, 0].dropna()
    ax1.plot(s1.index, s1, color=c1, linewidth=2, zorder=3)
    ax1.set_ylabel(df.columns[0], color=c1, fontsize=9)
    ax1.tick_params(axis='y', labelcolor=c1)
    _end_label(ax1, s1.index, s1, df.columns[0], c1, 2)
    
    s2 = df.iloc[:, 1].dropna()
    ax2.plot(s2.index, s2, color=c2, linewidth=1.5, linestyle="--", zorder=2)
    ax2.set_ylabel(df.columns[1], color=c2, fontsize=9)
    ax2.tick_params(axis='y', labelcolor=c2)
    ax2.spines['right'].set_visible(True)
    ax2.spines['right'].set_color(c2)
    
    xmin, xmax = ax1.get_xlim()
    ax1.set_xlim(xmin, xmax + (xmax - xmin) * 0.15)
    
    EconStyle.set_title(ax1, title, subtitle)
    EconStyle.add_top_rule(ax1)
    EconStyle.add_source(fig, source)
    return fig

def make_comparison_chart(df, title, subtitle=None, source="The Economics Hub", 
                         colors=None, height=None, **kwargs):
    return make_line_chart(df, title, subtitle, source, normalize=True, 
                          colors=colors, height=height, ylabel="Indexed (100 = Start)", **kwargs)

def make_scatter_chart(df, title, subtitle=None, source="The Economics Hub", 
                      colors=None, height=None, **kwargs):
    if len(df.columns) < 2: raise ValueError("Scatter needs 2 columns")
    size = (8.5, float(height)) if height else "standard"
    fig, ax = EconStyle.create_figure(size=size)
    c = colors[0] if colors else "#003366"
    ax.scatter(df.iloc[:,0], df.iloc[:,1], color=c, s=50, alpha=0.7, edgecolors="white", zorder=3)
    ax.set_xlabel(df.columns[0], fontsize=9)
    ax.set_ylabel(df.columns[1], fontsize=9)
    ax.grid(True)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig

# ═══════════════════════════════════════════════
# MAIN INTERFACE
# ═══════════════════════════════════════════════

CHART_BUILDERS = {
    "line": make_line_chart, 
    "bar": make_bar_chart, 
    "dual": make_dual_axis_chart,
    "comparison": make_comparison_chart,
    "scatter": make_scatter_chart
}

def main():
    parser = argparse.ArgumentParser(description="Economics Hub Custom Chart Generator")
    parser.add_argument("file", help="Path to Excel/CSV file")
    parser.add_argument("--type", choices=list(CHART_BUILDERS.keys()), help="Force chart type")
    parser.add_argument("--title", required=True, help="Chart Title")
    parser.add_argument("--subtitle", help="Chart Subtitle")
    parser.add_argument("--source", default="The Economics Hub", help="Data Source")
    parser.add_argument("--ylabel", help="Y-Axis Label")
    parser.add_argument("--colors", help="Comma-separated colors (e.g. 'us,europe')")
    parser.add_argument("--height", help="Custom chart height (e.g. 6.0)")
    parser.add_argument("--normalize", action="store_true", help="Index to 100")
    parser.add_argument("--date-format", default="%b '%y", help="Date format (e.g. '%Y')")
    
    args = parser.parse_args()
    
    print(f"📊 Processing: {args.file}")
    df, has_dates = load_data(args.file)
    
    chart_type = args.type or auto_detect_type(df, has_dates)
    if args.normalize: chart_type = "comparison" # Override if flag set
    
    custom_colors = parse_colors(args.colors)
    
    fig = CHART_BUILDERS[chart_type](
        df, 
        title=args.title, 
        subtitle=args.subtitle, 
        source=args.source,
        ylabel=args.ylabel,
        colors=custom_colors,
        height=args.height,
        normalize=args.normalize,
        date_fmt=args.date_format
    )
    
    out_dir = PROJECT_ROOT / "output" / "custom"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = args.title.lower().replace(" ", "_")[:40] + ".png"
    out_path = out_dir / filename
    
    EconStyle.save_chart(fig, out_path)
    print(f"✅ Saved to: {out_path}")

if __name__ == "__main__":
    main()