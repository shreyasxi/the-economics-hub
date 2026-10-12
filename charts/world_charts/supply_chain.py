"""EconHub ten-year export of the New York Fed's monthly GSCPI."""
import pandas as pd


def ten_year_series(report):
    rows = report["rows"]
    end = pd.Period(rows[-1]["month"], freq="M").to_timestamp()
    calendar = pd.date_range(end=end, periods=120, freq="MS")
    values = {pd.Period(r["month"], freq="M").to_timestamp(): r["value"] for r in rows}
    # Missing months remain NaN so the line breaks rather than bridging a gap.
    return pd.Series(values).reindex(calendar)


def draw(report, path):
    from charts.style import EconStyle
    import matplotlib.ticker as mticker

    series = ten_year_series(report)
    start, end = series.index[0], series.index[-1]
    blue, muted = EconStyle.LINE_BLUE, EconStyle.INK_MUTED
    fig, ax = EconStyle.create_figure(size="wide")
    ax.fill_between(series.index, series.values, 0, where=series.values > 0,
                    interpolate=True, color=EconStyle.LINE_MAROON, alpha=.10, zorder=1)
    ax.hlines(0, start, end, color=muted, linewidth=1.2, linestyles=(0, (4, 2.5)), zorder=2)
    ax.plot(series.index, series.values, color=blue, lw=2.5, zorder=3,
            solid_joinstyle="round", solid_capstyle="round")
    ax.scatter([end], [series.iloc[-1]], color=blue, s=58, edgecolors="white", linewidths=1.3, zorder=6)
    # Keep labels within the data area rather than reserving three empty years
    # to the right of a ten-year series.
    ax.text(.985, .965, f"{end:%b %Y}  {series.iloc[-1]:+.2f}", transform=ax.transAxes,
            ha="right", va="top", fontsize=10, weight="bold", color=blue)
    low, high = min(series.min(), 0), max(series.max(), 0)
    span = high - low or 1
    ax.set_ylim(low - span * .04, high + span * .07)
    ax.set_xlim(start - (end - start) * .008, end + (end - start) * .015)
    # Same restrained context labels as India's GFCF chart: muted ink,
    # no boxes/arrowheads, and thin stems stopping short of the observation.
    # Historical context is supported by the NY Fed posts linked in insights;
    # these labels identify episodes, not an attribution of the whole index.
    events = [
        ("2020-04", "2019-08", .72, "2020 COVID\nlockdowns"),
        ("2021-12", "2020-08", .90, "Late 2021\nbottleneck peak"),
        ("2022-04", "2023-05", .80, "2022 China lockdowns /\nRussia–Ukraine war"),
        ("2026-04", "2025-03", .56, "2026 Hormuz\ndisruption"),
    ]
    lower, upper = ax.get_ylim()
    for month, label_month, label_fraction, label in events:
        point = pd.Period(month, freq="M").to_timestamp()
        label_x = pd.Period(label_month, freq="M").to_timestamp()
        if point not in series.index or pd.isna(series.loc[point]) or not start <= label_x <= end:
            continue
        point_y = float(series.loc[point])
        label_y = lower + (upper - lower) * label_fraction
        direction = 1 if label_y > point_y else -1
        ax.annotate(label, xy=(point, point_y + direction * span * .015),
                    xytext=(label_x, label_y), textcoords="data", ha="center",
                    va="bottom" if direction > 0 else "top", fontsize=8.5,
                    linespacing=1.2, color="#56616D",
                    arrowprops=dict(arrowstyle="-", color="#56616D", linewidth=.55,
                                    shrinkA=4, shrinkB=0), zorder=6)
    years = [pd.Timestamp(year, 1, 1) for year in range(start.year, end.year + 1)
             if year % 2 == 0 and start <= pd.Timestamp(year, 1, 1) <= end]
    ax.set_xticks(years)
    ax.set_xticklabels([str(t.year) for t in years])
    ax.set_xticks([pd.Timestamp(year, 1, 1) for year in range(start.year, end.year + 1)
                  if year % 2 and start <= pd.Timestamp(year, 1, 1) <= end], minor=True)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: f"{value:g}"))
    ax.tick_params(axis="y", length=0, labelsize=EconStyle.FONT_SIZE_TICK, pad=4)
    ax.tick_params(axis="x", which="major", length=4, width=.8, pad=4,
                   labelsize=EconStyle.FONT_SIZE_TICK)
    ax.tick_params(axis="x", which="minor", length=2.5, width=.6)
    ax.grid(axis="y", color=EconStyle.GRID_COLOR, linewidth=.5)
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)
    for spine in ("top", "left", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(EconStyle.AXIS_COLOR)
    ax.spines["bottom"].set_linewidth(1)
    EconStyle.set_title(ax, report["title"],
                       "Monthly · standard deviations; zero = historical average · last ten years")
    EconStyle.add_top_rule(ax)
    fig.tight_layout(rect=[.02, .04, .98, .96])
    EconStyle.add_source(fig, "Federal Reserve Bank of New York (GSCPI)", report["as_of"])
    EconStyle.save_chart(fig, path)
