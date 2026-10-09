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
    editions = sorted(p for p in (root/'output/weekly').iterdir() if p.is_dir() and any(p.glob('*.png')))
    out = args.out or (editions[-1] if editions else None)
    if out is None or not out.is_dir() or not any(out.glob('*.png')):
        parser.error('Use an existing Weekly chart edition directory')
    cutoff = pd.Timestamp(out.name)
    today = pd.Timestamp.now(tz='Asia/Kolkata').date()
    # Saturday editions are generated that Saturday, after Friday's close.
    # A current weekday cutoff could include an uncompleted Yahoo session.
    if cutoff.date() > today or (cutoff.date() == today and cutoff.weekday() < 5):
        parser.error('Use a completed trading cutoff (a current Saturday edition is valid)')
    target = out/'market_matrix.json'
    try:
        from data.fetchers.nse_tri import NiftyTRIFetcher
        payload = build(YFinanceFetcher(), cutoff, nse_fetcher=NiftyTRIFetcher(
            audit_dir=out/'market_matrix_sources'/'nse_tri'))
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
