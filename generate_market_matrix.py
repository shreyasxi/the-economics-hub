#!/usr/bin/env python3
"""Generate a same-edition matrix; no cached prior observations are reused."""
import argparse
import json
from pathlib import Path
import pandas as pd
from data.processors.market_matrix import build
from data.fetchers.yfinance_fetcher import YFinanceFetcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = args.out
    if out is None:
        weekly = root/'output/weekly'
        editions = sorted(p for p in weekly.iterdir() if p.is_dir() and any(p.glob('*.png'))) if weekly.is_dir() else []
        out = editions[-1] if editions else None
    if out is None or not out.is_dir() or not any(out.glob('*.png')):
        parser.error('Use an existing Weekly chart edition directory')
    edition = pd.Timestamp(out.name)
    today = pd.Timestamp.now(tz='Asia/Kolkata').date()
    # Saturday editions are generated that Saturday, after Friday's close.
    # A current weekday cutoff could include an uncompleted Yahoo session.
    if edition.date() > today:
        parser.error('Use an edition dated today or earlier')
    # Manual weekday runs still publish to today's edition, but only use
    # observations through yesterday; today's session may be incomplete.
    cutoff = edition
    if edition.date() == today and edition.weekday() < 5:
        cutoff = edition - pd.Timedelta(days=1)
    target = out/'market_matrix.json'
    try:
        from data.fetchers.nse_tri import NiftyTRIFetcher
        payload = build(YFinanceFetcher(), cutoff, nse_fetcher=NiftyTRIFetcher(
            audit_dir=out/'market_matrix_sources'/'nse_tri'))
        payload['as_of'] = str(edition.date())
        payload['observation_cutoff'] = str(cutoff.date())
    except Exception as exc:
        # A failed rerun must not leave a prior successful payload publishable.
        target.unlink(missing_ok=True)
        print('MATRIX FAILED:', exc)
        return 1
    temp = target.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n')
    temp.replace(target)
    for group in payload['groups']:
        for row in group['rows']:
            print(row['ticker_or_series'], row['latest_date'], row['history_start'], '5Y:', row['returns']['5Y'])
    print('Left out:', payload['left_out'])
    print('Written:', target)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
