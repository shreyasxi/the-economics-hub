"""
Economics Hub — Chart Insights & Practical Takeaways
======================================================
Maps each chart's filename stem (after stripping leading numeric prefix) to a
2-paragraph institutional-grade analysis string rendered in Markdown.

Usage:
    from config.insights import get_insight
    text = get_insight("09_vix_trend.png")   # → str or None
"""

from __future__ import annotations

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

    "sector_rotation_12m": """\
**How to read this chart:** Total return for all 11 S&P 500 GICS sectors over the trailing 12 months, sorted from best to worst. Returns are measured on dividend-adjusted prices, which matters at this horizon: Utilities, Staples and Real Estate yield roughly 3%, enough to move them several places up the ranking against a price-only measure. Read it beside the weekly chart above — that one shows the past five sessions, this one shows the trend those sessions sit inside. A sector at the top of both has momentum; a sector leading the week but trailing the year is a bounce, not a turn.

**Practical takeaway:** The spread between the best and worst sector is the market's dispersion: a narrow spread means the index is carrying every sector together, a wide one means leadership is concentrated and the index return says little about the average stock. Watch for a defensive sector climbing the 12-month ranking while the index makes highs — a year-long rotation into Utilities, Staples and Health Care usually reflects positioning that has already happened, not a forecast. Concentration is the other risk this chart exposes: when Technology and Communication Services lead by a wide margin over a full year, the index's return depends on a small number of very large companies, and a reversal in those names is not diversifiable by owning the index.
""",

    "india_sector_rotation": """\
**How to read this chart:** Weekly percentage returns for major NIFTY sector indices — Banking, IT, Auto, FMCG, Pharma, Metal, Realty, Energy, PSU Bank, and Infrastructure — sorted from best to worst. The relative performance of Bank Nifty vs. NIFTY IT is the single most important indicator of India's domestic vs. global narrative: banks outperforming IT signals domestic credit expansion; IT outperforming banks signals global tech spending recovery and/or rupee depreciation tailwinds.

**Practical takeaway:** PSU Bank leadership alongside Metal/Infra outperformance typically signals a government capex cycle — budget-driven infrastructure spending flowing into state-owned enterprises. FMCG outperforming cyclicals in India reflects rural demand recovery or urban consumption caution. When Realty and Auto underperform simultaneously, it often precedes an RBI tightening cycle concern. Compare this chart to the S&P sector rotation chart to distinguish India-idiosyncratic drivers from global sector rotation patterns that happen to flow through Indian indices.
""",

    "india_sector_rotation_12m": """\
**How to read this chart:** The one-year change in each NIFTY sector index, sorted from best to worst, taken from NSE's own daily snapshot of every index and its level a year earlier. These are price indices, so the returns leave out dividends — unlike the S&P sector chart in the Equities section, which uses total returns. The gap is small, as most sectors yield around 1–3% a year, but it can swap the order of sectors that sit close together. Read it beside the weekly NIFTY chart: that one shows the past five sessions, this one the trend those sessions sit inside.

**Practical takeaway:** A year is long enough for sector leadership to reflect the economy rather than the news cycle. Leadership by PSU banks, metals and infrastructure has typically reflected government capex and a commodity upswing; by IT and pharma, a weaker rupee and export demand; by FMCG and autos, the strength of domestic consumption. Compare the order with the S&P 500's: a sector leading in both markets points to a global driver, while one leading only in India points to something domestic — policy, credit growth or the rupee.
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
**How to read this chart:** ICE BofA option-adjusted spreads (OAS) for US investment-grade (IG) and high-yield (HY) corporate bonds: the extra yield investors demand over Treasuries to hold them, in basis points. High yield is on the left axis and investment grade on the right (dashed), scaled so that their spikes line up. The chart covers the three years FRED now carries, because since April 2026 it publishes only the latest three years of ICE's indices. Dotted lines mark 400 bps for high yield and 150 bps for investment grade, levels usually read as credit stress. Each of the widest points is labelled with the shock behind it, and the values in the key are the latest readings.

**Practical takeaway:** Credit spreads are the price of default risk, and in a shock they move with equities. Each spike in these three years came with a sell-off in shares, and each gave back most of its rise within about two months: the 10-year Treasury yield's run to 5% in October 2023, the yen carry-trade unwind in August 2024, the US tariff shock of April 2025 and the oil spike from the Iran war in March 2026. High yield spent only a few weeks above 400 bps, in autumn 2023 and April 2025, and investment grade never reached 150 bps. At 268 bps for high yield and 77 bps for investment grade, spreads are close to the tightest of the period. Investors are being paid little to take default risk, which keeps borrowing cheap for companies but leaves little cushion if growth weakens. When high yield widens much faster than investment grade, the stress is concentrated in the weakest, most indebted borrowers. When both widen together, it is a broad retreat from risk.
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

    "stock_bond_correlation": """\
**How to read this chart:** The rolling 60-day correlation between the daily returns of the S&P 500 (SPY) and long-dated US Treasuries (TLT), from TLT's launch in 2002, drawn as one reading a week. A reading below zero means the two move in opposite directions — when shares fall, bonds rise — which is the behaviour a 60/40 portfolio is built on. Above zero means they fall together, and bonds are no longer insurance. The grey panel marks the years since 2021, and the labels count how often the correlation sat above zero before and after, on every daily reading; the number at the right is the latest reading.

**Practical takeaway:** This is the single most important number for anyone holding a balanced portfolio, and it is not fixed. For the two decades to 2020 the correlation sat below zero on most days, which is why the 60/40 worked so well; since 2021 it has spent more time above zero than below, and in 2022 both sides of the portfolio fell at once. The driver is what is moving markets: when growth scares dominate, bonds rally as shares fall and the correlation is negative; when inflation and rate expectations dominate, both are repriced by the same discount rate and the correlation turns positive. A sustained move above zero means the diversification in a balanced portfolio has quietly stopped working, and that hedging has to come from somewhere else — cash, gold or explicit downside protection.
""",

    "defensives_cyclicals": """\
**How to read this chart:** An equal-weighted basket of the defensive S&P 500 sectors (consumer staples, utilities and healthcare) divided by an equal-weighted basket of the cyclical ones (consumer discretionary, technology and industrials). Both baskets start at 100 two years ago and are rebalanced daily, so each sector counts equally throughout. The line is their relative performance since then: above 100 means defensives have outperformed, and the figure at its end is that performance in per cent. The dashed line is the 26-week average.

**Practical takeaway:** This reads risk appetite from where money actually sits inside the index, so unlike an equity-versus-bond ratio it cannot be distorted by a move in interest rates. Investors rotate into staples and utilities when they expect slower growth or want earnings that hold up in a downturn, and into technology and discretionary when they expect the opposite. A sustained rise while the index itself is still climbing is the more interesting signal: it means the market is advancing but its leadership is turning cautious, which has often preceded a broader loss of momentum. The chart covers two years because over longer spans the trend drowns out the rotations: since 2006 cyclicals have beaten defensives by about half, largely on technology's long run. Read it alongside the high-beta versus low-volatility ratio. They measure the same instinct from different angles, and when they disagree it is usually because a handful of megacap technology names are dominating the cap-weighted sectors.
""",

    "risk_appetite_ratio": """\
**How to read this chart:** The SPHB/SPLV ratio: Invesco's S&P 500 High Beta ETF (the 100 stocks in the index that have moved most with the market) divided by its S&P 500 Low Volatility ETF (the 100 steadiest), weekly since both launched in May 2011 and indexed to 100 then. The S&P indices behind them are not freely available for earlier years. A rising line means high-beta stocks are beating low-volatility ones, as investors reach for risk within equities; a falling line means they are retreating to defensive stocks. Unlike SPY/TLT, this signal cannot be obscured by moves in bond yields. The figure at the end is the change since 2011, and the grey band marks the 2020 recession.

**Practical takeaway:** The long view shows how much the ratio depends on the market's regime. Through most of the 2010s low-volatility stocks won and the ratio drifted lower, bottoming at 57 in the Covid crash of 2020. High beta then led the recovery and gave ground in the 2022 bear market. Since the tariff low of April 2025, the ratio has more than doubled, from 85 to a record 182. That says risk appetite within equities is as strong as at any time since 2011, and also that a reversal would have far to fall. High-beta stocks are the first that investors sell when they turn cautious, so a sharp drop in the ratio while the index holds up is the early warning. A rise alongside rising equities, backed by tightening credit spreads, is the healthy version of risk appetite.
""",

    "market_breadth": """\
**How to read this chart:** The RSP/SPY ratio: the Invesco S&P 500 Equal Weight ETF divided by the SPDR S&P 500 ETF, which is weighted by market capitalisation, weekly since January 2006 and indexed to 100 then. Equal weight gives each of the 500 companies the same weight (about 0.2%), while cap weight gives Apple, Microsoft and Nvidia weights of 6–7% each. A falling line means the market's gains are increasingly concentrated in the largest companies; a rising line means the average stock is keeping up. The figure at the end is the relative performance since 2006, and grey bands mark US recessions.

**Practical takeaway:** The long view shows two regimes. From the 2008 low of 87 to a peak of 112 in April 2015, equal weight beat cap weight as the average company recovered from the financial crisis. Since then the ratio has fallen by about 30%, reaching its lowest in the 20 years shown, 78, in May 2026. That is the longest and deepest stretch of mega-cap dominance in this record, driven by the largest technology companies. The ratio also fell in both recessions, 2008 and 2020, when investors crowded into the biggest, safest names. A falling ratio during a rally is the warning, because the gains then rest on a few stocks and the index is more exposed to a reversal in them. Improving breadth is a necessary, though not sufficient, condition for a durable bull market. A rising ratio while the index is flat often signals rotation into value and cyclical names, which tends to help financials, industrials and energy.
""",

    "gold_spx_ratio": """\
**How to read this chart:** The gold-to-S&P 500 price ratio over 2 years, with a 52-week rolling mean as reference. Gold prices reflect safe-haven demand, currency debasement fears, and geopolitical risk premium; SPX prices reflect US corporate earnings growth and risk appetite. A rising Gold/SPX ratio means investors are rotating from growth assets into protection — a meaningful signal given the opportunity cost of holding non-yielding gold.

**Practical takeaway:** The Gold/SPX ratio has historically peaked at, or slightly after, equity market tops in major bear markets — it is a coincident-to-lagging indicator of equity stress, not a leading one. Its primary value is as a *confirmation* signal: if equities are declining *and* the Gold/SPX ratio is rising, you have two-sided confirmation of a genuine risk-off regime. When gold rises alongside equities (both the ratio and SPX increasing), it can indicate a nominal growth environment where both real and financial assets are being inflated — often associated with dollar weakness and fiscal expansion. A Gold/SPX ratio sustainably above its 52-week mean while equities consolidate is a classic late-cycle positioning signal.
""",

    "commodities_vs_equities": """\
**How to read this chart:** The S&P GSCI commodity index divided by the S&P 500 at each month-end, rebased to 100 in January 1984 and drawn on a log scale so that equal percentage moves look the same size. A rising line means commodities are outperforming shares; a falling line means shares are winning. The dots date the major turns, and the note says how rare today's level is in the ratio's own history. Both are price indices: the S&P 500 here leaves out dividends, and the GSCI spot index leaves out the returns from holding futures.

**Practical takeaway:** The ratio has a built-in downward drift — company earnings compound over time, while commodity prices mostly keep pace with inflation — so the long decline is not a signal in itself. The cycles around that drift are: commodities outperformed from the 1999 low to the 2008 high as China's build-out met years of underinvestment in supply, then lagged for twelve years as shale oil and new mines arrived and technology earnings compounded, before rebounding sharply into 2022. Its turns have often lined up with turns in US inflation: the 2008 and 2022 highs came a month before US CPI inflation peaked, and the 2020 low a month before it bottomed. A very low reading says how far commodities have fallen out of favour against equities; it is context, not a timing signal, and the ratio can stay low for years.
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

    "em_vix": """\
**How to read this chart:** VXEEM is the CBOE's measure of the volatility options traders expect over the next 30 days in the iShares MSCI Emerging Markets ETF (EEM), quoted in annualised percentage points. The purple line is the daily close over the past three years; the dashed grey line is its 52-week average, and the shaded areas mark stretches when expected volatility sat above that average. As a rule of thumb, a reading of 20 implies a typical one-month move in EEM of about ±5.8% (20 divided by the square root of 12).

**Practical takeaway:** Spikes in VXEEM mark episodes when investors pay up to protect emerging-market portfolios, typically around global risk-off events, a sharp rise in the US dollar or a jump in US yields. Such episodes often coincide with foreign portfolio outflows from emerging markets, India included (see the FPI chart on the India tab). A single spike that fades quickly points to a short-lived shock; a sustained stretch above the 52-week average points to a higher-volatility regime. Comparing VXEEM with the US VIX on the Volatility charts separates stress specific to emerging markets from a global sell-off.
""",

    "crude_oil_curve": """\
**How to read this chart:** Every point is a separate WTI futures contract: what the market will pay today for a barrel delivered in that month. The blue line is the curve now, the dashed grey line the same contracts a month ago, and the shaded band is the gap between each delivery month and the front-month price. When the curve slopes **down** — backwardation — buyers are paying a premium for barrels available immediately, which happens when physical supply is tight. When it slopes **up** — contango — later barrels cost more, so the market is effectively paying for storage, the signature of a glut. The shape matters more than the level: prices can be high in either regime.

**Practical takeaway:** The curve is a cleaner read on physical tightness than the headline price, because it strips out the part of the price that is simply a weaker dollar or a broader risk rally. Deep backwardation rewards holding inventory and discourages stockpiling, so it usually accompanies falling inventories and gives producers little reason to hedge future output. A flip into contango after a supply shock is one of the earliest signs that the shock has passed. Comparing the two lines matters as much as the shape: a curve that has lifted at the front but barely moved at the back is a prompt disruption, whereas a parallel shift reflects a change in the long-run price view. For oil importers such as India, a front-loaded spike hurts the current account immediately while leaving longer-dated hedging costs largely intact.
""",

    "gold_real_rates": """\
**How to read this chart:** Not a time series — a path. Each step is one month over the past ten years, positioned by the 10-year US real yield (horizontal) and the gold price (vertical). Real yields are what inflation-protected Treasuries pay after inflation, so they are what an investor gives up by holding gold, which pays nothing. The textbook relationship is therefore negative: as real yields rise, gold should fall. The blue path is 2016–2021, when that rule held almost perfectly; the maroon path is 2022 to today, when it stopped. The correlations in the legend are computed from the same data.

**Practical takeaway:** The blue path runs down and to the right exactly as theory says it should. The maroon path turns and climbs: real yields rose to their highest in over a decade and gold rose with them, which the old framework cannot explain. The widely accepted reason is a change in who is buying — central banks, particularly in emerging markets, have been accumulating gold as a reserve asset since 2022, and that demand is insensitive to what Treasuries yield. The practical consequence is that forecasting gold from the Fed's rate path, a standard approach for two decades, no longer works on its own; reserve-diversification flows now matter at least as much. Watch whether the path ever bends back toward the blue line, which would signal the old rule reasserting itself.
""",

    "commodities_breadth": """\
**How to read this chart:** The share of 13 major commodities — crude oil (Brent and WTI), natural gas, gold, silver, platinum, copper, wheat, corn, soybeans, coffee, sugar and cocoa — trading above their own 200-day average, since 2008. The heavy line is the 3-month average of the daily share, which is drawn faintly behind it: with 13 members the daily reading moves in steps of about eight points, and the average shows the cycle through that noise. Each commodity is judged only against its own history, so the measure is not distorted by the fact that a barrel of oil and an ounce of gold are priced on completely different scales. Above the 50% line, most of the complex is in an uptrend; below it, most is not. The names listed on the chart say exactly which are above and below today.

**Practical takeaway:** A headline commodity index can be dragged up by one squeezed market while everything else falls, and breadth is what separates the two cases. A broad advance — most members rising together — points to a genuine global demand impulse and usually carries an inflation signal that central banks respond to. A narrow advance points to a supply shock in a single market, which is louder in the headlines than it is in the inflation data and tends to reverse once supply recovers. Breadth describes a rally; it does not time one. Since 2008, readings above 80% and below 20% have been followed by ordinary returns for the basket over the next year, so the chart is best read as a map of how widely prices are rising — and so how broad any inflation impulse is — rather than as a signal to buy or sell.
""",

    "commodity_cycle": """\
**How to read this chart:** The S&P GSCI spot index — a production-weighted basket of energy, metals and agricultural commodities in which energy carries the largest weight — divided by the US consumer price index, so that every month is measured in the same money, and rebased so that its average since 1984 equals 100. Monthly averages are used, and a month appears once its CPI has been published. The dots mark each major turn: a high once prices had fallen 36% from it, a low once they had risen 57%. Above 100, commodities are dearer in real terms than their four-decade norm; below it, cheaper.

**Practical takeaway:** Commodity prices move in long cycles because supply responds slowly: high prices draw in investment in mines, wells and farmland that takes years to arrive, and the new supply then outlasts the demand that called for it. The chart shows a long real decline through the 1980s and 1990s to a low in December 1998, the boom to June 2008 as China industrialised, a second high in April 2011, the bust to lows in January 2016 and April 2020, and the post-pandemic spike to June 2022. Read it for context rather than timing: where the index sits against its long-run average says how much of a cycle is already in the price, not when it will turn. Because energy dominates the index, the line is above all a picture of oil; the breadth chart beside it says whether a move is an energy story or a broad one.
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
**How to read this chart:** US headline CPI inflation (blue) and core PCE inflation (teal), each the % change on a year earlier, with the 5-year, 5-year forward inflation expectation rate (orange): the average inflation bond markets price for the five years starting five years from now, shown as monthly averages. The dashed line is the Federal Reserve's 2% target, which is defined for PCE inflation. Headline CPI includes food and energy and swings with oil; core PCE leaves them out and is the measure the Fed watches most closely. The lines are smooth curves through the published monthly figures, which are unchanged; the labels give the latest reading. CPI has no October 2025 figure because the US government shutdown cancelled that month's survey.

**Practical takeaway:** Core PCE running well above 2% keeps the Fed cautious about cutting, which keeps US yields and the dollar firm and tightens conditions for emerging markets, India included, through portfolio flows and the rupee. The expectations line is the credibility check: while it stays near 2–2.5% as actual inflation swings, markets expect a spike to fade. A sustained move above 2.5% would signal that investors doubt the Fed will bring inflation back to target, the case in which it keeps policy tight even as growth slows.
""",

    "macro_labour": """\
**How to read this chart:** Two panels on one time axis. The top panel is the US unemployment rate (monthly household survey); the highlighted figure in its top-right corner is the latest monthly change in nonfarm payrolls, the headline jobs number. The bottom panel is initial claims for unemployment insurance, averaged over four weeks to smooth weekly noise; claims are the most timely read on layoffs. Each panel has its own scale, so compare direction and turning points rather than the heights of the lines. The lines are smooth curves through the published figures; there is no October 2025 unemployment rate because the government shutdown cancelled that survey month.

**Practical takeaway:** Claims usually turn before the unemployment rate: a sustained rise from their low has typically come ahead of a rising rate, which moves slowly. Rising claims together with a rising unemployment rate is the pattern that pushes the Fed towards cuts, which tends to soften the dollar and US yields, easing pressure on the rupee and supporting foreign portfolio flows into India. A slowly rising rate with steady claims more often reflects more people looking for work than layoffs. The Sahm rule reading, a recession signal built from the unemployment rate, is in the US summary table.
""",

    "macro_em_vulnerability": """\
**How to read this chart:** The EM Vulnerability Scorecard ranks major emerging economies across multiple risk dimensions: current account balance, foreign exchange reserve adequacy, external debt-to-GDP, inflation, fiscal deficit, and political risk. Countries in the top-right quadrant (high vulnerability on multiple dimensions) are most at risk from external financing shocks; those in the bottom-left are the EM "safe havens" within the asset class.

**Practical takeaway:** This scorecard is most useful in the context of a global dollar tightening cycle — the vulnerabilities it flags become market-moving events when USD liquidity contracts. India's positioning on this scorecard versus peers like Turkey and Brazil explains why INDA's volatility profile is structurally lower despite similar nominal return profiles. Key metrics to watch: current account deficit widening (requires more external financing), FX reserve drawdown (central bank burning reserves to defend currency), and real interest rate turning negative (inflation exceeding policy rate — a recipe for currency depreciation and capital flight).
""",

    "macro_oecd_cli": """\
**How to read this chart:** Every economy the OECD publishes a composite leading indicator for, ranked by its latest reading. The index is amplitude-adjusted, so 100 is that economy's own long-term trend and the bar is the distance from it: to the right means running above trend, to the left below. The name beside each bar is the OECD's cycle phase, which combines that level with the direction of travel over three months: expansion (above trend and rising), downturn (above trend but falling), recovery (below trend and rising) and slowdown (below trend and falling). The colour repeats the phase, so it is never carried by colour alone. OECD's own aggregates (G7, G20, the euro-area big four) are left out: this ranks economies against each other, not blocs against economies.

**Practical takeaway:** The indicator is built to signal turning points in growth relative to trend roughly six to nine months ahead, so the phase matters more than the exact level. An economy moving from expansion to downturn is the early warning; slowdown turning into recovery marks the trough. Levels are not comparable as growth rates: 101 means above that economy's own trend, whether its trend growth is 1% or 6%, so a fast-growing economy can sit below a slow one here. The latest two or three months are revised as new data arrive, and the indicator gives false signals: it kept the United States below trend through 2024, a year of strong US growth.
""",
    # ── MACRO: FED BALANCE SHEET ────────────────────────────────────────────

    "macro_balance_sheet": """\
**How to read this chart:** The Federal Reserve's total balance sheet assets (WALCL) in trillions of dollars over time, with Quantitative Easing (QE) and Quantitative Tightening (QT) eras shaded. QE periods (balance sheet expanding) correspond to the Fed purchasing Treasuries and MBS to inject liquidity; QT periods (balance sheet shrinking) correspond to allowing securities to roll off without reinvestment. The balance sheet is the "size" dimension of monetary policy, distinct from the "price" dimension (interest rates).

**Practical takeaway:** Balance sheet expansion historically correlates with equity multiple expansion (higher P/E ratios) and credit spread compression — the direct result of excess liquidity seeking yield. Quantitative Tightening (QT) has the opposite effect but at a slower, less predictable pace. The speed of QT matters: aggressive QT in 2018 contributed directly to the Q4 2018 equity selloff; the Fed pivoted to stopping QT in early 2019. The current QT pace and the Fed's bank reserve "comfort level" (estimated at $3–3.5T) determine how long QT can continue before liquidity stress emerges — watch repo market rates as the leading indicator of QT running too hot.
""",

    # ── WORLD: US EQUITY VALUATIONS ─────────────────────────────────────────

    "macro_cape": """\
**How to read this chart:** The top panel is Robert Shiller's cyclically adjusted price-to-earnings ratio (CAPE) for the S&P 500 and its predecessor indices since 1881: the index price divided by the average of the previous ten years of earnings, both adjusted for inflation, which smooths out a single business cycle. The bottom panel is Shiller's excess CAPE yield: the earnings yield (1 ÷ CAPE) minus the real 10-year Treasury yield, meaning the bond yield less average inflation over the previous ten years. Dashed lines are the averages since 1881. The latest month in Shiller's file is left out while it is provisional (priced off a single day's close); Shiller estimates CPI for months the official figure is missing or not yet published, such as October 2025.

**Practical takeaway:** A high CAPE has historically been followed by lower returns over the following ten years rather than an immediate fall, so it is a guide to long-run expected returns, not a timing tool. The excess CAPE yield puts valuations against bonds: a low reading means shares offer little extra earnings yield over inflation-protected government debt, leaving less cushion if earnings disappoint or real yields rise. The peaks of 1929 and 1999 were followed by poor ten-year real returns. Part of the rise in CAPE since the 1990s may be structural (higher profit margins, changes in accounting, more capital-light companies), so compare readings with recent decades as well as the long-run average.
""",

    "macro_equity_risk_premium": """\
**How to read this chart:** Aswath Damodaran's implied equity risk premium for the S&P 500: the return investors can expect from US shares above the 10-year Treasury yield, backed out from the index level, the cash returned to shareholders over the last twelve months (dividends and buybacks) and analysts' expected earnings growth. It is calculated at the start of each month, so it moves with prices, bond yields and forecasts. The dashed line is the average since the monthly series began in September 2008.

**Practical takeaway:** A lower premium means shares are priced to earn less over government bonds, because investors are confident or because valuations are stretched relative to yields. A premium near the bottom of its range while Treasury yields are high means equities offer little compensation for their extra risk. The premium jumped in the 2008–09 financial crisis, the 2011 euro-area crisis and briefly in 2020 and 2022, when shares cheapened sharply against bonds. The estimate depends on its growth and cash-flow assumptions, so the direction and range are more informative than any single month's level.
""",

    # ── WORLD: COUNTRY RISK ─────────────────────────────────────────────────

    "macro_country_erp": """\
**How to read this chart:** Aswath Damodaran's estimate of the total equity risk premium for each G20 market: the extra return over a risk-free rate an investor should demand to own shares there. The grey part of each bar is the mature-market premium, the same for every country and anchored on the implied premium for the S&P 500. The maroon part is the country risk premium: the default spread that goes with the government's Moody's rating, scaled up because shares are more volatile than government bonds. Russia has no sovereign rating and is not shown. Damodaran updates the figures in January and July.

**Practical takeaway:** The premium is a building block of the cost of equity: the higher it is, the higher the return companies in that market must earn to satisfy shareholders, and the less investors should pay for a given stream of earnings. Countries with the same rating get the same premium, which is why several bars tie. Ratings move slowly, so the premium can lag a change in a country's fortunes; the ratings-vs-markets chart shows where credit markets already disagree with the agencies.
""",

    "macro_regional_erp": """\
**How to read this chart:** Each dot is one country Damodaran rates, placed at its total equity risk premium; the rows group them by region, ordered by the region's average. The large maroon dot on each row is that region's GDP-weighted average and the dashed line is the global average. The columns on the right give the average and its change over the year in percentage points. A few near-default sovereigns sit far above every other country and would squash the chart, so the scale stops at 20% and the source line says how many are left out.

**Practical takeaway:** The spread of dots matters as much as the average. A region whose countries cluster tightly, like Western Europe, behaves as a block: its average describes almost every country in it. A region whose dots stretch across the chart, like Asia or Africa, contains both calm and dangerous markets, and its average describes neither — which is where a country-level view pays, because the safest places inside a risky region are often mispriced by investors who treat the region as one. A falling premium means investors demand less compensation for risk, which tends to draw capital in and lift valuations. GDP weighting also lets one large economy dominate its region's figure.
""",

    "macro_ratings_vs_markets": """\
**How to read this chart:** Each bar is a disagreement, in percentage points. It takes the country risk premium implied by what markets charge to insure a government's debt against default — its sovereign credit default swap spread, net of Switzerland's as a near-riskless benchmark — and subtracts the premium implied by the government's Moody's rating. A teal bar to the left means markets see less risk than the rating does; a maroon bar to the right means they see more. Both premiums are scaled the same way, so the difference is like for like. Countries with no traded credit default swap, such as Argentina, cannot be compared and are left out.

**Practical takeaway:** Ratings change slowly and in steps while swap prices move daily, so a wide gap can foreshadow a rating action: market pricing well below the rating's implied risk is the pattern that tends to come before upgrades, and pricing well above it before downgrades. The gap also flags where a rating-based premium, the usual input for valuing companies in that market, may be too high or too low — a country whose markets are far calmer than its rating is one where textbook cost-of-equity numbers overstate the risk. Swap markets for smaller sovereigns can be thin, so their gaps deserve more caution than those of large, liquid issuers.
""",

    # ── WORLD: RATE CYCLE, EMERGING MARKETS ─────────────────────────────────

    "macro_rate_cycle": """\
**How to read this chart:** The BIS policy rate database covers the Fed, the ECB, the Bank of Japan, the RBI and most large emerging-market central banks: 38 today, and between 31 and 40 in any month since 2000, because some series start later and others stop, as when a country joins the euro. Each month's moves are measured in basis points and weighted by the size of the economy:

1. **Bars:** hikes (red, above the line) and cuts (blue, below) as an average move across these economies, each weighted by its share of their combined GDP at purchasing power parity. China (about a quarter of the total), the US (a fifth) and the euro area (a seventh) dominate, so a quarter-point Fed hike adds about 5bp and a 10bp cut in China's loan prime rate about 3bp.
2. **Black line:** hikes minus cuts, averaged over six months: roughly how fast the average policy rate of these economies is rising or falling. Above zero, the world is tightening.
3. **Dashed line:** the same with every central bank weighted equally, so Iceland counts as much as the US. When it runs above the black line, smaller economies are tightening harder, or easing less, than the big ones; below it, they are easing harder. It mixes how many banks move with how far they move, because emerging-market banks often move 100bp or more at a time.

The figures beside the latest bar give its net move and how many banks raised or cut rates. GDP is from the World Bank, each year's own and the latest published for the current year. A move of more than 200bp in a month counts as 200bp: no big central bank has moved that much in a month since 2000, and bigger moves are currency crises (Argentina in 2001, Russia in 2014 and 2022, Turkey) that would otherwise outweigh the Fed. A cap of 150bp or 300bp gives almost the same lines. The BIS publishes about a week late, so for the Fed, ECB, Bank of England, Bank of Japan and RBI any move since its last day is read from the bank's own announcement; the latest month stays faded, and out of both lines, until it is over and every bank has reported. China is the one-year loan prime rate, the rate the BIS records; the strip above shows the PBoC's 7-day reverse repo rate, which the loan prime rate follows.

**Practical takeaway:** Central banks rarely move alone. They face the same oil prices, the same dollar and the same swings in global demand, so the bars come in waves. The deepest easing came with recessions: cuts worth 61bp in December 2008, from 28 banks, and 52bp in March 2020, from 30 banks led by the Fed's 1.5-point cut. The sharpest tightening was 2022: 42bp of hikes in September alone, from 28 banks, and 225 hikes against 12 cuts over the year. 2024 and 2025 were an easing wave, with 111 and 112 cuts against 11 and 7 hikes. In 2026 the cycle has turned. The dashed line crossed above zero in June and the black line in August, so smaller and emerging-market banks turned first and the big economies followed. In September the Fed, the ECB and the Bank of Japan all raised rates, the first month since 2000 in which all three did. September comes to +10bp so far, a level only 28 of the 320 months since 2000 have reached, and none since October 2023. Keep the size in view, though: added up, this year's moves come to +7bp so far, after −96bp in 2025 and +204bp in 2022. So far this is a turn, not a 2022-style wave.

The nearest parallel is mid-2008, another wave of hikes into an oil and food price spike: 17 banks raised rates in June 2008, and by December 28 were cutting as the financial crisis hit. The parallel is loose. By weight that wave barely registers (the black line peaked below +5bp a month), because 15 of the 17 were emerging markets and the Fed had been cutting since September 2007; this time the Fed is raising rates too. Brent crude jumped from about $70 a barrel in February 2026 to $100 in March, two months before the hikes began. The parallel shows how fast an oil-driven wave can reverse if growth cracks; it is not a forecast that it will. A synchronised turn matters beyond any one economy, because it lifts borrowing costs everywhere at once, including the cost of dollar funding for emerging markets such as India.
""",

    "macro_em_borrowing": """\
**How to read this chart:** Yields, in per cent, on US-dollar bonds issued by emerging-market companies, from ICE BofA's indices: high yield, meaning rated below investment grade (orange), and investment grade (teal), against the 10-year US Treasury yield (blue). Weekly averages; FRED carries only the last three years of the ICE indices. The gap between an EM line and the Treasury line is roughly the extra return investors demand for emerging-market corporate risk. The Weekly Markets tab tracks that spread on its own; this chart shows the all-in cost of borrowing.

**Practical takeaway:** This is what dollar funding costs EM borrowers, including Indian companies that borrow abroad through external commercial borrowings. Yields rise for two different reasons: higher US Treasury yields (a global rates move, with spreads steady) or wider spreads (stress in EM credit, often alongside a strong dollar and capital outflows). The second is the more dangerous for India. A high-yield line climbing faster than the Treasury line means investors are pulling back from riskier EM credit; a narrowing gap with falling Treasury yields is the most supportive backdrop for EM borrowing and inflows.
""",

    "macro_em_dollar": """\
**How to read this chart:** The Federal Reserve's nominal emerging-market dollar index (blue) tracks the dollar against a basket of emerging-market currencies weighted by trade with the US, so the Mexican peso and Chinese yuan carry the most weight. The saffron line is the rupee. The other two lines are picked by the data, not by hand: of the ten emerging-market currencies FRED quotes daily, whichever has weakened most against the dollar over the window (maroon) and whichever has strengthened most (teal). Every line is that currency per dollar, weekly averages set to 100 three years ago, so up means the currency has weakened; the labels give each line's change over the period.

**Practical takeaway:** The index is the broad tide and the individual currencies show how far apart the same tide can push them. When the rupee moves with the index, it is riding global forces — US rates and risk appetite — and the driver is not Indian. When it pulls above the index, something local is at work: the oil import bill, portfolio outflows, or the Reserve Bank letting the currency adjust. The gap between the best and worst performer is the useful number for anyone holding emerging-market assets: a wide gap means country choice mattered more than the asset class, and currency hedging decisions dominated returns. A weakening rupee also warns of imported inflation, since India pays for oil, gold and electronics in dollars.
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

    "india_nifty_it_trend": """\
**How to read this chart:** The NIFTY IT Index level over the trailing 12 months, with the latest week shaded. As the benchmark for India's IT services export economy — dominated by TCS, Infosys, Wipro, HCL, and Tech Mahindra — this index is simultaneously a proxy for global IT spending (demand-side) and INR/USD rate dynamics (supply-side). A 5–7% depreciation in the rupee adds roughly 2–3 percentage points to NIFTY IT earnings in rupee terms.

**Practical takeaway:** The NIFTY IT index is structurally sensitive to three forces: US corporate IT budget cycles (which lead the index by 2–3 quarters), generative AI disruption risk (a structural negative for traditional offshore services), and the INR/USD rate (a natural hedge that buffers dollar-denominated revenue). Watch for divergence between NIFTY IT and US tech (QQQ/XLK) — when Indian IT underperforms US tech for more than a quarter, it typically signals AI disruption concerns rather than cycle weakness. The sector has historically traded at a premium to the broader NIFTY 50 — a narrowing premium is a structural warning sign.
""",

    "india_fpi_monthly": """\
**How to read this chart:** Each bar is one month's net portfolio investment into India in US$ billion: foreign investors' purchases of Indian equities and debt minus their sales, as reported by the RBI. Green bars are net inflows, red bars net outflows. The badge shows the cumulative total for the 24 months on the chart. The RBI publishes this series about two to three months after the month ends and revises recent months, so the latest bars can change.

**Practical takeaway:** Portfolio flows are the most volatile part of India's capital account. Sustained outflows put pressure on the rupee and on liquidity in Indian markets, and have typically coincided with periods of global risk aversion or a strong US dollar; sustained inflows ease both. A run of outflows while the trade deficit widens is the combination most likely to weaken the rupee and draw RBI intervention, visible in the forex reserves chart.
""",

    "india_inflation_bar": """\
**How to read this chart:** India's inflation landscape shown as a multi-series comparison — CPI Headline, CPI Core (ex-food and energy), and CPI Food. The RBI targets headline CPI within a 4% ± 2% band (i.e. 2–6%), with a preference for sustaining it near 4%. Food inflation, which carries approximately 45% weight in India's CPI basket, is the single largest driver of headline volatility. Core CPI is the RBI's preferred measure of underlying demand-driven inflation.

**Practical takeaway:** The most important signal in this chart is the *spread* between headline and core CPI. When headline significantly exceeds core, the primary driver is food and fuel — supply-side shocks that are typically transitory and outside the RBI's direct control. When core CPI rises toward or above headline, the inflation problem has become demand-driven, requiring tighter monetary policy. For equity investors, core CPI above 5% for two or more consecutive months is the threshold above which RBI rate hikes become more probable than pauses. Food inflation above 8% for a sustained period creates political pressure, triggers government export bans on agricultural commodities, and compresses rural consumption — all structurally negative for FMCG and consumer staples sectors.
""",

    "india_expenditure_quality": """\
**How to read this chart:** Central government spending in each month of the financial year, in ₹ lakh crore: capital expenditure in blue and revenue expenditure in red, derived from the year-to-date figures in the Controller General of Accounts' monthly accounts. The badge shows capital expenditure so far as a share of the full-year Budget Estimate. The black line (right axis) is capital expenditure as a share of that month's total spending. March usually shows a jump in revenue spending as departments close the year's accounts.

**Practical takeaway:** A higher capital share means more of each rupee goes into assets such as roads, railways and defence equipment rather than salaries, interest and subsidies, which supports growth beyond the current year. Monthly capex is lumpy, so the pattern across the year matters more than any single month. A badge share well below the part of the year that has passed (a third by July, half by September) points to underspending, which can happen when revenue disappoints and spending is held back to protect the deficit target; weak spending in the first half followed by a rush in the final quarter points to execution delays.
""",

    "india_deficit_financing": """\
**How to read this chart:** How the central government finances its fiscal deficit, from the "sources of financing the deficit" table in the Controller General of Accounts' monthly accounts, in ₹ lakh crore. Each monthly bar is the position for the year to date; the bar on the right is the full-year Budget Estimate. Sources that supply money stack up from zero and those that absorb it stack down, so the black diamond, the fiscal deficit, is what remains after netting the two. Market borrowings are net borrowing through government securities sold in the market. Small savings combine securities issued against small savings with the National Small Savings Fund line; the two can move in opposite directions from month to month, so they are shown together. Other domestic covers state provident funds, special deposits and the table's "Others" line. Cash is the change in the government's cash balance, including surplus cash it has invested, plus any ways and means advances from the RBI: a drawdown helps finance the deficit, while a build-up (below zero) means more was raised than the deficit needed. The badge shows the year-to-date deficit as a share of the Budget's full-year figure.

**Practical takeaway:** Market borrowings finance most of the deficit, so they decide how much government debt the bond market has to absorb. The government usually schedules more than half of its annual bond issuance in the first half of the year, so early on borrowing can run ahead of the deficit and the surplus appears below zero as a cash build-up that is drawn down later. Heavier use of small savings leaves fewer bonds for the market, but these deposits usually cost the government at least as much as market borrowing, because their rates are set with a spread over government bond yields. External financing is small, which keeps the deficit funded almost entirely in rupees and limits currency risk. A ways and means advance, if one appears, means the government briefly ran short of cash.
""",

    "india_fiscal_deficit_gdp": """\
**How to read this chart:** The central government's fiscal deficit (total spending minus receipts other than borrowing) as a share of nominal GDP for each of the last ten financial years. A lighter bar marked with an asterisk is a year still in progress, showing the deficit so far against full-year GDP. The dashed line is the latest year's budget target (for FY26, the medium-term goal of bringing the deficit below 4.5% of GDP) and the dotted line is the 3% target of the Fiscal Responsibility and Budget Management (FRBM) framework.

**Practical takeaway:** The deficit peaked at 9.2% of GDP in FY21, when the pandemic cut revenue and raised spending, and has come down in most years since. A smaller deficit means less government borrowing, which leaves more room in the bond market for other borrowers and eases pressure on long-term rates such as the 10-year government bond yield. Rating agencies and bond investors watch whether stated targets are met, so a miss matters more than the level alone.
""",

    # ── INDIA: MONETARY CONDITIONS ───────────────────────────────────────────

    "india_repo_rate": """\
**How to read this chart:** The RBI's policy repo rate history shown as a step chart — each horizontal segment represents a policy hold period, each vertical step represents an MPC decision to hike or cut. Annotated with each meeting date and the prevailing rate. This is the anchor of India's entire yield curve: repo rate decisions directly set the overnight interbank rate (WACR) and, with a lag, influence 91-day T-bills, 10-year G-Secs, and ultimately bank lending and deposit rates.

**Practical takeaway:** The rate cycle context determines everything downstream in India macro. Identify whether the RBI is in a tightening cycle (2022–23), a prolonged hold (2023–24), or an easing cycle (2024-onwards). Each phase has a distinct transmission: tightening compresses credit growth and slows home loans; easing stimulates both. India's neutral real rate is estimated at 1–1.5%, meaning a repo rate above 5.5–6% is restrictive. Watch the gap between the repo rate and current CPI — when the real rate turns positive and persistent, the preconditions for a rate cut cycle are satisfied.
""",

    "india_money_supply": """\
**How to read this chart:** Two lines showing M3 (broad money supply) growth YoY % versus aggregate bank credit growth YoY %. The gap between the two is the monetary transmission signal: when credit growth exceeds M3 growth, banks are expanding loan books faster than deposits are accumulating — a structural tightening of liquidity; when M3 grows faster than credit, excess money creation is sitting idle (risk-off environment) or being deployed into government securities rather than private credit.

**Practical takeaway:** The credit-M3 spread is one of the cleanest leading indicators of RBI liquidity operations. A sustained positive spread (credit > M3) precedes CRR/SLR adjustments and OMO purchases by the RBI to inject liquidity. A negative spread (M3 > credit) signals monetary accommodation in excess of private credit demand — consistent with a rate cut cycle or low investment sentiment. India's historical "normal" for bank credit growth is 12–15% YoY; below 10% is a soft-credit regime; above 16% risks asset quality concerns in the medium term.
""",

    "india_credit_deposit": """\
**How to read this chart:** Grouped bars showing bank credit growth YoY % and deposit growth YoY % side-by-side each month, with the Credit-Deposit (CD) ratio overlaid as a secondary-axis line. The CD ratio (total credit ÷ total deposits) is the core liquidity health metric for India's banking system: a rising CD ratio means the system is lending more of every deposit rupee, compressing the liquidity buffer.

**Practical takeaway:** India's banking system historically operates with a CD ratio between 70–78%. Sustained CD ratios above 78% signal that deposit mobilisation is lagging credit demand — which has historically preceded RBI calls for banks to raise deposit rates, moderated loan growth, or tighter systemic liquidity. The chart also shows whether credit-deposit divergence is cyclical (temporary growth surge) or structural (persistent deposit shortfall). When deposit growth consistently trails credit growth for 4+ months, watch for RBI governor commentary on deposit mobilisation — this has been a frequent conference theme in 2023–24.
""",

    "india_rate_transmission": """\
**How to read this chart:** Each line is the cumulative change, in basis points, since the start of the current policy rate cycle: the RBI's repo rate against the rates banks actually charge and pay. The figures are the RBI's own, from Table IV.3 of the State of the Economy article in each month's Bulletin, and every edition restates the cycle to date — so reading the same row across editions traces how far the policy move has travelled. The external benchmark rate (EBLR) follows the repo mechanically and is left off; what matters is the gap between the repo line and the loan and deposit lines, which is the part of the move that has not reached borrowers and savers. Bank rates are reported with a lag, so the last point is usually two months behind the repo rate.

**Practical takeaway:** Transmission is slow, partial and reversible. In the cycle that began in February 2025, the full repo cut reached the external benchmark immediately, while fresh lending rates moved by roughly two-thirds of it and fresh deposit rates moved further still before giving part of it back — cumulative deposit pass-through peaked and then narrowed as banks competed for funding against strong credit demand. Fresh deposit rates are the most volatile line because they reflect the mix of new business each month, not the whole deposit book; outstanding rates move slowest, since existing loans and deposits reprice only at reset dates. A widening gap between the repo line and the lending lines means policy is working less than the headline rate suggests, and it is the clearest signal that further cuts may be needed to achieve the same effect.
""",

    # ── INDIA: ECONOMIC ACTIVITY ──────────────────────────────────────────────

    "india_iip": """\
**How to read this chart:** India's Index of Industrial Production (IIP) year-on-year percentage change, shown as green/red monthly bars with a 3-month moving average overlay. IIP measures the volume of output across manufacturing (77% weight), mining (14%), and electricity (9%). It is released monthly by MoSPI with a 6-week lag and serves as the official measure of industrial output — the closest India has to a monthly GDP proxy for the real sector.

**Practical takeaway:** IIP is inherently volatile due to base effects and seasonal manufacturing cycles; the 3M MA is more informative than any single month. Sustained IIP above 5–6% YoY is consistent with RBI's 7%+ real GDP growth projections. Cross-reference with PMI: PMI is forward-looking (surveys) while IIP is backward-looking (actual output); when both are elevated simultaneously, India's manufacturing cycle is genuinely strong. IIP weakness below 2% for 3+ consecutive months has historically preceded downward revisions to advance GDP estimates and triggered RBI accommodation discussions.
""",

    # ── INDIA: EXTERNAL SECTOR ────────────────────────────────────────────────

    "india_forex_reserves": """\
**How to read this chart:** Dual panel showing India's total foreign exchange reserves in USD billions (area chart, left panel) and the week-on-week change in reserves (diverging bars, right panel). Data sourced from the RBI's weekly statistical supplement, released every Friday for the prior week. India's forex reserves are the RBI's primary instrument for INR management: they buy USD (accumulate reserves) when the INR is appreciating and sell USD (draw down reserves) when the INR is under depreciation pressure.

**Practical takeaway:** Reserves above $600B provide approximately 12 months of import cover — a historically strong buffer that the RBI uses as a communications anchor. The weekly change chart is more actionable: sustained weekly drawdowns of $2–4B over 4+ consecutive weeks almost always indicate active RBI intervention to defend the INR. Sharp single-week drops ($5–8B) typically reflect forward contract settlements or emergency intervention during EM sell-offs (e.g., during US rate hike cycles). Reserve accumulation weeks confirm a period of INR stability or RBI building a buffer ahead of anticipated external volatility.
""",

    "india_trade": """\
**How to read this chart:** Monthly merchandise exports and imports in USD billions shown as grouped bars, with the trade deficit plotted as a secondary-axis line. Data sourced from DGCI&S via RBI DBIE. India is structurally a trade deficit country — imports (primarily crude oil, gold, electronics) consistently exceed exports — making the deficit magnitude a key variable for the current account balance and INR pressure.

**Practical takeaway:** India's merchandise trade deficit typically runs at $20–25B per month under stable conditions. Deficits below $20B signal either weak import demand (slowdown) or strong export performance; deficits above $28–30B signal commodity price surges (crude oil being the dominant driver — every $10/barrel rise in Brent adds approximately $12–14B to India's annual import bill) or gold import spikes. The services trade surplus (software exports, remittances) partially offsets the merchandise deficit but is not captured here — for the full current account picture, note that India's services surplus of ~$150B/year (FY24) structurally cushions the merchandise gap.
""",

    "india_promoter_holdings": """\
**How to read this chart:** Every listed Indian company files a shareholding pattern with the exchange within 21 days of each quarter end. This counts how much of each company its promoter holds — the founding family, the parent company or, for state-owned firms, the government — and groups the companies into 2.5-point bands. The bars are the latest quarter; the grey outline is the earliest quarter NSE keeps, drawn over exactly the same companies, so the change is promoters buying and selling rather than the market listing new firms. Two rules shape the picture: control passes at 50%, and no promoter may hold more than 75%, because at least a quarter of every listed company must sit with the public. The handful of companies above 75% are recent listings and state holdings still being brought down to it.

**Practical takeaway:** This is the single biggest structural difference between Indian equities and American ones. The median Indian company is majority-owned by one identifiable owner, and the tallest bar on the chart is the group parked within touching distance of the legal ceiling — promoters holding every share the law allows. For an investor it means minority shareholders rarely decide anything, and the governance question is not whether management is accountable to owners but whether the owner treats the minority fairly; for the market it means a large share of the register never trades, so free float is thinner than market capitalisation suggests. The slow leftward drift is the story to watch: promoters have been selling into a strong market, at roughly half a point of the median company a year, which gradually deepens the free float. Note that the like-for-like comparison excludes companies listed since the earlier quarter; including today's newer listings, which come to market with higher promoter stakes, lifts the current median by about two points.
""",

    # ── WEEKLY: CRYPTO ASSETS ────────────────────────────────────────────────

    "eth_btc_ratio": """\
**How to read this chart:** The ETH/BTC price ratio (left axis, primary signal) — how many Bitcoin each unit of Ethereum commands — plotted against indexed performance lines for both Bitcoin and Ethereum on the secondary axis (deliberately faint to avoid visual competition with the ratio). The ratio is a direct measure of relative risk appetite within the crypto complex: rising ETH/BTC means investors are rotating from the "digital gold" thesis (BTC) into higher-beta crypto (ETH and broader altcoins); falling ETH/BTC means capital is consolidating back into Bitcoin, a crypto risk-off signal.

**Practical takeaway:** The ETH/BTC ratio is the single most reliable intra-crypto risk sentiment indicator available. Historically, ETH/BTC rising above its 52-week mean and sustaining that level for 4+ weeks has preceded "altcoin season" — broad rallies across smaller-cap tokens following Ethereum's leadership. ETH/BTC breaking below its 52-week mean and staying there signals Bitcoin dominance expansion — a regime associated with institutional allocation preference for BTC as a macro asset and tepid retail participation in the broader ecosystem. For macro investors, a rising ETH/BTC ratio concurrent with a rising BTC price is the most risk-on crypto regime; a falling ETH/BTC concurrent with a falling BTC price is the most risk-off.
""",

    "btc_global_m2": """\
**How to read this chart:** Bitcoin's price (orange, left axis, log scale) against global M2 (blue dashed line, right axis): the broad money of the United States, China, the euro area, Japan, the UK, Canada and Australia, converted to US dollars at each week's exchange rate (OECD and FRED data). Because it is counted in dollars, global M2 moves with the exchange rate as well as with money creation: a strong dollar shrinks the other six economies' money once converted, even while it grows at home. Grey shading marks each spell of two months or more in which global M2 was lower in dollars than a year earlier. The values in the key are the latest readings.

**Practical takeaway:** Since 2013 global M2 has doubled in dollars, to about $118 trillion, while bitcoin has risen several thousand-fold, so their levels correlate at 0.95. Any two rising series do that, though, so the number says little about cause. Direction is the more useful evidence. All three spells in which global M2 shrank in dollars (2015, early 2019 and 2022–23) came with bitcoin in a bear market, at its worst 77–85% below its previous peak. Each time the shrinkage was the dollar's doing: at fixed exchange rates, global money kept growing 5–8% a year. The timing is looser than the popular claim that bitcoin follows global M2 about three months later. Quarter by quarter, the change in global M2 has correlated about 0.35 with bitcoin's move in the following quarter: a real but weak lead that explains roughly a tenth of bitcoin's swings. Nor does rising liquidity guarantee a rising bitcoin: in the year to July 2026, global M2 grew 7% in dollars while bitcoin fell 45%, the break shown in the chart above. Watch the dollar as closely as the central banks, because a strong dollar has been what turned global M2 down.
""",

    "btc_mvrv_zscore": """\
**How to read this chart:** The chart compares what bitcoin is worth at today's price with what its holders paid for it, and measures how stretched the gap between the two is.

1. **Market value (MV)**, the purple line on the left axis: every bitcoin in existence valued at today's price, which is its market capitalisation.
2. **Realised value (RV)**, the blue line on the left axis: every bitcoin valued at the price at which it last moved on-chain, roughly what holders paid in total. Coin Metrics' free data carries market value and MVRV (MV ÷ RV) but not realised value itself, so RV here is MV divided by MVRV.
3. **MVRV Z-score**, the orange line on the right axis: the gap between the two (MV − RV) divided by the standard deviation of market value over bitcoin's whole history up to that day. It says how stretched the gap is by the market's own past standards.

The left axis is a log scale, so equal distances are equal percentage moves. The red band is a Z-score above 7. In the green band, below 0, market value has fallen under realised value and the average holder is sitting on a loss. Dots label each cycle's peak with its value, and each spell in the green band with the month of its low.

**Practical takeaway:** The green band has the cleaner record. Every major low since 2011 — October 2011, January 2015, December 2018, the March 2020 crash and November 2022 — came with the Z-score below zero, when the market valued bitcoin at less than holders had paid for it. The red band has worked less well each cycle: the peaks of 10.7 in 2013 and 10.1 in 2017 sat deep inside it, the 2021 peak only just reached it (7.2 in February, while the price top of November 2021 came at 3.5), and the latest cycle peaked at 3.4 in December 2024, with the October 2025 price record at only 2.5. As more coins sit with long-term holders and funds, the gap between market and realised value has narrowed at each top, so the gauge is best read against its own recent peaks rather than the fixed line. As of September 2026 it stands near 1, having bottomed at 0.2 in June without entering the green band.
""",

    "btc_zscore_global_m2": """\
**How to read this chart:** Inspired by [*Bitcoin: A Global Liquidity Barometer*](https://www.lynalden.com/bitcoin-a-global-liquidity-barometer/), the September 2024 report Lyn Alden commissioned from Sam Callahan. It found that bitcoin moves with global money supply more consistently than other major assets, but that the link tends to break down when the MVRV Z-score falls from a cycle high, as bitcoin's own boom-and-bust cycle takes over. The top panel is the Z-score, explained under the chart beside this one. Grey shading runs from each of its cycle highs to the low that followed, or to today where no low has formed yet. The bottom panel is the correlation between bitcoin's weekly price and global M2 over the previous 52 weeks, both in logs. A reading of +1 means the two rose and fell together over the year, 0 means no relationship, and −1 means they moved in opposite directions. Global M2 is the broad money of the United States, China, the euro area, Japan, the UK, Canada and Australia, converted to dollars at each week's exchange rate (OECD and FRED data).

**Practical takeaway:** Most of the time the link holds: since 2012 the correlation has been above zero in 85% of weeks, averaging 0.42. The report's pattern shows up, but loosely. While the Z-score fell from a cycle high, the correlation averaged 0.35, against 0.46 at other times, and the falls of 2014, 2018 and 2021–22 each pushed it below zero for a spell. Yet three of the four deepest breaks before 2026 (2012, 2019 and 2020) came with the Z-score low and rising. Part of the reason is arithmetic. Global M2 in dollars rose over almost nine in ten 12-month periods, so the correlation largely records whether bitcoin itself rose or fell over the year: it averaged 0.52 when bitcoin was up on the year and 0.16 when it was down. The present break is the one that stands out. The correlation turned negative in February 2026 and has stayed below zero for 31 weeks, nearly twice as long as any earlier spell. It reached −0.90 in July, against a previous low of −0.54 in 2012, as bitcoin fell 45% in the year to July while global M2 rose 7%. Read it as a regime check, not a timing tool. The correlation's level has not predicted bitcoin's next year, which was positive about 70% of the time whatever the reading. But a reading this low says bitcoin is being driven by the unwinding of its own 2024–25 boom rather than by liquidity, and that rising global money has not, so far, been enough to lift it.
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


    # ── RBI SENTINEL ─────────────────────────────────────────────────────────

    "rbi_stance_meter": """\
**How to read this chart:** The dial displays the RBI MPC's current composite policy stance \
on a continuous scale from −1.0 (Extremely Dovish) to +1.0 (Extremely Hawkish). The score is \
derived from the most recent set of MPC documents using a hybrid model: a curated central-bank-specific \
lexicon pre-scores the text for RBI-specific phrases (e.g. "withdrawal of accommodation" = +1.0), \
then the Anthropic Claude API provides a contextual validation and sub-dimension breakdown. \
The five sub-dimensions — Inflation Stance, Growth Stance, Liquidity Stance, Rate Guidance, and FX/External Stance — \
are weighted and fused into the single composite displayed here. A score near zero does not mean "no view" — \
it may mean the committee is actively balancing competing concerns, which is itself a meaningful signal.

**Practical takeaway:** A composite score crossing −0.3 and continuing to fall has historically \
preceded RBI rate cuts by 1–2 meetings. A score above +0.5 sustained over two consecutive meeting \
cycles signals a committee prepared to act on inflation regardless of growth conditions — typically \
negative for rate-sensitive sectors (real estate, NBFCs, capex-heavy industrials) and supportive \
of the INR through carry dynamics. The most actionable signal is a large divergence between the \
Resolution score and the Minutes score: when Minutes are significantly more hawkish than the \
Resolution, the committee's official statement is understating internal pressure, and markets may \
be underpricing the risk of a hawkish surprise at the next meeting.
""",

    "rbi_tone_vs_10y": """\
**How to read this chart:** Each dot on the left is one MPC decision since December 2016. Across is the change in the Resolution's tone score from the previous meeting (−1 most dovish to +1 most hawkish); up is the change in the 10-year G-sec yield from the previous day's close to the close on decision day. The Resolution is released during bond-market hours, so that day's close already reflects it. Filled dots are holds; hollow dots are hikes (red) and cuts (blue). The panel on the right runs exactly the same test on other markets: a bar outside the shaded band is statistically significant. Why the 10-year yield matters: it is India's benchmark long-term interest rate. It sets the base cost of government borrowing, anchors the pricing of corporate bonds, bank loans and home loans, and feeds into the discount rate used to value equities, so it is the main channel through which a shift in the RBI's message reaches the wider economy and investors' portfolios.

**Findings:** Changes in the Resolution's tone line up with 10-year G-sec moves on decision day, historically about 5 bps per typical shift. Testing on new meetings is under way. In numbers: +15.7 bps per unit of tone change (t = 4.0), after controlling for the rate decision itself and any change in the stated stance. Tone raises the share of the day's move explained from 18% to 37%. The Resolution carries the signal; the Governor's Statement adds nothing beyond it. The level of tone does not move yields — only the change does, which is how a policy surprise behaves.

**Other financial markets:** The same question was put to the Nifty 50, Bank Nifty, USD/INR, gold in rupees and India VIX, and to 91-day and 364-day T-bill yields, over three windows: decision day, the day after the Minutes are released, and the following one and three months. Each was tested with the Resolution, the Governor's Statement and the full composite separately, and corrected for running many tests at once. Equities, the rupee, gold and volatility show no relationship in any window. An apparent link to future T-bill yields disappeared once their normal pull back toward the repo rate was accounted for.

**How robust the bond result is:** It holds excluding 2020, excluding the three off-cycle meetings, before and after 2022, and with any single meeting removed (t stays above 3.5). On 5,000 sets of random non-meeting days, a result this strong appeared 0.02% of the time, and yields show nothing in the five days before a meeting.

**What it does not show:** This is not a forecast of where yields go next, and it is not investment advice. The effect comes entirely from the language model's reading of the text — a simple keyword count shows nothing — and every historical meeting predates the model's training cutoff, so hindsight cannot be fully ruled out. Only meetings scored live, before the market closes, can settle that.

*Data: RBI Sentinel Resolution scores; 10-year G-sec yield, Investing.com (checked against FBIL weekly); Nifty 50, Bank Nifty, USD/INR, gold and India VIX, Yahoo Finance. 60 decisions, December 2016 – August 2026. Regressions use Newey–West standard errors.*
""",

    "rbi_sentiment_trajectory": """\
**How to read this chart:** Each point is one MPC meeting's tone score, from −1 (most dovish) to +1 \
(most hawkish), read separately from the three documents: the Policy Statement (the Resolution, \
published on decision day), the MPC Minutes (about two weeks later) and the Governor's Statement \
(decision day, in the corpus from August 2020). Red shading marks hawkish territory, blue dovish. \
The strip beneath is the decision taken at each meeting — red for a hike, blue for a cut, grey for \
a hold — on the same time axis, so every dot sits under its meeting.

**Practical takeaway:** Tone moves with the policy cycle: hawkish through the 2018 and 2022–23 \
tightening, dovish through the 2019–20 and 2025 easing. The strip shows where tone and action part \
company — the long run of grey holds through 2023–24 came with persistently hawkish language, and \
the holds of 2026 with tone climbing back above neutral. The three documents usually agree; when \
the Minutes diverge from the Policy Statement, they show how the committee's debate differed from \
its published decision.
""",

    "rbi_resolution_vs_minutes": """\
**How to read this chart:** For each of the last eight MPC meetings, three bars are shown \
per cycle — the sentiment score derived from the official Policy Resolution, the score from the \
MPC Minutes, and the score from the Governor's Statement. The spread (s) annotated above each \
group is the maximum score minus the minimum score across all three documents. A high spread \
indicates fragmented signalling; a low spread indicates consensus across the full corpus. \
RBI Minutes are structured differently from Fed Minutes: each MPC member's individual assessment \
is published in full, enabling richer sentiment extraction per member.

**Practical takeaway:** When all three bars are tightly clustered (spread < 0.15) on the hawkish \
side, the signal has the highest conviction — the Governor, the Resolution, and the internal \
deliberation all corroborate the stance. When bars diverge sharply (spread > 0.30), exercise \
caution: the official statement may not reflect the full complexity of the committee's view. \
A Governor bar that is persistently above both the Resolution and the Minutes is a forward-looking \
signal that the Governor is personally advocating for tightening ahead of formal consensus.
""",

    "rbi_subdimension_radar": """\
**How to read this chart:** The five axes represent orthogonal dimensions of the MPC's policy \
stance: Inflation Stance (dismissive → alarmed), Growth Stance (concerned → optimistic), \
Liquidity Stance (accommodative → tightening), Rate Guidance (cuts ahead → hikes ahead), \
and FX/External Stance (depreciation-tolerant → defensive). Each polygon represents one MPC \
meeting. A larger polygon area indicates a more hawkish meeting overall; the shape of the polygon \
reveals which dimensions are driving the stance. The current meeting is plotted against the \
previous meeting for direct comparison.

**Practical takeaway:** The Rate Guidance axis is the most forward-looking dimension and the \
highest-weight signal for near-term positioning. When Rate Guidance shifts hawkish while Inflation \
Stance remains neutral, the committee is front-running inflation data — typically a signal to trim \
duration. When Growth Stance collapses toward "concerned" while all other axes remain hawkish, \
the committee is approaching a forced pivot: watch for a Resolution score reversal in the following \
1–2 meetings.
""",

    "rbi_rate_and_sentiment": """\
**How to read this chart:** The step line (left axis) is the RBI repo rate; the black line (right \
axis) is the composite sentiment score for each MPC meeting, from −1 (most dovish) to +1 (most \
hawkish). The two series sit on different scales, so read the direction and timing of each line \
rather than the gap between them.

**Practical takeaway:** Committee tone moves with the rate cycle — firmly hawkish through the \
2022–23 tightening and the long hold that followed, dovish through the 2019–20 and 2025 easing \
cycles. The score is most closely tied to the decision taken at the same meeting (correlation \
0.72, falling to 0.57 for the next meeting). In formal tests covering every meeting since \
October 2016 — regressions with robust standard errors and out-of-sample forecasts from 2020 — \
the composite did not predict the next rate decision beyond what the RBI's own stated stance \
already signals. Read a gap between tone and policy, such as a hawkish score during a hold, as \
evidence of how the committee is framing its pause rather than as a forecast of the next move.
""",

    "rbi_governor_divergence": """\
**How to read this chart:** Each bar shows how much the Governor's Statement score deviates from \
the meeting's composite score (Minutes 50% + Resolution 35% + Governor 15%). Positive bars \
indicate the Governor is more hawkish than the committee consensus; negative bars indicate the \
Governor is more dovish. The zero line represents perfect alignment between the Governor's personal \
tone and the committee average.

**Practical takeaway:** The Governor's Statement is released simultaneously with the Resolution \
but is entirely the Governor's own voice — not a committee document. Persistent positive divergence \
(Governor more hawkish than the composite for 2+ cycles) is a forward-looking signal: the Governor \
is personally building a rhetorical case for tightening ahead of formal committee alignment. This \
pattern has historically preceded rate hike cycles by one to two meetings. Conversely, a sharp \
negative divergence signals a Governor who is more open to easing than the committee's formal \
position, often a precursor to a change-in-stance announcement.
""",

}
