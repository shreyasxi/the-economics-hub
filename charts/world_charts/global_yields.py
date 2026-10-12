"""Export and native dashboard panels for the same audited yield observations."""
from pathlib import Path
import altair as alt
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import pandas as pd
from charts.style import EconStyle

BLUE = "#1F5596"
RED = "#B91C1C"


def panel_rows(country):
    """One chronological series: national observations replace overlapping monthly backfill."""
    weeks = country["weekly"]
    native_months = {r["date"][:7] for r in weeks}
    observations = [(r, "monthly") for r in country["monthly"] if r["date"][:7] not in native_months]
    observations += [(r, "weekly") for r in weeks]
    rows, previous, segment = [], None, 0
    for row, field in sorted(observations, key=lambda item: item[0]["date"]):
        day = pd.Timestamp(row["date"])
        if previous is not None:
            prev_day, prev_field = previous
            gap = ((day.to_period("M") - prev_day.to_period("M")).n > 1
                   if field == "monthly" or prev_field == "monthly" else (day - prev_day).days > 10)
            if gap:
                segment += 1
        rows.append({"date": row["date"], "yield": row["value"],
                     "source": "OECD" if field == "monthly" else "National source",
                     "observation": day.strftime("%b %Y" if field == "monthly" else "%d %b %Y"),
                     "segment": str(segment),
                     "definition": country["monthly_note"] if field == "monthly" else country["national"]["yield_type"]})
        previous = day, field
    return rows


def history_percentile(country):
    """Equal month weights prevent dense recent weekly observations dominating history."""
    months = {r["date"][:7]: r["yield"] for r in panel_rows(country)}
    if len(months) < 12:
        return None
    value = country["latest"]["value"]
    values = list(months.values())
    return 100 * (sum(v < value for v in values) + .5 * sum(v == value for v in values)) / len(values)


def ytd_change(country, as_of):
    """Yield move in basis points from the last available prior-year observation."""
    year = pd.Timestamp(as_of).year
    if pd.Timestamp(country["latest"]["date"]).year != year:
        return None
    baseline = [r for r in panel_rows(country) if pd.Timestamp(r["date"]).year < year]
    if not baseline:
        return None
    return 100 * (country["latest"]["value"] - baseline[-1]["yield"])


def panel(country, start_date, end_date):
    base = alt.Chart(alt.Data(values=panel_rows(country))).encode(
        x=alt.X("date:T", title=None, scale=alt.Scale(domain=[start_date, end_date]),
                axis=alt.Axis(format="%Y", tickCount=4, grid=False, labelAngle=0)),
        y=alt.Y("yield:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(format="~g", tickCount=4)),
        detail="segment:N",
        tooltip=[alt.Tooltip("observation:N", title="Observation"),
                 alt.Tooltip("yield:Q", title="Yield (%)", format=".3f"),
                 alt.Tooltip("source:N", title="Source"), alt.Tooltip("definition:N", title="Definition")],
    )
    return (base.mark_line(strokeWidth=3.8, color=RED) + base.mark_circle(size=25, color=RED)).properties(
        height=180).configure_view(stroke=None).configure_axis(
        domain=False, ticks=False, labelFont="Inter", labelFontSize=11,
        labelColor="#4B5563", gridColor="#E4E7EB")


def select_countries(report, region="All regions", sort="Highest yield"):
    countries = [c for c in report["countries"] if region == "All regions" or c["region"] == region]
    if sort == "Highest yield":
        return sorted(countries, key=lambda c: (-c["latest"]["value"], c["label"]))
    if sort == "Lowest yield":
        return sorted(countries, key=lambda c: (c["latest"]["value"], c["label"]))
    if sort == "Largest YTD rise (bp)":
        return sorted(countries, key=lambda c: (ytd_change(c, report["as_of"]) is None,
                      -(ytd_change(c, report["as_of"]) or 0), c["label"]))
    if sort == "Highest versus own history":
        return sorted(countries, key=lambda c: (history_percentile(c) is None,
                      -(history_percentile(c) or 0), c["label"]))
    return sorted(countries, key=lambda c: c["label"])


def draw(report, path):
    EconStyle.apply_global_style()
    fig, axes = plt.subplots(5, 4, figsize=(13, 13), squeeze=False)
    fig.subplots_adjust(left=.055, right=.97, bottom=.11, top=.84, hspace=1.12, wspace=.35)
    fig.text(.055, .974, "Bond Yields", fontsize=23, weight="bold", va="top")
    fig.text(.055, .932, "20 countries · nominal local-currency yields · latest available observations",
             fontsize=10, color=EconStyle.INK_MUTED)
    for ax, country in zip(axes.flat, select_countries(report)):
        latest = country["latest"]
        ax.text(0, 1.30, country["label"], transform=ax.transAxes, fontsize=10.3, weight="bold")
        ax.text(1, 1.30, f"{latest['value']:.2f}%", transform=ax.transAxes, ha="right", fontsize=12,
                color=BLUE, weight="bold")
        when = pd.Timestamp(latest["date"]).strftime("%d %b %Y" if country["latest_frequency"].startswith("National") else "%b %Y")
        ax.text(0, 1.10, when + (" · STALE" if country["stale"] and country["code"] != "IND" else ""), transform=ax.transAxes,
                fontsize=8, color=EconStyle.INK_MUTED)
        rows = panel_rows(country)
        for segment in dict.fromkeys(r["segment"] for r in rows):
            points = [r for r in rows if r["segment"] == segment]
            ax.plot(pd.to_datetime([r["date"] for r in points]), [r["yield"] for r in points],
                    color=RED, lw=2.8, marker="o", markersize=2.5)
        ax.set_xlim(pd.Timestamp(report["start_date"]), pd.Timestamp(report["as_of"]) + pd.Timedelta(days=20))
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.yaxis.set_major_locator(MaxNLocator(3))
        ax.tick_params(axis="both", labelsize=8, length=0)
        ax.grid(axis="y", color="#E4E7EB", lw=.6)
        ax.grid(axis="x", visible=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.text(.055, .06, "Each panel has its own scale. Latest available national observations take priority; OECD supplies history and fallback.",
             fontsize=8, color=EconStyle.INK_MUTED)
    fig.text(.055, .042, "Observation dates are retained. Source definitions can differ at joins; missing periods remain gaps.",
             fontsize=7.7, color=EconStyle.INK_MUTED)
    EconStyle.add_source(fig, "OECD · national central banks and treasuries", report["as_of"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight", facecolor=EconStyle.BACKGROUND)
    EconStyle.save_chart(fig, path)
