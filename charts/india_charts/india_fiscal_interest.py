"""One fiscal-interest chart: annual burden and current fiscal-year YTD trend."""
from pathlib import Path
import numpy as np
from matplotlib.patches import Patch
from charts.style import EconStyle
from data.processors.fiscal_interest import load_interest_data

FILENAME = '08_india_interest_revenue.png'


def generate(output_dir):
    output_dir = Path(output_dir)
    try:
        annual, monthly = load_interest_data()
    except (ValueError, OSError, KeyError) as exc:
        (output_dir / FILENAME).unlink(missing_ok=True)
        print(f'   ⚠ Interest burden unavailable: {exc}')
        return None
    colors = {'Actual': '#1E3A8A', 'Provisional': '#93A8D4', 'Budget': '#D97706'}
    fig, axes = EconStyle.create_figure(size='wide', ncols=2,
                                      gridspec_kw={'width_ratios': [1.65, 1]}, sharey=True)
    fig.subplots_adjust(left=.065, right=.975, bottom=.23, top=.72, wspace=.12)
    font = EconStyle._get_font('regular')
    fig.text(.065, .95, 'How Much Revenue Goes to Interest?', fontsize=22,
             fontproperties=EconStyle._get_font('bold'), va='top')
    fig.text(.065, .85, 'Central government interest payments as a share of revenue receipts (%)',
             fontsize=10, fontproperties=font)
    ax, current = axes
    x = np.arange(len(annual))
    bars = ax.bar(x, annual.interest_share, color=annual.status.map(colors), width=.67, zorder=3)
    for bar, value in zip(bars, annual.interest_share):
        ax.text(bar.get_x()+bar.get_width()/2, value+1, f'{value:.1f}',
                ha='center', fontsize=7.5, fontproperties=font)
    labels = ['FY'+fy[-2:] for fy in annual.fy]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8, rotation=45, ha='right')
    ax.set_ylabel('Interest / revenue receipts (%)', fontsize=9)
    ax.set_title('Annual fiscal burden', loc='left', fontsize=11, fontweight='bold', pad=12)
    ax.legend(handles=[Patch(color=c, label=s) for s,c in colors.items()],
              loc='upper left', fontsize=7.5, ncol=3, frameon=False)
    m = np.arange(len(monthly))
    current.plot(m, monthly.interest_share, color=colors['Actual'], linewidth=2,
                 marker='o', markersize=5, zorder=4)
    be = annual.iloc[-1]
    current.axhline(be.interest_share, color=colors['Budget'], linestyle='--', linewidth=1.2,
                   label=f'Full-year Budget: {be.interest_share:.1f}%')
    current.legend(loc='upper right', fontsize=7.5, frameon=False)
    current.set_title(f"FY{be.fy[-2:]} cumulative April–month", loc='left',
                      fontsize=11, fontweight='bold', pad=12)
    current.set_xticks(m)
    current.set_xticklabels(monthly.date.dt.strftime('%b'), fontsize=9)
    current.set_xlim(-.35, max(len(monthly)-.5, .5))
    last = monthly.iloc[-1]
    current.annotate(f'{last.interest_share:.1f}%', (m[-1], last.interest_share),
                     xytext=(0, 10), textcoords='offset points', ha='center',
                     fontsize=10, fontweight='bold', color=colors['Actual'])
    ceiling = max(annual.interest_share.max(), monthly.interest_share.max())
    ax.set_ylim(0, max(60, np.ceil((ceiling+5)/10)*10))
    for panel in axes:
        panel.set_axisbelow(True)
        panel.yaxis.grid(True, alpha=.15, color='#9CA3AF')
        panel.xaxis.grid(False)
        EconStyle.add_top_rule(panel)
    fig.text(.065, .10, 'Revenue receipts = net central taxes + non-tax revenue; excludes borrowing and capital receipts.',
             fontsize=8, fontproperties=font, color=EconStyle.TEXT_MUTED)
    fig.text(.065, .025, f'Source: Union Budget actuals / CGA provisional accounts | Current year through {last.date:%b %Y}',
             fontsize=7.5, fontproperties=font, color=EconStyle.TEXT_MUTED)
    EconStyle.draw_credit(fig, x=.975, y=.025)
    path=output_dir/FILENAME
    EconStyle.save_chart(fig,path)
    print(f'   ✓ Interest burden (annual + current fiscal year through {last.date:%b %Y})')
    return path
