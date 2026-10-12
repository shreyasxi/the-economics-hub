"""Offline, dated evidence for the four broader overview cards.

Directions require a two-thirds majority within a pillar. Equity indices
never outvote credit or volatility. Counts are unweighted, not GDP/CPI weights.
"""
import math
from datetime import datetime


def number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def month_label(month):
    return datetime.strptime(month[:7], '%Y-%m').strftime('%b %Y')


def previous_month(month, offset=1):
    year, mo = map(int, month[:7].split('-'))
    total = year * 12 + mo - 1 - offset
    return f'{total // 12:04d}-{total % 12 + 1:02d}'


def direction(values, up, down, neutral='Mixed', tolerance=0):
    values = [v for v in values if number(v)]
    if not values:
        return 'Awaiting data'
    if sum(v > tolerance for v in values) / len(values) >= 2 / 3:
        return up
    if sum(v < -tolerance for v in values) / len(values) >= 2 / 3:
        return down
    return neutral


def answer(state, evidence, metrics=None):
    return dict(state=state, evidence=evidence, metrics=metrics or [], context='')


def market_risk(inputs):
    from data.processors.market_regime import EQUITIES, CREDIT, COMMODITIES
    rows = inputs.get('rows', {})
    equities = [rows[k] for k in EQUITIES if k in rows]
    credit = [rows[k] for k in CREDIT if k in rows]
    vol = rows.get('vix')
    if len(equities) < 6 or len(credit) < 2 or not vol or 'median_20d' not in vol:
        return answer('Awaiting data', 'Insufficient three-month equity, credit or sustained-volatility coverage.')
    # Neutral bands avoid treating small moves as a firm directional signal.
    equity_state = direction([r['quarter'] for r in equities], 'Risk-on', 'Risk-off', tolerance=1)
    credit_state = direction([-r['quarter'] for r in credit], 'Risk-on', 'Risk-off', tolerance=5)
    volatility_state = 'Risk-on' if vol['percentile'] <= 50 else 'Risk-off' if vol['percentile'] >= 75 else 'Mixed'
    pillars = [equity_state, credit_state, volatility_state]
    state = pillars[0] if len(set(pillars)) == 1 else 'Mixed'
    recent = [direction([r['month'] for r in equities], 'Risk-on', 'Risk-off', tolerance=1),
              direction([-r['month'] for r in credit], 'Risk-on', 'Risk-off', tolerance=2),
              direction([-vol['month_change_pct']], 'Risk-on', 'Risk-off', tolerance=5)]
    recent_support = sum(v == 'Risk-on' for v in recent)
    quarterly_support = sum(v == 'Risk-on' for v in pillars)
    momentum = ('improving' if recent_support > quarterly_support else
                'weakening' if recent_support < quarterly_support else
                'supportive' if recent_support == 3 else 'defensive' if recent.count('Risk-off') == 3 else 'mixed')
    when = datetime.strptime(inputs['as_of'], '%Y-%m-%d').strftime('%d %b %Y')
    rising = sum(r['quarter'] > 1 for r in equities)
    narrowing = sum(r['quarter'] < -5 for r in credit)
    widening = sum(r['quarter'] > 5 for r in credit)
    credit_count, credit_verb = (widening, 'widened') if widening > narrowing else (narrowing, 'narrowed')
    vol_context = 'low' if vol['percentile'] <= 50 else 'elevated' if vol['percentile'] >= 75 else 'mid-range'
    evidence = (f"Through {when}: three-month gains exceeded 1% in {rising}/{len(equities)} equity markets; "
                f"{credit_count}/{len(credit)} credit spreads {credit_verb} by over 5 bp. "
                f"VIX’s 20-session median is {vol['median_20d']:.1f} ({vol_context} versus its past year). "
                f"One-month signals are {momentum}. ")
    commodities = [f"{name} {rows[k]['quarter']:+.1f}%" for k,name in COMMODITIES.items() if k in rows]
    if commodities:
        evidence += 'Commodities over three months: ' + ', '.join(commodities) + '. '
        reversals = [name for k,name in COMMODITIES.items() if k in rows and
                     abs(rows[k]['quarter']) > 1 and abs(rows[k]['month']) > 1 and rows[k]['quarter'] * rows[k]['month'] < 0]
        if reversals:
            evidence += 'One-month reversals: ' + ' / '.join(reversals) + '. '
    else:
        evidence += 'Commodity context unavailable. '
    return answer(state, evidence.strip(), [dict(pillar=name,state=value) for name,value in
                                           zip(('equities','credit','volatility'),pillars)])


def inflation_breadth(report, measure, month, baseline):
    national = [c for c in report.get('countries', []) if not c.get('aggregate')]
    eligible = [c for c in national if c.get('series', {}).get(measure)]
    changes = []
    for country in eligible:
        series = {r['month']: r['value'] for r in country['series'][measure] if number(r.get('value'))}
        if month in series and baseline in series:
            changes.append(series[month] - series[baseline])
    return dict(total=len(eligible), matched=len(changes), rising=sum(v > .05 for v in changes),
                easing=sum(v < -.05 for v in changes), flat=sum(abs(v) <= .05 for v in changes), changes=changes)


def global_inflation(snapshot):
    report = snapshot.get('inflation_breadth', {})
    breadth = report.get('breadth', {})
    if not breadth:
        return answer('Awaiting data', 'A comparable country inflation snapshot is unavailable.')
    month, baseline = breadth['month'], breadth['comparison_month']
    head = inflation_breadth(report, 'headline', month, baseline)
    core = inflation_breadth(report, 'core', month, baseline)
    if not head['total'] or head['matched'] / head['total'] < .8:
        return answer('Awaiting data', 'Fewer than 80% of countries have matched headline observations.')
    state = direction(head['changes'], 'Building', 'Easing', tolerance=.05)
    evidence = (f"{month_label(month)} vs {month_label(baseline)}: headline inflation eased in "
                f"{head['easing']}/{head['matched']} countries and rose in {head['rising']}. ")
    if core['total'] and core['matched'] / core['total'] >= .8:
        core_state = direction(core['changes'], 'Building', 'Easing', tolerance=.05)
        evidence += f"Core rose in {core['rising']}/{core['matched']}. "
        if state in ('Building', 'Easing') and core_state in ('Building', 'Easing') and state != core_state:
            state = 'Mixed'
            evidence += 'Headline and core trends diverge. '
    else:
        evidence += f"Core coverage: {core['matched']}/{core['total']}; too limited for a breadth verdict. "
    major_labels = {'USA': 'US', 'EA': 'euro area', 'CHN': 'China',
                    'JPN': 'Japan', 'GBR': 'UK', 'IND': 'India'}
    major_metrics = []
    for measure, label in (('headline', 'Major-economy headline'),):
        groups = {'rose': [], 'cooled': [], 'was little changed': []}
        deltas = []
        for country in report.get('countries', []):
            code = country.get('code')
            if code not in major_labels:
                continue
            series = {r['month']: r['value'] for r in country.get('series', {}).get(measure, [])
                      if number(r.get('value'))}
            if month not in series or baseline not in series:
                continue
            delta = series[month] - series[baseline]
            deltas.append(delta)
            movement = 'rose' if delta > .05 else 'cooled' if delta < -.05 else 'was little changed'
            groups[movement].append(major_labels[code])
            major_metrics.append(dict(country=code, measure=measure, period=month,
                                      comparison_month=baseline, value=series[month], change=delta))
        if deltas:
            clauses = [f"{verb} in {' / '.join(names)}" for verb, names in groups.items() if names]
            evidence += label + ' ' + '; '.join(clauses) + '. '
            if measure == 'headline' and len(deltas) == len(major_labels):
                major_state = direction(deltas, 'Building', 'Easing', tolerance=.05)
                if state in ('Building', 'Easing') and major_state in ('Building', 'Easing') and state != major_state:
                    state = 'Mixed'
                    evidence += 'Country breadth and major economies diverge. '
    return answer(state, evidence, major_metrics)


def latest_pair(rows, key, period='month'):
    valid = [r for r in rows if number(r.get(key))]
    valid.sort(key=lambda r: r[period])
    if not valid:
        return None, None
    latest = valid[-1]
    prior = next((r for r in reversed(valid[:-1]) if r[period][:7] == previous_month(latest[period])), None)
    return latest, prior


def india_activity(monthly, iip, industries):
    mfg, mfg_prev = latest_pair(monthly, 'india_mfg_pmi')
    svc, svc_prev = latest_pair(monthly, 'india_svc_pmi')
    if not mfg or not svc or mfg['month'] != svc['month']:
        return answer('Awaiting data', 'Manufacturing and services PMI need a common observation month.')
    pmis = [mfg['india_mfg_pmi'], svc['india_svc_pmi']]
    state = 'Expanding' if min(pmis) > 50 else 'Contracting' if max(pmis) < 50 else 'Mixed'
    evidence = f"{month_label(mfg['month'])}: manufacturing PMI {pmis[0]:.1f}, services {pmis[1]:.1f}"
    if mfg_prev and svc_prev:
        changes = [pmis[0] - mfg_prev['india_mfg_pmi'], pmis[1] - svc_prev['india_svc_pmi']]
        momentum = 'both gaining momentum' if min(changes) > 0 else 'both losing momentum' if max(changes) < 0 else 'momentum diverging'
        evidence += f" ({changes[0]:+.1f} and {changes[1]:+.1f} points; {momentum})"
    evidence += '. '
    latest, prior = latest_pair(iip, 'growth_rate')
    if latest:
        evidence += f"{month_label(latest['month'])} IIP grew {latest['growth_rate']:.1f}% YoY"
        if prior:
            evidence += f", versus {prior['growth_rate']:.1f}% previously"
        evidence += '. '
        if (state == 'Expanding' and latest['growth_rate'] < 0) or (state == 'Contracting' and latest['growth_rate'] > 0):
            state = 'Mixed'
    month = industries.get('latest_month')
    valid, accelerating = [], []
    if month:
        for row in industries.get('rows', []):
            cells = {c['month']: c['value'] for c in row['cells'] if number(c.get('value'))}
            if month in cells:
                valid.append(cells[month])
                if previous_month(month) in cells:
                    accelerating.append(cells[month] - cells[previous_month(month)])
        if valid:
            evidence += f"{month_label(month)}: {sum(v > 0 for v in valid)}/{len(valid)} manufacturing industries expanded"
            if accelerating:
                evidence += f", and growth accelerated in {sum(v > .05 for v in accelerating)}/{len(accelerating)}"
            evidence += '.'
    return answer(state, evidence.strip())


def india_inflation(derived, items):
    if not derived:
        return answer('Awaiting data', 'Validated CPI contributions are unavailable.')
    latest = derived[-1]
    month = latest['month']
    previous = next((r for r in derived if r['month'] == previous_month(month)), None)
    headline = float(latest['published_headline'])
    evidence = f"{month_label(month)} headline CPI {headline:.2f}%"
    change = headline - float(previous['published_headline']) if previous else None
    if change is not None:
        evidence += f" ({change:+.2f} pp from the prior month)"
    drivers = sorted(latest['buckets'].items(), key=lambda kv: float(kv[1]), reverse=True)[:2]
    evidence += '. Largest weighted contributions: ' + ', '.join(f'{name} {float(value):+.2f} pp' for name, value in drivers) + '. '
    current = {r['item_code']: r for r in items if r['month_key'] == month and number(r.get('yoy'))}
    prior = {r['item_code']: r for r in items if r['month_key'] == previous_month(month) and number(r.get('yoy'))}
    matched = [float(r['yoy']) - float(prior[k]['yoy']) for k, r in current.items() if k in prior]
    state = 'Awaiting data'
    if current:
        evidence += f"Prices were above a year earlier in {sum(r['yoy'] > 0 for r in current.values())}/{len(current)} items. "
    if len(matched) >= .8 * len(current) and matched:
        rising, easing = sum(v > .05 for v in matched), sum(v < -.05 for v in matched)
        state = direction(matched, 'Broadening', 'Cooling', tolerance=.05)
        evidence += f"YoY inflation accelerated in {rising}/{len(matched)} matched items and eased in {easing}. "
        if change is not None and ((state == 'Broadening' and change < -.05) or (state == 'Cooling' and change > .05)):
            state = 'Mixed'
            evidence += 'Headline and item breadth diverge. '
    else:
        evidence += 'Insufficient matched item coverage to judge acceleration. '
    evidence += 'Item counts are unweighted.'
    return answer(state, evidence)
