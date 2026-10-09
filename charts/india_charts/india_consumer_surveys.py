"""Canonical India consumer-confidence indices and component comparisons."""

from datetime import datetime
import json
import logging
import math
from pathlib import Path

from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MultipleLocator
import matplotlib.dates as mdates
import matplotlib.patheffects as pe

from charts.style import EconStyle
from data.processors import rbi_surveys as rbi


NAMES = (
    '27_india_consumer_confidence_urban_rural',
    '28_india_consumer_confidence_urban_components',
    '29_india_consumer_confidence_rural_components',
    '27b_india_discretionary_spending_sentiment',
)

RETIRED_NAME = '28_india_consumer_confidence_drivers'

TITLES = ['India Consumer Confidence — Urban vs Rural']

COLORS = {
    'Urban': EconStyle.CATEGORICAL_COLORS[0],
    'Rural': EconStyle.CATEGORICAL_COLORS[5],
}

COMPONENTS = rbi.COMPONENTS


# ---------------------------------------------------------------------
# SHARED FURNITURE
# ---------------------------------------------------------------------

def furniture(fig, title, subtitle, date, extra=None):
    """
    Shared editorial furniture for the headline consumer-confidence chart.

    Legend is deliberately NOT handled here anymore because the headline
    chart now places Urban/Rural directly alongside the subtitle.
    """
    EconStyle.add_editorial_header(fig, title, subtitle)

    if extra:
        fig.text(
            .965,
            .813,
            extra,
            ha='right',
            fontsize=9,
            color=EconStyle.INK_MUTED,
        )

    fig.text(
        .04,
        .033,
        f'Source: RBI · Urban & Rural Consumer Confidence Surveys | '
        f'Through {date:%b %Y}',
        fontsize=7,
        color=EconStyle.TEXT_MUTED,
    )

    EconStyle.draw_credit(fig, x=.96, y=.027, size=6.6)


# ---------------------------------------------------------------------
# 1. INDIA CONSUMER CONFIDENCE — URBAN VS RURAL
# ---------------------------------------------------------------------

def render_confidence(series, common, marker, destination):
    fig, axes = EconStyle.create_figure(
        size=(9.2, 4.8),
        nrows=1,
        ncols=2,
        sharex=True,
    )

    # Reserve endpoint-label gutters without widening the dashboard figure.
    axes[0].set_position([.075, .18, .335, .55])
    axes[1].set_position([.565, .18, .335, .55])

    dates = [datetime.fromisoformat(d) for d in common]
    panel_limits = []

    # Cleaner subtitle — Urban/Rural legend now occupies the space where
    # "RBI consumer surveys" previously appeared.
    furniture(
        fig,
        TITLES[0],
        'Current conditions and one-year-ahead expectations',
        dates[-1],
    )

    for ax, key, name in zip(
        axes,
        ('csi', 'fei'),
        ('Current Situation Index', 'Future Expectations Index'),
    ):
        values_all = [
            r[key]
            for rs in series.values()
            for r in rs
            if r[key] is not None
        ]

        limits = (
            math.floor((min(values_all + [100]) - 2) / 5) * 5,
            math.ceil((max(values_all + [100]) + 2) / 5) * 5,
        )

        panel_limits.append(list(limits))

        ax.set_title(
            name,
            loc='left',
            fontsize=11,
            weight='bold',
            pad=10,
        )

        ax.set_ylim(*limits)
        ax.set_xlim(dates[0], dates[-1])

        # More horizontal guides than before, while keeping the neutral
        # threshold visually dominant.
        ax.yaxis.set_major_locator(MultipleLocator(5))

        ax.grid(axis='x', visible=False)
        ax.grid(
            axis='y',
            color=EconStyle.GRID_COLOR,
            lw=.55,
            alpha=.9,
        )

        ax.set_axisbelow(True)

        # Neutral threshold remains stronger than ordinary grid lines.
        ax.axhline(
            100,
            color=EconStyle.INK_MUTED,
            lw=1.0,
            zorder=3,
        )

        ax.text(
            .01,
            100 + 1.1,
            'Neutral = 100',
            transform=ax.get_yaxis_transform(),
            fontsize=7.5,
            color=EconStyle.INK_MUTED,
            va='bottom',
            path_effects=[
                pe.withStroke(
                    linewidth=3,
                    foreground='white',
                )
            ],
        )

        ax.tick_params(
            length=0,
            labelsize=9,
            pad=7,
        )

        # Prepare both series once so the gap between Urban/Rural can be
        # shaded before drawing the hero lines.
        urban_values = [
            math.nan if r[key] is None else r[key]
            for r in series['Urban']
        ]

        rural_values = [
            math.nan if r[key] is None else r[key]
            for r in series['Rural']
        ]

        # Subtle neutral shading between Urban and Rural.
        ax.fill_between(
            dates,
            urban_values,
            rural_values,
            color=EconStyle.GRID_COLOR,
            alpha=.22,
            linewidth=0,
            zorder=1,
        )

        end_values = [
            series[g][-1][key]
            for g in COLORS
        ]

        offsets = [0, 0]

        if abs(end_values[0] - end_values[1]) < 4:
            offsets = [
                8 if end_values[0] >= end_values[1] else -8,
                8 if end_values[1] > end_values[0] else -8,
            ]

        for (g, color), offset in zip(COLORS.items(), offsets):
            values = (
                urban_values
                if g == 'Urban'
                else rural_values
            )

            # Urban = solid, Rural = dashed.
            linestyle = '-' if g == 'Urban' else '--'

            ax.plot(
                dates,
                values,
                color=color,
                lw=2.2,
                ls=linestyle,
                zorder=5,
            )

            ax.scatter(
                dates[-1],
                values[-1],
                c=color,
                s=35,
                edgecolors=EconStyle.BAR_EDGE_COLOR,
                linewidths=.6,
                zorder=6,
                clip_on=False,
            )

            ax.annotate(
                f'{g} {values[-1]:.1f}',
                (dates[-1], values[-1]),
                xytext=(10, offset),
                textcoords='offset points',
                fontsize=9,
                weight='bold',
                color=color,
                va='center',
                annotation_clip=False,
            )

    ticks = dates[::6]

    if dates[-1] != ticks[-1]:
        ticks.append(dates[-1])

    for ax in axes:
        ax.set_xticks(ticks)
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter('%b\n%Y')
        )

    EconStyle.save_chart(fig, destination)

    return panel_limits


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def signed(value):
    return f'{value:+.1f}'.replace('-', '−')


def change_cue(value):
    # Sign describes the change, never the level.
    # Below displayed precision is treated as neutral.
    return (
        EconStyle.INK_MUTED
        if abs(value) < .05
        else EconStyle.LINE_TEAL
        if value > 0
        else EconStyle.LINE_MAROON
    )


# ---------------------------------------------------------------------
# 3 / 4. URBAN AND RURAL COMPONENT TABLES
# ---------------------------------------------------------------------

def render_components(rows, date, previous, geography, destination):
    """RBI component table: previous, latest and change for each horizon."""

    fig, ax = EconStyle.create_figure(size=(9.2, 4.8))

    # Use more vertical canvas and reduce the gap above the source footer.
    ax.set_position([.075, .045, .89, .70])

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()

    EconStyle.add_editorial_header(
        fig,
        f'India Consumer Confidence — {geography} Components',
        f'Net household sentiment (pp) · '
        f'{previous:%b %Y} vs {date:%b %Y}',
    )

    fig.text(
    .075,
    .775,
    'Survey respondents indicate whether conditions have improved, remained unchanged, or worsened;\n'
    'net response is the difference between favourable and unfavourable responses.',
    fontsize=9.0,
    weight='medium',
    color=EconStyle.INK_MUTED,
    linespacing=1.25,
)

    color = COLORS[geography]

    # Pull the table substantially closer to the component names.
    groups = [
        (
            'current',
            'CURRENT PERCEPTION',
            .205,
            .365,
            (.265, .385, .515),
        ),
        (
            'ahead',
            '1Y AHEAD EXPECTATIONS',
            .585,
            .375,
            (.645, .765, .895),
        ),
    ]

    row_positions = (.72, .58, .44, .30, .16)

    for horizon, title, left, width, centers in groups:
        # Neutral group bands without full cell borders.
        ax.add_patch(
            Rectangle(
                (left, .055),
                width,
                .945,
                facecolor=EconStyle.ROW_ALT,
                alpha=1 if horizon == 'current' else .55,
                edgecolor='none',
                zorder=0,
            )
        )

        ax.text(
            left + width / 2,
            .958,
            title,
            ha='center',
            va='center',
            fontsize=10,
            weight='bold',
            color=color,
        )

        ax.plot(
            [left + .015, left + width - .015],
            [.915, .915],
            color=color,
            lw=1,
        )

        for center, label in zip(
            centers,
            (
                f'{previous:%b %Y}',
                f'{date:%b %Y}',
                'Δ',
            ),
        ):
            ax.text(
                center,
                .852,
                label,
                ha='center',
                va='center',
                fontsize=9.5,
                weight=(
                    'bold'
                    if center != centers[0]
                    else 'normal'
                ),
                color=(
                    EconStyle.INK_MUTED
                    if center == centers[0]
                    else EconStyle.INK
                ),
            )

        for y, (name, _) in zip(
            row_positions,
            COMPONENTS,
        ):
            row = next(
                r
                for r in rows
                if r['geography'] == geography
                and r['horizon'] == horizon
                and r['component'] == name
            )

            for center, key, size, weight, ink in zip(
                centers,
                (
                    'previous_value',
                    'plotted_value',
                    'delta',
                ),
                (11, 13, 11),
                (
                    'normal',
                    'bold',
                    'bold',
                ),
                (
                    EconStyle.INK_MUTED,
                    EconStyle.INK,
                    change_cue(row['delta']),
                ),
            ):
                ax.text(
                    center,
                    y,
                    signed(row[key]),
                    ha='center',
                    va='center',
                    fontsize=size,
                    weight=weight,
                    color=ink,
                )

    for y, (name, _) in zip(
        row_positions,
        COMPONENTS,
    ):
        ax.text(
            0,
            y,
            name,
            fontsize=10.5,
            weight='medium',
            va='center',
            color=EconStyle.INK,
        )

        if y > .16:
            ax.plot(
                [0, 1],
                [y - .07, y - .07],
                color=EconStyle.GRID_COLOR,
                lw=.4,
                zorder=1,
            )

    # Removed:
    # "Positive = favourable sentiment · Δ = latest − previous (pp)"

    EconStyle.add_source(
        fig,
        f'RBI · {geography} Consumer Confidence Survey',
        f'{date:%b %Y}',
    )

    EconStyle.save_chart(fig, destination)


# ---------------------------------------------------------------------
# 2. DISCRETIONARY SPENDING SENTIMENT
# ---------------------------------------------------------------------

def render_discretionary(report, destination):
    """
    Shared balance scale and geography colours.
    Current = solid; 1Y Ahead = dashed.
    """

    dates = [
        datetime.fromisoformat(d)
        for d in report['common_dates']
    ]

    fig, axes = EconStyle.create_figure(
        size=(9.2, 4.8),
        nrows=1,
        ncols=2,
        sharex=True,
        sharey=True,
    )

    axes[0].set_position([.075, .155, .305, .525])
    axes[1].set_position([.565, .155, .305, .525])

    EconStyle.add_editorial_header(
        fig,
        'Discretionary Spending Sentiment — India',
        'Household views on non-essential spending',
    )

    # Clear explanation in the space where the legend previously sat.
    # Compact explainer band between the editorial header and the chart panels.
    fig.text(
    .5,
    .825,
    'Survey respondents report whether non-essential spending increased, '
    'stayed the same, or decreased.\n'
    'Net response = % increased − % decreased.',
    fontsize=9.1,
    weight='medium',
    color=EconStyle.INK,
    va='top',
    linespacing=1.25,
    ha='center',
    bbox=dict(
        boxstyle='round,pad=0.35',
        facecolor=EconStyle.ROW_ALT,
        edgecolor='none',
        alpha=.95,
    ),
)

    values = [
        r[h + '_net']
        for rs in report['series'].values()
        for r in rs
        for h in ('current', 'ahead')
    ]

    low, high = min(values), max(values)

    padding = max(
        3,
        (high - low) * .10,
    )

    # Include zero when it is sufficiently close to remain economically useful.
    if low > 0 and low < (high - low) * .25:
        low = 0

    limits = (
        math.floor((low - padding) / 5) * 5,
        math.ceil((high + padding) / 5) * 5,
    )

    for ax, (g, color) in zip(
        axes,
        COLORS.items(),
    ):
        rows = report['series'][g]

        current = [
            r['current_net']
            for r in rows
        ]

        ahead = [
            r['ahead_net']
            for r in rows
        ]

        ax.set_title(
            g,
            loc='left',
            fontsize=11,
            weight='bold',
            pad=10,
            color=color,
        )

        ax.set_ylim(*limits)
        ax.set_xlim(dates[0], dates[-1])

        ax.yaxis.set_major_locator(
            MultipleLocator(
                10
                if limits[1] - limits[0] > 40
                else 5
            )
        )

        ax.grid(axis='x', visible=False)

        ax.grid(
            axis='y',
            color=EconStyle.GRID_COLOR,
            lw=.5,
            alpha=.85,
        )

        ax.set_axisbelow(True)

        ax.tick_params(
            length=0,
            labelsize=9,
            pad=7,
            labelleft=True,
        )

        if limits[0] <= 0 <= limits[1]:
            ax.axhline(
                0,
                color=EconStyle.INK_MUTED,
                lw=.8,
                zorder=3,
            )

        # Expectations gap.
        ax.fill_between(
            dates,
            current,
            ahead,
            color=color,
            alpha=.07,
            linewidth=0,
            zorder=1,
        )

        gap = ahead[-1] - current[-1]

        offsets = (
            (0, 0)
            if abs(gap)
            >= (limits[1] - limits[0]) * .07
            else (
                -7 if gap >= 0 else 7,
                7 if gap >= 0 else -7,
            )
        )

        for values_, label, ls, offset in zip(
            (current, ahead),
            ('Current', '1Y Ahead'),
            ('-', '--'),
            offsets,
        ):
            ax.plot(
                dates,
                values_,
                color=color,
                lw=2.2,
                ls=ls,
                zorder=5,
            )

            ax.scatter(
                dates[-1],
                values_[-1],
                color=color,
                s=28,
                edgecolors=EconStyle.BAR_EDGE_COLOR,
                linewidths=.6,
                clip_on=False,
                zorder=6,
            )

            ax.annotate(
                f'{label} {values_[-1]:.1f}',
                (dates[-1], values_[-1]),
                xytext=(8, offset),
                textcoords='offset points',
                fontsize=9,
                weight='bold',
                color=color,
                va='center',
                annotation_clip=False,
            )

    fig.text(
        .016,
        .46,
        'Net response (pp)',
        rotation=90,
        ha='center',
        va='center',
        fontsize=9,
    )

    ticks = dates[::6]

    if ticks[-1] != dates[-1]:
        ticks.append(dates[-1])

    for ax in axes:
        ax.set_xticks(ticks)
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter('%b\n%Y')
        )

    fig.text(
        .04,
        .033,
        f'Source: RBI · Urban & Rural Consumer Confidence Surveys | '
        f'Through {dates[-1]:%b %Y}',
        fontsize=7,
        color=EconStyle.TEXT_MUTED,
    )

    EconStyle.draw_credit(
        fig,
        x=.96,
        y=.027,
        size=6.6,
    )

    EconStyle.save_chart(
        fig,
        destination,
    )

    return list(limits)


# ---------------------------------------------------------------------
# GENERATION
# ---------------------------------------------------------------------

def generate(output_dir, directory=rbi.CONSUMER_DIR):
    output_dir = Path(output_dir)

    artifacts = [
        output_dir / (name + ext)
        for name in (*NAMES, RETIRED_NAME)
        for ext in ('.png', '.json')
    ]

    for path in artifacts:
        path.unlink(missing_ok=True)

    try:
        comparison = rbi.load_consumer_comparison(
            directory
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        latest = datetime.fromisoformat(
            comparison['latest_date']
        )

        previous = datetime.fromisoformat(
            comparison['previous_date']
        )

        # -------------------------------------------------------------
        # Headline Urban vs Rural chart
        # -------------------------------------------------------------

        limits = render_confidence(
            comparison['series'],
            comparison['common_dates'],
            comparison['coverage_marker'],
            output_dir / (NAMES[0] + '.png'),
        )

        meta = dict(
            latest_date=comparison['latest_date'],
            previous_date=comparison['previous_date'],
            sources=comparison['sources'],
            source_urls=rbi.CONSUMER_SOURCES,
            common_dates=comparison['common_dates'],
            panel_y_limits=limits,
            latest_indices={
                g: rows[-1]
                for g, rows in comparison['series'].items()
            },
            source_notes={
                g: s['notes']
                for g, s in comparison['surveys'].items()
            },
        )

        (
            output_dir / (NAMES[0] + '.json')
        ).write_text(
            json.dumps(
                meta,
                indent=2,
                allow_nan=False,
            ) + '\n'
        )

        # -------------------------------------------------------------
        # Urban / Rural component tables
        # -------------------------------------------------------------

        for geography, name in zip(
            COLORS,
            NAMES[1:3],
        ):
            rows = [
                r
                for r in comparison['components']
                if r['geography'] == geography
            ]

            render_components(
                rows,
                latest,
                previous,
                geography,
                output_dir / (name + '.png'),
            )

            meta = dict(
                latest_date=comparison['latest_date'],
                previous_date=comparison['previous_date'],
                geography=geography,
                presentation='component_table',
                source=rbi.CONSUMER_SOURCES[geography],
                sources={
                    geography:
                    comparison['sources'][geography]
                },
                components=rows,
                index_reconciliation=[
                    r
                    for r in comparison['index_reconciliation']
                    if r['geography'] == geography
                ],
            )

            (
                output_dir / (name + '.json')
            ).write_text(
                json.dumps(
                    meta,
                    indent=2,
                    allow_nan=False,
                ) + '\n'
            )

        # -------------------------------------------------------------
        # Discretionary spending sentiment
        # -------------------------------------------------------------

        discretionary = (
            rbi.load_discretionary_comparison(
                surveys=comparison['surveys']
            )
        )

        discretionary['panel_y_limits'] = (
            render_discretionary(
                discretionary,
                output_dir / (NAMES[3] + '.png'),
            )
        )

        (
            output_dir / (NAMES[3] + '.json')
        ).write_text(
            json.dumps(
                discretionary,
                indent=2,
                allow_nan=False,
            ) + '\n'
        )

        print(
            f'   RBI consumer confidence: '
            f'{latest:%b %Y} → four charts'
        )

        return [
            output_dir / (name + '.png')
            for name in NAMES
        ]

    except Exception as exc:
        for path in artifacts:
            path.unlink(missing_ok=True)

        logging.warning(
            'RBI CONSUMER SURVEY CHARTS OMITTED: %s',
            exc,
        )

        return []