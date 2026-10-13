"""GST growth from exact official monthly amounts on a consistent cess basis."""
from pathlib import Path

import pandas as pd

DEFAULT_GST = Path(__file__).resolve().parents[1] / 'inputs/gst/gst_monthly.csv'


def load_gst_growth(path=DEFAULT_GST):
    data = pd.read_csv(path)
    data['date'] = pd.to_datetime(data['month'], format='%Y-%m')
    if data['date'].duplicated().any():
        raise ValueError('GST data contains duplicate months')
    if not data['basis'].eq('excluding_compensation_cess').all():
        raise ValueError('GST amounts must consistently exclude compensation cess')
    for field in ('gross_gst_crore', 'net_gst_crore', 'refunds_crore'):
        data[field] = pd.to_numeric(data[field], errors='raise')
        if data[field].isna().any() or (data[field] < 0).any():
            raise ValueError(f'GST {field} must contain non-negative amounts')
    if (data['gross_gst_crore'] <= 0).any() or (data['net_gst_crore'] <= 0).any():
        raise ValueError('Gross and net GST must be positive')
    # Official totals are independently rounded to crore.
    if ((data.gross_gst_crore - data.refunds_crore - data.net_gst_crore).abs() > 2).any():
        raise ValueError('GST gross less refunds does not reconcile to net')
    data = data.sort_values('date').set_index('date')
    latest = data.index.max()
    required = pd.date_range(latest - pd.DateOffset(months=23), latest, freq='MS')
    missing = required.difference(data.index)
    if len(missing):
        raise ValueError('Missing GST months: ' + ', '.join(missing.strftime('%Y-%m')))
    current = data.loc[required[-12:]].copy()
    prior = data.reindex(current.index - pd.DateOffset(years=1))
    for kind in ('gross', 'net'):
        field = f'{kind}_gst_crore'
        current[f'{kind}_yoy'] = (current[field].to_numpy() / prior[field].to_numpy() - 1) * 100
    return current.reset_index(names='date')
