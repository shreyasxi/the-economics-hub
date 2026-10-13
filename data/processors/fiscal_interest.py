"""Validated annual and cumulative monthly Union-government interest burden."""
from pathlib import Path
import numpy as np
import pandas as pd

INPUTS = Path(__file__).resolve().parents[1] / 'inputs'
ANNUAL = INPUTS / 'fiscal_interest/annual.csv'
MONTHLY = INPUTS / 'cag/cag_manual_accounts.csv'


def _ratio(frame):
    for field in ('interest_payments', 'revenue_receipts'):
        frame[field] = pd.to_numeric(frame[field], errors='raise')
        if not np.isfinite(frame[field]).all():
            raise ValueError(f'Missing or invalid fiscal interest {field}')
    if (frame.interest_payments < 0).any() or (frame.revenue_receipts <= 0).any():
        raise ValueError('Interest must be non-negative and revenue receipts positive')
    frame['interest_share'] = frame.interest_payments / frame.revenue_receipts * 100
    return frame


def load_interest_data(annual_path=ANNUAL, monthly_path=MONTHLY):
    annual = pd.read_csv(annual_path)
    if annual.fy.duplicated().any() or not annual.status.isin(['Actual', 'Provisional']).all():
        raise ValueError('Duplicate annual fiscal year or invalid actuals status')
    annual = _ratio(annual).sort_values('fy')
    manual = pd.read_csv(monthly_path, comment='#', dtype={'fy': str})
    fy = manual.loc[~manual.month.isin(['BE', 'RE']), 'fy'].max()
    rows = manual[manual.fy == fy].copy()
    if rows.month.duplicated().any():
        raise ValueError('Duplicate current-year fiscal interest month')
    budget = rows[rows.month == 'BE'].copy()
    monthly = rows[~rows.month.isin(['BE', 'RE'])].copy()
    if budget.empty or monthly.empty:
        raise ValueError('Interest chart needs current-year monthly and Budget rows')
    for frame in (monthly, budget):
        for field in ('net_tax_revenue', 'non_tax_revenue'):
            frame[field] = pd.to_numeric(frame[field], errors='raise')
        frame['revenue_receipts'] = frame.net_tax_revenue + frame.non_tax_revenue
        _ratio(frame)
    monthly['date'] = pd.to_datetime(monthly.month, format='%b-%y')
    monthly = monthly.sort_values('date')
    first = pd.Timestamp(f'{fy[:4]}-04-01')
    expected = pd.date_range(first, monthly.date.max(), freq='MS')
    if not monthly.date.tolist() == expected.tolist():
        raise ValueError('Current fiscal trend needs every month from April; no gap filling')
    if monthly.date.max() > first + pd.DateOffset(months=11):
        raise ValueError('Current interest month is outside its fiscal year')
    if (monthly.interest_payments.diff().dropna() < 0).any():
        raise ValueError('Cumulative interest payments fall; verify revision')
    if annual.fy.max() >= fy:
        raise ValueError('Annual actuals overlap the current fiscal-year Budget')
    be = pd.DataFrame([dict(fy=fy, status='Budget',
                            interest_payments=budget.interest_payments.iloc[0],
                            revenue_receipts=budget.revenue_receipts.iloc[0],
                            source_url=budget.revenue_source.iloc[0],
                            interest_share=budget.interest_share.iloc[0])])
    return pd.concat([annual, be], ignore_index=True), monthly.reset_index(drop=True)
