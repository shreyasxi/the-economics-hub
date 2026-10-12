> **Deployment update (12 October 2026):** The owner confirmed source permissions. Validated Global, macro and India datasets now ship publicly in Git under `data/published/portfolio_lab/`. See [DEPLOYMENT.md](DEPLOYMENT.md) for validation and refresh commands. No separate storage or snapshot secrets are required.

# Indian Investor Mode — implementation and research report

12 October 2026. Branch `codex/indian-investor-mode`. Local **reference research** implementation; no commit, push, merge, deployment or workflow change. Existing unrelated uncommitted work is preserved.

The mode is available within Portfolio Lab as **Indian Investor — INR**, beside **Global Portfolio — USD**. It provides a curated 12-instrument universe, A/B construction, INR wealth, holding and currency attribution, covariance, a parsimonious factor model, Indian macro distributions, historical/direct stress and cash-flow-aware monthly SIP research.

**Release boundary:** the calculations are validated reference-price simulations. They are not executable fund-NAV or exchange-order backtests. Historical public-release receipts, contemporaneous executable FX, settlement, fund cutoff rules and whole-unit constraints have not been established. No control silently implies those capabilities.

The pre-implementation [architecture/source feasibility report](INDIA_FEASIBILITY.md) records the initial source and architecture decisions.

## 1. Architecture

Shared components remain the holdings simulator, allocation validation, self-financing rebalance/cost solver, wealth statistics, P&L ledger, empirical covariance, HAC OLS and historical/hypothetical stress arithmetic. Global defaults retain $10,000, daily observations and √252 volatility. INR calls explicitly select initial rupee wealth, weekly evaluation and √52. Weekly source calendars allow at most fourteen days between evaluated observations; individual mark ages remain separately bounded.

New modules:

- `config/portfolio_india_settings.py`: curated instruments, templates, explicit episode windows.
- `data/fetchers/portfolio_india.py`: explicit snapshot preparation, source/identity checks, immutable source copies and SHA-256 hashes, reconstructed normalised returns on load, atomic CURRENT activation. No downloads on UI reruns.
- `data/processors/portfolio_currency.py`: timestamp/publication-aware marks, exact FX conversion, standalone and actual-holdings FX P&L, strict permission/identity boundary for future Direct/Growth NAV imports.
- `data/processors/portfolio_sip.py`: dated subscriptions, simulated holdings/units, shared interval simulation/rebalancing, capital/gain, flow-adjusted TWR and XIRR.
- `data/processors/portfolio_india_regimes.py`: read-only RBI/CPI inputs, monthly ex-post labels and India equity/FX weekly design.
- `portfolio_lab/india.py`: mode-specific builder and research presentation, independent session keys, INR formatting, actual eligibility/errors.
- `verify_india.py` and `render_india_alternatives.py`: independent numerical demonstration and six retained layout trials.

`data/paths.py` registers the new namespace beneath the already ignored `data/stores/portfolio_lab/`. Active source histories and converted observations are published under `data/published/portfolio_lab/`; local previews and superseded runs stay outside Git. No database server, paid API, new LLM inference or automatic refresh was introduced.

## 2. Data and approved universe

Current immutable input snapshot: `20261012T053907Z`. Full prepared reference panel: **927 weekly dates, 2009-01-07–2026-10-07**. Comparisons intersect each selected instrument's actual available marks. The existing short TRI snapshot is not used to truncate fund-only comparisons when NIFTYBEES is the benchmark.

| Instrument | Type / return convention | Verified source observations |
|---|---|---|
| Nifty 50 TRI | Gross total-return benchmark | 2021-09-27–2026-10-09 |
| Nifty Next 50 TRI | Gross total-return benchmark | 2021-09-27–2026-10-09 |
| Nifty Midcap 150 TRI | Gross total-return benchmark | 2021-09-27–2026-10-09 |
| Nifty Smallcap 250 TRI | Gross total-return benchmark | 2021-09-27–2026-10-09 |
| NIFTYBEES.NS | Indian equity ETF, adjusted market close | 2009-01-02–2026-10-09 |
| GOLDBEES.NS | Domestic physical-gold ETF, adjusted market close | 2009-01-02–2026-10-09 |
| GILT5YBEES.NS | Medium-maturity sovereign ETF, adjusted market close | 2021-04-07–2026-10-09 |
| LTGILTBEES.NS | 8–13yr sovereign ETF, adjusted market close | 2018-05-11–2026-10-09 |
| LIQUIDCASE.NS | Actual liquid ETF, adjusted market close | 2024-01-17–2026-10-09 |
| SPY | USD-listed US-equity ETF, adjusted close | 1993-01-29–2026-10-09 |
| EFA | USD-listed developed-market ETF, adjusted close | 2001-08-27–2026-10-09 |
| EEM | USD-listed emerging-market ETF, adjusted close | 2003-04-14–2026-10-09 |

First observed source dates are not asserted to be fund inception. GILT5YBEES' [issuer](https://etf.nipponindiaim.com/Funds/details/2022) independently gives inception **2021-04-05**, ISIN **INF204KC1030**, and a total-return benchmark subject to expenses/tracking error. Other ETF stable ISINs are retained in metadata; unknown exact issuer inception dates are explicitly marked uncertified. ETF units do not have mutual-fund Direct/Regular or Growth/IDCW plan variants. These are **market-price histories, not growth NAVs**.

The [NSE circular](https://archives.nseindia.com/content/circulars/CML52187.pdf) establishes the May 2022 gilt ticker changes; no DIY stitching was performed. Yahoo labels Indian ETFs as EQUITY. Admission therefore requires a curated independently verified ETF symbol/ISIN, INR quote identity, and an ETF source name, rather than assuming that this vendor classification means an ordinary company share. Explicit adjusted-close and reported distribution-factor checks pass. Provider corporate-action records are not claimed to be a complete independent exchange action audit. Current-day incomplete bars are excluded. Source volume/zero-volume diagnostics remain available; secondary-market prices and stale/no-trade marks can differ from NAV.

The NIFTY records reuse the existing validated official gross-TRI snapshot, including source receipts, hashes and independent checks. No price-index/dividend-estimate substitution. The five-year local backfill is the acquired coverage, **not the full history offered by the provider**. Official older/back-cast index history and index launch dates do not establish a fund's existence.

[NSE's fixed-income portal](https://niftyindices.com/reports) distinguishes total-return histories from the 10-year clean-price exception. Composite G-Sec, 5/10yr and duration buckets, corporate-debt and liquid benchmarks were investigated, with source definitions retained for future additions. No yield, clean-price or spot series is used as bond total return. The 5yr ETF is **medium maturity**, not a certified short-duration fund; the 8–13yr category is maturity exposure, not a validated duration number. True short-duration sovereign and corporate-debt benchmark studies remain outside this first approved universe. LIQUIDCASE is a fund with market risk/expenses, not a theoretical risk-free asset.

AMFI/AMC growth NAVs are not acquired in bulk. The import boundary validates scheme code, ISIN, AMC, plan, option, inception, permission and verified continuity; it rejects Regular/IDCW variants and pre-inception history. Enabling a scheme requires a source permission and identity audit. No renamed/merged NAVs are automatically combined.

### FX and information timing

[DEXINUS](https://fred.stlouisfed.org/series/DEXINUS) supplies **7,515 observed fixings, 1996-10-15–2026-10-02**, expressed as **INR per one USD**. The [Federal Reserve H.10](https://www.federalreserve.gov/releases/h10/hist/) convention is New York noon; public dissemination is weekly, normally Monday 16:15 New York. Its next release at this audit is 13 October because 12 October is a federal holiday. The [Board's public-domain disclaimer](https://www.federalreserve.gov/disclaimer.htm) and FRED source attribution apply; this is not FBIL data.

Checkpoints are Wednesdays **15:30 Asia/Kolkata**, moving to the next observed Indian session when closed. Domestic prices use the latest completed prior-day close (17:00 availability buffer). USD ETFs use the latest completed New York 16:00 close. FX uses only a week whose scheduled public release has passed, with federal holidays moving release to the next federal business day. Stored evidence includes source date, checkpoint, scheduled availability and FX fixing time. Mark ages are bounded at seven days for instruments and twelve for FX; invalid values and unbounded carries are rejected.

This avoids same-date US/India close joins and premature use of a still-unreleased H.10 week. However, scheduled availability is **not a vintage-by-vintage audit of actual dissemination**. Revised histories and asynchronous/stale prices cannot establish a point-in-time executable strategy. Weekly sampling avoids manufacturing daily FX precision, but cannot remove asynchronous covariance bias. Reference wealth uses mathematical fractional units and does not model lot rounding, NAV cutoff, settlement, spreads, loads, taxes or remittance costs.

## 3. Financial methods

**Portfolios:** long-only weights must sum to 100%; normalisation happens only on explicit click. Templates apply on selection. No arbitrary three/five-holding cap. Zero-weight selections do not restrict the active comparison window. Index-only, fund-only and mixed holdings have distinct labels. NIFTY TRI and NIFTYBEES benchmarks can be selected; incomplete crisis history fails explicitly without substitution or renormalisation.

**Currency:** INR level = USD adjusted level × INR/USD. Simple return = foreign return + FX return + interaction. Standalone compounded endpoint components reconcile exactly. Portfolio FX contributions instead sum actual entering INR holdings times each interval's local return, FX return and product, divided by initial wealth; domestic P&L and trading costs complete the reconciliation. EFA/EEM's USD fund returns already contain underlying-country currency effects; only incremental USD/INR conversion is added. Domestic INR prices/NAVs never receive another FX conversion.

**Costs/performance:** the shared solver makes rebalances self-financing, charging buys plus sells. Reference lump-sum paths exclude initial entry/terminal liquidation costs; SIP subscriptions also incur the selected purchase cost. CAGR uses elapsed days/365.25; weekly volatility uses sample SD×√52, with at least26 returns/182 days. Weekly drawdowns miss daily/intraperiod extremes. Covariance retains signed and >100% variance shares; capital allocation is shown on the same percent scale.

**SIP:** requested monthly day1–28 rolls to the next eligible reference valuation within the contribution end date. Initial capital is optional. Contributions can stop while holdings continue to the analysis end. Requests before complete instrument coverage fail rather than accumulate fictitious earlier purchases. Gross invested capital, market value, gain, dated flows/units and returns are separate. Flow-adjusted TWR removes net subscriptions and excludes subscription purchase fees; XIRR includes gross investor cash flows and therefore those fees. Rebalancing/costs use the shared engine. This is reference-unit accounting, not an assertion that stale prices were executable or that fund cutoff rules were met.

**XIRR:** negative investor contributions plus positive terminal value; ACT/365; bracketed bisection in log(1+r). Conventional single-sign-change flows have one root. Insufficient/no-bracket flows return an explicit unavailable state. Non-conventional flows are refused rather than arbitrarily selecting a potentially ambiguous root. Short horizons carry an annualisation warning. XIRR is not CAGR or evidence of superior total wealth.

**Factors:** NIFTY TRI and USD/INR weekly raw returns only; no automatically added gold, debt, credit or sentiment factor. Reuse OLS and four-week Bartlett Newey–West HAC uncertainty. Minimum104 matched weeks, condition/rank/constant-factor safeguards, R²/residual diagnostics and two-half stability. Display standardised shocks in weekly-return pp, actual reference dates and week-bucket labels. Rate sensitivity is not fund duration; causation/alpha/hedge claims are not inferred.

**Regimes:** actual effective RBI repo decisions from Sentinel's read-only corpus, never tone; net month-end rate changes classify tightening/easing/unchanged months. Canonical MoSPI published YoY rates cover Jan2024–Aug2026; changes are computed within comparable bases only, skipping the Dec2025/Jan2026 boundary and gaps. Currency states use observed month-end reference changes. Complete monthly intervals use final eligible weekly marks, not official daily month-end indices. Quantiles/counts/runs are descriptive ex-post; no annualisation of non-contiguous states or investable signal. A plotted state requires six months and three runs, a deliberately low descriptive threshold prominently disclosed. Domestic liquidity was investigated but its roughly one-year comparable history is too short for a broad regime study, so no decorative liquidity control is exposed.

**Stress:** specified 2008, 2013 taper/INR, 2016 demonetisation, 2020, 2022 calendar-year and RBI tightening windows. The first four are unavailable for the demonstrated portfolios due to actual acquired index/fund coverage. Instrument eligibility is visible. RBI's [six-hike cycle](https://www.rbi.org.in/scripts/AnnualReportPublications.aspx?Id=1384) runs 4 May2022–8 February2023; evaluated marks bracket it through15 February to capture the final decision's subsequent prices. Pre/post52 weekly returns, entire-episode covariance, explicit ex-post/noisy-sample labels. Direct foreign shocks apply multiplicative FX, not simple addition; scenarios are assumptions, not forecasts.

## 4. Executed research findings

All outputs are in [validation.json](../output/portfolio_lab/india/validation.json), generated by `python -m portfolio_lab.verify_india`. Exact source convention above applies to every number. Predetermined allocations were not optimised. Main common period **6 October2021–7 October2026**, monthly rebalancing, 5bps buys+sells, ₹1,00,000 initial wealth.

### Gold and diversification

A: NIFTYBEES60/GILT5YBEES40. B: NIFTYBEES51/GILT5YBEES34/GOLDBEES15, preserving the equity/bond ratio in the non-gold allocation.

| Quantity | A, without gold | B, 15% gold |
|---|---:|---:|
| Final reference wealth | ₹1,35,342 | ₹1,54,105 |
| Cumulative return | 35.34% | 54.10% |
| CAGR | 6.24% | 9.03% |
| Evaluated annual volatility | 8.16% | 7.50% |
| Evaluated maximum drawdown | −9.08% | −8.03% |

Gold improved these measured outcomes in this period. That is not a universal diversification claim or forward expectation. Risk shares change materially by window and episode.

### Indian versus international equities

On identical dates, NIFTY50 **gross TRI** returned35.57%; SPY **actual fund reference exposure in INR** returned149.81%. These are different instrument types, with index expenses absent and fund expenses embedded. SPY's components: USD fund92.33pp, USD/INR29.89pp, interaction27.59pp =149.81pp. The currency contribution is not simply added without interaction; source fixing lag limits exact contemporaneous interpretation.

### Government maturities during RBI tightening

Evaluated4 May2022–15 February2023: GILT5YBEES returned **3.22%**, volatility3.06%, max weekly drawdown−1.56%; LTGILTBEES returned **4.23%**, volatility4.59%, drawdown−1.93%. Longer maturity earned more over this window and was more volatile. Rate increases are not the sole explanation: carry, yield expectations, fund pricing/tracking and start/end selection matter. A true short-duration government comparison is not claimed.

### Lump sum versus SIP

For B, ₹10,000 on monthly day1, rolled to eligible dates: **61 contributions**, first6 October2021, last7 October2026. Gross capital **₹6,10,000**, terminal reference wealth **₹7,65,048**, gain **₹1,55,048**, XIRR **9.0884%**, flow-adjusted TWR **54.1417%**.

Investing the same gross₹6,10,000 at the first date, with the same5bps purchase fee and monthly rebalance cost, gives terminal **₹9,39,569**, money-weighted XIRR **9.0131%**. Total subscription charges are₹305 in each case; they occur at different dates. SIP's slightly higher money-weighted rate does not imply greater wealth: most SIP capital spends less time invested. Lump-sum underlying CAGR9.03% and SIP XIRR are not interchangeable metrics. Cash flows can alter allocation drift, so SIP's flow-adjusted TWR need not exactly equal the lump-sum path.

### Diversification in a supported Indian episode

RBI tightening window: A return4.94%, max weekly drawdown−5.39%; B return5.80%, drawdown−4.72%; NIFTY TRI drawdown−7.91%. B's fixed-target risk shares move: equity **99.45%→86.63%**, gilt **2.65%→6.66%**, gold **−2.10%→6.71%**, pre52/during41 returns. Gold did not remain a negative variance contributor, despite helping realised returns in this episode. Empirical covariance is not a causal policy effect.

For a separate2022 allocation NIFTYBEES40/GILT5YBEES30/GOLDBEES10/SPY20, exact portfolio components are domestic+3.0699pp, foreign market−3.7284pp, currency+2.1100pp, interaction−0.0573pp, costs−0.0111pp = **+1.3831%**. Rupee movement offset part of the foreign loss in the observed reference marks; it did not eliminate foreign-market risk.

Additional model evidence for B:261 weekly intervals, equity coefficient0.5002, currency−0.0568, R²0.8558. This domestic-gold portfolio is not automatically called a currency hedge. Regime month counts: RBI6 tightening/4 easing/49 unchanged; CPI14 rising/16 falling; FX37 depreciation/22 appreciation. Small/unplotted states and gaps remain transparent.

## 5. Visual design and review

Studied actual CPI contributions, IIP momentum, consumer confidence, overnight monetary conditions, NFCI, banking liquidity, Global Rate Cycle and long-history Weekly figures, plus EconStyle and current Lab outputs. Reused their editorial rules, meaningful colours, explicit units, direct values and paired analytical questions. Indian tickers and risk labels were shortened for legibility, while exact identities remain accessible. The final pass incorporates the concurrent presentation work: shared centered 900px chart placement, scoped Inter typography, editorial summary tables, full-width normalization controls, and the investor entry cards. INR legends stack vertically and overlapping axis ticks are suppressed on narrow screens; SIP metrics use the same compact table as lump-sum outcomes.

Six real-data composition trials were generated and opened:

- [Wealth1](../output/portfolio_lab/india/alternatives/wealth-1.png), [Wealth2](../output/portfolio_lab/india/alternatives/wealth-2.png): shared substantial wealth plot selected; aligned wealth/drawdown retained as an alternative.
- [SIP1](../output/portfolio_lab/india/alternatives/sip-1.png), [SIP2](../output/portfolio_lab/india/alternatives/sip-2.png): capital/value overlay selected for direct A/B comparison; shaded portfolio small multiples retained.
- [Stress1](../output/portfolio_lab/india/alternatives/stress-1.png), [Stress2](../output/portfolio_lab/india/alternatives/stress-2.png): losses plus risk-share shifts selected; full-width losses above before/during correlation matrices retained.

Static exports use canonical EconStyle header/top rule/source/wordmark/save_chart. The INR wealth plot explicitly labels its nonzero observed-value range so modest fluctuations remain distinguishable; logarithmic scaling is explicit. SIP capital/value retains a zero baseline. Interactive charts retain sufficient height, stronger horizontal guides, INR lakh/crore axes, Indian-grouped rupee values and responsive legends. Invested capital is stepped at contribution dates. Reconciled FX bars, signed capital/risk comparisons, factor intervals and regime quantiles have distinct purposes rather than repeating default chart types.

Desktop (1280×800) and mobile (390×844) screenshots are retained in [screenshots](../output/portfolio_lab/india/screenshots/). These are sequential viewport captures, not one-shot full-page images. Wealth, SIP, stress losses/risk, FX decomposition, factors and macro distributions were visually reviewed; final mobile wealth and summary captures confirm responsive labels and tables. UI examples use their visible preset allocations; the controlled gold study above uses51/34/15 and is separately labelled in the static previews/report.

## 6. Verification

Latest full source suite: **663 passed**. Expanded focused suite: **52 passed**; subsequent core/UI checks: **40 core** and **11 India/UI tests passed**. Logs are in `output/portfolio_lab/india/`. Independent direct share-unit/fixed-point-cost calculations match both lump-sum and SIP wealth; NumPy covariance reproduces signed shares; independent least squares matches fitted coefficients; exact multiplicative FX and portfolio P&L reconcile; XIRR NPV is effectively zero.

Focused tests cover source timestamps/DST/federal holidays, missing/nonpositive FX, no future US close, no second INR conversion, NAV plan/permission/ISIN/inception, contribution timing/units/capital, stopping subscriptions before terminal valuation, conventional/ambiguous XIRR flows, arbitrary eight-holding cases, cost reconciliation, canonical CPI base boundary, real RBI decisions, history availability, mode switching and state preservation. Synthetic fixtures are test-only; none enter canonical or production histories.

Global regression tests retain previous methodology/defaults. No existing tests were weakened. Full suite is scoped to the repository's `tests/` directory; unrelated ignored audit-output copies are not source tests.

## 7. Deployment readiness and remaining gates

Feature files changed: `data/paths.py`, `portfolio_lab/page.py`, `charts.py`, `README.md`; shared `portfolio_analytics.py`, `portfolio_attribution.py`, `portfolio_stress.py`. New files: `config/portfolio_india_settings.py`, `data/fetchers/portfolio_india.py`, the three India/currency/SIP processors, `portfolio_lab/india.py`, `verify_india.py`, `render_india_alternatives.py`, the two India test modules and the feasibility/implementation reports. Unrelated app/dashboard/database/workflow changes in this shared checkout are not part of this feature.

Ready: local curated reference research, both modes, exact INR/FX accounting, SIP/XIRR, supported macro/factor/stress calculations and retained visual alternatives. Explicit CLI collection/preparation, immutable inputs and cache separation are implemented.

Not claimed ready: executable fund-NAV/order simulation, corporate-debt benchmarks, licensed true short-duration government indices, AMFI Direct/Growth scheme coverage, vintage-verified FX publication and real-time investability/tax/remittance eligibility.

The owner confirmed source permissions for the public datasets. The release includes the active snapshots, original source identities and validation evidence. Deployment needs no additional data storage or snapshot secrets. Refresh using DEPLOYMENT.md, then run the repository and portfolio deployment checks before accepting updated data.
