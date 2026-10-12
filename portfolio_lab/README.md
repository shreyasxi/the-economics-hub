> **Deployment update (12 October 2026):** Private snapshot delivery is implemented. See [DEPLOYMENT.md](DEPLOYMENT.md) for the package, secrets, validation and refresh procedure. Earlier local-only release notes below describe the previous deployment state; source-permission limitations remain recorded.

> **Indian Investor Mode:** See [INDIAN_INVESTOR.md](INDIAN_INVESTOR.md) for the INR implementation, data/rights boundaries, SIP methodology, executed research and visual review.
>
> **BTC/oil and visual redesign:** See [REDESIGN.md](REDESIGN.md) for verified coverage, calendar/rights audit, visual alternatives, screenshots and executed validation.
>
> **Portfolio Lab 2.0:** The expanded research release and executed findings are documented in [RESEARCH_V2.md](RESEARCH_V2.md). The notes below retain the v1 foundation audit.

# Portfolio Lab v1 — local implementation and release notes

Implemented 11 October 2026 on `codex/portfolio-lab-v1`. Local release candidate;
**not published, committed, pushed, merged or deployed**. No workflow was added or edited by this task.
The checkout already contained extensive World/dashboard/workflow work, and other work can continue
in the shared checkout. Review only this feature's files and its small app integration hunks.

## Architecture and changed files

- `config/portfolio_settings.py`: approved eight-ETF universe, currency/source/adjustment metadata,
  educational templates, crisis windows, analytical defaults.
- `data/paths.py`: adds `PORTFOLIO_STORE_DIR` under `data/stores/portfolio_lab/`.
- `.gitignore`: excludes that complete data namespace from public Git.
- `data/fetchers/portfolio_prices.py`: explicit preparation CLI, identity and adjustment validation,
  immutable CSV bundles, corporate-action evidence, provenance and hashes, atomic CURRENT pointer,
  local reader and freshness policy. Reuses the existing Yahoo fetcher's retries and explicit Adj Close.
- `data/processors/portfolio_analytics.py`: allocation validation, calendar alignment, historical
  holdings simulator, trading costs, metrics, covariance and variance contributions; no Streamlit or I/O.
- `data/processors/portfolio_stress.py`: independent episode replay and simultaneous hypothetical shocks.
- `portfolio_lab/page.py`: session-local builder and presentation; only reads a prepared snapshot.
  Canonical allocation models survive hiding B and page navigation; no personal allocations are written to disk.
- `portfolio_lab/charts.py`: Altair financial charts using EconStyle colours. No new chart framework,
  static PNG export feature or dependencies. Research views render only the selected analysis.
- `portfolio_lab/verify_real.py`: explicit real-data verification with an independent share-unit reference.
- `tests/test_portfolio_{analytics,data,ui}.py`: numerical, data-integrity and Streamlit interaction tests.
- `app.py`: registers a hidden `/portfolio-lab` page and adds an entry below the Analysis header,
  before its existing sections. Masthead, footer, top navigation and search remain shared.

## Local commands

Run from the repository root with its existing environment (Python 3.9; no Python 3.10+ syntax).
Streamlit remains pinned at 1.50.0. No dependency versions were changed by Portfolio Lab.

```sh
.venv/bin/python -m data.fetchers.portfolio_prices --prepare
.venv/bin/python -m portfolio_lab.verify_real
.venv/bin/python -m pytest tests -q
.venv/bin/python -m streamlit run app.py --server.headless true --server.port 8502
```

Open `http://localhost:8502/portfolio-lab` or use Analysis → Open Portfolio Lab.
Preparation requires Yahoo connectivity. It retrieves each full history only during the explicit command;
allocations never trigger remote calls. It discards the current New York session, retains all downloaded
corporate-action fields, validates the entire bundle, then atomically activates it. Failed preparation
leaves the previous snapshot active. Full refreshes capture upstream revisions to historical adjustments.
No schedule was introduced. A weekly manual refresh is sufficient for v1; after authorization a private
scheduled refresh could run this command and verify its output before replacing the snapshot.

## Data coverage and definition

Source: Yahoo Finance through yfinance 1.2.0 in the local environment. Snapshot retrieved 11 October 2026 UTC.
Every ETF's latest observation is **9 October 2026**. First *observed* trading dates are from the returned
history, not invented inception dates or assumptions about an issuer's legal fund inception.
Yahoo metadata confirms the exact symbol, USD listing currency and ETF instrument type.

| ETF | First observed trading date | Daily closes |
|---|---|---:|
| SPY | 1993-01-29 | 8,482 |
| EFA | 2001-08-27 | 6,317 |
| EEM | 2003-04-14 | 5,911 |
| AGG | 2003-09-29 | 5,795 |
| IEF | 2002-07-30 | 6,089 |
| TLT | 2002-07-30 | 6,089 |
| LQD | 2002-07-30 | 6,089 |
| GLD | 2004-11-18 | 5,507 |

Explicit **Adj Close** ratios are labelled a distribution-adjusted ETF historical-return proxy.
[Yahoo's adjustment definition](https://in.help.yahoo.com/kb/adjusted-close-sln28256.html) describes
split and distribution adjustment. Preparation reconciles day-to-day adjustment-factor changes against
reported dividends and prior split-adjusted Close, with a relative tolerance of 0.0005 (five basis points)
for source rounding. It never falls back to Close, adds distributions again, or enables repair to invent values.
ETF expenses are already reflected in fund performance. Backward dividend multipliers approximate
reinvestment and are not an independently audited investor total-return index. Source action omissions
shared by both price adjustment and action records cannot be ruled out by this internal reconciliation.

Raw evidence, combined adjusted prices, observed-date metadata, retrieval timestamp, yfinance version
and SHA-256 checksums live together in each private snapshot. Loading checks hashes, source evidence,
identity, quality, and coverage agreement. Future refreshes retain earlier bundles; do not publicly publish
either raw or derived histories without an established redistribution basis.

## Methodology

Initial wealth is $10,000 at the first eligible close. Dated adjusted-price ratios change each asset's
notional holdings. Buy-and-hold drifts naturally. Monthly, quarterly and annual strategies restore target
allocations at the last eligible close preceding the next calendar period; new weights affect subsequent
returns. There is no final-close rebalance or use of future returns. No initial-entry or liquidation charge.

Optional proportional costs default to zero, range 0–100 bps, and apply to actual buys **plus** sells.
The engine solves the self-financing equation `C = fee * sum(abs(w*(V-C)-holdings))`, deducts C and allocates
the remainder. Turnover is traded notional / pre-trade wealth (twice the one-way convention).
Benchmark returns are a single approved ETF with no additional trading charge.

All portfolios and benchmark use identical dates. The combined source calendar preserves observations;
coverage is intersected at the endpoints and displayed explicitly. Within common coverage, any missing
holding or benchmark price blocks results. Whole-market holidays have no rows; nothing is filled.
A calendar gap over seven days blocks calculation. If every source omitted the same date, that isolated
omission would not be detectable without a separate authoritative exchange calendar; this is a known
source-validation limit. Shorter supplied histories never extend backwards or become synthetic proxies.

CAGR uses actual elapsed calendar days / 365.25. Historical volatility uses sample daily standard deviation
× sqrt(252). Both annualised statistics need 126 returns and 182 elapsed calendar days. Drawdown includes
initial wealth and refers to the selected window only. Total return and dollar wealth do not require annualisation.

Risk decomposition uses target weights (not drifted weights) and sample covariance over the final 252 common
return observations in the main window, or all available with at least 20 returns. Annualised covariance is
252 × daily covariance. Contribution is `w_i*(Sigma*w)_i / (w.T*Sigma*w)`. Contributions reconcile to 100%;
negative hedging contributions remain visible. Variance ≤ 1e-14 has no percentage decomposition.

Historical stress windows are independent of the main lookback. Each starts afresh at target allocations,
requires complete observed coverage for every selected asset and benchmark, then uses the same simulator
and costs. Windows are explicit analytical boundaries, not claims about every asset's peak/trough.
Hypothetical shocks use immediate simultaneous weighted arithmetic, without dynamic paths or probability estimates.

## Licensing and deployment audit — publication blocked

The [yfinance documentation](https://ranaroussi.github.io/yfinance/) calls its API access personal use only
and directs users to Yahoo's terms. Attempts to retrieve the directly linked Yahoo terms endpoints returned
HTTP 999; their complete current terms were not accessible in this audit. No explicit public-display,
bulk-redistribution or derived-data publication entitlement has been established. A downloadable endpoint
and the open-source library licence do not establish those rights. Keeping data out of Git helps prevent bulk
redistribution but does **not** itself resolve public display rights or server-side retrieval permission.

Therefore the current Yahoo snapshot is for local research and the implementation is **not ready for public
publication** until the owner establishes appropriate rights or chooses a licensed distribution-adjusted source.
There is no silent substitution to unadjusted data. No claim of legal clearance is made.

Streamlit Cloud will not receive Git-ignored snapshots automatically. A clean checkout intentionally shows
an unavailable-data notice rather than fabricated results. No startup download or public download control
was added. A private, rights-compliant provisioning mechanism is an additional deployment prerequisite.

Exact release sequence after those prerequisites and the owner's explicit approval:

1. Establish permission covering application display, derived calculations, server access and storage.
   If a different source is selected, adapt preparation, preserve the same return convention/provenance contract,
   and revalidate all observations and numerical checks before release.
2. Arrange private deployment provisioning of a complete validated bundle plus its CURRENT pointer at
   `data/stores/portfolio_lab/`. On Streamlit Cloud this needs an approved startup/bootstrap integration with
   a private data source or storage service; this integration has not been implemented or authorized here.
   Never force-add the current Yahoo store to the public repository.
3. Refresh and run the real verifier, portfolio tests and repository regression suite using the deployment data.
4. Review and stage only Portfolio Lab files and its app/path/ignore hunks. The working tree contains unrelated
   changes (including workflow changes made outside this task); do not include those accidentally.
5. Obtain approval for commit/push/merge/deployment. Publish the reviewed feature to Monetaria's existing
   Streamlit Cloud main branch and reboot the application as required.
6. Verify the actual production `/portfolio-lab` route, Analysis entry, source dates, crisis coverage, interactions,
   mobile layout and all existing navigation. Only then describe it as live.
7. Consider an authorized private scheduled refresh later; no workflow YAML or schedules were changed here.

## Verification and remaining limitations

Independent share-unit calculations matched engine wealth paths for buy-and-hold, monthly, quarterly and annual
strategies, and independently checked CAGR, daily volatility and drawdown. Single SPY equals adjusted SPY ratios;
all eight ETFs work together; identical portfolios match; invalid weights and omitted source observations fail.
A 50/30/20 allocation with shocks −20% SPY, −5% AGG and +10% GLD yields **−9.5%**, with reconciled contributions.

All three episodes have complete real coverage for **all eight ETFs**, including their exact requested boundary dates.
Buy-and-hold and monthly results matched the independent reference. At zero costs for 60/40 A and 50/30/20 B:

| Episode | Closes | A return, buy-and-hold | B return, buy-and-hold | SPY return |
|---|---:|---:|---:|---:|
| 2007-10-09 to 2009-03-09 | 356 | −30.16% | −20.59% | −55.19% |
| 2020-02-19 to 2020-04-30 | 51 | −7.07% | −5.06% | −13.64% |
| 2022-01-03 to 2022-12-30 | 251 | −16.16% | −12.89% | −18.65% |

Local numerical evidence is saved under ignored `output/portfolio_lab/verification.json` and `real_checks.txt`.
Synthetic histories occur only in isolated tests. Tests also verify exact cost accounting, no look-ahead,
negative risk contributions, near-zero variance, corrupted bundles, failed refresh activation, wrong ticker identity,
B duplication/normalisation/preservation, no rendering-time fetches, and absent data notices.

Optional best/worst calendar-year statistics, rolling 12-month range, recovery duration and static PNG exports
are omitted. Taxes, initial-entry/liquidation costs, user-specific fees and execution slippage are excluded.
No user accounts, persisted personal holdings, unrestricted tickers, currency conversion, recommendations or optimisation.
Public data rights and Cloud provisioning remain the material release blockers.

Final local QA: `pytest tests -q --disable-warnings` passed **629 tests** (including the then-current
shared-checkout work); the focused portfolio interaction suite passed **2 tests** after the final state fix.
The feature's numerical/data suite includes **20 tests**. The broad suite was scoped to `tests/` because
unscoped pytest also discovers obsolete baseline tests under ignored `output/india_gva_iip_audit/` and
fails collection there. Those unrelated archives were left untouched.

Desktop (1440 × 1000) and mobile (390 × 844) screenshots were captured and inspected. QA fixed cramped
risk bars, mobile legend clipping, state cleanup when B is hidden and accidental wheel zoom during phone
scrolling. Core comparison tables fit the phone width, controls stack, charts retain their zero-based wealth
axes and full legends, and dates/assumptions remain visible. Research uses a horizontal three-choice selector
and only builds the active view, avoiding hidden-chart sizing and unnecessary calculations.

Actual browser navigation was checked for Weekly Markets, World, India, RBI Sentinel, Analysis and About.
Existing pages displayed their expected content without Streamlit exceptions; masthead, footer and top-level
navigation remained present. Chart-search suggestions for gold rendered normally. The Analysis link opened
Portfolio Lab; historical replay and methodology sections rendered against the real prepared snapshot.
The concurrently added Historical analogues section on Analysis was preserved.

Screenshot evidence lives in ignored `output/portfolio_lab/screenshots/`:
`desktop-performance.jpg`, `desktop-risk.jpg`, `mobile-performance.jpg`, `mobile-builder.jpg`,
`mobile-stress.jpg`, and `analysis-entry.jpg`. These are local review evidence, not published assets.
No production verification was performed because deployment has not been approved and data rights remain unresolved.
