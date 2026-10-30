"""Exact-window sector investment comparisons; missing periods never become zero."""
from datetime import date
import calendar
import math

PERIODS = ('Latest fortnight', 'Latest complete month', 'Three months', 'Six months')


def previous_fortnight(day):
    if day.day != 15:
        return day.replace(day=15)
    first = day.replace(day=1)
    from datetime import timedelta
    return first - timedelta(days=1)


def period_dates(cutoff, period):
    end = date.fromisoformat(cutoff)
    if end.day not in (15, calendar.monthrange(end.year, end.month)[1]):
        raise ValueError('Invalid fortnight cutoff')
    if period not in PERIODS:
        raise ValueError('Unsupported flow period')
    if period == 'Latest complete month' and end.day == 15:
        end = previous_fortnight(end)
    count = {'Latest fortnight': 1, 'Latest complete month': 2, 'Three months': 6, 'Six months': 12}[period]
    days = [end]
    for _ in range(count - 1):
        days.append(previous_fortnight(days[-1]))
    return [d.isoformat() for d in reversed(days)]


def rank_sectors(datasets, period):
    cutoffs = {d.get('flows_as_of') or d['as_of'] for d in datasets.values()}
    if len(cutoffs) != 1:
        raise ValueError('Sector flow cutoffs differ; a consistent publication is required')
    cutoff = cutoffs.pop()
    days = period_dates(cutoff, period)
    rows = []
    for sector, data in datasets.items():
        by_date = {r['date']: r for r in data['flows']}
        if len(by_date) != len(data['flows']):
            raise ValueError('Duplicate sector flow period')
        complete = all(day in by_date for day in days)
        selected = [by_date[day] for day in days if day in by_date]
        if any(not math.isfinite(r['equity_flow_cr']) for r in selected):
            raise ValueError('Non-finite sector flow')
        net = sum(r['equity_flow_cr'] for r in selected) if complete else None
        opening = selected[0].get('opening_equity_auc_cr') if complete else None
        relative = 100 * net / opening if opening is not None and math.isfinite(opening) and opening > 0 else None
        rows.append(dict(sector=sector, net_cr=net, relative_pct=relative, opening_auc_cr=opening,
                         observations=len(selected), expected=len(days)))
    from datetime import timedelta
    start = previous_fortnight(date.fromisoformat(days[0])) + timedelta(days=1)
    return rows, start.isoformat(), days[-1], cutoff
