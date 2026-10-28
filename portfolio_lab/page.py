"""Portfolio Lab's presentation: session-local allocations, prepared inputs only."""
from datetime import date
from html import escape
import numpy as np
import pandas as pd
import streamlit as st
from portfolio_lab.layout import centered_chart, centered_note, research_navigation
from portfolio_lab.labels import asset_label, short_asset_label, asset_frame, asset_chart_frame

from config.portfolio_settings import ASSETS, EPISODES, REBALANCING, TEMPLATES
from data.fetchers.portfolio_prices import freshness, load_bundle, snapshot_path
from data.processors.portfolio_analytics import compare, metrics, risk_contributions, validate_weights
from data.processors.portfolio_stress import historical_replay, hypothetical_shock
from portfolio_lab.charts import allocation_risk, correlations, paths, heading_html, legend_html, contribution_bars
from data.fetchers.portfolio_bitcoin import DISCLOSURE as BTC_DISCLOSURE
from portfolio_lab.research import attribution_view, risk_view, regimes_view, diversification_view


@st.cache_data(show_spinner=False, max_entries=3)
def _load_prepared(bundle):
    return load_bundle(bundle)


def _apply(prefix, weights):
    st.session_state[prefix + "_model"] = dict(weights)
    st.session_state[prefix + "_assets"] = list(weights)
    for t in ASSETS:
        st.session_state[prefix + "_" + t] = float(weights.get(t, 0)*100)


def _normalize(prefix):
    assets = st.session_state.get(prefix + "_assets", [])
    total = sum(st.session_state.get(prefix+"_"+t, 0) for t in assets)
    if total > 0:
        for t in assets:
            st.session_state[prefix+"_"+t] = st.session_state.get(prefix+"_"+t, 0)*100/total


def _template_changed(prefix):
    _apply(prefix, TEMPLATES[st.session_state[prefix + "_template"]])


def _builder(prefix, title, available):
    st.markdown("#### " + title)
    st.selectbox("Portfolio type", list(TEMPLATES), key=prefix+"_template",
                 on_change=_template_changed, args=(prefix,))
    st.button("Normalize weights", key=prefix+"_normalize", on_click=_normalize, args=(prefix,), use_container_width=True)
    selected = st.multiselect("Holdings", list(available), key=prefix+"_assets",
                              format_func=asset_label)
    weights = {}
    weight_columns = st.columns(2)
    for i, t in enumerate(selected):
        key = prefix+"_"+t
        if key not in st.session_state:
            st.session_state[key] = st.session_state.get(prefix + "_model", {}).get(t, 0.0)*100
        weights[t] = weight_columns[i % 2].number_input(short_asset_label(t) + " weight (%)", min_value=0.0, max_value=100.0,
                                      step=1.0, format="%.2f", key=key)/100
    st.session_state[prefix + "_model"] = weights.copy()
    st.caption("Total allocation: {:.2f}%".format(sum(weights.values())*100))
    try:
        validate_weights(weights)
    except ValueError as exc:
        st.error(str(exc))
    return weights


def _table(outcomes):
    # Text values keep percentages and dollar wealth distinct, suppress NaN.
    display = outcomes.copy().astype(object)
    for row in display.index:
        for col in display.columns:
            value = outcomes.loc[row, col]
            display.loc[row, col] = ("—" if pd.isna(value) else "${:,.0f}".format(value)
                                     if "wealth" in row.lower() else "{:.2f}".format(value)
                                     if "ratio" in row.lower() else "{:.2%}".format(value))
    headings = "".join("<th>" + escape(str(c)) + "</th>" for c in display.columns)
    rows = "".join("<tr><th>" + escape("Sortino ratio" if row == "Sortino ratio (0% target)" else str(row)) + "</th>" + "".join(
        "<td>" + escape(str(display.loc[row, c])) + "</td>" for c in display.columns) + "</tr>" for row in display.index)
    st.markdown('<table class="pl-summary"><thead><tr><th>Metric</th>' + headings +
                '</tr></thead><tbody>' + rows + '</tbody></table>', unsafe_allow_html=True)


def _header(latest=None, root=None, manifest=None, reference_date=None):
    meta = (
        '<div class="rbi-head-meta"><span class="rbi-head-meta-label">Analysis through</span>'
        f'<span class="rbi-head-meta-value">{escape(str(latest))}</span></div>'
    ) if latest else ''
    if latest and root is not None and manifest is not None:
        from portfolio_lab.status import banner_html
        meta = banner_html(latest, root, manifest, reference_date)
    st.markdown(
        '<div class="rbi-head"><div class="rbi-head-text">'
        '<p class="rbi-head-title">Portfolio Lab</p>'
        '<p class="rbi-head-dek">Explore how hypothetical portfolios perform across market cycles, '
        'where their risk comes from, and how they respond to historical and simulated shocks.</p>'
        '<p class="rbi-head-note"><em>Note: Some features are still under development.</em></p>'
        '</div>' + meta + '</div>', unsafe_allow_html=True,
    )


def _enter_mode(mode):
    st.session_state['pl_entered'] = True
    st.session_state['pl_mode'] = mode


def _entry_cards():
    with st.container(key="pl-investor-entry"):
        global_card, india_card = st.columns(2, gap="large")
        with global_card:
            st.button(
                "**Global Investor**  \nInternational assets and portfolio research in US dollars.  \n  \nEnter Global Portfolio →",
                key="pl_enter_global", on_click=_enter_mode, args=("Global Portfolio — USD",),
                use_container_width=True,
            )
        with india_card:
            st.button(
                "**Indian Investor**  \nIndian and international allocations, measured in rupees.  \n  \nEnter Indian Portfolio →",
                key="pl_enter_india", on_click=_enter_mode, args=("Indian Investor — INR",),
                use_container_width=True,
            )


def _render():
    # Detach hidden widgets from Streamlit's cleanup; canonical allocations
    # also survive navigation away in non-widget, session-local model keys.
    for key in list(st.session_state):
        if key.startswith(("pl_a_", "pl_b_", "in_")) and not key.endswith(("_apply", "_normalize", "_normalise", "_duplicate")):
            st.session_state[key] = st.session_state[key]
    st.markdown('''<style>
    .st-key-portfolio-lab {font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;}
    .pl-refresh-meta {max-width:290px;min-width:215px;white-space:normal!important;text-align:right;}
    .pl-analysis-cutoff {font:600 13px/1.5 Inter,sans-serif;color:#0A1F3D;}
    .pl-analysis-cutoff strong {font-weight:700;}
    .pl-refresh-line {font:11px/1.5 Inter,sans-serif;color:#6B7280;}
    @media(max-width:640px) {.pl-refresh-meta {max-width:100%;min-width:0;}}
    .st-key-portfolio-lab p,.st-key-portfolio-lab label,.st-key-portfolio-lab input,
    .st-key-portfolio-lab button,.st-key-portfolio-lab [role="combobox"] {font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;}
    .pl-chart-heading {max-width:900px;margin-left:auto!important;margin-right:auto!important;border-top:2px solid #1A1A1A;padding-top:16px;margin:24px 0 12px;}
    .st-key-portfolio-lab .pl-chart-heading h3 {font-family:Inter,sans-serif!important;font-size:23px!important;font-weight:700!important;line-height:1.25!important;margin:0 0 7px!important;}
    .pl-chart-heading p {color:#4B5563;font-size:13px!important;margin:0!important;}
    .pl-chart-legend {max-width:900px;margin-left:auto!important;margin-right:auto!important;display:flex;flex-wrap:wrap;gap:12px 28px;margin:10px 0 14px;font-size:13px;color:#4B5563;}
    .st-key-portfolio-lab .pl-chart-legend,.st-key-portfolio-lab .pl-chart-legend span,.st-key-portfolio-lab .pl-chart-legend b {font-family:Inter,sans-serif!important;}
    .pl-chart-legend span {display:inline-flex;align-items:center;gap:8px;}
    .pl-chart-legend i {width:20px;height:3px;display:inline-block;}
    .pl-chart-legend b {font-variant-numeric:tabular-nums;color:#1A1A1A;font-size:16px;}
    .st-key-portfolio-lab .pl-builder-title {font-family:Inter,sans-serif!important;font-size:23px!important;font-weight:700!important;border-bottom:2px solid #1A1A1A;padding-bottom:12px;margin:26px 0 18px;}
    .st-key-portfolio-lab [data-testid="stVegaLiteChart"] {background:transparent;}
    .st-key-pl-investor-entry {margin:28px 0 36px;}
    .st-key-pl_enter_global button,.st-key-pl_enter_india button {
        min-height:300px; border:0; border-radius:10px; padding:36px 38px;
        display:flex; align-items:center; justify-content:flex-start; text-align:left;
        box-shadow:0 12px 28px rgba(10,31,61,.12); color:white!important;
        transition:transform .18s ease,box-shadow .18s ease;
    }
    .st-key-pl_enter_global button {background:linear-gradient(125deg,#0A2540,#084B83)!important;}
    .st-key-pl_enter_india button {background:linear-gradient(125deg,#571313,#942727)!important;}
    .st-key-pl_enter_global button:hover,.st-key-pl_enter_india button:hover {
        transform:translateY(-3px);box-shadow:0 16px 32px rgba(10,31,61,.2);
    }
    .st-key-pl_enter_global button:focus-visible,.st-key-pl_enter_india button:focus-visible {
        outline:3px solid #A88947;outline-offset:5px;
    }
    .st-key-pl_enter_global button p,.st-key-pl_enter_india button p {
        color:#F5F7FA!important;font-size:18px!important;line-height:1.8!important;margin:0!important;
    }
    .st-key-pl_enter_global button strong,.st-key-pl_enter_india button strong {
        font-family:'Lora',Georgia,serif!important;font-size:32px!important;
        line-height:1.25!important;color:#FFFFFF!important;display:inline-block;margin-bottom:16px;
    }
    @media(max-width:640px) {
        .st-key-pl_enter_global button,.st-key-pl_enter_india button {min-height:245px;padding:28px;}
        .st-key-pl_enter_global button strong,.st-key-pl_enter_india button strong {font-size:28px!important;}
    }
    @media(prefers-reduced-motion:reduce) {
        .st-key-pl_enter_global button,.st-key-pl_enter_india button {transition:none;}
    }
    .st-key-pl-regime-timeline,.st-key-in-regime-timeline {margin-top:-24px;}
    .st-key-pl-research-navigation [role="radiogroup"] {justify-content:center;flex-wrap:wrap;}
    .st-key-pl-research-navigation [data-testid="stWidgetLabel"] {text-align:center;width:100%;}
    .pl-centered-note {max-width:900px;margin:8px auto 18px;text-align:center;color:#59616D;font-size:13px!important;line-height:1.6;}
    .pl-summary { width:100%; max-width:760px; table-layout:fixed; border-collapse:collapse; font-family:Inter,sans-serif; font-size:14px; margin:12px auto 24px; }
    .pl-summary th, .pl-summary td { padding:10px 8px; border-bottom:1px solid #d8d8d0; text-align:right; overflow-wrap:break-word; }
    .pl-summary th:first-child { text-align:left; width:34%; font-weight:500; }
    .pl-summary thead th { border-top:2px solid #000; border-bottom:1px solid #000; color:#003366; }
    @media(max-width:640px) { .pl-summary {font-size:11px;} .pl-summary th,.pl-summary td {padding:8px 3px;} }
    </style>''', unsafe_allow_html=True)
    header = st.empty()
    with header.container():
        _header()
    if not st.session_state.get('pl_entered'):
        _entry_cards()
        return
    mode=st.radio('Investor mode',['Global Portfolio — USD','Indian Investor — INR'],horizontal=True,key='pl_mode')

    def update_header(latest, root=None, manifest=None, reference_date=None):
        with header.container():
            _header(latest, root, manifest, reference_date)

    if mode=='Indian Investor — INR':
        from portfolio_lab.india import render as render_india
        render_india(on_ready=update_header)
        return
    try:
        bundle = snapshot_path()
        prices, manifest = _load_prepared(str(bundle))
    except (ValueError, OSError, KeyError) as exc:
        st.warning("Portfolio data unavailable: " + str(exc))
        st.info("The published portfolio dataset is unavailable. Please try again later.")
        return
    latest = min(m["latest_observation"] for m in manifest["assets"].values())
    update_header(latest, bundle.parent, manifest)
    status = freshness(latest)
    if status.startswith(("Stale", "Invalid")):
        st.warning(status)
    if "pl_a_assets" not in st.session_state:
        _apply("pl_a", st.session_state.get("pl_a_model", TEMPLATES["Traditional 60/40"]))
    if "pl_b_assets" not in st.session_state:
        _apply("pl_b", st.session_state.get("pl_b_model", TEMPLATES["Diversified allocation"]))
    if "pl_b_template" not in st.session_state:
        st.session_state["pl_b_template"] = "Diversified allocation"
    st.markdown('<h3 class="pl-builder-title">Portfolio Builder</h3>', unsafe_allow_html=True)
    enable_b = st.checkbox("Compare Portfolio B", key="pl_compare")
    if enable_b:
        a_col, b_col = st.columns(2)
        with a_col:
            a = _builder("pl_a", "Portfolio A", manifest["assets"])
        with b_col:
            b = _builder("pl_b", "Portfolio B", manifest["assets"])
    else:
        a = _builder("pl_a", "Portfolio A", manifest["assets"])
        b = a.copy()
    period = st.date_input("Analysis period", value=(prices.index[0].date(), pd.Timestamp(latest).date()),
                           min_value=prices.index[0].date(), max_value=prices.index[-1].date())
    c1, c2, c3 = st.columns(3)
    rebalance = c1.selectbox("Rebalancing", list(REBALANCING))
    benchmark = c2.selectbox("Benchmark", [t for t in manifest["assets"] if t != "BTC"], format_func=short_asset_label)
    st.caption("Benchmark: " + short_asset_label(benchmark))
    cost = c3.number_input("Trading cost (bps of buys + sells)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    if len(period) != 2 or period[0] >= period[1]:
        st.info("Select a start and an end date with at least two trading closes.")
        return
    try:
        common, results = compare(prices, a, b, benchmark, str(period[0]), str(period[1]), rebalance, cost)
    except ValueError as exc:
        st.error("Calculation unavailable: " + str(exc))
        return
    if not enable_b:
        results.pop("Portfolio B")
    if 'BTC' in set(a)|set(b):
        st.caption('BTC: prior UTC-day fixing on ETF sessions · asynchronous reference valuation. Weekend moves enter the next session; weekend drawdowns are not measured.')
    if 'USO' in set(a)|set(b):
        st.caption('USO is a crude-oil futures fund. Roll effects, fund expenses and historical mandate changes enter observed returns; this is not WTI spot exposure.')
    outcomes = pd.DataFrame({n: metrics(r) for n, r in results.items()})
    st.markdown(heading_html('Growth of $10,000',''),unsafe_allow_html=True)
    with st.container(horizontal=True, horizontal_alignment="center"):
        with st.container(width=900, key="pl-wealth-tools"):
            subtitle, scale_control = st.columns([2.4, 1.3], gap="small", vertical_alignment="center")
            with subtitle:
                st.caption('{} – {} · same starting wealth and observation window'.format(common.index[0].date(),common.index[-1].date()))
            with scale_control:
                scale = st.radio('Wealth scale',['Linear','Logarithmic'],horizontal=True,key='pl_wealth_scale',label_visibility="collapsed")
    st.markdown(legend_html(results),unsafe_allow_html=True)
    centered_chart(paths(results,log=scale=='Logarithmic',wealth_baseline=True))
    centered_note('Dashed lines: initial $10,000 and benchmark. '+('Log scale shows proportional changes.' if scale=='Logarithmic' else 'Linear scale shows dollar changes.'))
    _table(outcomes.loc[["Cumulative return", "CAGR", "Annualised volatility", "Maximum drawdown", "Sortino ratio (0% target)", "Final wealth ($)"]])
    if outcomes.loc["CAGR"].isna().any():
        st.caption("Annualised metrics require at least 126 daily returns and 182 calendar days.")
    if st.session_state.get("pl_view") == "Risk & Factors":
        st.session_state["pl_view"] = "Risk"
    if st.session_state.get("pl_stress_mode") == "Factor shocks":
        st.session_state["pl_stress_mode"] = "Historical replay"
    view = research_navigation('pl_view')
    if view == "Overview":
        st.markdown(heading_html('Portfolio Drawdown','Drawdown from the running wealth peak · selected period only'),unsafe_allow_html=True)
        st.markdown(legend_html(results,is_drawdown=True),unsafe_allow_html=True)
        centered_chart(paths(results,is_drawdown=True,height=300))
        with st.expander("Holdings drift and rebalance trades"):
            selected = st.selectbox("Portfolio detail", list(results), key="pl_details")
            st.dataframe(asset_frame((results[selected].weights*100).round(2)), use_container_width=True)
            st.dataframe(results[selected].trades, use_container_width=True)
    if view == "Performance Attribution":
        attribution_view(common, results, rebalance, cost)
    if view == "Risk":
        risk_view(common, results, a, b, prices)
    if view == "Macro Regimes":
        regimes_view(results)
    if view == "Stress Testing":
        stress_mode=st.selectbox("Stress analysis",["Historical replay","Direct asset shocks"],key="pl_stress_mode")
        if stress_mode=="Historical replay":
            st.markdown("#### Historical stress replay")
            episode = st.selectbox("Historical episode", list(EPISODES), key="pl_episode")
            start, end = EPISODES[episode]
            st.caption("{} to {} · Isolated historical replay beginning with the chosen allocation at the episode start. "
                       "Independent of the main lookback; same rebalancing and costs.".format(start, end))
            with st.expander("Instrument availability for this episode"):
                availability=[]
                eligible=prices.loc[start:end]
                for t in dict.fromkeys(list(a)+list(b)+[benchmark]):
                    values=prices[t].dropna()
                    availability.append({"Asset":short_asset_label(t),"First observed":str(values.index[0].date()),"Complete episode":bool(len(eligible)>1 and eligible[t].notna().all())})
                st.dataframe(pd.DataFrame(availability),hide_index=True,use_container_width=True)
            try:
                window, replay, summary, asset_returns = historical_replay(prices, a, b, benchmark, episode, rebalance, cost)
                if not enable_b:
                    replay.pop("Portfolio B")
                    summary = summary.drop(columns="Portfolio B")
                st.caption("Actual eligible closes: {} to {}.".format(window.index[0].date(), window.index[-1].date()))
                diversification_view(prices,a,b,benchmark,episode,rebalance,cost,enable_b)
                _table(summary)
                with st.expander('Standalone asset returns during the episode'):
                    st.dataframe((asset_returns*100).rename('Asset episode return (%)').round(2).rename(index=short_asset_label),use_container_width=True)
            except ValueError as exc:
                st.warning(str(exc))
        if stress_mode=="Direct asset shocks":
            st.markdown("#### Hypothetical scenario — not a probability forecast")
            st.caption("Enter simultaneous percentage shocks. Immediate weighted arithmetic from target allocations, "
                       "without a dynamic simulation or trading costs.")
            shocks = {}
            for t in dict.fromkeys(list(a)+list(b)):
                shocks[t] = st.number_input(short_asset_label(t) + " shock (%)", min_value=-100.0, max_value=1000.0,
                                           value=-20.0 if t == "SPY" else 0.0, step=1.0, key="pl_shock_"+t)/100
            contributions = {}
            for name, weights in [("Portfolio A", a)] + ([("Portfolio B", b)] if enable_b else []):
                impact, parts = hypothetical_shock(weights, shocks)
                st.markdown("**{} impact: {:.2%}**".format(name, impact))
                contributions[name] = parts
            centered_chart(contribution_bars(asset_chart_frame(pd.DataFrame(contributions).fillna(0))))
            with st.expander('Exact shock contributions (pp)'):
                st.dataframe(asset_frame((pd.DataFrame(contributions).fillna(0)*100).round(2)),use_container_width=True)

    with st.expander("Methodology and data"):
        from portfolio_lab.status import data_timing_text
        st.caption(data_timing_text(latest, manifest))
        st.markdown("""
**Return definition.** Explicit Yahoo adjusted-close ratios are a split- and distribution-adjusted ETF historical-return proxy.
Backward adjustment approximates distribution reinvestment; it is not a separately audited investor total-return index.
No dividends are added a second time. Preparation checks adjustment-factor changes against reported distributions.
Bitcoin uses timestamp-aligned Coin Metrics reference-price ratios with no yield or distributions.
All instruments are valued in USD; foreign-equity holdings can retain currency exposure and are not assumed hedged.
Source-reported fund inception and first observed close are distinct. No pre-observation backfill.
Fund expenses are embedded; investor taxes, fees and execution slippage are excluded.

**Calendar and missing data.** All comparisons use identical common coverage. Whole-market holidays have no rows.
An isolated missing holding or benchmark price inside that coverage blocks calculation. Prices are never filled;
gaps exceeding seven calendar days also block calculation. Episode coverage must be complete, without proxies.

**Trading.** Initial investment is $10,000 at the first eligible close. Holdings drift with daily adjusted returns.
Monthly, quarterly or annual trades occur at the last eligible close before the next period; target weights apply to
subsequent returns. No final-close trade is made. Initial entry and final liquidation costs are excluded.
Rebalance cost equals the bps rate times actual buys plus sells, with costs deducted before allocating the remaining wealth.
Turnover is total buys plus sells divided by pre-trade wealth (twice the one-way convention).

**Statistics.** CAGR uses elapsed calendar days / 365.25. Volatility is sample daily standard deviation × √252.
Annualisation requires 126 returns and 182 calendar days. Sortino uses a 0% minimum acceptable return:
mean daily return × √252 / √mean(min(daily return, 0)²), with all evaluated returns in the denominator.
It is undefined when downside variation is zero. Drawdowns include starting wealth and refer only to the chosen window.
Risk uses target weights and empirical sample covariance of 252 or 756 common daily returns
(or fewer with explicit disclosure, minimum max(20, five times holdings)). Negative contributions are retained. Near-zero variance has no percentage decomposition.

**Stress tests.** Each historical episode starts afresh at target allocations and replays observed instrument returns.
The explicit windows do not imply universal peaks or troughs. Hypothetical shocks are user assumptions, not probabilities or forecasts.

**Research safeguards.** Attribution uses daily dollar P&L / initial wealth, costs separate, and reconciles to compounded net return.
Macro classifications are ex-post revised observation-month labels, never point-in-time trading signals. No pooled-regime annualisation.
The current surviving ETF universe is not the historical investment opportunity set. Models and correlations may change.
No duration/convexity metadata has been validated, so direct duration scenarios are deferred.

**Operations.** Interactions use cached prepared data and never trigger downloads. Allocations remain in session state.
Validated datasets ship with the application. Refresh uses the preparation and publication commands in the deployment guide.
        """)
        st.markdown('**Bitcoin calendar and execution convention.** '+BTC_DISCLOSURE)
        st.markdown('[Coin Metrics PriceUSD definition](https://github.com/coinmetrics/docs-website/blob/master/asset-metrics/market/priceusd.md) · [Community license: CC BY-NC 4.0](https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data) · [USO issuer](https://www.uscfinvestments.com/uso)')
        st.caption("Retrieved UTC: " + manifest["retrieved_utc"] + " · yfinance " + manifest["yfinance_version"])
        coverage = pd.DataFrame([{**{"Ticker": t, "Name": m["name"], "Currency": m["currency"]},
                                 "Source-reported fund inception": m.get("source_reported_fund_inception", "Not recorded"),
                                 "First observed trading date": m["first_observation"],
                                 "Latest observation": m["latest_observation"], "Quality": m["quality"],
                                 "Source": m["source"], "Adjustment": m["adjustment"]}
                                for t, m in manifest["assets"].items()])
        st.dataframe(coverage, hide_index=True, use_container_width=True)
        st.markdown("[Yahoo adjustment definition](https://in.help.yahoo.com/kb/adjusted-close-sln28256.html) · "
                    "[yfinance access disclaimer](https://ranaroussi.github.io/yfinance/)")


def render():
    with st.container(key="portfolio-lab"):
        _render()
