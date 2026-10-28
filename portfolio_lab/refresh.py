"""Twice-weekly, all-or-nothing preparation of the public Portfolio Lab release.

Run python -m portfolio_lab.refresh. Requires FRED_API_KEY; never fetches from
the app UI. Collection, tests and independent verifiers run against a fresh
candidate store, so a failure leaves the public and local active data alone.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

from data.paths import PROJECT_ROOT, PORTFOLIO_STORE_DIR, PUBLIC_PORTFOLIO_DIR
from portfolio_lab.deployment import _bundle, publish, validate

log = logging.getLogger(__name__)
SCHEDULE = 'Wednesday and Saturday at 10:45 UTC (16:15 IST)'


def coverage(root):
    """Read source dates rather than confusing retrieval time with observation time."""
    root = Path(root)
    result = {}
    for namespace in ('', 'macro', 'india'):
        manifest = json.loads((_bundle(root / namespace) / 'manifest.json').read_text())
        for key, meta in manifest.get('series', manifest.get('assets', {})).items():
            result[(namespace or 'global') + '/' + key] = meta.get(
                'latest_observation', meta.get('latest', meta.get('last')))
        if namespace == 'india':
            result['india/USD-INR'] = manifest['fx_latest']
    return result


def validate_freshness(root, previous=None, today=None):
    from data.fetchers.portfolio_macro import SERIES
    import pandas as pd

    today = today or datetime.now(timezone.utc).date()
    observed = coverage(root)
    for key, day in observed.items():
        namespace, instrument = key.split('/', 1)
        limit = SERIES[instrument][2] if namespace == 'macro' else (14 if instrument == 'USD-INR' else 7)
        age = (today - datetime.fromisoformat(day).date()).days
        if age < 0 or age > limit:
            raise ValueError(f'{key}: observation {day} is outside the allowed {limit}-day age')
        if previous and key in previous and day < previous[key]:
            raise ValueError(f'{key}: coverage would regress from {previous[key]} to {day}')
    # India uses weekly reference checkpoints; source freshness alone is not
    # enough when FX or alignment gaps make the usable common window older.
    panel = pd.read_csv(_bundle(Path(root) / 'india') / 'prices.csv', index_col='Date', parse_dates=True)
    usable = panel.dropna()
    if usable.empty or not 0 <= (today - usable.index[-1].date()).days <= 14:
        raise ValueError('India: no complete weekly portfolio checkpoint within 14 days')
    return observed


def collect_tri(destination, now=None):
    """Reuse a recently verified canonical snapshot, or fetch only the four benchmarks.

    The Portfolio refresh never rewrites the India dashboard's source store.
    Full source history and independent single-date checks use its existing
    official collector; no price-index or stale-data substitution is allowed.
    """
    from config.india_equity_matrix import INDICES, SOURCE_PAGE, ENDPOINT, RETURN_METHOD
    from config.portfolio_india_settings import INDEX_IDS
    from data.paths import INDIA_STORE_DIR
    from data.fetchers.india_equity_tri import IndiaTRIFetcher
    from data.processors.india_equity_matrix import validate_series

    now = now or datetime.now(timezone.utc)
    cutoff = (now.astimezone(ZoneInfo('Asia/Kolkata')).date() - timedelta(days=1)).isoformat()
    specs = [spec for spec in INDICES if spec['id'] in INDEX_IDS]
    canonical = INDIA_STORE_DIR / 'india_equity_tri.json'
    snapshot = None
    if canonical.exists():
        candidate = json.loads(canonical.read_text())
        try:
            retrieved = datetime.fromisoformat(candidate['fetched_at'].replace('Z', '+00:00'))
            if retrieved.tzinfo is None:
                retrieved = retrieved.replace(tzinfo=timezone.utc)
            if not timedelta(0) <= now - retrieved <= timedelta(hours=24):
                raise ValueError('Canonical TRI requires a fresh collection')
            if (candidate['currency'] != 'INR' or candidate['return_method'] != RETURN_METHOD
                    or candidate['source_url'] != SOURCE_PAGE or candidate['as_of'] < cutoff):
                raise ValueError('Canonical TRI identity or cutoff differs')
            by_id = {row['id']: row for row in candidate['series']}
            for spec in specs:
                series = validate_series(by_id[spec['id']], spec, cutoff)
                if not 0 <= (now.date() - series.index[-1].date()).days <= 7:
                    raise ValueError('Canonical benchmark is stale')
            snapshot = dict(candidate, series=[by_id[spec['id']] for spec in specs], failures=[])
            log.info('Using canonical NSE TRI verified within the last 24 hours')
        except (ValueError, KeyError, TypeError):
            snapshot = None
    if snapshot is None:
        client = IndiaTRIFetcher()
        mapping_sha = client.mapping()
        rows = []
        for spec in specs:
            row = client.history(spec, cutoff)
            validate_series(row, spec, cutoff)
            rows.append(row)
        snapshot = dict(schema_version=1, as_of=cutoff, fetched_at=now.isoformat(),
                        source_url=SOURCE_PAGE, endpoint=ENDPOINT, mapping_sha256=mapping_sha,
                        return_method=RETURN_METHOD, currency='INR', series=rows, failures=[])
    Path(destination).write_text(json.dumps(snapshot, separators=(',', ':'), allow_nan=False) + '\n')


def run_step(args, env, attempts=1):
    for attempt in range(1, attempts + 1):
        log.info('Running %s (attempt %d/%d)', ' '.join(args), attempt, attempts)
        try:
            subprocess.run([sys.executable, *args], cwd=PROJECT_ROOT, env=env, check=True)
            return
        except subprocess.CalledProcessError:
            if attempt == attempts:
                raise
            time.sleep(10 * attempt)


def write_summary(before, after, destination=None):
    lines = ['## Portfolio Lab refresh', '', 'All three bundles validated and published together.', '',
             '| Source | Previous observation | Published observation |', '|---|---|---|']
    for key, day in sorted(after.items()):
        lines.append(f'| {key} | {before.get(key, "Not previously published")} | {day} |')
    lines += ['', 'Unchanged observation dates remain unchanged even after a successful source check.', '']
    text = '\n'.join(lines)
    print(text)
    if destination:
        with Path(destination).open('a', encoding='utf-8') as stream:
            stream.write(text)


def refresh(destination=PUBLIC_PORTFOLIO_DIR):
    from dotenv import load_dotenv
    load_dotenv()
    if os.environ.get('FRED_API_KEY', '') in ('', 'YOUR_FRED_API_KEY'):
        raise ValueError('FRED_API_KEY is required to refresh Portfolio Lab; previous release preserved')
    destination = Path(destination)
    before = coverage(destination) if destination.exists() else {}
    # The parent is ignored. Every attempt gets new pointers and has no deployed
    # override or fallback to old published bundles.
    PORTFOLIO_STORE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='refresh-', dir=PORTFOLIO_STORE_DIR) as temporary:
        stage = Path(temporary).resolve()
        env = dict(os.environ, MONETARIA_PORTFOLIO_STORE=str(stage),
                   MONETARIA_PORTFOLIO_TRI=str(stage / 'nse_tri.json'),
                   PYTHONPATH=str(PROJECT_ROOT), MPLBACKEND='Agg', PYTHONUTF8='1')
        run_step(['-m', 'portfolio_lab.refresh', '--tri-output', str(stage / 'nse_tri.json')], env, 3)
        run_step(['-m', 'data.fetchers.portfolio_prices', '--prepare'], env, 3)
        run_step(['-m', 'data.fetchers.portfolio_macro'], env, 3)
        run_step(['-m', 'data.fetchers.portfolio_india', '--collect', '--prepare'], env, 3)
        validate(stage)
        after = validate_freshness(stage, previous=before)
        test_files = [str(path.relative_to(PROJECT_ROOT)) for path in sorted(
            (PROJECT_ROOT / 'tests').glob('test_portfolio*.py'))]
        run_step(['-m', 'pytest', *test_files, '-q'], env)
        for module in ('verify_real', 'verify_expansion', 'verify_research', 'verify_india'):
            run_step(['-m', 'portfolio_lab.' + module], env)
        # Verifiers may write audit reports inside the candidate. Publication
        # copies active bundles only; the audit reports stay out of Git.
        validate(stage)
        after = validate_freshness(stage, previous=before)
        metadata = dict(schema=1, checked_utc=datetime.now(timezone.utc).isoformat(),
                        schedule=SCHEDULE, coverage=after)
        publish(destination, stage, refresh_metadata=metadata)
    write_summary(before, after, os.environ.get('GITHUB_STEP_SUMMARY'))


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tri-output', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.tri_output:
        collect_tri(args.tri_output)
    else:
        refresh()


if __name__ == '__main__':
    main()
