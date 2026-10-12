"""A large chart of monthly country inflation small multiples."""
import math
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, FuncFormatter
import pandas as pd

from charts.style import EconStyle


def draw(report, path):
    countries = report["countries"]
    columns = 4
    rows = math.ceil(len(countries) / columns)
    EconStyle.apply_global_style()
    # A narrower physical canvas makes type larger at the same browser width.
    # Vector output below prevents Streamlit's raster downsampling from
    # softening the many small labels when this chart is displayed or enlarged.
    height = 1.85 * rows + 3.2
    fig, axes = plt.subplots(rows, columns, figsize=(12, height), squeeze=False)
    fig.subplots_adjust(left=.055, right=.97, bottom=1.4 / height, top=1 - 2.35 / height,
                        hspace=1.0, wspace=.32)
    national = sum(not c["aggregate"] for c in countries)
    fig.text(.055, 1 - .3 / height, "Global Inflation Breadth", fontsize=23, weight="bold", va="top")
    fig.text(.055, 1 - .75 / height,
             f"Monthly inflation across {national} countries" + (" and the euro area" if any(c["aggregate"] for c in countries) else "")
             + "  ·  % year-on-year  ·  last three years", fontsize=10.5, va="top", color=EconStyle.INK_MUTED)
    b = report["breadth"]
    month = pd.Period(b["month"], freq="M").to_timestamp()
    fig.text(.055, 1 - 1.12 / height,
             f"{month:%b %Y}: {b['easing']} easing  ·  {b['rising']} rising  ·  {b['little_changed']} little changed"
             f"   |   {b['matched']}/{b['total_countries']} countries with a matched three-month comparison",
             fontsize=9.5, va="top")
    handles = [Line2D([0], [0], color=EconStyle.LINE_BLUE, lw=2, label="Headline CPI"),
               Line2D([0], [0], color=EconStyle.LINE_ORANGE, lw=1.7, ls="--", label="Excluding food & energy")]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(.97, 1 - 1.40 / height),
               frameon=False, ncol=2, fontsize=10)
    fig.add_artist(Line2D([.055, .97], [1 - 1.7 / height] * 2, transform=fig.transFigure,
                         color=EconStyle.RULE_HEAVY, lw=1.5))
    calendar = pd.period_range(report["start_month"], report["end_month"], freq="M").to_timestamp()
    for ax, country in zip(axes.flat, countries):
        headline = country["series"]["headline"]
        latest = headline[-1]
        ax.text(0, 1.32, country["label"], transform=ax.transAxes, fontsize=10.5, weight="bold", color=EconStyle.INK)
        ax.text(1, 1.32, f"{latest['value']:.1f}%", transform=ax.transAxes, ha="right", fontsize=12.5, weight="bold",
                color=EconStyle.LINE_BLUE)
        values = {r["month"]: r["value"] for r in headline}
        previous = str(pd.Period(latest["month"], freq="M") - 3)
        change = values[latest["month"]] - values[previous] if previous in values else None
        label = pd.Period(latest["month"], freq="M").to_timestamp().strftime("%b %Y")
        label += f"  ·  Δ3m {change:+.1f} pp" if change is not None else "  ·  Δ3m unavailable"
        ax.text(0, 1.12, label, transform=ax.transAxes, fontsize=8.2, color=EconStyle.INK_MUTED)
        for name, color, style in [("headline", EconStyle.LINE_BLUE, "-"), ("core", EconStyle.LINE_ORANGE, "--")]:
            records = country["series"][name]
            if not records:
                continue
            series = pd.Series({pd.Period(r["month"], freq="M").to_timestamp(): r["value"] for r in records})
            # Reindex to show breaks for missing months; never connect across gaps.
            ax.plot(calendar, series.reindex(calendar), color=color, lw=1.9 if name == "headline" else 1.5,
                    ls=style, solid_capstyle="round", dash_capstyle="round", zorder=3)
            ax.scatter(series.index[-1], series.iloc[-1], color=color, s=17, edgecolors="white", linewidths=.5, zorder=4)
        notes = []
        if not country["series"]["core"]:
            if country["core_note"]:
                notes.append("Core ends " + pd.Period(country["core_note"].split()[-1], freq="M").to_timestamp().strftime("%b %Y"))
            else:
                notes.append("Core not available")
        elif country["series"]["core"][-1]["month"] != latest["month"]:
            notes.append("Core through " + country["series"]["core"][-1]["month"])
        transition = country["transitions"].get("headline")
        if transition and report["start_month"] <= transition <= report["end_month"]:
            ax.axvline(pd.Period(transition, freq="M").to_timestamp(), color="#A0A0A0", lw=.8, ls=":")
            notes.append("Join " + pd.Period(transition, freq="M").to_timestamp().strftime("%b %Y"))
        if notes:
            ax.text(0, -.40, " · ".join(notes), transform=ax.transAxes, fontsize=6.9, color=EconStyle.INK_MUTED)
        ax.axhline(0, color="#A0A0A0", lw=.7, zorder=1)
        ax.set_xlim(calendar[0], calendar[-1] + pd.Timedelta(days=15))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=3, min_n_ticks=3))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.tick_params(axis="both", labelsize=8.2, length=0, pad=4)
        ax.grid(axis="y", color="#E4E7EB", lw=.6)
        ax.grid(axis="x", visible=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.margins(y=.15)
    for ax in list(axes.flat)[len(countries):]:
        ax.set_visible(False)
    fig.text(.055, 1.0 / height,
             "Each panel has its own vertical scale. Latest months differ. Gaps are missing observations; no interpolation.",
             fontsize=8, color=EconStyle.INK_MUTED)
    fig.text(.055, .78 / height,
             "National CPI baskets differ. Breadth excludes the euro-area aggregate; little changed = within ±0.05 pp over three months.",
             fontsize=7.5, color=EconStyle.INK_MUTED)
    EconStyle.add_source(fig, "OECD national CPI · COICOP 1999 / 2018", report["as_of"])
    # Embed glyph paths so bundled fonts survive browser rendering and zoom.
    svg_path = Path(path).with_suffix(".svg")
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({"svg.fonttype": "path"}):
        fig.savefig(svg_path, format="svg", bbox_inches="tight", pad_inches=.12,
                    facecolor=EconStyle.BACKGROUND)
    EconStyle.save_chart(fig, path)
