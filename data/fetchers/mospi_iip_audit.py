"""Shared IIP source validation and legacy overlap diagnostics.

Never writes production data or restores the discontinued DBIE series.
Official API: /api/iip/getIIPData?frequency=Monthly&type=General&base_year=...
"""
import calendar
from decimal import Decimal

FIELDS = {'base_year', 'year', 'month', 'type', 'category', 'sub_category',
          'index', 'growth_rate'}


def validate(rows, base):
    result = {}
    for row in rows:
        if set(row) != FIELDS:
            raise ValueError('IIP schema changed')
        if (row['base_year'] != base or row['type'] != 'General' or
                row['category'] != 'General' or row['sub_category'] != ''):
            raise ValueError('Wrong IIP concept/basis')
        if type(row['year']) is not int or row['month'] not in calendar.month_name[1:]:
            raise ValueError('Invalid IIP observation month')
        level, growth = Decimal(row['index']), Decimal(row['growth_rate'])
        if not level.is_finite() or level <= 0 or not growth.is_finite() or not -30 <= growth <= 30:
            raise ValueError('IIP sanity bounds failed')
        month = f"{row['year']}-{list(calendar.month_name).index(row['month']):02d}"
        if month in result:
            raise ValueError('Duplicate IIP month')
        result[month] = growth  # Published YoY rate; never the index level.
    if not result:
        raise ValueError('Empty IIP source')
    return result


def compare(rows, manual, base):
    official = validate(rows, base)
    return [dict(month=m, manual=str(v), official=str(official[m]),
                 equivalent=abs(Decimal(str(v))-official[m]) <= Decimal('.05'))
            for m, v in sorted(manual.items()) if m in official]
