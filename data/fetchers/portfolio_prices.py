"""Prepare validated Yahoo histories; UI loads only validated local snapshots.

No remote calls occur on page rendering. Preparation is explicit and writes an
immutable bundle before replacing the CURRENT pointer atomically.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
import shutil

import numpy as np
import pandas as pd

from config.portfolio_settings import ASSETS
from data.paths import PORTFOLIO_STORE_DIR
from data.processors.portfolio_analytics import validate_prices


ADJUSTMENT = "Yahoo explicit Adj Close; split/distribution-adjusted ETF historical-return proxy"


def validate_history(ticker, history):
    required = {"Close", "Adj Close", "Dividends", "Stock Splits"}
    if history.empty or not required.issubset(history):
        raise ValueError(ticker + ": missing explicit prices/corporate-action fields")
    history = history.copy()
    if history.index.tz is not None:
        history.index = history.index.tz_localize(None)
    history.index = history.index.normalize()
    validate_prices(history[["Close", "Adj Close"]])
    if history[list(required)].isna().any().any():
        raise ValueError(ticker + ": missing price/action observations")
    actions = history[["Dividends", "Stock Splits"]].to_numpy(dtype=float)
    if not np.isfinite(actions).all() or (actions < 0).any():
        raise ValueError(ticker + ": invalid corporate actions")
    # Yahoo Close is already split-adjusted. Adjustment-factor changes must
    # reconcile to its backward dividend multiplier, NOT add dividends again.
    factor = history["Adj Close"] / history["Close"]
    expected = 1 / (1-history["Dividends"]/history["Close"].shift(1))
    error = ((factor/factor.shift(1))/expected - 1).iloc[1:].abs()
    if not np.isfinite(error).all() or error.max() > 5e-4:
        raise ValueError(ticker + ": adjustment factors do not reconcile with distributions")
    if ticker == 'USO' and history.index[0] < pd.Timestamp('2020-04-29') <= history.index[-1]:
        if pd.Timestamp('2020-04-29') not in history.index or not np.isclose(history.loc['2020-04-29', 'Stock Splits'], .125):
            raise ValueError('USO: missing issuer-verified 1-for-8 reverse split on 2020-04-29')
        split_return = history['Adj Close'].pct_change(fill_method=None).loc['2020-04-29']
        if abs(split_return) > .5:
            raise ValueError('USO: implausible split-day return; unadjusted series suspected')
    return history, float(error.max())


def prepare(root=PORTFOLIO_STORE_DIR, expand=False):
    import yfinance as yf
    from data.fetchers.yfinance_fetcher import YFinanceFetcher
    root = Path(root)
    bundle = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    bundle.mkdir(parents=True, exist_ok=False)
    fetcher = YFinanceFetcher()
    frames, assets = {}, {}
    if expand:
        old = snapshot_path(root)
        existing, old_manifest = load_bundle(old)
        for ticker, metadata in old_manifest['assets'].items():
            if ticker == 'BTC':
                continue
            shutil.copy2(old/(ticker+'.csv'), bundle/(ticker+'.csv'))
            frames[ticker] = existing[ticker].dropna()
            assets[ticker] = metadata
    for ticker, config in ASSETS.items():
        if ticker == "BTC" or ticker in assets:
            continue
        print("Preparing " + ticker, flush=True)
        history = fetcher._download(ticker, "max", "1d", None, adjusted=True)
        source_ticker = yf.Ticker(ticker)
        identity = source_ticker.get_history_metadata()
        inception = source_ticker.get_info().get("fundInceptionDate")
        if (identity.get("symbol") != ticker or identity.get("currency") != "USD"
                or identity.get("instrumentType") != "ETF"):
            raise ValueError(ticker + ": source ticker/currency/instrument identity mismatch")
        # Do not include an unfinished current session; normalize by exchange date.
        local_today = pd.Timestamp.now(tz="America/New_York").date()
        history = history.loc[history.index.date < local_today]
        history, error = validate_history(ticker, history)
        if inception is not None and pd.Timestamp(inception, unit="s").normalize() > history.index[0]:
            raise ValueError(ticker + ": observed history precedes reported fund inception")
        volume = history["Volume"].tail(60)
        if len(volume) < 60 or not np.isfinite(volume).all() or volume.mean() < 100000:
            raise ValueError(ticker + ": inadequate recent observed trading volume")
        history.to_csv(bundle / (ticker + ".csv"), index_label="Date")
        frames[ticker] = history["Adj Close"]
        assets[ticker] = dict(config, ticker=ticker,
                             first_observation=str(history.index[0].date()),
                             latest_observation=str(history.index[-1].date()),
                             observations=len(history), quality="validated",
                             mean_daily_volume_60=float(volume.mean()),
                             source_first_trade_epoch=identity.get("firstTradeDate"),
                             source_reported_fund_inception=str(pd.Timestamp(inception,unit="s").date()) if inception else None,
                             inception_source="Yahoo fundInceptionDate; distinct from first observed close; not issuer-certified",
                             liquidity_rule="60 observed sessions: mean shares traded >= 100,000; not an execution guarantee",
                             verified_identity={k: identity[k] for k in ("symbol", "currency", "instrumentType")},
                             max_adjustment_factor_error=error,
                             source_url="https://finance.yahoo.com/quote/{}/history/".format(ticker))
    from data.fetchers.portfolio_bitcoin import fetch_bitcoin, align_bitcoin, CONVENTION
    btc = fetch_bitcoin()
    btc.to_csv(bundle/'BTC.csv', index=False)
    # Session union preserves individual ETF omissions for existing safeguards;
    # BTC evaluated only on observed SPY sessions, never creating weekend rows.
    frames['BTC'], evidence = align_bitcoin(btc, frames['SPY'].index)
    evidence.to_csv(bundle/'BTC_alignment.csv', index_label='Date')
    observed = frames['BTC'].dropna()
    assets['BTC'] = dict(ASSETS['BTC'], ticker='BTC', quality='validated',
        first_observation=str(observed.index[0].date()), latest_observation=str(observed.index[-1].date()),
        observations=len(observed), raw_first_label=btc.time.iloc[0].isoformat(),
        raw_latest_label=btc.time.iloc[-1].isoformat(), raw_observations=len(btc),
        fixing_convention='PriceUSD end of labelled UTC day; effective at label + one day',
        valuation_convention=CONVENTION,
        verified_identity={'asset':'btc', 'metric':'PriceUSD', 'currency':'USD'},
        license='Coin Metrics Community CC BY-NC 4.0; attribution and noncommercial condition',
        source_url='https://community-api.coinmetrics.io/v4/timeseries/asset-metrics')
    prices = pd.DataFrame(frames).sort_index()
    validate_prices(prices)
    prices.to_csv(bundle / "prices.csv", index_label="Date")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.glob("*.csv")}
    manifest = {"schema": 2, "valuation_convention": CONVENTION, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "source": "Yahoo Finance via yfinance + Coin Metrics Community PriceUSD", "yfinance_version": yf.__version__,
                "adjustment": ADJUSTMENT, "assets": assets, "sha256": hashes,
                "publication_status": "Public Portfolio Lab snapshot"}
    (bundle/"manifest.json").write_text(json.dumps(manifest, indent=2))
    # Read and verify the entire bundle before activation.
    load_bundle(bundle)
    pointer = root / ("CURRENT-" + uuid.uuid4().hex + ".tmp")
    pointer.write_text(bundle.name)
    os.replace(str(pointer), str(root/"CURRENT"))
    print("Validated snapshot: " + str(bundle), flush=True)
    return bundle


def snapshot_path(root=PORTFOLIO_STORE_DIR):
    from portfolio_lab.deployment import active_root
    root = active_root(root)
    pointer = root/"CURRENT"
    if not pointer.exists():
        raise ValueError("No prepared portfolio data. Run .venv/bin/python -m data.fetchers.portfolio_prices --prepare locally.")
    name = pointer.read_text().strip()
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("Invalid snapshot pointer.")
    return root/name


def load_bundle(bundle):
    bundle = Path(bundle)
    manifest = json.loads((bundle/"manifest.json").read_text())
    if manifest.get("schema") not in (1, 2) or not manifest.get("assets") or not set(manifest["assets"]).issubset(ASSETS):
        raise ValueError("Unsupported portfolio manifest/universe.")
    if manifest.get("adjustment") != ADJUSTMENT:
        raise ValueError("Unsupported return-adjustment convention.")
    for name in ["prices.csv"] + [t + ".csv" for t in manifest["assets"]] + (["BTC_alignment.csv"] if "BTC" in manifest["assets"] else []):
        if hashlib.sha256((bundle/name).read_bytes()).hexdigest() != manifest["sha256"].get(name):
            raise ValueError("Snapshot checksum mismatch: " + name)
    prices = pd.read_csv(bundle/"prices.csv", index_col="Date", parse_dates=True)
    validate_prices(prices)
    if set(prices) != set(manifest["assets"]):
        raise ValueError("Price universe mismatch.")
    for ticker in manifest["assets"]:
        if ticker == 'BTC':
            from data.fetchers.portfolio_bitcoin import validate_bitcoin, align_bitcoin, CONVENTION
            if manifest.get('schema') != 2 or manifest.get('valuation_convention') != CONVENTION:
                raise ValueError('BTC: unsupported valuation convention')
            raw = validate_bitcoin(pd.read_csv(bundle/'BTC.csv'))
            expected, evidence = align_bitcoin(raw, prices.SPY.dropna().index)
            actual = prices.BTC.reindex(expected.index)
            if not np.allclose(expected, actual, equal_nan=True, rtol=1e-12):
                raise ValueError('BTC: aligned prices differ from timestamped source')
            saved = pd.read_csv(bundle/'BTC_alignment.csv', index_col='Date', parse_dates=True)
            for field in ['valuation_utc','fixing_utc']:
                if not pd.DatetimeIndex(pd.to_datetime(saved[field],utc=True)).equals(pd.DatetimeIndex(evidence[field])):
                    raise ValueError('BTC: timestamp evidence mismatch')
            if not np.allclose(saved.PriceUSD,evidence.PriceUSD,equal_nan=True,rtol=1e-12):
                raise ValueError('BTC: fixing evidence mismatch')
            meta = manifest['assets']['BTC']; observed = actual.dropna()
            if (meta.get('quality') != 'validated' or meta.get('verified_identity') != {'asset':'btc','metric':'PriceUSD','currency':'USD'}
                or meta['observations'] != len(observed) or meta['raw_observations'] != len(raw)
                or meta['first_observation'] != str(observed.index[0].date())
                or meta['latest_observation'] != str(observed.index[-1].date())
                or meta['raw_first_label'] != raw.time.iloc[0].isoformat()
                or meta['raw_latest_label'] != raw.time.iloc[-1].isoformat()):
                raise ValueError('BTC: coverage/identity mismatch')
            continue
        history = pd.read_csv(bundle/(ticker+".csv"), index_col="Date", parse_dates=True)
        history, _ = validate_history(ticker, history)
        values = prices[ticker].dropna()
        if not values.index.equals(history.index) or not np.allclose(values, history["Adj Close"], rtol=1e-12):
            raise ValueError(ticker + ": prices do not match source evidence")
        metadata = manifest["assets"][ticker]
        if (metadata.get("verified_identity") != {"symbol": ticker, "currency": "USD", "instrumentType": "ETF"}
                or metadata.get("quality") != "validated"):
            raise ValueError(ticker + ": unverified source identity or quality")
        if (str(values.index[0].date()) != metadata["first_observation"] or
                str(values.index[-1].date()) != metadata["latest_observation"] or
                len(values) != metadata["observations"]):
            raise ValueError(ticker + ": metadata coverage mismatch")
    return prices, manifest


def freshness(latest, today=None):
    today = today or datetime.now(timezone.utc).date()
    age = (today-pd.Timestamp(latest).date()).days
    if age < 0:
        return "Invalid future observation"
    return "Stale: {} calendar days since latest observation".format(age) if age > 7 else "Historical end-of-day observations"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Fetch full adjusted histories for local research")
    parser.add_argument("--expand", action="store_true", help="Reuse validated ETF evidence; add USO and BTC")
    parser.add_argument("--root", type=Path, default=PORTFOLIO_STORE_DIR)
    args = parser.parse_args()
    if args.prepare or args.expand:
        prepare(args.root, expand=args.expand)
    else:
        _, manifest = load_bundle(snapshot_path(args.root))
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
