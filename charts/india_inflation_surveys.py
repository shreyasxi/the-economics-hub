"""Canonical India inflation survey charts, rendered from validated local workbooks."""
from datetime import datetime
import json
import logging
from pathlib import Path
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MultipleLocator, FuncFormatter
from charts.style import EconStyle
from data import rbi_surveys as rbi

NAMES = ('25_india_inflation_expectations', '26_india_household_price_categories')
SERIES = rbi.SERIES
TITLE = 'Inflation Expectations - India'
def render_expectations(records, destination):
    latest, previous, earlier = rbi.select_curves(records)
    fig, curve = EconStyle.create_figure(size=(9.2, 4.8))
    curve.set_position([.11, .18, .85, .55])
    EconStyle.add_editorial_header(
        fig, TITLE, 'Household perceived inflation and future expectations · Current vs. 3M vs. 1Y ahead')
    styles = [(latest, "Latest", EconStyle.INK, 3.5, "-"),
              (previous, "Previous", EconStyle.LINE_BLUE, 2.1, "--"),
              (earlier, "Year earlier", EconStyle.LINE_ORANGE, 1.8, "-")]
    handles = []
    all_values = [r[k] for r, *_ in styles for k in SERIES]
    lo, hi = min(all_values), max(all_values)
    padding = max((hi - lo) * .25, .25)
    curve.set_ylim(lo - padding, hi + padding)
    curve.set_xlim(-.2, 2.2)
    # Category boundary halfway between Current and 3M; Current stays white.
    curve.axvspan(.5, 2.2, facecolor=EconStyle.ROW_ALT, alpha=.8,
                  edgecolor="none", zorder=0)
    curve.text(1.35, .96, "EXPECTATIONS", transform=curve.get_xaxis_transform(),
               ha="center", va="top", fontsize=8.5, fontweight="medium",
               color=EconStyle.INK_MUTED)
    for r, label, color, lw, ls in reversed(styles):
        values = [r[k] for k in SERIES]
        line, = curve.plot(range(3), values, color=color, lw=lw, ls=ls,
                           marker="o" if r is latest else None, ms=7,
                           markerfacecolor="white", markeredgewidth=1.8,
                           zorder=10 if r is latest else 5)
        handles.insert(0, line)
        if r is latest:
            for x, y in enumerate(values):
                curve.annotate(f"{y:.2f}%", (x, y), xytext=(0, 13 if x != 2 else -23),
                               textcoords="offset points", ha="center", fontsize=11,
                               fontweight="bold", color=color,
                               path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    fig.legend(handles, [f"{label} · {r['date']:%b %Y}" for r, label, *_ in styles],
                 loc="upper left", bbox_to_anchor=(.075, .838), frameon=False,
                 ncol=3, borderaxespad=0, prop={"size": 10},
                 columnspacing=1.8, handlelength=2.7, handletextpad=.7)
    curve.set_xticks([0, 1, 2], ["Current\n(perceived)", "3M Ahead", "1Y Ahead"])
    curve.set_ylabel("Median inflation (%)", labelpad=10, fontsize=11, fontweight="medium")
    curve.yaxis.set_major_locator(MultipleLocator(.5))
    curve.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.1f}%"))

    curve.set_axisbelow(True)
    curve.grid(axis="y", color=EconStyle.GRID_COLOR, linewidth=.4)
    curve.grid(axis="x", visible=False)
    curve.tick_params(axis="both", length=0, labelsize=10.5, pad=7)
    for label in curve.get_xticklabels():
        label.set_fontweight("medium")
    for side in ("top", "left", "right"):
        curve.spines[side].set_visible(False)
    curve.spines["bottom"].set_linewidth(.8)
    fig.text(.04, .03,
             f"Source: RBI · Inflation Expectations Survey of Households | Survey: {latest['date']:%b %Y}",
             fontproperties=EconStyle._get_font("regular"),
             fontsize=EconStyle.FONT_SIZE_SOURCE, color=EconStyle.TEXT_MUTED,
             ha="left", va="bottom")
    EconStyle.draw_credit(fig, x=.96, y=.03)
    return EconStyle.save_chart(fig, destination)

SUBTITLE = "Share of households expecting prices to rise · 3M ahead vs 1Y ahead"

def render_categories(report, destination):
    fig, ax = EconStyle.create_figure(size=(9.2, 4.8))
    ax.set_position([.19, .18, .67, .55])
    # An unbordered strip spans the heading and all five change values.
    fig.add_artist(Rectangle((.875, .18), .09, .60, transform=fig.transFigure,
                             facecolor=EconStyle.ROW_ALT, edgecolor="none", zorder=0))
    EconStyle.add_editorial_header(
        fig, 'What Households Think Will Get More Expensive', SUBTITLE)
    muted, strong = EconStyle.INK_MUTED, EconStyle.CATEGORICAL_COLORS[0]
    for y, r in enumerate(report["categories"]):
        a, b = r["three_month"], r["one_year"]
        ax.plot([a, b], [y, y], color=EconStyle.RULE_LIGHT, lw=1.2, zorder=2)
        ax.scatter([a], [y], s=58, facecolors="white", edgecolors=muted, linewidths=1.6, zorder=3)
        ax.scatter([b], [y], s=72, color=strong, edgecolors=EconStyle.BAR_EDGE_COLOR,
                   linewidths=EconStyle.BAR_EDGE_WIDTH, zorder=4)
        # Labels above/below markers remain separated even for Food's small gap.
        ax.annotate(f"{a:.2f}%", (a, y), xytext=(0, 8), textcoords="offset points",
                    ha="center", va="bottom", color=muted, fontsize=9.5)
        ax.annotate(f"{b:.2f}%", (b, y), xytext=(0, -8), textcoords="offset points",
                    ha="center", va="top", color=strong, fontsize=9.5, fontweight="bold")
        ax.text(1.097, y, f"{r['change_pp']:+.2f}", transform=ax.get_yaxis_transform(),
                ha="center", va="center", fontsize=10, color=EconStyle.INK,
                fontweight="bold" if y < 2 else "medium")
    ax.text(1.097, 1.065, "CHANGE\n(pp)", transform=ax.transAxes, fontsize=9,
            ha="center", va="bottom", color=EconStyle.INK, fontweight="bold")
    ax.set_yticks(range(5), [r["category"].replace("Household durables", "Household\ndurables")
                            for r in report["categories"]])
    ax.set_ylim(4.6, -.6)
    values = [r[h] for r in report['categories'] for h in ('three_month', 'one_year')]
    ax.set_xlim(min(64, max(0, min(values)-5)), max(90, min(100, max(values)+5)))
    ax.xaxis.set_major_locator(MultipleLocator(5))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_xlabel("Share of households expecting prices to rise", fontsize=10,
                 fontweight="medium", labelpad=12)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=EconStyle.GRID_COLOR, linewidth=.4)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0, labelsize=9, pad=7)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontweight("medium")
    for side in ("top", "left", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(EconStyle.INK)
    ax.spines["bottom"].set_linewidth(.7)
    handles = [Line2D([], [], marker="o", linestyle="none", markerfacecolor="white", markeredgecolor=muted,
                      markeredgewidth=1.6, markersize=7),
               Line2D([], [], marker="o", linestyle="none", color=strong, markersize=8,
                      markeredgecolor=EconStyle.BAR_EDGE_COLOR, markeredgewidth=EconStyle.BAR_EDGE_WIDTH)]
    fig.legend(handles, ["3M ahead", "1Y ahead"], loc="upper left", bbox_to_anchor=(.075, .838),
               ncol=2, frameon=False, fontsize=10, borderaxespad=0, handletextpad=.5, columnspacing=2)
    date = datetime.fromisoformat(report["survey_date"])
    fig.text(.04, .04, f"Source: RBI · Inflation Expectations Survey of Households | Survey: {date:%b %Y}",
             fontproperties=EconStyle._get_font("regular"), fontsize=EconStyle.FONT_SIZE_SOURCE,
             color=EconStyle.TEXT_MUTED)
    EconStyle.draw_credit(fig, x=.96, y=.04)
    return EconStyle.save_chart(fig, destination)

def generate(output_dir, directory=rbi.INFLATION_DIR):
    output_dir = Path(output_dir)
    artifacts = [output_dir / (name + ext) for name in NAMES for ext in ('.png', '.json')]
    for path in artifacts:
        path.unlink(missing_ok=True)
    try:
        workbook = rbi.discover_inflation(directory)
        records, missing = rbi.read_observations(workbook)
        latest, previous, earlier = rbi.select_curves(records)
        report = rbi.read_categories(workbook)
        output_dir.mkdir(parents=True, exist_ok=True)
        render_expectations(records, output_dir / (NAMES[0]+'.png'))
        render_categories(report, output_dir / (NAMES[1]+'.png'))
        meta = dict(workbook=str(workbook), workbook_sha256=report['workbook_sha256'],
                    source=rbi.INFLATION_SOURCE, statistic='Median',
                    latest=rbi.serializable(latest), previous=rbi.serializable(previous),
                    year_earlier=rbi.serializable(earlier), missing_fields=missing)
        (output_dir / (NAMES[0]+'.json')).write_text(json.dumps(meta, indent=2, allow_nan=False)+'\n')
        (output_dir / (NAMES[1]+'.json')).write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        print(f'   RBI inflation surveys: {latest["date"]:%b %Y} → two charts')
        return [output_dir / (name+'.png') for name in NAMES]
    except Exception as exc:
        for path in artifacts:
            path.unlink(missing_ok=True)
        logging.warning('RBI INFLATION SURVEY CHARTS OMITTED: %s', exc)
        return []
