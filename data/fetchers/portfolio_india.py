"""Explicit snapshot preparation. No NSE/AMFI automated downloads or UI I/O."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import json
import hashlib
import os
import shutil
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from data.paths import PORTFOLIO_INDIA_STORE_DIR, INDIA_EQUITY_TRI
from config.portfolio_india_settings import ETFS, FOREIGN, INDEX_IDS
from config.india_equity_matrix import INDICES
from data.processors.india_equity_matrix import validate_series
from data.fetchers.portfolio_prices import validate_history, snapshot_path, load_bundle, source_epoch, closed_history


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect():
    """Yahoo/Fed only. Each raw response is retained for validation."""
    import yfinance as yf
    from data.fetchers.fred_fetcher import FredFetcher
    root=PORTFOLIO_INDIA_STORE_DIR/'inputs';root.mkdir(parents=True,exist_ok=True)
    for ticker in ETFS:
        asset=yf.Ticker(ticker)
        frame=asset.history(period='max',auto_adjust=False,actions=True,raise_errors=True)
        frame,excluded=closed_history(frame,'Asia/Kolkata')
        if excluded:
            print(f'{ticker}: omitted incomplete trailing price rows: {", ".join(excluded)}',flush=True)
        frame,err=validate_history(ticker,frame)
        meta=asset.get_history_metadata()
        if meta.get('currency')!='INR' or meta.get('symbol')!=ticker or meta.get('instrumentType') not in ('ETF','EQUITY') or 'ETF' not in meta.get('longName','').upper():
            raise ValueError('Indian ETF source identity failed: '+str({k:meta.get(k) for k in ['symbol','currency','instrumentType','longName']}))
        frame.to_csv(root/(ticker+'.csv'),index_label='Date')
        (root/(ticker+'.json')).write_text(json.dumps(dict(currency=meta['currency'],symbol=meta['symbol'],
            instrumentType=meta['instrumentType'],longName=meta.get('longName'),firstTradeDate=source_epoch(meta.get('firstTradeDate')),
            excluded_unpriced_sessions=excluded,
            retrieved_utc=datetime.now(timezone.utc).isoformat(),adjustment_error=err),indent=2))
        print(ticker,len(frame),str(frame.index[0].date()),str(frame.index[-1].date()),flush=True)
    from config.settings import FRED_API_KEY
    fx=FredFetcher(api_key=FRED_API_KEY).fetch_series('DEXINUS',period_years=30).dropna().sort_index()
    if fx.empty or fx.index.duplicated().any() or not np.isfinite(fx).all() or (fx<=0).any():
        raise ValueError('Invalid Fed H.10 INR per USD')
    fx.rename('value').to_csv(root/'DEXINUS.csv',index_label='Date')
    print('DEXINUS',len(fx),fx.index[0],fx.index[-1],flush=True)


def prepare():
    from data.processors.portfolio_currency import weekly_reference_panel
    root=PORTFOLIO_INDIA_STORE_DIR;inputs=root/'inputs'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    bundle=root/stamp;bundle.mkdir(parents=True,exist_ok=False)
    raw_dir=bundle/'raw';raw_dir.mkdir()
    shutil.copy2(INDIA_EQUITY_TRI,raw_dir/'nse_tri.json')
    snapshot=json.loads(INDIA_EQUITY_TRI.read_text())
    if snapshot.get('currency')!='INR' or snapshot.get('return_method')!='official NSE gross total-return index':
        raise ValueError('Official INR gross TRI source required')
    specs={s['id']:s for s in INDICES};histories={};meta={};receipts={}
    for entry in snapshot['series']:
        key=entry['id']
        if key not in INDEX_IDS:continue
        histories[key]=validate_series(entry,specs[key],snapshot['as_of'])
        meta[key]=dict(name=entry['label']+' TRI',kind='Index benchmark',asset_class='Indian equity benchmark',
            currency='INR',source=snapshot['source_url'],return_convention='Official gross total-return index',
            inception='Not independently certified; observed/back-cast history is not fund inception')
    if set(INDEX_IDS)-set(histories):raise ValueError('Required official benchmark unavailable')
    for ticker,(name,group,isin) in ETFS.items():
        path=inputs/(ticker+'.csv')
        shutil.copy2(path,raw_dir/path.name)
        shutil.copy2(inputs/(ticker+'.json'),raw_dir/(ticker+'.json'))
        frame=pd.read_csv(path,index_col='Date',parse_dates=True)
        frame,_=validate_history(ticker,frame)
        frame=frame.loc[frame.index<pd.Timestamp.now(tz='Asia/Kolkata').tz_localize(None).normalize()]
        identity=json.loads((inputs/(ticker+'.json')).read_text())
        if identity.get('symbol')!=ticker or identity.get('currency')!='INR' or identity.get('instrumentType') not in ('ETF','EQUITY') or 'ETF' not in identity.get('longName','').upper():
            raise ValueError('ETF evidence mismatch')
        histories[ticker]=frame['Adj Close'];receipts['raw/'+path.name]=digest(raw_dir/path.name)
        meta[ticker]=dict(name=name,kind='Indian ETF',asset_class=group,currency='INR',isin=isin,
            issuer_inception='2021-04-05' if ticker=='GILT5YBEES.NS' else 'Not independently certified; first observed date is used',
            source='Yahoo Finance via yfinance',return_convention='Explicit split/distribution-adjusted market close, not fund NAV',
            mean_volume_60=float(frame.Volume.tail(60).mean()),zero_volume_fraction=float(frame.Volume.eq(0).mean()),
            inception='First observed close only; no prehistory stitching',identity=identity)
    global_path=snapshot_path();global_prices,global_meta=load_bundle(global_path)
    for ticker in FOREIGN:
        histories[ticker]=global_prices[ticker].dropna()
        meta[ticker]=dict(name=global_meta['assets'][ticker]['name'],kind='Foreign-listed ETF',asset_class=global_meta['assets'][ticker]['asset_class'],
            currency='USD',source='Yahoo Finance via validated Global bundle '+global_path.name,
            return_convention='Explicit adjusted USD close × publication-lagged Fed INR/USD reference')
    fx=pd.read_csv(inputs/'DEXINUS.csv',index_col='Date',parse_dates=True)['value']
    panel,local,fx_marks,evidence=weekly_reference_panel(histories,meta,fx)
    for key,series in histories.items():
        file=bundle/(key+'.csv');series.rename('value').to_csv(file,index_label='Date')
        meta[key].update(first=str(series.index[0].date()),last=str(series.index[-1].date()),observations=len(series),sha256=digest(file))
    fx.rename('value').to_csv(bundle/'DEXINUS.csv',index_label='Date')
    panel.to_csv(bundle/'prices.csv',index_label='Date');local.to_csv(bundle/'local.csv',index_label='Date')
    fx_marks.to_csv(bundle/'fx.csv',index_label='Date');evidence.to_csv(bundle/'alignment.csv',index=False)
    manifest=dict(schema=1,retrieved_utc=datetime.now(timezone.utc).isoformat(),assets=meta,source_receipts=receipts,
        nse_snapshot_sha256=digest(INDIA_EQUITY_TRI),fx_source='Federal Reserve H.10 / FRED DEXINUS',
        fx_first=str(fx.index[0].date()),fx_latest=str(fx.index[-1].date()),fx_observations=len(fx),
        fx_availability_note='Scheduled weekly releases with federal-holiday adjustment; actual vintage-by-vintage release receipts are not available. Revised-history reference research, not a point-in-time execution strategy.',
        fx_convention='INR per USD; noon New York fixing, weekly public release',frequency='weekly',
        publication='Public Portfolio Lab snapshot',
        files={p.relative_to(bundle).as_posix():digest(p) for p in bundle.rglob('*') if p.is_file()})
    (bundle/'manifest.json').write_text(json.dumps(manifest,indent=2))
    load(bundle)
    temp=root/'CURRENT.tmp';temp.write_text(stamp);os.replace(str(temp),str(root/'CURRENT'))
    print('Validated INR snapshot:',bundle,flush=True)
    return bundle


def current():
    from portfolio_lab.deployment import active_root
    root = active_root(PORTFOLIO_INDIA_STORE_DIR.parent) / 'india'
    name=(root/'CURRENT').read_text().strip()
    if Path(name).name!=name or name in ('','.', '..'):raise ValueError('Invalid INR snapshot pointer')
    return root/name


def manifest_path(name):
    """Read legacy Windows receipts on Linux; write new receipts with POSIX paths."""
    relative = PurePosixPath(name.replace('\\', '/'))
    if relative.is_absolute() or PureWindowsPath(name).drive or '..' in relative.parts or not relative.parts:
        raise ValueError('Invalid INR bundle file path')
    return relative


def load(bundle):
    bundle=Path(bundle);m=json.loads((bundle/'manifest.json').read_text())
    if m.get('schema')!=1:raise ValueError('Invalid INR source schema')
    for name,sha in m['files'].items():
        if digest(bundle.joinpath(*manifest_path(name).parts))!=sha:raise ValueError('INR bundle checksum mismatch')
    if set(m['assets'])!=set(INDEX_IDS+list(ETFS)+FOREIGN):raise ValueError('Unapproved INR universe')
    for key,meta in m['assets'].items():
        expected_currency='USD' if key in FOREIGN else 'INR'
        expected_kind='Foreign-listed ETF' if key in FOREIGN else 'Indian ETF' if key in ETFS else 'Index benchmark'
        if meta['currency']!=expected_currency or meta['kind']!=expected_kind:raise ValueError('Instrument type/currency mismatch')
        if key in ETFS and meta.get('isin')!=ETFS[key][2]:raise ValueError('ETF ISIN identity mismatch')
    histories={key:pd.read_csv(bundle/(key+'.csv'),index_col='Date',parse_dates=True)['value'] for key in m['assets']}
    fx=pd.read_csv(bundle/'DEXINUS.csv',index_col='Date',parse_dates=True)['value']
    from data.processors.portfolio_currency import weekly_reference_panel
    rebuilt,local,fx_marks,evidence=weekly_reference_panel(histories,m['assets'],fx)
    saved=pd.read_csv(bundle/'prices.csv',index_col='Date',parse_dates=True)
    pd.testing.assert_frame_equal(saved,rebuilt,check_freq=False,rtol=1e-12)
    return rebuilt,local,fx_marks,m


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--collect',action='store_true');p.add_argument('--prepare',action='store_true');a=p.parse_args()
    if a.collect:collect()
    if a.prepare:prepare()
