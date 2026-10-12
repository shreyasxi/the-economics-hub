> **Deployment update (12 October 2026):** The owner confirmed source permissions. Validated Global, macro and India datasets now ship publicly in Git under `data/published/portfolio_lab/`. See [DEPLOYMENT.md](DEPLOYMENT.md) for validation and refresh commands. No separate storage or snapshot secrets are required.

# Portfolio Lab — asset expansion and visual redesign

Local review build, 11 October 2026. No commit, push, merge or deployment. Portfolio Lab retains its own navigation tab beside Analysis. Unrelated dashboards and workflows were preserved.

## A. Assets, calendar and rights

28 instruments now available: the existing 26 ETFs, USO and direct BTC reference exposure. Immutable local snapshot `20261011T104200Z-bbcd77e1`; raw histories, corporate actions, alignment evidence and hashes stay in ignored `data/stores/portfolio_lab/`.

| Instrument | Verified source coverage | Evaluation coverage | Return methodology |
|---|---|---|---|
| BTC | 5,929 daily PriceUSD labels, 2010-07-18–2026-10-10 | 4,083 ETF sessions, 2010-07-19–2026-10-09 | Direct reference-price ratios; no distributions or yield |
| USO | 5,158 fund closes, 2006-04-10–2026-10-09 | Actual observed history, no backfill | Explicit adjusted-close fund returns |

[Coin Metrics PriceUSD documentation](https://github.com/coinmetrics/docs-website/blob/master/asset-metrics/market/priceusd.md) defines the daily value as the labelled UTC day's end-of-day fixing. The implementation conservatively makes midnight labels effective **one day later**. Raw seven-day history and timezone-bearing timestamps are preserved. Missing, duplicate, unordered, non-midnight, nonpositive or wrong-asset observations are rejected.

The evaluation calendar uses SPY's actual observed sessions. At **16:00 America/New_York (20:00/21:00 UTC)**, BTC uses the session date's 00:00 UTC fixing: the preceding UTC day's close. Exact fixing/checkpoint evidence prevents future joins. ETFs use actual session closes, including earlier holiday closes. This is asynchronous reference valuation, not simultaneous executable prices. Revised history establishes fixing-time alignment, not historical API publication latency or point-in-time availability.

Friday-to-Monday BTC ratios compound all intervening source-day changes. Weekends remain in raw data; no flat ETF weekend rows are manufactured. Interior missing prices block calculations; outside coverage stays unavailable. No unlimited carry-forward. Volatility uses √252 evaluation intervals; drawdown omits intrainterval/weekend extremes. Comparisons share identical dates.

Rebalances are hypothetical transfers at reference marks with drift, target weights and optional costs on buys plus sells. Achievable execution at the stale BTC fixing is not claimed. Custody, spreads, slippage, taxes and liquidity constraints are excluded. Early BTC reference prices do not establish that a $10,000 allocation could actually have been implemented at those prices. Large early-history growth is retained, with an explicitly selected logarithmic scale option.

### USO and April 2020

USO is an exchange-traded commodity pool holding oil-related futures. WTI spot is a market-price reference; futures require explicit maturities/rolling; a fund additionally reflects its holdings, expenses and mandate changes. No spot returns or synthetic continuous contracts replace USO. Contango can erode a rolling long position relative to spot, while backwardation can have the opposite effect; neither guarantees long-term tracking.

The [issuer](https://www.uscfinvestments.com/uso) and [SEC filing](https://www.sec.gov/Archives/edgar/data/1327068/000110465920091976/uso-20200630x10q.htm) verify the **1-for-8 reverse split after 28 April 2020 close, adjusted trading on 29 April**. Source split=0.125. Yahoo Close/Adj Close already incorporate it; no second adjustment is applied. Verified 29 April return **+5.6338%**, April return **−43.2304%**, worst 2020 daily return **−25.3150%**. Actual severe losses are preserved; fake eightfold jumps are rejected.

[April holdings disclosure](https://www.sec.gov/Archives/edgar/data/1327068/000117120020000242/i20244_uso-8k.htm) and [issuer resources](https://www.uscfinvestments.com/resources/uso) document changing futures exposures during the disruption. Current rolling rules are not applied retroactively. Vendor split/distribution-factor checks pass. This remains a vendor return proxy, not a contract-level reconstruction or independently licensed total-return index.

[IBIT](https://www.ishares.com/us/products/333011/ishares-bitcoin-trust-etf) was investigated as a separately labelled custody/fee wrapper with January 2024 history; it was not added because direct BTC satisfies this release. [USL](https://www.uscfinvestments.com/usl) offers a materially different equal-weighted twelve-month futures profile; it is deferred pending its own history/action audit. Neither inherits synthetic earlier data.

### Licensing

[Coin Metrics Community](https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data) and its [data repository](https://github.com/coinmetrics/data) specify **CC BY-NC 4.0**: attribution and noncommercial conditions apply. Free API access does not establish commercial rights. The owner confirmed source permissions for this public release. Active source histories and evidence are included under `data/published/portfolio_lab/`.

## B. Visual redesign

Opened actual finished Banking Liquidity, NFCI, India CPI Contributions, urban/rural Consumer Confidence, RBI sentiment trajectory, weekly credit spreads, showcase crude curve and Global Rate Cycle figures. Inspected `charts/style.py` and `charts/world_charts/world_rate_cycle_dashboard.py`. Their strong top rules, editorial hierarchy, meaningful colours, direct numbers, restrained grids, clear periods and ample vertical space set the standard.

The old Lab gave too much space to input widgets and dense tables, repeated weak time-series treatments and lacked a clear question-first hierarchy. The builder/assumptions now collapse, visible summaries retain holdings/period/costs, wealth leads every view, and supporting exact tables sit in expanders. A/B inputs persist across views.

| View | New composition |
|---|---|
| Wealth | Shared 440px wealth plot; A blue/B teal/benchmark dashed grey; endpoint marks and final values; initial $10,000 guide; explicit linear/log |
| Attribution | Sorted horizontal signed contributions on shared pp scale; A/B rows, zero rule, outward numeric labels, separate costs and exact reconciliation |
| Risk | Signed variance-contribution bars with capital diamonds and numerical capital row labels; no 0–100 clipping |
| Factors | Coefficient/95% HAC intervals transformed to separate SPY−10%, yield+100bp, optional OAS+100bp responses, all in weekly-return pp |
| Regimes | 10–90/25–75 percentile intervals, median dots, observed-month counts and classification timeline |
| Stress | Episode drawdowns paired with before/during signed risk shares; exact episode attribution below |
| Supporting | Annotated fixed-range correlation heatmaps; refined rolling lines and diagnostic charts |

Banking Liquidity motivated connected analytical panels; India contributions motivated signed attribution; Consumer Confidence and long-history figures informed restrained alignment and endpoint values. Global Rate Cycle informed visible reporting/estimation periods. No mixed-unit coefficient axis, extra explanatory BTC/oil factors or pooled regime annualisation was introduced.

### Alternatives retained and inspected

Generate with `python -m portfolio_lab.render_alternatives`. Every static preview retains canonical EconStyle header/top rule/source/wordmark and `save_chart`.

- [Wealth 1 — shared overlay](../output/portfolio_lab/redesign/alternatives/wealth-1-overlay.png): chosen for maximum vertical resolution and final-wealth comparison.
- [Wealth 2 — wealth plus drawdown](../output/portfolio_lab/redesign/alternatives/wealth-2-wealth-drawdown.png): informative, but splits flagship height. Drawdown remains in Overview.
- [Stress 1 — losses plus risk concentration](../output/portfolio_lab/redesign/alternatives/stress-1.png): chosen because covariance contributions incorporate allocation sizes and connect directly to portfolio risk.
- [Stress 2 — losses plus correlation shifts](../output/portfolio_lab/redesign/alternatives/stress-2.png): useful relationships, but less direct without position sizes; correlation detail remains accessible.

Title/legend alignment was corrected after opening the previews.

## C. Validation and executed results

Predetermined illustrative A=SPY60/AGG40; B=SPY45/AGG30/GLD10/BTC5/USO10. Common closes **2014-01-02–2026-10-09**; monthly rebalancing; 5bps on buys plus sells; initial $10,000; SPY benchmark without incremental costs. Not optimised or recommended.

| Quantity | A | B | SPY |
|---|---:|---:|---:|
| Final wealth | $30,603.55 | $39,735.29 | $52,666.09 |
| Cumulative return | 206.04% | 297.35% | 426.66% |
| CAGR | 9.16% | 11.41% | 13.90% |
| Evaluated annualised volatility | 10.55% | 10.44% | 17.10% |
| Evaluated max drawdown | −21.63% | −24.77% | −33.72% |

B accounting attribution (pp): SPY159.0531, AGG9.5669, GLD31.5717, BTC60.6454, USO36.9844, costs−0.4685 = **297.3529pp**. Independent share-unit simulation and fixed-point cost calculation reproduce wealth; independent sample covariance reproduces signed risk shares. Weekly OLS matches independent least squares:661 intervals, equity0.5667, rate−1.1939, R²0.726. Regime processing supplies151 matched months before dimension-specific omissions.

| Episode | A return / max drawdown | B return / max drawdown | BTC / USO standalone return |
|---|---|---|---|
| COVID, 2020-02-19–04-30 | −6.87% / −21.49% | −15.73% / −24.65% | −14.06% / −78.62% |
| 2022, 2022-01-03–12-30 | −15.89% / −20.53% | −13.24% / −18.64% | −64.88% / +27.87% |
| Global Financial Crisis | Comparison unavailable with BTC | Explicit incomplete-BTC-history warning | No proxy/backfill/renormalisation |

In 2022, B's SPY variance share rises53.54%→67.03%, AGG0.72%→7.67%, BTC17.15%→7.21%, USO23.58%→13.19%. Pre252/during250 observations, fixed target weights. Ex-post covariance associations are not causal explanations or information available before the crisis.

Full audit: [validation.json](../output/portfolio_lab/redesign/validation.json), reproducible with `python -m portfolio_lab.verify_expansion`.

### Checks

- Repository suite **646 passed** (`pytest tests -q`) before the final additional UI check. Unscoped collection hits duplicate test modules in a pre-existing ignored India-audit output; no unrelated files were removed to conceal this.
- Expanded focused suite **46 passed**. Final core/data/research **41 passed** and final UI **5 passed** after polishing.
- Tests cover DST/UTC, raw weekends and weekend compounding, no future matching, missing fixings, no prehistory/tail carry, reverse splits, common windows, weights/drift/rebalancing/costs, attribution, covariance, factor units, stress availability and hypothetical shocks. UI checks include BTC/oil allocations across every view and the 2008 unavailable state. Logs remain in `output/portfolio_lab/redesign/`.
- Factors require104 matched weeks and expose uncertainty/window/sample/poor-fit diagnostics. Regimes retain minimum evidence thresholds and descriptive ex-post labels.

Actual rendered review: desktop1280×720 and mobile390×844, scrolling through controls and outputs. The review caught/fixed frontend padding errors missed by Python AppTest, serif legend text, negative-label direction, dense factor/regime grids and an invisible timeline. Mobile controls wrap, legends stack and paired stress charts become sequential panels. Large holding sets increase chart height; heatmap annotations above ten assets are omitted while retaining tooltips/tables.

Before/after evidence in [screenshots](../output/portfolio_lab/redesign/screenshots/): `before.jpg`, desktop wealth/attribution/risk/factors/regimes/stress and mobile counterparts. Multiple viewport captures retain context and complete chart axes; these are not labelled full-page screenshots.

## D. Files and publication readiness

Changed by this request: `config/portfolio_settings.py`; `data/fetchers/portfolio_prices.py`; new `portfolio_bitcoin.py`; `portfolio_lab/charts.py`, `page.py`, `research.py`, `README.md`; new `render_alternatives.py`, `verify_expansion.py`, this report; `tests/test_portfolio_data.py`, `test_portfolio_ui.py`; new `test_portfolio_expansion.py`. Existing analytical processors are intact.

Before public release:

1. Establish ETF-feed display/redistribution and ICE-factor rights; confirm Coin Metrics noncommercial compliance/attribution or obtain commercial permission.
2. Prepare licensed immutable bundles in deployment, keep raw source histories outside Git, rerun numerical/source checks.
3. Review asynchronous BTC valuation and early-history execution limits; approve the feature diff separately from unrelated checkout work.
4. Only with explicit approval, commit/push/merge/deploy. No scheduling or deployment workflow was changed.

Ready for deployment validation with the versioned public datasets.
