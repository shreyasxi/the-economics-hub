> **Deployment update (12 October 2026):** Private snapshot delivery is implemented. See [DEPLOYMENT.md](DEPLOYMENT.md) for the package, secrets, validation and refresh procedure. Earlier local-only release notes below describe the previous deployment state; source-permission limitations remain recorded.

# Portfolio Lab 2.0 — local research release

Implemented on `codex/portfolio-lab-v2`, preserving the v1 core and unrelated working-tree changes. No commit, push, merge, workflow change or deployment was performed.

## Executed research demonstration

Illustrative allocations, predetermined and not optimised or recommended:

- A: 60% SPY / 40% AGG.
- B: 35% SPY / 10% EFA / 20% IEF / 15% LQD / 15% GLD / 5% VNQ.

Common actual closes: 2004-11-18 through 2026-10-09. Monthly rebalancing, 5 bps on buys plus sells. Initial wealth $10,000; SPY benchmark without incremental trading costs. All statistics below were executed by `python -m portfolio_lab.verify_research`.

| Quantity | A | B | SPY |
|---|---:|---:|---:|
| Cumulative return | 431.34% | 440.81% | 878.75% |
| CAGR | 7.93% | 8.02% | 10.98% |
| Annualised volatility | 11.33% | 10.30% | 18.83% |
| Maximum drawdown | -35.78% | -30.96% | -55.19% |
| Final wealth ($) | $53,133.68 | $54,081.31 | $97,874.61 |

### A. What drove the difference?

B finished $947.65 ahead, a 9.48 percentage-point cumulative-return difference. Its lower SPY contribution was offset by other holdings, especially gold. This is accounting attribution, not a causal factor decomposition. Dollar P&L / starting wealth incorporates compounding through actual entering holdings; costs reconcile separately.

| Holding contribution (percentage points) | A | B |
|---|---:|---:|
| SPY | 391.955 | 244.416 |
| AGG | 39.836 | 0.000 |
| EFA | 0.000 | 42.637 |
| IEF | 0.000 | 19.229 |
| LQD | 0.000 | 21.996 |
| GLD | 0.000 | 92.943 |
| VNQ | 0.000 | 20.258 |
| Trading costs | -0.454 | -0.665 |

A contributed mainly through equities; B had 92.94 pp from gold and 42.64 pp from developed-market equities. Contributions are not standalone holding returns or allocation-weighted CAGRs. Cost totals were $45.36 for A and $66.54 for B over the simulation, not annual fees.

### B/E. Risk diversification and window sensitivity

| Target-weight risk snapshot | A: 252 | A: 756 | B: 252 | B: 756 |
|---|---:|---:|---:|
| SPY variance contribution | 89.73% | 91.46% | 38.82% | 48.04% |
| AGG variance contribution | 10.27% | 8.54% | 0.00% | 0.00% |
| EFA variance contribution | 0.00% | 0.00% | 14.07% | 13.81% |
| IEF variance contribution | 0.00% | 0.00% | 5.33% | 5.84% |
| LQD variance contribution | 0.00% | 0.00% | 5.26% | 7.05% |
| GLD variance contribution | 0.00% | 0.00% | 33.53% | 19.58% |
| VNQ variance contribution | 0.00% | 0.00% | 3.00% | 5.67% |
| Historical annualised volatility | 8.58% | 9.78% | 9.81% | 9.42% |

B spreads its variance contributions across more holdings, but that does not guarantee lower total risk. Its full-history volatility is lower than A’s; its latest 252-return target-weight volatility is higher. At 756 returns B’s volatility is slightly lower. B’s gold risk share moves from 33.53% to 19.58% between windows. This is material estimation sensitivity. Negative hedge contributions are preserved during stress. No proprietary diversification score or shrinkage has been introduced.

### Empirical financial associations

Two-factor weekly raw-return model: SPY adjusted return plus DGS10 yield change in decimal units. Exact ETF endpoint dates are matched to observed yield dates; holiday omissions remove intervals rather than fill levels. The model has 1,133 intervals, 2004-11-26 to 2026-10-02.

| Estimate (HAC 95% normal interval) | A | B |
|---|---:|---:|
| Equity | 0.638 [0.615, 0.661] | 0.544 [0.513, 0.575] |
| Rate | -1.984 [-2.214, -1.755] | -3.303 [-3.669, -2.938] |
| R² | 0.988 | 0.885 |

Equity coefficients describe return pp per 1 pp equity return; rate coefficients describe return pp per +100 bps yield change. B has a lower equity association and stronger negative rate association. Its lower fit leaves more unexplained return variation; gold and foreign equities are not fully represented by this small model. The intercept is a raw-return regression intercept, not investment alpha. Rate beta is not issuer duration.

Earlier/later-half rate coefficients shift from −1.787 to −2.238 for A and −2.771 to −3.857 for B. Rolling models use 104 calendar weeks at 13-week steps and require complete windows. A recent three-factor credit extension has only 155 matched weeks (2023-10-20 to 2026-10-02); credit coefficients are −0.125 A and −0.274 B. It must not be interpreted as evidence about credit sensitivity in 2008.

### C. Diversification under stress

| Isolated replay | A return | B return | SPY return | SPY/AGG correlation pre → during → post | SPY/IEF correlation pre → during → post |
|---|---:|---:|---:|---|---|
| Global Financial Crisis | -35.77% | -29.49% | -55.19% | -0.215 → -0.005 → -0.171 | -0.318 → -0.482 → -0.274 |
| COVID-19 Market Shock | -6.87% | -5.57% | -13.64% | -0.350 → 0.177 → 0.113 | -0.496 → -0.551 → -0.152 |
| 2022 Equity and Bond Sell-Off | -15.89% | -14.43% | -18.65% | 0.039 → 0.325 → 0.163 | -0.086 → 0.193 → 0.045 |

Pre/post windows contain 252 daily returns. During windows contain 355 (GFC), 50 (COVID) and 250 (2022); especially COVID correlations have limited sampling precision. Each episode starts afresh at target holdings, independent of the main lookback. During/post covariance is ex-post, not a prospective forecast.

In the GFC, B’s IEF and gold contributed +3.38 pp and +3.47 pp, offsetting part of equity/REIT losses; LQD contributed −0.88 pp. In COVID, IEF contributed +1.42 pp while LQD contributed −0.13 pp, illustrating why broad bond labels obscure different behaviour. In 2022, A’s AGG contributed −4.86 pp and B’s IEF/LQD contributed −2.83/−2.58 pp; gold added only +0.21 pp. The SPY/IEF correlation moved positive in 2022. B’s episode return was better, but its 2022 maximum drawdown (−20.83%) was slightly worse than A’s (−20.53%).

### D. Macro-conditioned distributions

Latest revised-data ex-post observation-month labels; no historical release vintages or investable strategy. Inflation: annual CPI inflation minus its value three months earlier, sign classifies rising/falling. Growth: published CFNAIMA3 >=0 means at/above trend; <0 means below trend, not recession. Choices use economic definitions and fixed horizons, not portfolio-return optimisation.

| Dimension/state | Months / contiguous runs | A mean / median monthly return | B mean / median monthly return | A / B negative months |
|---|---:|---:|---:|---:|
| Inflation / Falling | 129 / 32 | 0.99% / 1.37% | 1.07% / 1.35% | 30.2% / 31.8% |
| Inflation / Rising | 130 / 31 | 0.36% / 0.61% | 0.30% / 0.28% | 36.2% / 40.8% |
| Growth / At/above trend | 103 / 21 | 0.59% / 0.92% | 0.55% / 1.00% | 32.0% / 33.0% |
| Growth / Below trend | 158 / 20 | 0.74% / 1.12% | 0.79% / 1.10% | 33.5% / 38.0% |

Observed B–A monthly mean differences are small: about +0.077 pp in falling inflation and −0.067 pp in rising inflation. Below-trend growth has higher mean returns in this sample; this descriptive result is not evidence that weak growth predicts gains. Full conditional volatility, 10th percentile, medians, downside counts and benchmark results are in the reproducible CSVs and UI. No significance or predictive claim is made. Samples are temporally dependent; contiguous runs are not independent experiments. At least 24 months and three runs are required before distribution summaries are shown.

Three inflation classifications and one growth classification are omitted over the demonstration. October 2025 CPI is genuinely absent; no imputation. The missing level also affects the three-month change comparison. September 2026 macro observations are not yet in this prepared snapshot.

## Data audit and provenance

All 26 candidates passed ETF identity, USD currency, explicit adjusted-close/distribution reconciliation and mean volume >=100,000 shares over 60 observed sessions. Recent volume is a liquidity screen, not a historical execution or spread guarantee. Latest ETF close is 2026-10-09. Fund inception is Yahoo source-reported, distinct from the first available trading close and not issuer certification. The simulator starts only at complete common observed prices. No synthetic pre-launch history, price fallback, arbitrary filling or unrestricted tickers.

| ETF | Source-reported inception | First actual close | 60-session mean shares |
|---|---|---|---:|
| SPY | 1993-01-22 | 1993-01-29 | 43,553,805 |
| EFA | 2001-08-14 | 2001-08-27 | 11,637,878 |
| EEM | 2003-04-07 | 2003-04-14 | 19,707,533 |
| AGG | 2003-09-22 | 2003-09-29 | 9,745,393 |
| IEF | 2002-07-22 | 2002-07-30 | 8,532,867 |
| TLT | 2002-07-22 | 2002-07-30 | 37,195,625 |
| LQD | 2002-07-22 | 2002-07-30 | 30,777,580 |
| GLD | 2004-11-18 | 2004-11-18 | 9,410,662 |
| QQQ | 1999-03-10 | 1999-03-10 | 35,133,780 |
| IWM | 2000-05-22 | 2000-05-26 | 21,416,612 |
| RSP | 2003-04-24 | 2003-05-01 | 7,155,848 |
| INDA | 2012-02-02 | 2012-02-03 | 5,048,527 |
| SHY | 2002-07-22 | 2002-07-30 | 4,135,597 |
| TIP | 2003-12-04 | 2003-12-05 | 1,937,785 |
| HYG | 2007-04-04 | 2007-04-11 | 42,571,463 |
| DBC | 2006-02-03 | 2006-02-06 | 951,623 |
| VNQ | 2004-09-23 | 2004-09-29 | 3,524,672 |
| BIL | 2007-05-25 | 2007-05-30 | 10,052,170 |
| XLK | 1998-12-16 | 1998-12-22 | 7,385,588 |
| XLF | 1998-12-16 | 1998-12-22 | 32,880,905 |
| XLE | 1998-12-16 | 1998-12-22 | 30,125,032 |
| XLV | 1998-12-16 | 1998-12-22 | 8,349,103 |
| XLP | 1998-12-16 | 1998-12-22 | 10,400,965 |
| XLU | 1998-12-16 | 1998-12-22 | 24,766,005 |
| IWF | 2000-05-22 | 2000-05-26 | 3,853,375 |
| IWD | 2000-05-22 | 2000-05-26 | 1,643,920 |

INDA cannot participate in the GFC; preparation does not backfill it. HYG/BIL begin in 2007 and lack a full 252-return pre-GFC window. Currency exposure of foreign equity funds remains in their actual USD returns; they are not assumed hedged. DBC is commodity futures exposure and VNQ is equity REIT exposure, not spot commodity/property prices. Current surviving ETFs do not represent the historical opportunity set.

| Economic source | Prepared history | Latest observation | Units |
|---|---|---|---|
| [DGS10](https://fred.stlouisfed.org/series/DGS10) | 1986-10-14 onward | 2026-10-08 | percent yield |
| [BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) | 2023-10-10 onward | 2026-10-08 | percent OAS |
| [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL) | 1986-10-01 onward | 2026-08-01 | seasonally adjusted index |
| [CFNAIMA3](https://fred.stlouisfed.org/series/CFNAIMA3) | 1986-10-01 onward | 2026-08-01 | published three-month activity index |

FRED source definitions: [DGS10](https://fred.stlouisfed.org/series/DGS10), [ICE HY OAS](https://fred.stlouisfed.org/series/BAMLH0A0HYM2), [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL), [CFNAIMA3](https://fred.stlouisfed.org/series/CFNAIMA3). Existing FredFetcher is reused; World snapshots retain too little rate/CPI history and Weekly fetches short change windows, so a separate private immutable research bundle is necessary. Monthly macro data are aligned by observation month, not claimed release date. [BLS documents the October 2025 data gap](https://www.bls.gov/bls/bls-handling-of-missing-data.htm).

Yahoo access is described by [yfinance](https://ranaroussi.github.io/yfinance/) as personal research use; no public-display licence has been established. FRED’s ICE notes explicitly restrict publishing and distributing top-level data without permission and limit available history to three years from April 2026. All raw bundles remain gitignored, including macro bundles. Publication requires a source-specific licence and a reviewed delivery/provisioning plan; hiding CSVs alone does not resolve derived-display rights.

## Implementation and quantitative methods

- Reused `portfolio_analytics.py` simulation: arbitrary holdings, long-only validated weights, actual drift, common daily calendar, period-close trades affecting subsequent returns, exact self-financing two-way cost, no final-close trade. Added covariance sample/condition/concentration diagnostics.
- Extended `portfolio_prices.py` and `portfolio_settings.py`: 26 curated instruments, source-reported launch audit and observed-volume screen. Immutable hashed snapshots and atomic activation retained; valid subsets support staged preparation.
- New `portfolio_attribution.py`: daily entering-holding dollar P&L, daily net contribution reconciliation, exact cumulative P&L / initial wealth, class aggregation, costs/turnover/drift. Rebalanced-vs-buy-and-hold is an explicitly limited counterfactual.
- New `portfolio_macro.py`: existing FRED reader, validated frequency/units/dates, missing monthly levels preserved, raw series hashes, source coverage/freshness, atomic activation. No remote UI calls.
- New `portfolio_factors.py`: matched weekly endpoints, exact date alignment; OLS, minimum max(104, 20×parameters), standardised condition <=1,000; Newey–West Bartlett HAC with four calendar-week lags and n/(n−p) correction, normal 95% intervals, residuals and fit. Missing weeks do not become artificial adjacent HAC lags. Rolling 104-week complete calendar windows; split-half diagnostics require 208 observations.
- New `portfolio_regimes.py`: calendar-month CPI transformations without filling, established activity-level threshold, explicit ex-post-only contract, complete monthly wealth intervals, missing labels omitted, episode counts, minimum samples, no pooled annualisation.
- Extended `portfolio_stress.py`: isolated real replay plus pre/during/post empirical covariance at constant target weights, reconciled loss attribution, unavailable-state reporting. Direct asset shocks retained.
- New `portfolio_lab/research.py` and chart extensions: coherent Overview / Attribution / Risk & Factors / Macro Regimes / Stress Testing views, persistent collapsible builder, sources and uncertainty. Historical replay, direct asset shocks and factor shocks use compact stress modes. Legacy route/navigation and page appearance retained.
- Updated `verify_real.py` to verify the expanded eligible universe and reject later-launch episode histories. New `verify_research.py`: executed real-data findings and independent share-unit P&L, centred-matrix covariance and normal-equation regression checks.

Covariance minimum is max(20, five observations per holding); 252/756 windows are separately identified. Singular/unstable covariance is flagged; no silent shrinkage. Target-weight variance contributions sum to one, negative hedging contributions retained, near-zero variance undefined. Actual historical simulation volatility and target-weight current-window risk are different quantities.

Factor scenarios use beta × coherent one-week equity/yield/spread shocks, excluding intercept. Yield/spread input bps divide by 10,000. Parameter-only uncertainty is x′Cov(beta)x; unexplained weekly SD is shown separately. Neither is a guaranteed loss or complete prediction interval. Large shocks extrapolate. Gold is not an identified factor in this release. Direct duration/convexity/spread-duration pricing is explicitly deferred: no validated, consistently defined instrument snapshot has been prepared. No made-up durations or interchangeable empirical betas.

## Verification and operations

Automated numerical cases cover compound attribution, class aggregation, independent rebalance costs, 40 holdings, OLS matrices, HAC independently summed scores including calendar gaps, model identification/sample size/units, no-future rolling boundaries, missing endpoints, CPI gaps, month matching/episode counts, ex-post contract, pre/during/post stress samples, inception unavailability, atomic macro data activation and checksums. Streamlit real-data tests cover each view, two sessions, retained allocations, three stress episodes, recent credit model, 756-return risk window and factor scenarios while fetch methods raise if called.

Full repository suite: 639 passed (141 seconds) after research integration; expanded focused portfolio suite: 39 passed, including short-lookback unavailable states. Independent real-data checks pass. Deprecation warnings are primarily existing Streamlit/Altair APIs; no suppressed failing calculations. Final tests and browser QA are recorded alongside local screenshots in `output/portfolio_lab/v2/`.

Prepare/refresh explicitly:

```sh
.venv/bin/python -m data.fetchers.portfolio_prices --prepare
.venv/bin/python -m data.fetchers.portfolio_macro
.venv/bin/python -m portfolio_lab.verify_research
.venv/bin/python -m pytest tests/test_portfolio_*.py -q
```

Data loads cache by immutable bundle path, independently of allocations; all user holdings remain session-local. Simulation and weekly models are inexpensive interactive calculations; rolling models run at 13-week steps rather than daily fits. No database, LLM, authentication, extra dependencies or workflow integration. Reproducibility inputs: research JSON stores asset and macro snapshot paths, source manifests, allocations, periods and assumptions.

Public readiness: local review ready, publication blocked by Yahoo/ICE rights and private snapshot provisioning. A clean public checkout intentionally displays an unavailable-data notice. After rights are settled, propose a separately approved offline refresh job that prepares both bundles, validates contracts/tests, and activates only passing snapshots. Keep old snapshots on failure. No workflow changes were made.

Browser QA: repaired the composite Altair box-plot dataset handoff using explicit inline observations; verified actual distributions render. Checked desktop at 1440×1000 and mobile at 390×844, including wrapped research navigation, readable attribution labels, regime sample tables/distributions and stress controls. Screenshots are local under `output/portfolio_lab/v2/screenshots/`. Source bundles remain ignored.
