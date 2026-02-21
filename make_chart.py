#!/usr/bin/env python3
"""
Economics Hub — Custom Chart Pipeline v4.0
================================================================
Turn any CSV/Excel dataset into a publication-ready chart.

USAGE CHEAT SHEET:
------------------

Example command: 

python make_chart.py "data/external/india_inflation.xlsx" 
--title "India Inflation-  Headline vs Food" --subtitle "CPI Year-on-Year % Change" --colors "navy,orange" 
--source "MoSPI" --type dual

CHART TYPES:
---------------------
1. LINE CHART (Default)
   python make_chart.py "data.xlsx" --title "Inflation Trend"

2. VERTICAL GROUPED BAR (Fixed: Now properly sized for dates)
   python make_chart.py "inflation.xlsx" --type bar --title "Headline vs Food"

3  HORIZONTAL BAR (For Categories like Sectors)

4. NET FLOWS (Red/Green Bars)
   python make_chart.py "inflation.xlsx" --type barh
   
5. AREA (Stacked area chart)   

6. COMBO (Bars + Line)

7. DUAL AXIS (Left vs Right scale)
   
8. COMPARISON CHART (Rebases all series to 100 at start, good for asset performance comparison)
   python make_chart.py "stocks.xlsx" --type comparison --title "S&P 500 vs Gold"

9. SCATTER PLOT

10. SLOPE — Before/after comparison (FT-style slopegraph)
    python make_chart.py "change.csv" --type slope --title "2024 vs 2025"

12. LOLLIPOP — Clean alternative to bar charts but when you have a lot of entreis to plot
    python make_chart.py "rankings.csv" --type lollipop --title "Country Rankings"

13. DIVERGING — Horizontal bars diverging from center
    python make_chart.py "sentiment.csv" --type diverging --title "Bull vs Bear"

14. STEP — Step chart (great for policy rates)
    python make_chart.py "fed_rates.csv" --type step --title "Fed Funds Rate"

16. BAND — Line with confidence/range bands
    python make_chart.py "forecast.csv" --type band --title "GDP Forecast"

17. TARGET — Bars with target markers
    python make_chart.py "performance.csv" --type target --title "Sales vs Target"

18. DONUT — Composition/share charts
    python make_chart.py "market_share.csv" --type donut --title "Market Share"

19. HEATMAP — Correlation matrices, calendar views
    python make_chart.py "correlation.csv" --type heatmap --title "Asset Correlations"

21. RANGE — Min-max range chart
    python make_chart.py "forecasts.csv" --type range --title "Analyst Estimates"

22. EVENT — Line chart with event annotations
    python make_chart.py "prices.csv" --type event --events "2024-03-15:Rate Cut,2024-06-01:Election"

OPTIONS:
  --type          line | bar | barh | dual | comparison | scatter | flows | area | combo |
                  slope | lollipop | diverging | dumbbell | step | band | 
                  target | donut | heatmap | range | event
  --height        Chart height in inches (default ~5.0)
  --colors        Comma-separated list (e.g., "red,blue" or "#F00,#00F")
  --title         Chart title (required)
  --subtitle      Chart subtitle
  --source        Data source label (default: "The Economics Hub")
  --ylabel        Y-axis label
  --date-fmt      Format for x-axis dates (e.g., "%Y" for just year)
  --output        Output filename (default: auto-generated)
  --normalize     Index all series to 100 at start
  --preview       Lower DPI for quick preview
  --ref-line      Add horizontal reference line (e.g., "50:Neutral" or "2:Target")
  --events        Event markers for event chart (e.g., "2024-03-15:Rate Cut,2024-06-01:Election")
  
 You can use these names instead of hex codes:

| Name | Color |
|------|-------|
| `navy`, `blue` | #003366 |
| `orange`, `gold` | #D97706 |
| `green`, `positive` | #059669 |
| `red`, `negative` | #B91C1C |
| `purple` | #7C3AED |
| `teal`, `cyan` | #0891B2 |
| `pink`, `magenta` | #BE185D |

CSV FORMAT:
  - First column: dates (any parseable format) OR category labels
  - Remaining columns: numeric series (column headers become series names)
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap

# Import your existing style module
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from style.economics_hub_style import EconStyle
except ImportError:
    # Fallback styling if running standalone
    class EconStyle:
        BACKGROUND = "#FFFFFF"
        FONT_FAMILY = "sans-serif"
        SERIES_COLORS = ["#003366", "#D97706", "#059669", "#7C3AED", "#B91C1C"]
        FONT_SIZE_AXIS = 9
        
        @staticmethod
        def create_figure(size=(9.5, 5)):
            fig, ax = plt.subplots(figsize=size)
            ax.set_facecolor("#FFFFFF")
            return fig, ax
        
        @staticmethod
        def set_title(ax, title, subtitle=None):
            ax.set_title(title, loc="left", fontsize=14, fontweight="bold", pad=20)
            if subtitle:
                ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=10)

        @staticmethod
        def add_top_rule(ax):
            ax.spines['top'].set_visible(True)
            ax.spines['top'].set_linewidth(1.5)

        @staticmethod
        def finalize(fig, ax, source=None):
            if source:
                ax.text(0, -0.1, f"Source: {source}", transform=ax.transAxes, fontsize=8, color="#666666")
            plt.tight_layout()

        @staticmethod
        def save_chart(fig, path):
            fig.savefig(path, dpi=300, bbox_inches="tight")


# ═══════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════

def load_data(filepath):
    fp = Path(filepath)
    if fp.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(fp)
    elif fp.suffix == ".tsv":
        df = pd.read_csv(fp, sep="\t")
    else:
        df = pd.read_csv(fp)

    first_col = df.columns[0]
    try:
        df[first_col] = pd.to_datetime(df[first_col])
        df = df.set_index(first_col)
        df = df.sort_index()
        has_dates = True
    except (ValueError, TypeError):
        df = df.set_index(first_col)
        has_dates = False

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    return df, has_dates

def parse_colors(color_arg, n_needed=1):
    default_palette = ["#003366", "#D97706", "#059669", "#7C3AED", "#B91C1C", 
                       "#0891B2", "#BE185D", "#4338CA", "#15803D", "#9333EA"]
    if not color_arg:
        return default_palette
    
    raw = color_arg.split(",")
    final = []
    for c in raw:
        c = c.strip()
        if c.lower() in ["red", "negative"]: final.append("#B91C1C")
        elif c.lower() in ["green", "positive"]: final.append("#059669")
        elif c.lower() in ["blue", "navy"]: final.append("#003366")
        elif c.lower() in ["orange", "gold"]: final.append("#D97706")
        elif c.lower() in ["purple"]: final.append("#7C3AED")
        elif c.lower() in ["teal", "cyan"]: final.append("#0891B2")
        elif c.lower() in ["pink", "magenta"]: final.append("#BE185D")
        else: final.append(c)
    
    while len(final) < n_needed:
        final.extend(default_palette)
    return final[:n_needed]

def _add_subtitle_legend(ax, labels, colors, ncol=None):
    """Clean top-right legend aligned with subtitle."""
    handles = [mpatches.Patch(color=c, label=l) for l, c in zip(labels, colors)]
    if ncol is None: ncol = min(len(labels), 4)
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=ncol, frameon=False, fontsize=10, 
              handletextpad=0.5, borderaxespad=0)

def _format_date_axis(ax, fmt):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=10))

def _add_reference_line(ax, ref_line):
    """Parse and add reference line from string like '50:Neutral' or just '50'."""
    if not ref_line:
        return
    parts = ref_line.split(":")
    value = float(parts[0])
    label = parts[1] if len(parts) > 1 else None
    ax.axhline(y=value, color="#666666", linewidth=1.2, linestyle="--", alpha=0.7, zorder=1)
    if label:
        ax.text(ax.get_xlim()[1], value, f" {label}", va="center", ha="left",
                fontsize=8, color="#666666")


# ═══════════════════════════════════════════════
# EXISTING CHART BUILDERS (UNCHANGED)
# ═══════════════════════════════════════════════

def make_line_chart(df, title, subtitle=None, source="The Economics Hub", 
                   colors=None, height=None, date_fmt="%b '%y", normalize=False, 
                   ref_line=None, **kwargs):
    
    if normalize:
        # Normalize to 100 at the start (base 100)
        df = df / df.iloc[0] * 100
        if not subtitle: subtitle = "Rebased to 100 at start"
    
    fig, ax = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    palette = parse_colors(colors, len(df.columns))
    
    for i, col in enumerate(df.columns):
        c = palette[i]
        vals = df[col].dropna()
        if vals.empty: continue
        
        # Aesthetic: Thick transparent line + Thin solid line
        ax.plot(vals.index, vals, color=c, linewidth=3, alpha=0.15, zorder=2)
        ax.plot(vals.index, vals, color=c, linewidth=2, label=col, zorder=3)
        
        # End label
        last_val = vals.iloc[-1]
        ax.annotate(f" {last_val:.1f}", xy=(vals.index[-1], last_val),
                    xytext=(3, 0), textcoords="offset points",
                    color=c, fontsize=9, fontweight="bold", va="center")

    _format_date_axis(ax, date_fmt)
    _add_reference_line(ax, ref_line)
    
    if len(df.columns) > 1:
        _add_subtitle_legend(ax, df.columns, palette)
        
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_vertical_bar_chart(df, title, subtitle=None, source="The Economics Hub", 
                            colors=None, height=None, date_fmt="%b '%y", ref_line=None, **kwargs):
    """
    Vertical grouped bars. Calculates width dynamically.
    """
    fig, ax = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    palette = parse_colors(colors, len(df.columns))
    
    # 1. Determine safe bar width based on data frequency
    if len(df) > 1:
        min_delta = pd.Series(df.index).diff().min().days
        if pd.isna(min_delta) or min_delta == 0: min_delta = 30 # Default to monthly
    else:
        min_delta = 30

    # Use 80% of the available space
    total_group_width = min_delta * 0.8
    n_series = len(df.columns)
    bar_width = total_group_width / n_series
    
    # 2. Plotting
    for i, col in enumerate(df.columns):
        # Calculate offset in DAYS
        offset_days = (i - n_series/2 + 0.5) * bar_width
        
        # We must shift the Dates themselves by this TimeDelta
        shifted_dates = df.index + pd.Timedelta(days=offset_days)
        
        ax.bar(shifted_dates, df[col], width=bar_width, 
               color=palette[i], label=col, zorder=3, edgecolor="none")
        
    ax.axhline(0, color="black", linewidth=1, zorder=2)
    _format_date_axis(ax, date_fmt)
    _add_reference_line(ax, ref_line)
    _add_subtitle_legend(ax, df.columns, palette)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_horizontal_bar_chart(df, title, subtitle=None, source="The Economics Hub", 
                             colors=None, height=None, **kwargs):
    """Category bar chart (Horizontal)."""
    col = df.columns[0]
    vals = df[col].fillna(0)
    cats = df.index.astype(str)
    
    h = float(height) if height else max(3, 0.4 * len(cats) + 1.5)
    fig, ax = EconStyle.create_figure(size=(8, h))
    
    bar_colors = parse_colors(colors, len(vals)) if colors else ["#003366"] * len(vals)
    
    y_pos = np.arange(len(cats))
    ax.barh(y_pos, vals, color=bar_colors, height=0.6, zorder=3)
    
    for i, v in enumerate(vals):
        label = f"{v:,.1f}"
        ax.text(v, i, f"  {label}", va="center", ha="left" if v>0 else "right", 
                fontsize=9, fontweight="bold", color="#333333")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats)
    ax.invert_yaxis()
    ax.axvline(0, color="black", linewidth=0.8)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_dual_axis_chart(df, title, subtitle=None, source="The Economics Hub", 
                        colors=None, height=None, date_fmt="%b '%y", **kwargs):
    if len(df.columns) < 2: return make_line_chart(df, title, subtitle, **kwargs)
    
    fig, ax1 = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    ax2 = ax1.twinx()
    
    palette = parse_colors(colors, 2)
    c1, c2 = palette[0], palette[1]
    
    # Left Axis
    s1 = df.iloc[:, 0].dropna()
    ax1.plot(s1.index, s1, color=c1, linewidth=2.5, zorder=3)
    ax1.set_ylabel(df.columns[0], color=c1, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor=c1)
    
    # Right Axis
    s2 = df.iloc[:, 1].dropna()
    ax2.plot(s2.index, s2, color=c2, linewidth=2, linestyle="--", zorder=3)
    ax2.set_ylabel(df.columns[1], color=c2, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor=c2)
    
    # Legend
    handles = [plt.Line2D([],[], color=c1, lw=2.5, label=df.columns[0]),
               plt.Line2D([],[], color=c2, lw=2, ls="--", label=df.columns[1])]
    ax1.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.02),
               ncol=2, frameon=False)
    
    _format_date_axis(ax1, date_fmt)
    EconStyle.set_title(ax1, title, subtitle)
    EconStyle.add_top_rule(ax1)
    EconStyle.finalize(fig, ax1, source=source)
    return fig


def make_scatter_chart(df, title, subtitle=None, source="The Economics Hub", 
                      colors=None, height=None, **kwargs):
    if len(df.columns) < 2: raise ValueError("Scatter needs 2 columns")
    
    fig, ax = EconStyle.create_figure(size=(7, 6))
    c = parse_colors(colors, 1)[0]
    
    # Scatter plot
    ax.scatter(df.iloc[:,0], df.iloc[:,1], color=c, s=80, alpha=0.7, 
               edgecolors="white", linewidth=0.5, zorder=3)
    
    ax.set_xlabel(df.columns[0], fontsize=9, fontweight='bold')
    ax.set_ylabel(df.columns[1], fontsize=9, fontweight='bold')
    ax.grid(True, linestyle=":", alpha=0.6)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_flows_chart(df, title, subtitle=None, source="The Economics Hub", 
                    colors=None, height=None, date_fmt="%b '%y", **kwargs):
    """Green/Red bars for net flows."""
    fig, ax = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    
    vals = df.iloc[:, 0]
    dates = vals.index
    
    # Calculate width similar to vertical bar logic
    if len(df) > 1:
        min_delta = pd.Series(dates).diff().min().days or 30
    else: min_delta = 30
    bar_width = min_delta * 0.7 # 70% width
    
    c_pos, c_neg = "#059669", "#B91C1C"
    bar_colors = [c_pos if v >= 0 else c_neg for v in vals]
    
    ax.bar(dates, vals, width=bar_width, color=bar_colors, edgecolor="none", zorder=3)
    ax.axhline(0, color="black", linewidth=0.8)
    
    # Cumulative Tag
    cum_val = vals.sum()
    c_cum = c_pos if cum_val >= 0 else c_neg
    ax.text(0.98, 0.95, f"Cumulative: {cum_val:+,.1f}", transform=ax.transAxes,
            ha="right", va="top", color=c_cum, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=c_cum))
    
    _format_date_axis(ax, date_fmt)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_area_chart(df, title, subtitle=None, source="The Economics Hub", 
                   colors=None, height=None, date_fmt="%b '%y", **kwargs):
    fig, ax = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    palette = parse_colors(colors, len(df.columns))
    
    ax.stackplot(df.index, df.T, labels=df.columns, colors=palette, alpha=0.9)
    
    _format_date_axis(ax, date_fmt)
    _add_subtitle_legend(ax, df.columns, palette)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_combo_chart(df, title, subtitle=None, source="The Economics Hub", 
                    colors=None, height=None, date_fmt="%b '%y", **kwargs):
    """Col 1 = Bar, Col 2 = Line (Dual Axis)."""
    fig, ax1 = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    ax2 = ax1.twinx()
    
    palette = parse_colors(colors, 2)
    c_bar, c_line = palette[0], palette[1]
    
    # Calculate bar width
    min_delta = pd.Series(df.index).diff().min().days or 30
    bar_width = min_delta * 0.7
    
    # Bar (Left)
    ax1.bar(df.index, df.iloc[:,0], color=c_bar, alpha=0.4, width=bar_width, label=df.columns[0])
    ax1.tick_params(axis='y', labelcolor=c_bar)
    
    # Line (Right)
    ax2.plot(df.index, df.iloc[:,1], color=c_line, linewidth=2.5, label=df.columns[1])
    ax2.tick_params(axis='y', labelcolor=c_line)
    
    # Combined Legend
    handles = [mpatches.Patch(color=c_bar, alpha=0.4, label=df.columns[0]),
               plt.Line2D([], [], color=c_line, linewidth=2.5, label=df.columns[1])]
    
    ax1.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.02),
               ncol=2, frameon=False)

    _format_date_axis(ax1, date_fmt)
    EconStyle.set_title(ax1, title, subtitle)
    EconStyle.add_top_rule(ax1)
    EconStyle.finalize(fig, ax1, source=source)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# NEW CHART BUILDERS (v4.0)
# ═══════════════════════════════════════════════════════════════════════════════

def make_waterfall_chart(df, title, subtitle=None, source="The Economics Hub",
                        colors=None, height=None, **kwargs):
    """
    Waterfall chart for showing cumulative effect of sequential values.
    CSV format: Category | Value (positive = increase, negative = decrease)
    Last row can be "Total" which will be calculated automatically.
    """
    col = df.columns[0]
    cats = df.index.astype(str).tolist()
    vals = df[col].fillna(0).tolist()
    
    # Check if last is a total row
    has_total = cats[-1].lower() in ['total', 'net', 'sum', 'final']
    if has_total:
        cats = cats[:-1]
        vals = vals[:-1]
    
    # Calculate positions
    n = len(vals)
    cumulative = np.zeros(n + 1)
    for i, v in enumerate(vals):
        cumulative[i + 1] = cumulative[i] + v
    
    h = float(height) if height else max(4, 0.5 * n + 2)
    fig, ax = EconStyle.create_figure(size=(9, h))
    
    c_pos, c_neg, c_total = "#059669", "#B91C1C", "#003366"
    
    # Draw bars
    for i, (cat, val) in enumerate(zip(cats, vals)):
        bottom = min(cumulative[i], cumulative[i+1])
        height_bar = abs(val)
        color = c_pos if val >= 0 else c_neg
        
        ax.bar(i, height_bar, bottom=bottom, color=color, width=0.6, 
               edgecolor='white', linewidth=1, zorder=3)
        
        # Value label
        label_y = cumulative[i+1] + (0.02 * max(cumulative) * (1 if val >= 0 else -1))
        ax.text(i, label_y, f"{val:+,.0f}", ha='center', va='bottom' if val >= 0 else 'top',
                fontsize=9, fontweight='bold', color=color)
    
    # Add total bar
    if has_total or True:
        total = cumulative[-1]
        ax.bar(n, abs(total), bottom=min(0, total), color=c_total, width=0.6,
               edgecolor='white', linewidth=1, zorder=3)
        ax.text(n, total + (0.02 * max(abs(cumulative))), f"{total:,.0f}", 
                ha='center', va='bottom', fontsize=10, fontweight='bold', color=c_total)
        cats.append("Total")
    
    # Connector lines
    for i in range(n):
        ax.plot([i + 0.3, i + 0.7], [cumulative[i+1], cumulative[i+1]], 
                color='#666666', linewidth=1, linestyle=':', zorder=2)
    
    ax.axhline(0, color='black', linewidth=0.8, zorder=1)
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, rotation=45, ha='right', fontsize=9)
    ax.set_ylabel('Value', fontsize=9)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_slope_chart(df, title, subtitle=None, source="The Economics Hub",
                    colors=None, height=None, **kwargs):
    """
    Slope chart (slopegraph) — compare two time points.
    CSV format: Category | Period1 | Period2
    Great for: before/after, year-over-year comparisons
    """
    if len(df.columns) < 2:
        raise ValueError("Slope chart needs at least 2 columns (periods)")
    
    cats = df.index.astype(str).tolist()
    period1, period2 = df.columns[0], df.columns[1]
    vals1, vals2 = df.iloc[:, 0].values, df.iloc[:, 1].values
    
    h = float(height) if height else max(5, 0.4 * len(cats) + 2)
    fig, ax = EconStyle.create_figure(size=(8, h))
    
    palette = parse_colors(colors, len(cats))
    
    # Draw slopes
    for i, (cat, v1, v2) in enumerate(zip(cats, vals1, vals2)):
        color = palette[i]
        # Determine if increase or decrease
        is_increase = v2 >= v1
        alpha = 0.9 if is_increase else 0.6
        
        # Line
        ax.plot([0, 1], [v1, v2], color=color, linewidth=2.5, alpha=alpha, zorder=3)
        
        # Dots
        ax.scatter([0], [v1], color=color, s=60, zorder=4)
        ax.scatter([1], [v2], color=color, s=60, zorder=4)
        
        # Labels
        ax.text(-0.05, v1, f"{cat}: {v1:.1f}", ha='right', va='center', 
                fontsize=9, color=color, fontweight='bold')
        ax.text(1.05, v2, f"{v2:.1f}", ha='left', va='center',
                fontsize=9, color=color, fontweight='bold')
    
    # Period labels
    ax.text(0, ax.get_ylim()[1] * 1.05, period1, ha='center', fontsize=11, fontweight='bold')
    ax.text(1, ax.get_ylim()[1] * 1.05, period2, ha='center', fontsize=11, fontweight='bold')
    
    ax.set_xlim(-0.3, 1.3)
    ax.set_xticks([])
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_yticks([])
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_lollipop_chart(df, title, subtitle=None, source="The Economics Hub",
                       colors=None, height=None, **kwargs):
    """
    Lollipop chart — clean alternative to bar charts.
    CSV format: Category | Value
    """
    col = df.columns[0]
    cats = df.index.astype(str).tolist()
    vals = df[col].fillna(0).values
    
    h = float(height) if height else max(4, 0.35 * len(cats) + 2)
    fig, ax = EconStyle.create_figure(size=(9, h))
    
    palette = parse_colors(colors, len(cats))
    y_pos = np.arange(len(cats))
    
    for i, (y, v) in enumerate(zip(y_pos, vals)):
        color = palette[i] if colors else ("#059669" if v >= 0 else "#B91C1C")
        # Stem
        ax.hlines(y, 0, v, color=color, linewidth=2, zorder=2)
        # Dot
        ax.scatter([v], [y], color=color, s=100, zorder=3, edgecolors='white', linewidth=1)
        # Label
        offset = 0.02 * max(abs(vals)) * (1 if v >= 0 else -1)
        ax.text(v + offset, y, f"{v:,.1f}", va='center', ha='left' if v >= 0 else 'right',
                fontsize=9, fontweight='bold', color=color)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color='black', linewidth=0.8, zorder=1)
    ax.set_xlim(min(0, min(vals) * 1.2), max(0, max(vals) * 1.2))
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_diverging_bar_chart(df, title, subtitle=None, source="The Economics Hub",
                            colors=None, height=None, **kwargs):
    """
    Diverging horizontal bars — great for sentiment, positive vs negative.
    CSV format: Category | Value (positive/negative)
    """
    col = df.columns[0]
    cats = df.index.astype(str).tolist()
    vals = df[col].fillna(0).values
    
    h = float(height) if height else max(4, 0.4 * len(cats) + 2)
    fig, ax = EconStyle.create_figure(size=(9, h))
    
    c_pos, c_neg = "#059669", "#B91C1C"
    bar_colors = [c_pos if v >= 0 else c_neg for v in vals]
    
    y_pos = np.arange(len(cats))
    ax.barh(y_pos, vals, color=bar_colors, height=0.6, edgecolor='white', linewidth=0.5, zorder=3)
    
    # Value labels
    for i, v in enumerate(vals):
        offset = 0.01 * max(abs(vals)) * (1 if v >= 0 else -1)
        ax.text(v + offset, i, f"{v:+,.1f}", va='center', 
                ha='left' if v >= 0 else 'right',
                fontsize=9, fontweight='bold', color=bar_colors[i])
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color='black', linewidth=1.2, zorder=2)
    
    # Symmetric x-axis
    max_val = max(abs(vals)) * 1.2
    ax.set_xlim(-max_val, max_val)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_dumbbell_chart(df, title, subtitle=None, source="The Economics Hub",
                       colors=None, height=None, **kwargs):
    """
    Dumbbell chart — compare two values per category.
    CSV format: Category | Value1 | Value2
    Great for: Forecast vs Actual, Before vs After
    """
    if len(df.columns) < 2:
        raise ValueError("Dumbbell chart needs 2 columns")
    
    cats = df.index.astype(str).tolist()
    vals1, vals2 = df.iloc[:, 0].values, df.iloc[:, 1].values
    label1, label2 = df.columns[0], df.columns[1]
    
    h = float(height) if height else max(4, 0.4 * len(cats) + 2)
    fig, ax = EconStyle.create_figure(size=(9, h))
    
    palette = parse_colors(colors, 2)
    c1, c2 = palette[0], palette[1]
    
    y_pos = np.arange(len(cats))
    
    for i, (y, v1, v2) in enumerate(zip(y_pos, vals1, vals2)):
        # Connecting line
        ax.plot([v1, v2], [y, y], color='#9CA3AF', linewidth=2, zorder=2)
        # Dots
        ax.scatter([v1], [y], color=c1, s=100, zorder=3, edgecolors='white', linewidth=1)
        ax.scatter([v2], [y], color=c2, s=100, zorder=3, edgecolors='white', linewidth=1)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats, fontsize=9)
    ax.invert_yaxis()
    
    # Legend
    handles = [plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=c1, 
                          markersize=10, label=label1),
               plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=c2,
                          markersize=10, label=label2)]
    ax.legend(handles=handles, loc='lower right', bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_step_chart(df, title, subtitle=None, source="The Economics Hub",
                   colors=None, height=None, date_fmt="%b '%y", ref_line=None, **kwargs):
    """
    Step chart — great for policy rates, discrete changes.
    CSV format: Date | Value
    """
    fig, ax = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    palette = parse_colors(colors, len(df.columns))
    
    for i, col in enumerate(df.columns):
        c = palette[i]
        vals = df[col].dropna()
        if vals.empty: continue
        
        # Step plot
        ax.step(vals.index, vals, where='post', color=c, linewidth=2.5, 
                label=col, zorder=3)
        # Fill under
        ax.fill_between(vals.index, vals, step='post', color=c, alpha=0.1, zorder=2)
        
        # End label
        last_val = vals.iloc[-1]
        ax.annotate(f" {last_val:.2f}", xy=(vals.index[-1], last_val),
                    xytext=(5, 0), textcoords="offset points",
                    color=c, fontsize=10, fontweight="bold", va="center")
    
    _format_date_axis(ax, date_fmt)
    _add_reference_line(ax, ref_line)
    
    if len(df.columns) > 1:
        _add_subtitle_legend(ax, df.columns, palette)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_band_chart(df, title, subtitle=None, source="The Economics Hub",
                   colors=None, height=None, date_fmt="%b '%y", **kwargs):
    """
    Line with confidence band — great for forecasts, ranges.
    CSV format: Date | Central | Lower | Upper
    OR: Date | Value | Range (symmetric +/-)
    """
    fig, ax = EconStyle.create_figure(size=(9.5, float(height) if height else 5))
    c = parse_colors(colors, 1)[0]
    
    if len(df.columns) >= 3:
        # Explicit lower/upper bounds
        central = df.iloc[:, 0]
        lower = df.iloc[:, 1]
        upper = df.iloc[:, 2]
    elif len(df.columns) == 2:
        # Value + symmetric range
        central = df.iloc[:, 0]
        range_val = df.iloc[:, 1]
        lower = central - range_val
        upper = central + range_val
    else:
        raise ValueError("Band chart needs 2-3 columns: Central, [Lower, Upper] or [Range]")
    
    # Band fill
    ax.fill_between(df.index, lower, upper, color=c, alpha=0.2, zorder=2, label='Range')
    # Central line
    ax.plot(df.index, central, color=c, linewidth=2.5, zorder=3, label=df.columns[0])
    
    # End labels
    last_idx = df.index[-1]
    ax.annotate(f" {central.iloc[-1]:.1f}", xy=(last_idx, central.iloc[-1]),
                xytext=(5, 0), textcoords="offset points",
                color=c, fontsize=9, fontweight="bold", va="center")
    
    _format_date_axis(ax, date_fmt)
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_target_bar_chart(df, title, subtitle=None, source="The Economics Hub",
                         colors=None, height=None, **kwargs):
    """
    Horizontal bars with target markers.
    CSV format: Category | Actual | Target
    """
    if len(df.columns) < 2:
        raise ValueError("Target chart needs 2 columns: Actual, Target")
    
    cats = df.index.astype(str).tolist()
    actual = df.iloc[:, 0].values
    target = df.iloc[:, 1].values
    
    h = float(height) if height else max(4, 0.45 * len(cats) + 2)
    fig, ax = EconStyle.create_figure(size=(9, h))
    
    c_bar, c_target = "#003366", "#B91C1C"
    y_pos = np.arange(len(cats))
    
    # Bars for actual
    ax.barh(y_pos, actual, height=0.5, color=c_bar, alpha=0.8, zorder=3, label='Actual')
    
    # Target markers
    for i, (y, t) in enumerate(zip(y_pos, target)):
        ax.plot([t, t], [y - 0.35, y + 0.35], color=c_target, linewidth=3, zorder=4)
    
    # Value labels
    for i, (a, t) in enumerate(zip(actual, target)):
        pct = (a / t * 100) if t != 0 else 0
        color = "#059669" if a >= t else "#B91C1C"
        ax.text(max(a, t) + 0.02 * max(target), i, f"{pct:.0f}%", 
                va='center', fontsize=9, fontweight='bold', color=color)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats, fontsize=9)
    ax.invert_yaxis()
    
    # Legend
    handles = [mpatches.Patch(color=c_bar, alpha=0.8, label='Actual'),
               plt.Line2D([0], [0], color=c_target, linewidth=3, label='Target')]
    ax.legend(handles=handles, loc='lower right', bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_donut_chart(df, title, subtitle=None, source="The Economics Hub",
                    colors=None, height=None, **kwargs):
    """
    Donut chart for composition/market share.
    CSV format: Category | Value
    """
    col = df.columns[0]
    cats = df.index.astype(str).tolist()
    vals = df[col].fillna(0).values
    
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_facecolor('#FFFFFF')
    fig.patch.set_facecolor('#FFFFFF')
    
    palette = parse_colors(colors, len(cats))
    
    # Donut
    wedges, texts, autotexts = ax.pie(
        vals, labels=None, colors=palette, autopct='%1.1f%%',
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.5, edgecolor='white', linewidth=2)
    )
    
    # Style percentage labels
    for autotext in autotexts:
        autotext.set_fontsize(9)
        autotext.set_fontweight('bold')
    
    # Legend
    ax.legend(wedges, cats, loc='center left', bbox_to_anchor=(1, 0.5),
              frameon=False, fontsize=10)
    
    # Center text (total)
    total = sum(vals)
    ax.text(0, 0, f"Total\n{total:,.0f}", ha='center', va='center',
            fontsize=12, fontweight='bold')
    
    ax.set_title(title, loc='left', fontsize=14, fontweight='bold', pad=20)
    if subtitle:
        ax.text(0, 1.1, subtitle, transform=ax.transAxes, fontsize=10, color='#666666')
    
    fig.text(0.02, 0.02, f"Source: {source}", fontsize=8, color='#666666')
    fig.text(0.98, 0.02, "The Economics Hub", fontsize=10, fontweight='bold', 
             color='#1A1A1A', ha='right')
    
    plt.tight_layout()
    return fig


def make_heatmap_chart(df, title, subtitle=None, source="The Economics Hub",
                      colors=None, height=None, **kwargs):
    """
    Heatmap for correlations, matrices.
    CSV format: Row labels as index, column labels as headers, values in cells
    """
    h = float(height) if height else max(5, 0.5 * len(df) + 2)
    fig, ax = plt.subplots(figsize=(9, h))
    ax.set_facecolor('#FFFFFF')
    fig.patch.set_facecolor('#FFFFFF')
    
    # Custom colormap: red (negative) -> white (zero) -> blue (positive)
    cmap = LinearSegmentedColormap.from_list('custom', ['#B91C1C', '#FFFFFF', '#003366'])
    
    # Create heatmap
    data = df.values
    im = ax.imshow(data, cmap=cmap, aspect='auto', vmin=-1, vmax=1)
    
    # Labels
    ax.set_xticks(np.arange(len(df.columns)))
    ax.set_yticks(np.arange(len(df.index)))
    ax.set_xticklabels(df.columns, fontsize=9, rotation=45, ha='right')
    ax.set_yticklabels(df.index.astype(str), fontsize=9)
    
    # Cell values
    for i in range(len(df.index)):
        for j in range(len(df.columns)):
            val = data[i, j]
            color = 'white' if abs(val) > 0.5 else 'black'
            ax.text(j, i, f"{val:.2f}", ha='center', va='center',
                   fontsize=8, color=color, fontweight='bold')
    
    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.tick_params(labelsize=8)
    
    ax.set_title(title, loc='left', fontsize=14, fontweight='bold', pad=15)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=10, color='#666666')
    
    fig.text(0.02, 0.02, f"Source: {source}", fontsize=8, color='#666666')
    fig.text(0.98, 0.02, "The Economics Hub", fontsize=10, fontweight='bold',
             color='#1A1A1A', ha='right')
    
    plt.tight_layout()
    return fig


def make_bullet_chart(df, title, subtitle=None, source="The Economics Hub",
                     colors=None, height=None, **kwargs):
    """
    Bullet chart — progress against target with ranges.
    CSV format: Metric | Actual | Target | [Good] | [Excellent]
    """
    cats = df.index.astype(str).tolist()
    actual = df.iloc[:, 0].values
    target = df.iloc[:, 1].values if len(df.columns) > 1 else actual
    
    # Optional ranges
    good = df.iloc[:, 2].values if len(df.columns) > 2 else target * 0.8
    excellent = df.iloc[:, 3].values if len(df.columns) > 3 else target
    
    h = float(height) if height else max(3, 0.6 * len(cats) + 1.5)
    fig, ax = EconStyle.create_figure(size=(9, h))
    
    y_pos = np.arange(len(cats))
    bar_height = 0.5
    
    for i, (y, a, t, g, e) in enumerate(zip(y_pos, actual, target, good, excellent)):
        max_val = max(a, t, e) * 1.1
        
        # Background ranges
        ax.barh(y, max_val, height=bar_height, color='#E5E7EB', zorder=1)
        ax.barh(y, e, height=bar_height, color='#D1D5DB', zorder=2)
        ax.barh(y, g, height=bar_height, color='#9CA3AF', zorder=3)
        
        # Actual bar
        ax.barh(y, a, height=bar_height * 0.4, color='#003366', zorder=4)
        
        # Target marker
        ax.plot([t, t], [y - bar_height/2, y + bar_height/2], 
                color='#B91C1C', linewidth=3, zorder=5)
        
        # Value label
        ax.text(a + 0.02 * max_val, y, f"{a:,.0f}", va='center', fontsize=9, fontweight='bold')
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, None)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_range_chart(df, title, subtitle=None, source="The Economics Hub",
                    colors=None, height=None, **kwargs):
    """
    Range chart showing min-max with midpoint.
    CSV format: Category | Min | Max | [Actual/Mid]
    """
    if len(df.columns) < 2:
        raise ValueError("Range chart needs at least Min and Max columns")
    
    cats = df.index.astype(str).tolist()
    min_vals = df.iloc[:, 0].values
    max_vals = df.iloc[:, 1].values
    mid_vals = df.iloc[:, 2].values if len(df.columns) > 2 else (min_vals + max_vals) / 2
    
    h = float(height) if height else max(4, 0.4 * len(cats) + 2)
    fig, ax = EconStyle.create_figure(size=(9, h))
    
    c_range, c_mid = "#003366", "#D97706"
    y_pos = np.arange(len(cats))
    
    for i, (y, mn, mx, mid) in enumerate(zip(y_pos, min_vals, max_vals, mid_vals)):
        # Range bar
        ax.plot([mn, mx], [y, y], color=c_range, linewidth=8, solid_capstyle='round',
                alpha=0.3, zorder=2)
        # End caps
        ax.scatter([mn, mx], [y, y], color=c_range, s=50, zorder=3)
        # Midpoint
        ax.scatter([mid], [y], color=c_mid, s=100, zorder=4, edgecolors='white', linewidth=1.5)
        
        # Labels
        ax.text(mn - 0.02 * (max(max_vals) - min(min_vals)), y, f"{mn:.1f}", 
                va='center', ha='right', fontsize=8, color=c_range)
        ax.text(mx + 0.02 * (max(max_vals) - min(min_vals)), y, f"{mx:.1f}",
                va='center', ha='left', fontsize=8, color=c_range)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats, fontsize=10)
    ax.invert_yaxis()
    
    # Legend
    handles = [plt.Line2D([0], [0], color=c_range, linewidth=6, alpha=0.3, label='Range'),
               plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=c_mid,
                          markersize=10, label=df.columns[2] if len(df.columns) > 2 else 'Mid')]
    ax.legend(handles=handles, loc='lower right', bbox_to_anchor=(1.0, 1.02),
              ncol=2, frameon=False, fontsize=9)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


def make_event_chart(df, title, subtitle=None, source="The Economics Hub",
                    colors=None, height=None, date_fmt="%b '%y", events=None, **kwargs):
    """
    Line chart with event annotations.
    Use --events "2024-03-15:Rate Cut,2024-06-01:Election" to add markers
    """
    fig, ax = EconStyle.create_figure(size=(9.5, float(height) if height else 5.5))
    palette = parse_colors(colors, len(df.columns))
    
    for i, col in enumerate(df.columns):
        c = palette[i]
        vals = df[col].dropna()
        if vals.empty: continue
        
        ax.plot(vals.index, vals, color=c, linewidth=2.5, label=col, zorder=3)
        ax.plot(vals.index, vals, color=c, linewidth=4, alpha=0.15, zorder=2)
    
    # Parse and add events
    if events:
        y_range = ax.get_ylim()[1] - ax.get_ylim()[0]
        for event_str in events.split(','):
            parts = event_str.strip().split(':')
            if len(parts) == 2:
                event_date = pd.to_datetime(parts[0])
                event_label = parts[1]
                
                # Vertical line
                ax.axvline(event_date, color='#666666', linewidth=1, linestyle='--', 
                          alpha=0.7, zorder=1)
                
                # Label with rotation
                ax.annotate(event_label, xy=(event_date, ax.get_ylim()[1]),
                           xytext=(0, 5), textcoords='offset points',
                           fontsize=8, color='#666666', rotation=90, va='bottom', ha='center',
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                                    edgecolor='#CCCCCC', alpha=0.9))
    
    _format_date_axis(ax, date_fmt)
    
    if len(df.columns) > 1:
        _add_subtitle_legend(ax, df.columns, palette)
    
    EconStyle.set_title(ax, title, subtitle)
    EconStyle.add_top_rule(ax)
    EconStyle.finalize(fig, ax, source=source)
    return fig


# ═══════════════════════════════════════════════
# DISPATCHER
# ═══════════════════════════════════════════════

CHART_MAP = {
    # Original charts (unchanged)
    "line": make_line_chart,
    "bar": make_vertical_bar_chart,
    "barh": make_horizontal_bar_chart,
    "flows": make_flows_chart,
    "area": make_area_chart,
    "combo": make_combo_chart,
    "dual": make_dual_axis_chart,
    "comparison": lambda df, **kwargs: make_line_chart(df, **dict(kwargs, normalize=True)),
    "scatter": make_scatter_chart,
    
    # New charts (v4.0)
    "waterfall": make_waterfall_chart,
    "slope": make_slope_chart,
    "lollipop": make_lollipop_chart,
    "diverging": make_diverging_bar_chart,
    "dumbbell": make_dumbbell_chart,
    "step": make_step_chart,
    "band": make_band_chart,
    "target": make_target_bar_chart,
    "donut": make_donut_chart,
    "heatmap": make_heatmap_chart,
    "bullet": make_bullet_chart,
    "range": make_range_chart,
    "event": make_event_chart,
}

def main():
    parser = argparse.ArgumentParser(description="Economics Hub Custom Chart Generator v4.0", 
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("file", help="Path to Excel/CSV data file")
    parser.add_argument("--type", choices=list(CHART_MAP.keys()), help="Chart type override")
    parser.add_argument("--title", required=True, help="Main chart title")
    parser.add_argument("--subtitle", help="Chart subtitle")
    parser.add_argument("--source", default="The Economics Hub", help="Data source attribution")
    parser.add_argument("--colors", help="Comma-separated colors (e.g. '#003366,#FF9933')")
    parser.add_argument("--height", help="Chart height in inches")
    parser.add_argument("--date-fmt", default="%b '%y", help="Date format for x-axis")
    parser.add_argument("--normalize", action="store_true", help="Index all series to 100")
    parser.add_argument("--ref-line", help="Reference line (e.g., '50:Neutral' or just '50')")
    parser.add_argument("--events", help="Event markers for event chart (e.g., '2024-03-15:Rate Cut')")
    parser.add_argument("--output", help="Custom output filename")
    parser.add_argument("--preview", action="store_true", help="Lower DPI for quick preview")
    
    args = parser.parse_args()
    
    print(f"📊 Loading: {args.file}")
    df, has_dates = load_data(args.file)
    
    # Auto-detect type
    chart_type = args.type
    if not chart_type:
        if not has_dates:
            chart_type = "barh"
        elif len(df.columns) == 1:
            chart_type = "line"
        else:
            chart_type = "line"
            
    print(f"🎨 Generating {chart_type.upper()} chart...")
    builder = CHART_MAP.get(chart_type, make_line_chart)
    
    # Pass arguments (kwargs)
    fig = builder(
        df, 
        title=args.title, 
        subtitle=args.subtitle, 
        source=args.source, 
        colors=args.colors, 
        height=args.height,
        date_fmt=args.date_fmt,
        normalize=args.normalize,
        ref_line=args.ref_line,
        events=args.events
    )
    
    # Save
    out_dir = PROJECT_ROOT / "output" / "custom"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if args.output:
        out_path = out_dir / args.output
    else:
        safe_title = args.title.lower().replace(" ", "_").replace("/", "-")[:50]
        out_path = out_dir / f"{safe_title}.png"
    
    dpi = 150 if args.preview else 300
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor='white')
    print(f"✅ Saved to: {out_path}")

if __name__ == "__main__":
    main()
