"""
Economics Hub — Chart Insights & Practical Takeaways
======================================================
Maps each chart's filename stem (after stripping leading numeric prefix) to a
2-paragraph institutional-grade analysis string rendered in Markdown.

Usage:
    from config.insights import get_insight
    text = get_insight("09_vix_trend.png")   # → str or None
"""

import re
from pathlib import Path


def get_insight(filename: str) -> str | None:
    """Return the insight string for a given chart filename, or None if not found."""
    key = re.sub(r"^\d+[a-z]*_", "", Path(filename).stem)
    return CHART_INSIGHTS.get(key)


# ---------------------------------------------------------------------------
# CHART_INSIGHTS dictionary
# Key: filename stem after stripping leading "NN_" or "NNa_" prefix
# Value: 2-paragraph Markdown string
# ---------------------------------------------------------------------------

CHART_INSIGHTS: dict[str, str] = {

    # ── WEEKLY: EQUITIES ────────────────────────────────────────────────────

    "equities_weekly": """\
**How to read this chart:** Each bar shows the percentage price return of a major equity index over the past five trading days. Green bars indicate positive weekly performance; red bars indicate drawdowns. The zero line anchors the visual — the steeper the departure from zero across the entire chart, the more directional and correlated the week's global equity move was. Divergence between, say, US indices and Asian ones is often the more interesting signal than the absolute magnitude of any single bar.

**Practical takeaway:** A broad selloff (all bars red, similar depth) typically reflects a macro catalyst — rate shock, geopolitical event, or liquidity withdrawal — rather than idiosyncratic country risk. When India (Nifty 50) or Japan (Nikkei) diverges from the US/Europe complex, look for a domestic catalyst: RBI/BOJ policy surprise, earnings season timing, or currency-driven flows. Sustained weekly underperformance in EM versus DM is an early signal worth tracking in the credit spread and VIX charts below.
""",

    "equities_trend": """\
**How to read this chart:** Three major indices — S&P 500, Nifty 50, and FTSE 100 — are indexed to 100 at the start of the trailing 12 months, allowing a like-for-like performance comparison regardless of their native currency levels. Convergence of the lines signals correlated global risk sentiment; persistent divergence reveals which markets are being driven by domestic vs. external factors.

**Practical takeaway:** When Nifty 50 consistently outperforms SPX on this 12-month basis, it reflects India's structural domestic demand story and relative insulation from US tech sector volatility. A sharp convergence downward — all three lines compressing toward the 100 baseline — is a reliable signal of a global risk-off event. FTSE's persistent underperformance relative to SPX since 2022 reflects the structural FX headwind from sterling weakness and the UK's higher commodity-import inflation exposure.
""",

    # ── WEEKLY: FOREIGN EXCHANGE ────────────────────────────────────────────

    "fx_weekly": """\
**How to read this chart:** Weekly percentage moves in major currency pairs, anchored by the DXY (US Dollar Index). For cross rates like EUR/USD and GBP/USD, a positive bar means the dollar *weakened*; for USD/INR and USD/CNY, a positive bar means the dollar *strengthened* against the respective EM currency. The DXY move sets the directional context — if it dominates as the largest mover, the week's FX story is a dollar narrative, not a bilateral one.

**Practical takeaway:** Dollar strength weeks (DXY up, EM pairs showing dollar appreciation) tend to coincide with risk-off sentiment, rising US yields, or hawkish Fed rhetoric. Watch the USD/INR bar against the India VIX: when the rupee depreciates alongside rising India VIX, it signals portfolio capital outflows. A divergence where USD/JPY weakens sharply without a corresponding DXY move may indicate a carry trade unwind — historically a precursor to broader EM volatility.
""",

    "fx_trend": """\
**How to read this chart:** Key FX rates over the trailing 12 months, all indexed to 100 at the start. Because DXY and cross rates move in opposite directions for "dollar strength," compare the *slope* of each line rather than the absolute level. A rising USD/INR line alongside a falling EUR/USD line confirms a broad dollar appreciation cycle.

**Practical takeaway:** Sustained DXY appreciation over more than two quarters historically correlates with EM central bank intervention, tighter financial conditions in dollar-indebted economies, and downward pressure on commodity prices (oil, gold priced in USD). For India-watchers, the USD/INR trend over 12 months matters more than any single week's move — a structurally depreciating rupee erodes real import costs, widens the current account deficit, and forces RBI to deploy FX reserves.
""",

    # ── WEEKLY: GOVERNMENT BOND YIELDS ─────────────────────────────────────

    "yield_curve": """\
**How to read this chart:** This three-panel chart captures the full information set of US Treasury yield curves: the current curve shape, the change in yields since 4 weeks ago (tactical signal), and the change since 52 weeks ago (cyclical signal). An inverted curve — where short-end yields exceed long-end — has preceded every US recession since the 1970s with a typical lag of 12–24 months. The 2s10s spread is the canonical inversion metric.

**Practical takeaway:** When the 4-week change shows the short end rising faster than the long end, the Fed is still tightening expectations. When the 52-week change shows the long end rising faster than the short end (steepening), the bond market is repricing term premium — often driven by fiscal deficit concerns or inflation persistence. A bull steepener (short end falling faster) is typically the most risk-positive yield curve regime for equities, as it signals expected rate cuts without a growth collapse.
""",

    "us_yield_trend": """\
**How to read this chart:** The 2-year and 10-year US Treasury yields plotted over a 2-year trailing window provide the rate *level* context that the yield curve panel does not. The 2Y yield is the market's best real-time estimate of where the Fed Funds rate will be in two years — it leads Fed policy. The 10Y yield is the global risk-free rate benchmark that prices everything from mortgages to equity discount rates.

**Practical takeaway:** When 2Y yields are rising faster than 10Y (spread compressing or inverting), risk assets typically face headwinds. When 10Y yields rise without a corresponding 2Y move, it signals term premium repricing — a different, more structural concern driven by debt supply and foreign demand for US Treasuries. For equity investors, the absolute level of the 10Y yield matters more than its direction: a 10Y above 4.5% creates meaningful competition for the equity risk premium at current SPX valuations.
""",

    # ── WEEKLY: COMMODITIES ─────────────────────────────────────────────────

    "commodities_weekly": """\
**How to read this chart:** Weekly percentage changes across the core commodity complex — energy (WTI, Brent), metals (gold, silver, copper), and key agricultural inputs (wheat). The spread between energy and metals moves is important: simultaneous selloffs in oil *and* copper typically signal a demand-led global growth concern, whereas an oil spike with copper weakness is more consistent with a supply shock or geopolitical premium.

**Practical takeaway:** Gold's weekly move relative to oil is a reliable sentiment proxy — rising gold with falling oil indicates safe-haven demand (risk-off) rather than commodity cycle momentum. For India specifically, a weekly WTI/Brent spike directly pressures the current account and INR; a 10% oil shock over 4–6 weeks historically adds ~30–40 basis points to India's inflation. Uranium's presence in this chart tracks the long-cycle nuclear energy investment thesis, which runs on a very different cycle than the weekly commodity complex.
""",

    "commodities_trend": """\
**How to read this chart:** Brent crude, gold, silver, and copper indexed over 12 months reveal the structural commodity cycle — whether we are in an energy/resource upcycle or a deflationary commodity bust. Copper's outperformance of gold signals global industrial activity expansion; the reverse signals contraction or stagflation concerns.

**Practical takeaway:** The Brent/Gold ratio within this chart is a powerful macro regime indicator: a rising ratio (oil outperforming gold) signals an inflationary expansion; a falling ratio signals either a growth slowdown, a geopolitical premium on gold, or a supply-driven oil decline. Silver's behaviour relative to gold reveals the industrial demand overlay — silver has both monetary and industrial uses, so it outperforms gold in genuine commodity supercycle phases and underperforms in pure flight-to-safety moves.
""",

    # ── WEEKLY: VOLATILITY & SENTIMENT ─────────────────────────────────────

    "vix_trend": """\
**How to read this chart:** The CBOE VIX (30-day implied volatility) and VIX 3-Month are plotted together over 12 months. The *spread* between these two series — the VIX term structure — is as important as the absolute level. A VIX above 20 signals elevated near-term risk pricing; above 30 signals acute stress. When 30-day VIX rises *above* the 3-month VIX (an inverted term structure), the market is pricing an immediate shock as time-limited — typically a buying opportunity rather than a structural break.

**Practical takeaway:** The most actionable signal is a VIX spike followed by rapid mean-reversion back below 20 while equities remain weak — this "orphaned spike" pattern can indicate a deeper structural problem that options markets have not yet priced at longer horizons. Conversely, a slow, grinding VIX rise from 15 to 25 over several weeks without a sharp equity correction is a warning sign of building systemic stress. The 20 and 30 threshold levels on this chart are not arbitrary — institutional risk mandates globally use them as triggers for portfolio de-risking.
""",

    "sector_rotation": """\
**How to read this chart:** Weekly percentage returns for all 11 S&P 500 GICS sectors, sorted from best to worst performer. This chart reveals whether a weekly equity move was *broad* (most sectors positive or negative) or *narrow* (rotation between cyclicals and defensives). The sector that leads in a given week tells you what the market is pricing: Technology leadership = risk appetite + earnings growth premium; Utilities/Staples leadership = defensive flight; Energy leadership = commodity/geopolitical narrative.

**Practical takeaway:** Sustained sector rotation from Technology/Consumer Discretionary (growth) into Utilities/Health Care/Consumer Staples (defensive) over multiple weeks is a reliable leading indicator of equity weakness — it reflects institutional portfolio managers shifting to defensive positioning before absolute losses appear. Financials as the top-performing sector in a given week typically signals a yield curve steepening expectation or credit condition improvement, both of which are positive for the broader market. Watch for Energy leading while Technology lags — this combination often reflects stagflation concerns rather than healthy growth.
""",

    "india_sector_rotation": """\
**How to read this chart:** Weekly percentage returns for major NIFTY sector indices — Banking, IT, Auto, FMCG, Pharma, Metal, Realty, Energy, PSU Bank, and Infrastructure — sorted from best to worst. The relative performance of Bank Nifty vs. NIFTY IT is the single most important indicator of India's domestic vs. global narrative: banks outperforming IT signals domestic credit expansion; IT outperforming banks signals global tech spending recovery and/or rupee depreciation tailwinds.

**Practical takeaway:** PSU Bank leadership alongside Metal/Infra outperformance typically signals a government capex cycle — budget-driven infrastructure spending flowing into state-owned enterprises. FMCG outperforming cyclicals in India reflects rural demand recovery or urban consumption caution. When Realty and Auto underperform simultaneously, it often precedes an RBI tightening cycle concern. Compare this chart to the S&P sector rotation chart to distinguish India-idiosyncratic drivers from global sector rotation patterns that happen to flow through Indian indices.
""",

    "nifty_it_trend_custom": """\
**How to read this chart:** The NIFTY IT Index level over the trailing 12 months, with the most recent period highlighted. As the benchmark for India's IT services export economy — dominated by TCS, Infosys, Wipro, HCL, and Tech Mahindra — this index is simultaneously a proxy for global IT spending (demand-side) and INR/USD rate dynamics (supply-side). A 5–7% depreciation in the rupee adds roughly 2–3 percentage points to NIFTY IT earnings in rupee terms.

**Practical takeaway:** The NIFTY IT index is structurally sensitive to three forces: US corporate IT budget cycles (which lead the index by 2–3 quarters), generative AI disruption risk (a structural negative for traditional offshore services), and the INR/USD rate (a natural hedge that buffers dollar-denominated revenue). Watch for divergence between NIFTY IT and US tech (QQQ/XLK) — when Indian IT underperforms US tech for more than a quarter, it typically signals AI disruption concerns rather than cycle weakness. The sector has historically traded at a premium to the broader NIFTY 50 — a narrowing premium is a structural warning sign.
""",

    # ── WEEKLY: LABOUR & WAGES ──────────────────────────────────────────────

    "labour_market": """\
**How to read this chart:** Three FRED series plotted together capture the US labour market's health across different dimensions: JOLTS job openings (demand for labour), initial jobless claims (immediate layoff signal), and continued claims (duration of unemployment). A healthy labour market shows high openings, low initial claims, and low continued claims simultaneously. The divergence between openings (a lagging indicator) and claims (a leading indicator) is the most actionable signal.

**Practical takeaway:** Rising initial jobless claims over consecutive weeks is the single most reliable leading indicator of a Fed pivot — the Fed has historically cut rates within 12 months of a sustained claims increase. Continued claims rising faster than initial claims signals that displaced workers are struggling to find re-employment, a more structurally concerning signal than mere layoffs. The JOLTS openings-to-unemployed ratio (openings divided by unemployed workers) is the Fed's preferred measure of labour market tightness — above 1.5x, the Fed sees persistent wage inflation risk; below 1.0x, it signals labour market normalisation.
""",

    "wage_growth": """\
**How to read this chart:** Average Hourly Earnings (AHE) year-over-year percentage change for total private employees. This is the Fed's primary wage inflation tracker — sustained growth above 4% on a YoY basis, when combined with above-target CPI, has historically prompted tightening cycles. The chart's trend direction over 3–6 months is more important than the month-to-month print.

**Practical takeaway:** The "wage-price spiral" — where higher wages feed into service sector prices, which workers then demand compensation for — is the Fed's primary concern in a post-pandemic inflation context. Watch for the pace of deceleration: AHE decelerating from 5% to 4% is not the same as 5% to 3.5% — the latter implies genuine labour market slack. For equity markets, a sweet spot of 3.0–3.5% AHE growth is compatible with margin expansion and controlled input costs; above 4% in a period of slowing revenue growth is a margin compression signal.
""",

    # ── WEEKLY: CREDIT MARKETS ──────────────────────────────────────────────

    "credit_spreads": """\
**How to read this chart:** ICE BofA option-adjusted spreads (OAS) for Investment Grade (IG) and High Yield (HY) corporate bonds, plotted over 2 years on dual axes. HY spreads (left axis) represent the excess yield compensation demanded by investors over Treasuries for holding sub-investment-grade debt — a direct measure of systemic credit risk appetite. IG spreads (right axis, dashed) are narrower but move in the same direction. Alert thresholds at HY 400bps and IG 150bps mark the boundary between normal credit conditions and stress territory historically associated with equity drawdowns.

**Practical takeaway:** Credit spreads are the institutional investor's early warning system — they typically widen 4–8 weeks *before* equity markets fully price a deterioration. A spike in HY spreads above 400bps that persists for more than two weeks has preceded every significant S&P 500 correction since 2000. The IG/HY spread *ratio* matters as much as the absolute levels: when HY widens disproportionately relative to IG, it signals risk-specific concerns in levered corporate balance sheets rather than a broad macro shock. For macro investors, HY spreads compression to 250–300bps combined with rising equities is the "Goldilocks" credit regime.
""",

    "bond_etf_returns": """\
**How to read this chart:** TLT (20+ year Treasuries), LQD (investment-grade corporate bonds), and HYG (high-yield corporate bonds) indexed to 100 one year ago — showing total return including coupon income. This chart captures the full fixed income risk spectrum: duration risk (TLT), credit risk (LQD), and high-yield credit risk (HYG). The *relative* performance between these three tells you whether the bond market is underperforming due to rate moves (TLT down, LQD/HYG stable) or credit stress (HYG down more than LQD, both down more than TLT).

**Practical takeaway:** HYG outperforming TLT over 12 months is consistent with the equity bull market narrative — credit conditions are loose enough that investors are rewarded for moving down the credit quality spectrum. When TLT significantly underperforms both LQD and HYG, the primary risk in fixed income is duration (interest rate sensitivity), not credit — actionable for investors holding long-duration pension liabilities or mortgage-backed securities. A scenario where all three decline simultaneously indicates a rare "bear market in bonds" — typically driven by supply-demand imbalance in the Treasury market rather than credit deterioration.
""",

    # ── WEEKLY: INFLATION SIGNALS ───────────────────────────────────────────

    "breakeven_inflation": """\
**How to read this chart:** TIPS-derived breakeven inflation rates — the market's real-time estimate of average annual CPI over the next 5 and 10 years. These are computed as the spread between nominal Treasury yields and TIPS real yields of the same maturity. When breakevens exceed the Fed's 2% target (shown as a dashed reference line), the bond market is saying it does not believe inflation will sustainably return to target — a signal the Fed takes seriously in calibrating policy.

**Practical takeaway:** The 5Y/10Y breakeven *spread* (5Y minus 10Y) is a sophisticated signal: a positive spread (5Y > 10Y) indicates the market expects near-term inflation to be higher than long-term inflation — consistent with a transitory shock. A negative spread implies the market expects inflation to remain structurally elevated at the long end, which is the more hawkish and concerning signal for equity valuations. Breakevens above 2.8% for a sustained period (6+ months) historically correlate with multiple Fed tightening moves; below 1.8% they signal deflationary concern and typically precede equity underperformance in cyclical sectors.
""",

    "real_yields": """\
**How to read this chart:** 5-year and 10-year US TIPS real yields — the inflation-adjusted returns demanded by Treasury investors. A positive real yield means investors are receiving genuine purchasing-power-positive compensation for holding US debt; a negative real yield means the government is effectively paying investors less than inflation, a deeply unusual monetary policy condition last seen during QE programmes. The zero line here is the critical policy threshold.

**Practical takeaway:** Real yields are the most direct transmission mechanism of monetary policy to financial conditions. Rising real yields — especially from negative to positive — compress equity multiples (particularly growth stocks with long-duration earnings), strengthen the dollar, and put pressure on gold (which offers no yield). When 10Y real yields are above 2%, the opportunity cost of holding equities is historically high relative to risk-free alternatives. For EM investors, US real yields matter more than nominal yields: positive US real yields attract capital away from higher-yielding EM assets, driving portfolio outflows and currency pressure in India, Brazil, and South Africa simultaneously.
""",

    # ── WEEKLY: CROSS-ASSET RISK ────────────────────────────────────────────

    "copper_gold_ratio": """\
**How to read this chart:** The copper-to-gold price ratio (left axis, smoothed over 5 trading days) plotted against the US 10-year Treasury nominal yield (right axis, dashed). This is the "Gundlach indicator" — named after DoubleLine's Jeffrey Gundlach who popularised the observation that the copper/gold ratio leads 10-year Treasury yields by several months. Copper prices reflect industrial demand and global growth expectations; gold prices reflect safe-haven demand. A rising ratio means growth is beating safety — a risk-on signal. A falling ratio means safety is beating growth — a risk-off or deflationary signal.

**Practical takeaway:** When the copper/gold ratio diverges from the 10-year yield — specifically, when the ratio falls while the 10Y yield remains elevated — it is historically a reliable leading signal for yield compression (i.e., a Treasury rally). Portfolio managers use this as a bond entry signal. For equity investors, a sustained decline in the ratio over 8–12 weeks is a sector rotation signal: away from cyclicals (Industrials, Materials, Energy) and toward defensives (Utilities, Health Care, Consumer Staples). China is the world's largest copper consumer — a copper/gold ratio decline driven by Chinese demand weakness has very different portfolio implications than one driven by US recession fears.
""",

    "spy_tlt_ratio": """\
**How to read this chart:** The SPY/TLT price ratio — equity performance divided by long-duration Treasury performance — over 2 years, with the 52-week high/low range shown as a shaded band. This ratio rises when equities outperform bonds (risk-on regime) and falls when bonds outperform equities (risk-off or duration-driven flight-to-safety). The 52-week band contextualises whether the current ratio is at cycle extremes or within a normal range.

**Practical takeaway:** The SPY/TLT ratio breaking below its 52-week low is a significant regime-change signal — historically associated with the start of equity bear markets or the end of a reflationary cycle. Conversely, breaking above the 52-week high in a clean, sustained trend signals the market is fully risk-on and duration is being actively de-risked. For asset allocators, this ratio serves as a simple tactical trigger: a sustained decline toward the lower band suggests rotating from equity beta toward fixed income duration; a sustained rise suggests the opposite. The ratio is particularly useful for identifying when equities and bonds are "both working" (stagflation fear) versus the more normal environment where they trade inversely.
""",

    "risk_appetite_ratio": """\
**How to read this chart:** The SPHB/SPLV ratio — Invesco S&P 500 High Beta ETF divided by Invesco S&P 500 Low Volatility ETF — over 2 years, with a rolling 26-week mean as reference. This is a pure equity-complex signal that strips out fixed income and isolates whether equity investors are reaching for risk (high beta) or retreating to defensive stocks (low vol). Unlike SPY/TLT, this signal cannot be obscured by duration dynamics.

**Practical takeaway:** When SPHB/SPLV falls below its 26-week mean for more than three consecutive weeks, it signals institutional equity de-risking within the portfolio construction process — not just a sector rotation, but a genuine beta reduction. This is particularly valuable as a leading indicator in late-cycle markets when absolute equity levels may still be rising (momentum) even as risk appetite is quietly deteriorating. A sharp spike in the ratio following a prolonged decline indicates a capitulation-driven relief rally — statistically, these reversals tend to be aggressive but short-lived unless accompanied by credit spread compression and improving macro data.
""",

    "market_breadth": """\
**How to read this chart:** The RSP/SPY ratio — Invesco S&P 500 Equal Weight ETF divided by SPDR S&P 500 Cap-Weight ETF — with a 20-week moving average. Equal-weight indices assign each of the 500 companies the same weight (~0.2%), while cap-weight assigns Apple, Microsoft, and Nvidia weights of 6–7% each. A declining ratio means the market's gains are increasingly concentrated in the largest companies; a rising ratio means the rally is broad-based, with small and mid-cap S&P companies participating.

**Practical takeaway:** Sustained RSP/SPY decline over 2–3 quarters while the cap-weighted SPY continues to rally is one of the most reliable warning signs in technical macro analysis — a "hollow" market top driven by mega-cap momentum rather than broad economic expansion. This pattern appeared prominently in early 2000 and late 2021. For macro investors, improving RSP/SPY breadth is a necessary (though not sufficient) condition for declaring a genuine bull market rather than a concentrated tech bubble. When RSP/SPY rises while SPY is flat or declining (mean reversion in mega-caps), it often signals sector rotation into value and cyclical names — a positive signal for financials, industrials, and energy.
""",

    "gold_spx_ratio": """\
**How to read this chart:** The gold-to-S&P 500 price ratio over 2 years, with a 52-week rolling mean as reference. Gold prices reflect safe-haven demand, currency debasement fears, and geopolitical risk premium; SPX prices reflect US corporate earnings growth and risk appetite. A rising Gold/SPX ratio means investors are rotating from growth assets into protection — a meaningful signal given the opportunity cost of holding non-yielding gold.

**Practical takeaway:** The Gold/SPX ratio has historically peaked at, or slightly after, equity market tops in major bear markets — it is a coincident-to-lagging indicator of equity stress, not a leading one. Its primary value is as a *confirmation* signal: if equities are declining *and* the Gold/SPX ratio is rising, you have two-sided confirmation of a genuine risk-off regime. When gold rises alongside equities (both the ratio and SPX increasing), it can indicate a nominal growth environment where both real and financial assets are being inflated — often associated with dollar weakness and fiscal expansion. A Gold/SPX ratio sustainably above its 52-week mean while equities consolidate is a classic late-cycle positioning signal.
""",

    # ── WEEKLY: EMERGING MARKETS ────────────────────────────────────────────

    "em_fx_weekly": """\
**How to read this chart:** Weekly percentage change of six emerging market currencies against the US dollar — Brazilian Real, Mexican Peso, South African Rand, Turkish Lira, Indonesian Rupiah, and Korean Won. Bars are expressed as EM currency performance (positive = EM currency strengthened vs. USD). A week where all six bars are negative simultaneously indicates a broad dollar strengthening event; heterogeneous moves suggest idiosyncratic country-specific risk.

**Practical takeaway:** The most analytically valuable signal in this chart is *cross-currency divergence* within a single week. When the BRL and MXN (commodity-exporting, high-carry currencies) appreciate while TRY and IDR depreciate, it typically signals a commodity-driven EM distinction rather than a uniform dollar event. The Korean Won (KRW) is a particularly sensitive global risk barometer — its depreciation has historically preceded global equity corrections. Turkish Lira moves are almost entirely idiosyncratic (domestic inflation and unorthodox monetary policy), so TRY should always be read independently from the EM basket rather than as a systemic signal.
""",

    "em_equity_weekly": """\
**How to read this chart:** Weekly percentage returns for seven country ETFs across the emerging market universe: Brazil (EWZ), Mexico (EWW), South Africa (EZA), Taiwan (EWT), South Korea (EWY), India (INDA), and China (MCHI). Sorted from best to worst performer, this chart answers the critical EM allocation question: which countries are outperforming and which are absorbing the week's risk?

**Practical takeaway:** When India (INDA) outperforms China (MCHI) on a consistent weekly basis, it reflects the structural portfolio rotation from China into India that has been underway since 2022 among global EM fund managers. Korea (EWY) and Taiwan (EWT) tend to move in tandem — both are dominated by semiconductor giants (Samsung, TSMC) and are highly sensitive to the global technology cycle. South Africa (EZA) and Brazil (EWZ) are commodity proxies — their outperformance weeks almost always coincide with metals/energy price appreciation. A week where all seven ETFs are negative simultaneously is a dollar-strength event; a week where five of seven are positive indicates genuine EM risk appetite.
""",

    "india_vs_em_peers": """\
**How to read this chart:** India (INDA), the broad EM benchmark (EEM), China (MCHI), and South Korea (EWY) indexed to 100 one year ago on a total return basis. INDA is highlighted with a thicker line, making its performance trajectory versus peers immediately visible. This is the defining chart for India's investment thesis — it answers whether India is genuinely decoupling from EM or merely benefiting from a broader EM rally.

**Practical takeaway:** India's outperformance vs. EEM on this chart is structurally driven by four factors: higher domestic GDP growth, lower export dependence on China's demand cycle, a resilient domestic consumption base, and ongoing foreign institutional investor (FII) inflows following the MSCI weight increase. However, INDA underperforming EEM in any given month is not necessarily bearish for India — it can simply reflect China (which has a ~30% EEM weight) bouncing. Always decompose EEM's performance by checking MCHI separately. When INDA, EEM, MCHI, and EWY all decline simultaneously for 8+ weeks, it is a dollar-squeeze event rather than any country-specific story.
""",

"em_stress_monitor": """\
**How to read this chart:** Emerging market stress indicators — specifically combining EM High Yield sovereign credit spreads, EM Corporate spreads, and the Trade-Weighted US Dollar — provide a consolidated view of how international investors are pricing risk across the developing world. EM stress is heavily driven by external conditions (USD strength and US real yield levels) colliding with domestic vulnerabilities.

**Practical takeaway:** The most important principle in EM macro: external conditions (USD, US yields) are the *tide*, and domestic policies are the *swimming ability*. When the tide goes out (USD strengthens), all EM credit spreads face widening pressure. However, countries with sound fiscal positions and high FX reserves weather the storm far better than those with external financing needs. EM stress periods also create opportunities — historically, EM credit widening during a USD tightening cycle followed by a Fed pivot has been one of the most reliable mean-reversion trades in institutional macro.
""",

    # ── WEEKLY: ENERGY & AGRICULTURE ────────────────────────────────────────

    "brent_wti_spread": """\
**How to read this chart:** The Brent crude oil price minus WTI crude oil price, shown as a 5-day smoothed spread over 2 years. A positive spread (Brent premium) is the norm — Brent is the international benchmark reflecting seaborne crude supply from the North Sea, OPEC, and West Africa, while WTI is the US domestic benchmark. A widening Brent premium signals either geopolitical risk in international supply routes (Middle East, Russia) or a US supply surplus (Permian Basin oversupply, storage build at Cushing, Oklahoma).

**Practical takeaway:** A Brent-WTI spread widening from $2–3 (normal) to $5–7+ signals geopolitical risk premium entering the international oil market — this is the first indicator to watch during Middle East escalations or Russian sanctions tightening. Conversely, a negative spread (rare, when WTI > Brent) signals exceptional US supply constraints, typically pipeline bottlenecks or a Cushing inventory drawdown. For India — which imports roughly 80% of its oil needs at Brent-linked prices — a widening spread is a direct negative for the current account, even if WTI-based headlines suggest oil is "cheap."
""",

    "agri_weekly": """\
**How to read this chart:** Weekly percentage changes in six agricultural commodity futures — Wheat (CBOT), Corn (CBOT), Soybeans (CBOT), Coffee (ICE), Sugar (ICE), and Cocoa (ICE). These soft commodities operate on entirely different supply cycles from energy and metals: they respond to La Niña/El Niño weather patterns, crop reports (USDA WASDE), export bans, and seasonal harvest cycles. A single week's move in this complex often reflects a specific crop report or weather forecast rather than macro sentiment.

**Practical takeaway:** Coordinated spikes across Wheat, Corn, and Soybeans (the staple grains) — as opposed to moves in coffee, sugar, or cocoa — are direct food inflation indicators with significant second-order macro effects, particularly in import-dependent economies including India, MENA, and sub-Saharan Africa. Wheat is the most geopolitically sensitive: the Russia-Ukraine conflict created the most violent 12-week Wheat move in modern commodity history. For India-watchers, Soybean prices track edible oil import costs while Sugar moves impact domestic sugar mills and ethanol blending economics — both are politically sensitive price points for the Indian government.
""",

    # ── WEEKLY: INDIA VOLATILITY ────────────────────────────────────────────

    "india_vix_vs_us": """\
**How to read this chart:** India VIX (NSE's 30-day implied volatility measure, left axis, orange) plotted against CBOE VIX (US 30-day implied volatility, right axis, dashed black). Both are shown on separate scales as India VIX has historically traded at a structurally higher absolute level than US VIX (reflecting India's higher day-to-day equity volatility). The *spread* between India VIX and US VIX — and whether they move together or diverge — is the key analytical signal.

**Practical takeaway:** When India VIX spikes sharply without a corresponding move in US VIX, the catalyst is purely domestic: RBI monetary policy surprise, election results, fiscal budget announcement, or a major domestic financial institution stress event. This is the most valuable signal this chart offers — a "clean" India-specific volatility spike, isolated from global noise. Conversely, when both indices spike in unison, it confirms a global risk-off event rather than an India-specific concern. Sustained India VIX above 20 while US VIX remains below 15 historically correlates with FII (foreign institutional investor) outflows from Indian equities — watch this alongside USD/INR direction for confirmation.
""",

    # ── MACRO: INFLATION ────────────────────────────────────────────────────

    "macro_inflation": """\
**How to read this chart:** The US inflation dashboard shows the multi-dimensional nature of the price level — headline CPI, core CPI (excluding food and energy), and PCE (the Fed's preferred measure). CPI and PCE diverge in their basket composition: CPI overweights shelter (housing), while PCE captures broader consumer substitution behaviour. When headline CPI is running significantly above core, the driver is energy/food — a supply shock. When core CPI is running above headline, the driver is structural service-sector inflation.

**Practical takeaway:** The Fed targets core PCE at 2% — not CPI. A 6–9 month period where core PCE exceeds 2.5% is the threshold above which the Fed historically begins hiking cycles. Shelter's well-documented lag in CPI measurement (based on lease renewals rather than real-time rents) means official CPI can overshoot real-time inflation by 12–18 months on the way down — which is why the Fed prefers PCE. For equity investors, the most important decomposition is services inflation (sticky, driven by wages) versus goods inflation (volatile, driven by supply chains) — sustained services inflation above 4% is structurally negative for profit margins.
""",

    "macro_labour": """\
**How to read this chart:** The macro labour market dashboard aggregates US Non-Farm Payrolls (NFP), the unemployment rate, and JOLTS data into a single view. NFP is the headline number that moves markets on the first Friday of every month — but the unemployment *rate* and the *pace of job openings decline* are the more durable signals. The Beveridge Curve relationship (job openings vs. unemployment) is the Fed's framework for assessing labour market tightness.

**Practical takeaway:** An unemployment rate rising from its cycle low by more than 0.5 percentage points (the Sahm Rule threshold) has triggered a recession watch with near-perfect historical precision. The critical insight is directionality: an unemployment rate at 4% and rising is a fundamentally different macro environment than 4% and stable. JOLTS job openings declining rapidly without a corresponding increase in unemployment is a "soft landing" signal — the Fed's ideal outcome. When NFP beats consistently but unemployment also rises, it signals labour force re-entry (positive supply-side) rather than demand weakness.
""",

    "macro_financial": """\
**How to read this chart:** Financial conditions indices aggregate the information in credit spreads, equity prices, currency moves, and funding rates into a single number. Tighter financial conditions (rising index) mean credit is becoming more expensive and less available across the economy — a direct transmission mechanism of Fed policy. This chart typically shows components like the Chicago Fed NFCI or the Bloomberg Financial Conditions Index.

**Practical takeaway:** Financial conditions often tighten *before* the Fed raises rates (as markets pre-price hikes) and ease *before* the Fed cuts (as markets pre-price easing). The key asymmetry: conditions can tighten very rapidly (weeks) but ease slowly (months), particularly after credit events. For equity investors, a financial conditions tightening of more than 1 standard deviation from the 1-year mean has historically preceded equity drawdowns of 10–20% with a lag of 2–4 months. When financial conditions are easing but the Fed is still hiking, it signals the market is betting against the Fed — a high-conviction positioning that is periodically correct and periodically very wrong.
""",

    "macro_em_vulnerability": """\
**How to read this chart:** The EM Vulnerability Scorecard ranks major emerging economies across multiple risk dimensions: current account balance, foreign exchange reserve adequacy, external debt-to-GDP, inflation, fiscal deficit, and political risk. Countries in the top-right quadrant (high vulnerability on multiple dimensions) are most at risk from external financing shocks; those in the bottom-left are the EM "safe havens" within the asset class.

**Practical takeaway:** This scorecard is most useful in the context of a global dollar tightening cycle — the vulnerabilities it flags become market-moving events when USD liquidity contracts. India's positioning on this scorecard versus peers like Turkey and Brazil explains why INDA's volatility profile is structurally lower despite similar nominal return profiles. Key metrics to watch: current account deficit widening (requires more external financing), FX reserve drawdown (central bank burning reserves to defend currency), and real interest rate turning negative (inflation exceeding policy rate — a recipe for currency depreciation and capital flight).
""",

    "macro_oecd_cli": """\
**How to read this chart:** The OECD Composite Leading Indicators (CLI) for major economies — designed to predict turning points in economic activity 6–9 months ahead. An index above 100 indicates an economy likely to grow faster than its trend rate; below 100 indicates below-trend growth expected. The *direction* (accelerating or decelerating) matters as much as the absolute level.

**Practical takeaway:** The OECD CLI is one of the most valuable inter-market tools precisely because it leads GDP data by 6–9 months. Cross-country CLI divergence is the key investment signal: when the US CLI is decelerating while Eurozone or India CLIs are accelerating, it suggests sector rotation from US to international equities. When all major economy CLIs decline in unison, it is a global slowdown signal — the conditions under which commodities, EM equities, and cyclical sectors underperform simultaneously. The CLI's predictive value is strongest at extremes — readings below 98 or above 102 have historically had strong track records.
""",

    # ── MACRO: RECESSION WATCH ──────────────────────────────────────────────

    "macro_sahm": """\
**How to read this chart:** The Sahm Rule real-time recession indicator measures the rise in the unemployment rate relative to its 12-month low. Claudia Sahm's research showed that when this indicator reaches 0.5 percentage points or more, the US economy has always been in recession. The 0.5pp threshold is marked on this chart as the critical alert line. Unlike GDP-based recession definitions (which are lagging), the Sahm Rule fires in real-time using monthly jobs data.

**Practical takeaway:** The Sahm Rule's predictive power comes from the *snowball dynamics* of labour market deterioration: initial layoffs reduce consumer spending, which leads to further layoffs. Critically, the indicator does not require waiting for an NBER recession declaration — it fires while the deterioration is unfolding. For investors, a Sahm Rule breach above 0.5pp has historically been associated with Fed emergency rate cuts and equity drawdowns of 20–30% within 12 months. The indicator's false positive rate is remarkably low — in 60+ years of US employment data, it has never reached 0.5pp without being followed by a formal recession declaration.
""",

    "macro_balance_sheet": """\
**How to read this chart:** The Federal Reserve's total balance sheet assets (WALCL) in trillions of dollars over time, with Quantitative Easing (QE) and Quantitative Tightening (QT) eras shaded. QE periods (balance sheet expanding) correspond to the Fed purchasing Treasuries and MBS to inject liquidity; QT periods (balance sheet shrinking) correspond to allowing securities to roll off without reinvestment. The balance sheet is the "size" dimension of monetary policy, distinct from the "price" dimension (interest rates).

**Practical takeaway:** Balance sheet expansion historically correlates with equity multiple expansion (higher P/E ratios) and credit spread compression — the direct result of excess liquidity seeking yield. Quantitative Tightening (QT) has the opposite effect but at a slower, less predictable pace. The speed of QT matters: aggressive QT in 2018 contributed directly to the Q4 2018 equity selloff; the Fed pivoted to stopping QT in early 2019. The current QT pace and the Fed's bank reserve "comfort level" (estimated at $3–3.5T) determine how long QT can continue before liquidity stress emerges — watch repo market rates as the leading indicator of QT running too hot.
""",

    # ── MACRO: HOUSING & CONSUMER ───────────────────────────────────────────

    "macro_housing": """\
**How to read this chart:** US 30-year fixed mortgage rate (primary axis) plotted against Housing Starts (secondary axis, bar chart). This dual-series view captures the direct transmission of Fed rate policy into the housing economy. Mortgage rates are directly derived from 10-year Treasury yields plus a spread — they are among the most rate-sensitive consumer financial products in existence. Housing starts lead construction employment, materials demand (copper, lumber), and real estate transaction volumes by 3–6 months.

**Practical takeaway:** The US housing market exhibits "lock-in" dynamics — homeowners with 3% pandemic-era mortgages are unwilling to sell and take on a 7%+ mortgage on a new purchase. This "golden handcuffs" effect has reduced existing home supply while new construction demand remains price-constrained. A 10-year yield decline of 100bps historically stimulates a 15–25% increase in mortgage applications within 3 months. For the broader economy, housing is a powerful multiplier: a 1 percentage point increase in housing starts has historically added ~0.3–0.4 percentage points to GDP growth over the following 2 quarters through construction employment and consumer durables demand.
""",

    "macro_consumer": """\
**How to read this chart:** University of Michigan Consumer Sentiment Index with a long-run average reference line. Consumer sentiment is a leading indicator of consumer spending (70% of US GDP) — low confidence precedes spending contraction by 2–3 months. The chart shows the current reading in context of the full historical range, making it immediately visible whether current sentiment is at historically depressed or elevated levels.

**Practical takeaway:** Consumer sentiment is notoriously weak during high-inflation periods even when unemployment is low — the 2022 "Volcker-shock" comparison to current sentiment readings reflects the psychological weight of price level increases regardless of income growth. The expectations component (where consumers think the economy is heading) is more predictive of spending than the current conditions component. Sustained readings below the long-run mean for 3+ quarters have historically preceded consumer spending slowdowns; a sharp rebound in sentiment from a depressed base is one of the most reliable leading indicators of an economic recovery.
""",

    # ── MACRO: MONEY & RATES ────────────────────────────────────────────────

    "macro_money": """\
**How to read this chart:** M2 money supply year-over-year growth (bars, left axis) alongside the 2s10s yield curve spread and the 10Y-3M spread (lines, right axis). M2 growth reflects the pace of money creation — a leading indicator of nominal GDP and inflation with a lag of 12–18 months. The yield curve spreads are the market's real-time pricing of recession risk and Fed policy trajectory.

**Practical takeaway:** Milton Friedman's dictum — "inflation is always and everywhere a monetary phenomenon" — is most directly tested in this chart. The extraordinary M2 expansion of 2020–2021 (+25–27% YoY) was the monetary foundation of the 2021–2022 inflation surge, with the typical 12–18 month lag playing out with near-textbook precision. M2 contraction (negative YoY growth), which appeared briefly in 2023 for the first time since the 1930s, represents monetary tightening beyond the interest rate channel. The 10Y-3M spread turning deeply negative has preceded every US recession since 1970 with remarkable consistency — more reliable than the 2s10s spread for recession timing.
""",

    # ── MACRO: AGRICULTURAL PIPELINE (AGFLATION) ───────────────────────────

    "agflation_pipeline": """\
**How to read this chart:** The Agflation Pipeline tracks the transmission of agricultural commodity price pressures through the food production chain — from farm-gate input costs (fertiliser, energy) through processing to retail food prices. This multi-stage pipeline view shows where price pressures are building and where they are being absorbed or passed through, with implications for headline CPI's food component.

**Practical takeaway:** Agricultural commodity price spikes take 6–12 months to transmit to retail food prices due to processing, storage, and contract structures. This lag means that a wheat or corn price spike today predicts food CPI pressure 6–9 months forward — a leading indicator that CPI data alone misses. For emerging market central banks (RBI, Bank Indonesia, BCB), food inflation is particularly destabilising because food represents 35–50% of the CPI basket (vs. 12–14% in the US), meaning a global soft commodity spike translates directly into headline inflation pressure requiring policy response.
""",

    # ── INDIA DASHBOARD ─────────────────────────────────────────────────────

    "india_pmi": """\
**How to read this chart:** India's Manufacturing PMI and Services PMI plotted together over the trailing period. Both are diffusion indices — a reading above 50 signals expansion in that sector; below 50 signals contraction. The composite (blended) line reveals whether growth is broadening or narrowing. India's services PMI carries more structural weight than manufacturing, given services represent over 55% of GDP, but the manufacturing PMI is a more sensitive cycle indicator given its exposure to global trade and inventory cycles.

**Practical takeaway:** Sustained PMI readings above 55 in both manufacturing and services — India's structural norm in recent cycles — reflect robust domestic demand and solid business confidence. Watch for divergence: services PMI holding above 55 while manufacturing dips below 52 typically signals external headwinds (export slowdown, input cost pressure) without a domestic demand problem. A manufacturing PMI falling below 50 for two or more consecutive months has historically preceded a 10–15% correction in cyclical NIFTY sectors. The PMI print relative to consensus expectation — the "surprise" — drives the market reaction more than the absolute level.
""",

    "india_gst": """\
**How to read this chart:** Monthly GST (Goods and Services Tax) collections in India, shown as a bar chart with the year-on-year growth rate as a secondary signal. GST is India's broadest indirect tax, covering consumption across most goods and services. Total monthly collections above ₹1.5 lakh crore are considered robust; consistent growth above 10–12% YoY signals healthy nominal consumption. The chart reveals both the level of economic activity and the fiscal health of the central government's revenue mobilisation.

**Practical takeaway:** GST collections are among the most timely indicators of India's economic momentum — they are released on the first day of every month for the prior month, with minimal revision risk. A sustained acceleration in GST collections (3+ months of sequential growth) is a strong leading signal for NIFTY earnings revisions, particularly in consumer discretionary, FMCG, and banking sectors. Seasonality matters significantly: April (start of fiscal year) and October–December (festive season) structurally print higher collections. Strip out seasonal effects and focus on the underlying YoY trend. Weak GST collections also directly constrain the government's fiscal space, limiting the scope for discretionary capex in the second half of the fiscal year.
""",

    "india_credit": """\
**How to read this chart:** Year-on-year growth in aggregate bank credit in India (all scheduled commercial banks), sourced from RBI's weekly statistical supplement. This is the most direct measure of financial intermediation in the economy — whether banks are willing to lend and businesses/consumers are willing to borrow. Credit growth above 12–14% YoY is considered healthy in the Indian context; below 8% signals credit contraction or risk aversion.

**Practical takeaway:** Bank credit growth is a coincident indicator of the capex and consumption cycles. When credit to industry accelerates alongside credit to services and retail, it signals a broad-based expansion — the ideal macro backdrop. Watch for composition: retail credit (personal loans, home loans) expanding faster than industrial credit can signal consumer-led growth masking weak private sector investment — a less durable combination. RBI's credit data also captures the shadow of monetary policy: credit growth decelerating after rate hikes confirms the transmission mechanism is working. A divergence — where market rates rise but credit growth stays elevated — often signals that corporates are front-loading borrowing before higher rates bite, a pattern that precedes credit quality deterioration 3–6 months later.
""",

    "india_fpi": """\
**How to read this chart:** Monthly net Foreign Portfolio Investment (FPI) flows into India, disaggregated into equity and debt components where available. Positive bars represent net inflows (foreign investors buying Indian assets); negative bars represent net outflows (selling). FPI data is sourced from NSDL. The scale of flows matters less than the direction and duration — sustained outflows over 3+ months have historically preceded INR depreciation and NIFTY underperformance.

**Practical takeaway:** FPI flows are India's most politically and market-sensitive capital flow component. They are highly responsive to three external factors — US dollar strength, Fed rate expectations, and global risk appetite — and two domestic factors — India's earnings growth relative to EM peers and RBI/government policy credibility. A pattern of equity inflows combined with debt outflows typically signals foreign investors are positive on India's growth story but concerned about currency/rate risk. Conversely, simultaneous equity and debt outflows (both bars negative) signal a classic "sudden stop" — the most damaging scenario for the INR and equity markets simultaneously. Watch for the September–October window, when FPI rebalancing ahead of EM index reweights (MSCI, FTSE) can generate large, temporary flow distortions.
""",

    "india_inflation_bar": """\
**How to read this chart:** India's inflation landscape shown as a multi-series comparison — CPI Headline, CPI Core (ex-food and energy), and CPI Food. The RBI targets headline CPI within a 4% ± 2% band (i.e. 2–6%), with a preference for sustaining it near 4%. Food inflation, which carries approximately 45% weight in India's CPI basket, is the single largest driver of headline volatility. Core CPI is the RBI's preferred measure of underlying demand-driven inflation.

**Practical takeaway:** The most important signal in this chart is the *spread* between headline and core CPI. When headline significantly exceeds core, the primary driver is food and fuel — supply-side shocks that are typically transitory and outside the RBI's direct control. When core CPI rises toward or above headline, the inflation problem has become demand-driven, requiring tighter monetary policy. For equity investors, core CPI above 5% for two or more consecutive months is the threshold above which RBI rate hikes become more probable than pauses. Food inflation above 8% for a sustained period creates political pressure, triggers government export bans on agricultural commodities, and compresses rural consumption — all structurally negative for FMCG and consumer staples sectors.
""",

    "india_expenditure_quality": """\
**How to read this chart:** The composition of India's central government expenditure broken down into capital expenditure (CapEx) and revenue expenditure, with revenue expenditure further decomposed into interest payments, subsidies, and other components. Expenditure quality is measured by the CapEx-to-total-expenditure ratio — a higher ratio indicates more productive, growth-enhancing spending; a lower ratio dominated by interest and subsidies signals fiscal obligations crowding out investment.

**Practical takeaway:** India's fiscal transformation since 2020 has been defined by an explicit shift toward capital expenditure — central government CapEx has grown from ~₹3 lakh crore to over ₹10 lakh crore in four years. This "CapEx push" has been the primary driver of the infrastructure, defence, and industrial sectors' outperformance on NIFTY. The critical risk is execution: CapEx budgeted is not CapEx spent — the pace of utilisation in the first half of the fiscal year (April–September) is a leading indicator of whether the full-year target will be met. Under-execution in H1 (below 45% of full-year budget by September) typically leads to an H2 rush that inflates contractor revenues but misses multiplier effects. Interest payments exceeding 40% of revenue receipts is a structural fiscal constraint — India has been managing this ratio carefully and any deterioration should be watched.
""",

    "india_tax_composition": """\
**How to read this chart:** The composition of India's gross tax revenue broken down by component: Corporation Tax, Personal Income Tax, GST (CGST + IGST + UTGST), Customs Duties, and Union Excise Duties. This chart reveals the structural diversification and resilience of India's tax base — whether the government is reliant on any single revenue stream that is cyclically exposed.

**Practical takeaway:** The most important structural shift in India's tax landscape over the past decade has been the rise of direct taxes (corporate + personal income tax) as a share of total revenue — from roughly 50% to over 55% — reflecting formalisation of the economy, GST compliance improvements, and income growth in the formal sector. When personal income tax grows faster than corporate tax, it signals wage growth and employment formalisation — a positive structural indicator. A sharp decline in customs duties revenue signals either import compression (negative for the economy) or a deliberate policy shift (trade liberalisation for specific sectors). GST's share of total tax revenue being stable or growing reflects continued formalisation — the most important long-term fiscal tailwind for India. Sudden volatility in corporate tax collections is typically explained by advance tax payment timing or one-off deferred tax settlements, not the underlying cycle.
""",

    "india_fiscal_tracker": """\
**How to read this chart:** India's cumulative fiscal deficit as a percentage of the full-year budget estimate (BE) target, tracked monthly through the fiscal year (April–March). The chart shows the path of deficit accumulation compared to the prior year's pace and the full-year target. A sharp front-loading of the deficit (rapid rise in H1) signals either revenue underperformance or expenditure front-running; a gradual, controlled path signals fiscal discipline.

**Practical takeaway:** India's fiscal credibility has improved significantly since the FRBM (Fiscal Responsibility and Budget Management) Act framework was strengthened. The market's tolerance for slippage is narrow — a deficit-to-GDP projection above 5.5% typically triggers a sovereign rating outlook concern and puts upward pressure on 10-year G-Sec yields. Watch the trajectory against the prior year in the September–October window: if the cumulative deficit is tracking above the prior year's pace as a share of BE, it signals H2 expenditure compression is likely — negative for CapEx-linked sectors. Conversely, a deficit running well below BE by October signals either fiscal over-performance (positive for sovereign credibility) or planned expenditure slippage (negative for growth).
""",

    "india_monthly_capex": """\
**How to read this chart:** Month-by-month central government capital expenditure in absolute terms (₹ lakh crore), with current year versus prior year comparison bars. This is the highest-frequency and most market-sensitive fiscal data point in the Indian context, given the government's explicit commitment to a CapEx-led growth model. A monthly CapEx print significantly above the prior year confirms the government is on track to meet its full-year target.

**Practical takeaway:** Monthly CapEx data drives material market moves in India's infrastructure, construction, defence, and industrial sectors. The most actionable signal is the January–March print: CapEx typically surges in Q4 of the Indian fiscal year as ministries spend against their allocations. A Q4 surge that is structurally larger than the prior year confirms the CapEx target will be achieved — a strong positive for NIFTY Infrastructure and Realty indices. Watch for the July–August window, when CapEx typically softens due to monsoon-related construction delays — a temporary dip is normal; a sustained miss through September signals genuine execution underperformance. The multiplier from government CapEx to private sector investment (the "crowding in" effect) is approximately 1.5x over 12–18 months in India's current cycle.
""",

    "india_fiscal_deficit_gdp": """\
**How to read this chart:** India's fiscal deficit as a percentage of GDP, tracked over multiple fiscal years to show the consolidation trajectory. This is the single most important fiscal credibility metric for sovereign credit rating agencies (S&P, Moody's, Fitch), bond market investors, and the RBI. The chart contextualises the current year's deficit within the medium-term consolidation path India has committed to under FRBM targets.

**Practical takeaway:** India's trajectory from a 9.2% deficit-to-GDP in FY21 (COVID year) toward the 4.5–5% range represents one of the fastest post-pandemic fiscal consolidations among major EMs — a structural positive for India's sovereign rating and 10-year G-Sec yield trajectory. The market's implied "fair value" for fiscal consolidation is a deficit below 5% of GDP sustaining for two or more consecutive years, which has historically correlated with a 50–75 bps compression in the 10Y G-Sec spread over US Treasuries. Any fiscal slippage above 5.5% GDP — whether from revenue disappointment, election-related expenditure, or crisis spending — triggers a reassessment of India's rate cut timeline by the RBI. The relationship between India's fiscal deficit and the 10-year G-Sec yield is the central transmission mechanism for domestic bond market pricing.
""",

    # ── WEEKLY: CRYPTO ASSETS ────────────────────────────────────────────────

    "eth_btc_ratio": """\
**How to read this chart:** The ETH/BTC price ratio (left axis, primary signal) — how many Bitcoin each unit of Ethereum commands — plotted against indexed performance lines for both Bitcoin and Ethereum on the secondary axis (deliberately faint to avoid visual competition with the ratio). The ratio is a direct measure of relative risk appetite within the crypto complex: rising ETH/BTC means investors are rotating from the "digital gold" thesis (BTC) into higher-beta crypto (ETH and broader altcoins); falling ETH/BTC means capital is consolidating back into Bitcoin, a crypto risk-off signal.

**Practical takeaway:** The ETH/BTC ratio is the single most reliable intra-crypto risk sentiment indicator available. Historically, ETH/BTC rising above its 52-week mean and sustaining that level for 4+ weeks has preceded "altcoin season" — broad rallies across smaller-cap tokens following Ethereum's leadership. ETH/BTC breaking below its 52-week mean and staying there signals Bitcoin dominance expansion — a regime associated with institutional allocation preference for BTC as a macro asset and tepid retail participation in the broader ecosystem. For macro investors, a rising ETH/BTC ratio concurrent with a rising BTC price is the most risk-on crypto regime; a falling ETH/BTC concurrent with a falling BTC price is the most risk-off.
""",

    "btc_gold_ratio": """\
**How to read this chart:** The Bitcoin-to-Gold price ratio over 2 years — how many ounces of gold each Bitcoin commands — with a 52-week rolling mean as the structural reference level. Bitcoin and Gold are both positioned as "stores of value" and inflation hedges, but they respond very differently to monetary and risk regimes: Gold performs best in environments of dollar weakness, negative real rates, and geopolitical uncertainty; Bitcoin performs best in environments of high risk appetite, liquidity expansion, and growing institutional adoption.

**Practical takeaway:** The BTC/Gold ratio is one of the most informative macro positioning signals in modern markets. When the ratio rises above its 52-week mean, institutional capital is flowing from the "old" monetary hedge (gold) toward the "new" digital asset thesis — typically associated with Fed liquidity expansion, risk-on sentiment, and increasing crypto ETF or corporate treasury adoption. When the ratio falls sharply toward or below its 52-week mean, it signals classic flight to safety: gold reasserting its monetary store-of-value role while Bitcoin sells off as a risk asset. The ratio's divergence from its mean is more actionable than its absolute level — sustained divergence in either direction rarely lasts more than 6–9 months before mean-reverting.
""",

    "btc_global_m2": """\
**How to read this chart:** Bitcoin price (left axis) plotted against the combined balance sheet of the Federal Reserve and the European Central Bank, expressed in USD billions (right axis). This dual-axis view captures the leading academic and practitioner thesis that Bitcoin is fundamentally a global liquidity trade — its price is highly correlated with the expansion and contraction of major central bank balance sheets with a lag of approximately 10–13 weeks.

**Practical takeaway:** The Fed + ECB balance sheet is the most tractable proxy for global fiat liquidity, and its correlation with Bitcoin's price has been empirically robust across multiple cycles. Quantitative Easing (balance sheet expansion) injects liquidity that flows through risk assets sequentially — equities first, then credit, then commodities, then crypto, in order of liquidity. QT (balance sheet contraction) reverses this. Critically, Bitcoin's correlation to the balance sheet is most predictive at turning points: when the combined balance sheet peaks and begins to decline, it has historically preceded a BTC price peak by 3–4 months. When it troughs and begins to expand, Bitcoin has historically led the recovery by 1–2 months. Divergences — where BTC rallies despite balance sheet contraction — are typically temporary and driven by idiosyncratic crypto narratives (ETF approvals, halving events) rather than durable macro support.
""",

    "stablecoin_mcap": """\
**How to read this chart:** The combined market capitalisation of Tether (USDT) and USD Coin (USDC) in USD billions over a 2-year trailing period, with individual components shown as area fills. Stablecoin aggregate market cap is the closest available proxy for "dry powder" or investable capital parked within the crypto ecosystem. A rising combined market cap means capital is flowing into the crypto system in stable form — building the liquidity base for subsequent risk-on deployment. A contracting stablecoin market cap means capital is leaving crypto entirely.

**Practical takeaway:** Stablecoin market cap dynamics are one of the most forward-looking signals in crypto market structure analysis. An expanding stablecoin market cap that precedes or accompanies a crypto market correction represents "wall of worry" capital — investors who have de-risked but not exited the ecosystem. This capital is structurally supportive for the next risk-on phase. Conversely, stablecoin market cap contracting during a Bitcoin rally signals a "crowded long" — the rally is being financed from existing crypto holdings rather than fresh capital inflows, which is a less durable foundation. The USDT/USDC split matters: USDT dominance rising (USDC share shrinking) signals capital moving toward less regulated, higher-risk, offshore crypto activity; USDC share rising signals US-regulated institutional activity growing — a qualitatively different and more institutionally credible capital base.
""",

    # ── WEEKLY: VOLATILITY — MOVE INDEX ─────────────────────────────────────

    "move_index": """\
**How to read this chart:** The ICE BofA MOVE Index — the bond market's equivalent of the VIX — measures the implied volatility of US Treasury options across maturities (1Y, 2Y, 5Y, 10Y, 30Y), expressed in basis points of annualised yield volatility. An index reading of 100 means the bond market is pricing approximately ±100 bps of annualised yield movement. The 100-level is the canonical stress threshold. Post-GFC, the MOVE averaged ~60–80 in calm periods; the 2022 rate shock pushed it toward 160–180, levels not seen since the 2008–2009 crisis.

**Practical takeaway:** The MOVE Index is the institutional bond manager's primary risk gauge and often leads equity volatility (VIX) during rate-driven market dislocations. When MOVE rises sharply while VIX remains contained, it signals the stress is originating in fixed income — typically driven by unexpected inflation data, Fed communication uncertainty, or Treasury supply/demand imbalance — rather than in corporate or equity risk. This is the pattern preceding the most dangerous equity corrections: the ones the VIX doesn't see coming until Treasury dysfunction forces risk-off across all asset classes. A MOVE above 130 while the 10-year yield is rising rapidly is historically associated with credit spread widening, mortgage market stress, and dollar strength — all simultaneously. Watch for MOVE and VIX rising together, as that combination signals a systemic risk-off event rather than an isolated rates concern.
""",

}
