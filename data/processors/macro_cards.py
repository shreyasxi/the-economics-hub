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


def answer(state, evidence, metrics=None, conclusion='', observation_date=None):
    return dict(state=state, evidence=evidence, metrics=metrics or [], context='',
                conclusion=conclusion, observation_date=observation_date)


def market_risk(inputs):
    from data.processors.market_regime import EQUITIES, CREDIT
    rows = inputs.get('rows', {})
    equities = [rows[k] for k in EQUITIES if k in rows and all(number(rows[k].get(f)) for f in ('quarter', 'month'))]
    credit = [rows[k] for k in CREDIT if k in rows and all(number(rows[k].get(f)) for f in ('quarter', 'month'))]
    vol = rows.get('vix')
    if len(equities) < 6 or len(credit) < 2 or not vol or not all(number(vol.get(f)) for f in ('median_20d', 'percentile', 'month_change_pct')):
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
    rising = sum(r['quarter'] > 1 for r in equities)
    narrowing = sum(r['quarter'] < -5 for r in credit)
    widening = sum(r['quarter'] > 5 for r in credit)
    credit_count, credit_verb = (widening, 'widened') if widening > narrowing else (narrowing, 'narrowed')
    vol_context = 'low' if vol['percentile'] <= 50 else 'elevated' if vol['percentile'] >= 75 else 'mid-range'
    evidence = (f"Three-month gains currently exceed 1% in {rising}/{len(equities)} equity markets; "
                f"{credit_count}/{len(credit)} credit spreads have {credit_verb} by over 5 bp. "
                f"VIX’s 20-session median is {vol['median_20d']:.1f} ({vol_context} versus its past year). "
                f"One-month signals are {momentum}. ")
    # Commodity price direction alone cannot identify demand or risk appetite.
    conclusion = {'Risk-on': 'Equities, credit and volatility favour risk taking.',
                  'Risk-off': 'Equities, credit and volatility favour caution.',
                  'Mixed': 'Equities, credit and volatility do not agree.'}[state]
    return answer(state, evidence.strip(), [dict(pillar=name,state=value) for name,value in
                                           zip(('equities','credit','volatility'),pillars)],
                  conclusion, inputs['as_of'])


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
        return answer('Awaiting data', 'Comparable country inflation observations are unavailable.')
    month, baseline = breadth['month'], breadth['comparison_month']
    labels = {'USA': 'US', 'EA': 'euro area', 'CHN': 'China',
              'JPN': 'Japan', 'GBR': 'UK', 'IND': 'India'}
    countries = {c['code']: c for c in report.get('countries', []) if c.get('code') in labels}
    head = []
    for code, label in labels.items():
        series = {r['month']: r for r in countries.get(code, {}).get('series', {}).get('headline', [])
                  if number(r.get('value'))}
        if month not in series or baseline not in series:
            continue
        if series[month].get('classification') != series[baseline].get('classification'):
            continue
        head.append(dict(country=code, label=label, measure='headline', period=month,
                         comparison_month=baseline, value=series[month]['value'],
                         change=series[month]['value'] - series[baseline]['value']))

    def verdict(metrics):
        changes = [m['change'] for m in metrics]
        if any(v > .05 for v in changes) and any(v < -.05 for v in changes):
            return 'Mixed'
        return direction(changes, 'Building', 'Easing', tolerance=.05)

    def description(metrics):
        clauses = []
        for verb, predicate in [('rose', lambda v: v > .05), ('eased', lambda v: v < -.05),
                                ('was little changed', lambda v: abs(v) <= .05)]:
            names = [m['label'] for m in metrics if predicate(m['change'])]
            if names:
                clauses.append(f"{verb} in {' / '.join(names)}")
        return '; '.join(clauses)

    broad = inflation_breadth(report, 'headline', month, baseline)
    core = inflation_breadth(report, 'core', month, baseline)
    complete = broad['total'] and broad['matched'] / broad['total'] >= .8
    state = verdict([dict(change=v) for v in broad['changes']]) if complete else 'Awaiting data'
    evidence = (f"{month_label(month)} vs {month_label(baseline)}: headline inflation eased in "
                f"{broad['easing']}/{broad['matched']} countries and rose in {broad['rising']}. ")
    if core['total'] and core['matched'] / core['total'] >= .8:
        evidence += f"Core rose in {core['rising']}/{core['matched']} and eased in {core['easing']}. "
        core_state = verdict([dict(change=v) for v in core['changes']])
        if state in ('Building', 'Easing') and core_state in ('Mixed', 'Building', 'Easing') and core_state != state:
            state = 'Mixed'
    else:
        evidence += 'Broad core comparisons are limited. '
    if not complete:
        evidence += 'Insufficient matched country headline coverage. '
    major_state = verdict(head)
    if len(head) != len(labels):
        state = 'Awaiting data'
    elif state in ('Building', 'Easing') and major_state != state:
        state = 'Mixed'
    evidence += 'Major-economy headline ' + description(head) + '. ' if head else 'Major-economy headline comparisons unavailable. '
    if len(head) != len(labels):
        missing_head = [label for code, label in labels.items() if code not in {m['country'] for m in head}]
        evidence += 'Headline comparisons unavailable for ' + ' / '.join(missing_head) + '.'
    conclusion = {'Building': 'Headline inflation is rising across the countries reviewed.',
                  'Easing': 'Headline inflation is easing across the countries reviewed.',
                  'Mixed': 'Broad country inflation and major-economy trends are uneven.',
                  'Awaiting data': 'Comparable country readings are needed for an assessment.'}[state]
    return answer(state, evidence.strip(), head, conclusion, month + '-01')


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
    if latest and latest['month'][:7] < previous_month(mfg['month'], 3):
        latest, prior = None, None
    if latest:
        evidence += f"{month_label(latest['month'])} IIP grew {latest['growth_rate']:.1f}% YoY"
        if prior:
            evidence += f", versus {prior['growth_rate']:.1f}% previously"
        evidence += '. '
        if (state == 'Expanding' and latest['growth_rate'] < 0) or (state == 'Contracting' and latest['growth_rate'] > 0):
            state = 'Mixed'
    month = industries.get('latest_month')
    valid, accelerating = [], []
    if month and previous_month(mfg['month'], 3) <= month[:7] <= mfg['month'][:7]:
        for row in industries.get('rows', []):
            cells = {c['month']: c['value'] for c in row['cells'] if number(c.get('value'))}
            if month in cells:
                valid.append(cells[month])
                if previous_month(month) in cells:
                    accelerating.append(cells[month] - cells[previous_month(month)])
        if valid:
            evidence += f"{month_label(month)}: {sum(v > 0 for v in valid)}/{len(valid)} manufacturing industries expanded YoY"
            if accelerating:
                evidence += f", and growth accelerated in {sum(v > .05 for v in accelerating)}/{len(accelerating)}"
            evidence += '.'
    if not latest:
        evidence += ' Industrial production evidence unavailable.'
    if not valid:
        evidence += ' Manufacturing breadth unavailable.'
    conclusion = {'Expanding': 'Both PMI surveys indicate expansion in activity.',
                  'Contracting': 'Both PMI surveys indicate contraction in activity.',
                  'Mixed': 'PMI and output signals give an uneven activity picture.'}[state]
    return answer(state, evidence.strip(), conclusion=conclusion, observation_date=mfg['month'][:7] + '-01')


def india_inflation(derived, items):
    if not derived:
        return answer('Awaiting data', 'Validated CPI contributions are unavailable.')
    latest = max(derived, key=lambda row: row['month'])
    month = latest['month']
    previous = next((r for r in derived if r['month'] == previous_month(month)), None)
    headline = float(latest['published_headline'])
    evidence = f"{month_label(month)} headline CPI {headline:.2f}%"
    change = headline - float(previous['published_headline']) if previous else None
    if change is not None:
        evidence += f" ({change:+.2f} pp from the prior month)"
    drivers = sorted(latest['buckets'].items(), key=lambda kv: float(kv[1]), reverse=True)[:2]
    evidence += '. Weighted contributions: ' + ', '.join(f'{name} {float(value):+.2f} pp' for name, value in drivers) + '. '
    current = {r['item_code']: r for r in items if r['month_key'] == month and number(r.get('yoy'))}
    prior = {r['item_code']: r for r in items if r['month_key'] == previous_month(month) and number(r.get('yoy'))}
    matched = [float(r['yoy']) - float(prior[k]['yoy']) for k, r in current.items() if k in prior and all(r.get(field) == prior[k].get(field) for field in ('base_year', 'series', 'sector', 'state', 'item_name'))]
    state = 'Awaiting data'
    if current:
        evidence += f"Positive YoY inflation in {sum(r['yoy'] > 0 for r in current.values())}/{len(current)} items. "
    if len(matched) >= .8 * len(current) and matched:
        rising, easing = sum(v > .05 for v in matched), sum(v < -.05 for v in matched)
        state = direction(matched, 'Broadening', 'Cooling', tolerance=.05)
        evidence += f"YoY inflation accelerated in {rising}/{len(matched)} matched items"
        if state != 'Broadening':
            evidence += f", and eased in {easing}"
        evidence += '. '
        if change is not None and ((state == 'Broadening' and change < -.05) or (state == 'Cooling' and change > .05)):
            state = 'Mixed'
            evidence += 'Headline and item breadth diverge. '
    else:
        evidence += 'Insufficient matched item coverage to judge acceleration. '
    evidence += 'Item counts are unweighted; same-base comparisons only.'
    conclusion = {'Broadening': 'Inflation is accelerating across more matched items.',
                  'Cooling': 'Inflation is easing across more matched items.',
                  'Mixed': 'Headline and item-level inflation give a mixed picture.',
                  'Awaiting data': 'Item-level acceleration cannot yet be assessed.'}[state]
    return answer(state, evidence, conclusion=conclusion, observation_date=month + '-01')


def dated_card(card, today, max_age, refresh_failed=False):
    """Expose retained / overdue evidence without relabelling it as current."""
    result = dict(card)
    observation = card.get('observation_date')
    try:
        age = (today - datetime.strptime(observation, '%Y-%m-%d').date()).days
        stale = age < 0 or age > max_age
    except (TypeError, ValueError):
        stale = True
    if stale or refresh_failed:
        result.update(state='Awaiting data', conclusion='A current assessment needs refreshed evidence.',
                      evidence=('Refresh incomplete. ' if refresh_failed else 'Older or undated snapshot. ') +
                      (f"Observation: {observation}. " if observation else '') + card['evidence'].replace('currently ', ''))
    return result


def commodities(inputs):
    """Combine trend participation, price direction and Brent energy pressure."""
    members = inputs.get('members', [])
    rows = inputs.get('rows', {})
    if len(members) < 12 or not all(k in rows and all(number(rows[k].get(f)) for f in ('quarter','month'))
                                   for k in ('brent','copper','gold')):
        return answer('Awaiting data', 'Comparable commodity breadth and Brent, copper and gold prices are incomplete.',
                      conclusion='The commodity assessment needs broader dated coverage.')
    above = sum(m['above_200d'] for m in members)
    previous = sum(m['previous_above_200d'] for m in members)
    total = len(members)
    breadth = 'Broad' if above / total >= 2/3 else 'Narrow' if above / total <= 1/3 else 'Mixed'
    price_state = direction([rows[k]['quarter'] for k in ('brent','copper','gold')], 'Rising','Falling', tolerance=1)
    brent = rows['brent']
    energy = ('rising' if brent['quarter'] > 1 and brent['month'] > 1 else
              'easing' if brent['quarter'] < -1 and brent['month'] < -1 else 'uneven')
    state = ('Broad gains' if breadth == 'Broad' and above >= previous and price_state == 'Rising' and energy == 'rising' else
             'Broad declines' if breadth == 'Narrow' and above <= previous and price_state == 'Falling' and energy == 'easing' else 'Mixed')
    trend = {'Broad': 'Commodity uptrends are widespread', 'Narrow': 'Commodity uptrends are concentrated',
             'Mixed': 'Commodity trend participation is uneven'}[breadth]
    conclusion = trend + {'rising': '; Brent adds energy cost pressure.',
                          'easing': '; Brent eases energy cost pressure.',
                          'uneven': '; Brent’s recent direction is uneven.'}[energy]
    evidence = (f"{above}/{total} futures are currently above their 200-day averages "
                f"({previous}/{total} a month earlier). Three-month prices: Brent {brent['quarter']:+.1f}%, "
                f"copper {rows['copper']['quarter']:+.1f}%, gold {rows['gold']['quarter']:+.1f}%. "
                f"Brent moved {brent['month']:+.1f}% over one month. Futures moves do not establish demand or CPI pass-through.")
    curve = inputs.get('oil_curve', {})
    curve_valid = (curve.get('as_of') == inputs['as_of'] and
                   all(number(curve.get(k)) for k in ('spread', 'previous_spread')) and
                   curve.get('observation') and curve.get('comparison_date') and
                   len(curve.get('contracts', [])) == 2)
    if curve_valid:
        try:
            cutoff = datetime.strptime(inputs['as_of'], '%Y-%m-%d')
            import calendar
            prior_month = previous_month(inputs['as_of'])
            year, month = map(int, prior_month.split('-'))
            baseline = datetime(year, month, min(cutoff.day, calendar.monthrange(year, month)[1]))
            current_date = datetime.strptime(curve['observation'], '%Y-%m-%d')
            prior_date = datetime.strptime(curve['comparison_date'], '%Y-%m-%d')
            curve_valid = 0 <= (cutoff-current_date).days <= 4 and 0 <= (baseline-prior_date).days <= 4
        except (TypeError, ValueError):
            curve_valid = False
    evidence = evidence.replace('Futures moves do not establish demand or CPI pass-through.', '')
    if curve_valid:
        spread, prior_spread = curve['spread'], curve['previous_spread']
        change = spread - prior_spread
        curve_state = 'Backwardation' if spread > .25 else 'Contango' if spread < -.25 else 'Flat'
        # Curve evidence replaces the extra monthly price sentence, not an ever-longer list.
        evidence = evidence.replace(f"Brent moved {brent['month']:+.1f}% over one month. ", '')
        evidence += (f"WTI near–six-month spread {spread:+.2f} $/bbl "
                     f"({prior_spread:+.2f} a month earlier). ")
        if curve_state == 'Backwardation':
            movement = 'narrowed' if change < -.25 else 'widened' if change > .25 else 'held steady'
            evidence += f"Backwardation {movement}, suggesting {'less' if change < -.25 else 'greater' if change > .25 else 'persistent'} prompt tightness."
            conclusion = trend + f"; oil’s prompt premium has {movement}."
            if (energy == 'rising' and change < -.25) or energy == 'easing':
                state = 'Mixed'
        elif curve_state == 'Contango':
            evidence += 'Deferred oil costs more; no prompt premium.'
            conclusion = trend + '; the WTI curve shows no prompt premium.'
            if energy == 'rising':
                state = 'Mixed'
        else:
            evidence += 'The near-to-deferred curve is broadly flat.'
            conclusion = trend + '; the oil curve gives no clear tightness signal.'
        if curve['observation'] != inputs['as_of']:
            evidence += f" Curve observed {datetime.strptime(curve['observation'], '%Y-%m-%d').strftime('%d %b %Y')}."
    else:
        curve_state = 'Unavailable'
        evidence += 'Oil curve unavailable; prices alone do not establish demand or CPI pass-through.'
    return answer(state, evidence, [dict(pillar='breadth', state=breadth), dict(pillar='prices',state=price_state),
                                   dict(pillar='energy',state=energy), dict(pillar='oil_curve',state=curve_state)],
                  conclusion, inputs['as_of'])
