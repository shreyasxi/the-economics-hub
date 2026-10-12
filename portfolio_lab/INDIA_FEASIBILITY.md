> **Release update:** Source permissions are confirmed by the owner. The active datasets are published with the application; this earlier feasibility report retains the source and instrument decisions.

# Indian Investor Mode — architecture and source feasibility

12 October 2026; dedicated branch `codex/indian-investor-mode`. Existing uncommitted work remains intact. No workflows, commits or deployment.

Reuse the N-asset holdings simulator, attribution ledger, sample covariance, HAC regression and shock arithmetic. Add currency/source normalisation before simulation; add a cash-flow wrapper that reuses the simulator between contributions. Keep global defaults unchanged. Mode-specific widget keys isolate allocations.

Existing official gross NIFTY TRI snapshot covers roughly September 2021–9 October 2026, with response receipts, independent spot checks and hashes. Approve NIFTY50, Next50, Midcap150 and Smallcap250 for local benchmark research after validating each actual series. Index history is not fund history; provider back-casts are not evidence of investability. Do not refresh NSE automatically: its terms require written consent for automated collection and redistribution.

AMFI publishes NAV identities/history, but the current curated universe does not include bulk AMFI data. A strict growth-NAV import boundary will require scheme code, ISIN, AMC, plan, option, continuity and a permission statement. Index and fund data cannot be silently interchanged.

Initial investable examples will investigate Yahoo-adjusted Indian ETFs: NIFTYBEES, GOLDBEES, GILT5YBEES, LTGILTBEES and growth-accumulating LIQUIDCASE. NSE circular CML52187 establishes the 2022 symbol changes for the gilt ETFs; no manually stitched histories. Validate Yahoo INR identity, explicit adjustments/actions, source coverage and liquidity; omit any failed instrument. Debt ETF prices represent actual vehicles, not the entire sovereign market or fund NAVs. Never use yields as investment returns. Corporate-debt exposure remains outside the approved universe until an appropriate validated return history exists.

Reuse SPY/EFA/EEM adjusted USD histories. Investigate FBIL first, retaining its reference-rate definition. The public Federal Reserve H.10 USD/INR alternative has explicit New York noon fixings and weekly publication; use publication-lag-aware historical reference marks, with a disclosed weekly evaluation calendar to avoid pretending the FX series is a contemporaneous executable Indian close. Quote time and public release time must remain separate. No second conversion of INR instruments. Exact INR return = foreign return + FX return + interaction.

RBI effective repo decisions are already stored in Sentinel's read-only database; canonical MoSPI CPI histories have validated base transitions. Use ex-post monthly classifications and do not use tone scores as rates. Domestic liquidity history is only around one year: investigate coverage, without broad historical causal claims. Factor model starts with Indian equity and FX only; no unsupported duration or credit sensitivities.

Expected first release: curated index/fund/mixed portfolios; INR wealth/attribution/risk; exact FX decomposition; monthly SIP with actual dated cash flows/XIRR; RBI/CPI/currency descriptive distributions; supported 2022 stress replay and direct scenarios. Earlier crises explicitly unavailable when the required index/fund history is missing. Extend only after source validation. Public display remains a licensing gate; no restricted market histories enter Git.

Sources: [NSE terms](https://www.niftyindices.com/terms-of-use), [fixed income convention](https://niftyindices.com/reports), [AMFI terms](https://www.amfiindia.com/terms-of-use), [FBIL licensing FAQ](https://www.fbil.org.in/uploads/Data_Fee_Schedule_FAQ_repl_3576a15203.pdf), [Federal Reserve H.10 convention/publication](https://www.federalreserve.gov/releases/h10/hist/), [gilt symbol continuity](https://archives.nseindia.com/content/circulars/CML52187.pdf).
