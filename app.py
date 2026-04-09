"""
The Economics Hub — Streamlit Dashboard
Author: Shreyas Urgunde  |  shreyasxi.github.io

Three-tab publication dashboard:
  Weekly Markets  · Macro Pulse  · India Dashboard

Charts are served from assets/ (git-tracked, deployed) with a local
fallback to output/ for development. Pipeline controls are gated
behind PIPELINE_KEY — only visible to the publisher.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

from utils.chart_loader import (
    clean_title,
    get_charts,
    get_folder_mtime,
    is_pipeline_admin,
)
from config.insights import get_insight

PROJECT_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="The Economics Hub",
    page_icon="charts/Econhub_logo.jpg",  # <-- Replaced the emoji with your file path
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* ── Google Fonts: Inter (UI) + Merriweather (editorial) ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Merriweather:ital,wght@0,700;0,900;1,400&display=swap');

    /* ── Global base ── */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* ── Reduce Streamlit's default top padding ── */
    .main .block-container {
        padding-top: 1.0rem;
        padding-bottom: 2rem;
    }
    
    /* ── Centered Section Divider ── */
    .section-divider {
        height: 2px; /* This controls the thickness */
        background-color: #003366; /* Your signature navy blue */
        width: 60%; /* 60% of the page width */
        margin: 2.0rem auto 2.0rem auto; /* The 'auto' on left/right perfectly centers it */
        border-radius: 2px; /* Gives the ends a slightly polished, rounded look */
    }

    /* ── Institutional Masthead ── */
    .insti-masthead {
        font-family: 'Inter', sans-serif;
        font-size: 2.6rem;
        font-weight: 800;
        letter-spacing: -0.04em;
        color: #0A1128; 
        text-align: center;
        text-transform: uppercase;
        margin-bottom: 0;
        line-height: 1.1;
    }
    
    .insti-tagline {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        font-weight: 600;
        color: #6B7280; 
        text-align: center;
        letter-spacing: 0.15em; 
        text-transform: uppercase;
        margin-top: 0.6rem;
        margin-bottom: 1.2rem;
    }
    
    .substack-center-container {
        text-align: center;
        margin-bottom: 1.5rem;
    }
    
    .insti-rule {
        height: 2px;
        width: 100%;
        background: linear-gradient(90deg, rgba(0,51,102,0) 0%, rgba(0,51,102,1) 15%, rgba(0,51,102,1) 85%, rgba(0,51,102,0) 100%);
        margin-top: 0.5rem;
        margin-bottom: 2.5rem;
    }
    /* ── Substack Callout Box ── */
    .substack-box {
        background-color: #FFF8F0;
        border-left: 3px solid #FF6719;
        padding: 0.35rem 0.75rem;
        margin-top: 0.5rem;
        margin-bottom: 0.8rem; /* Pushes the horizontal line down slightly */
        display: inline-block; 
        border-radius: 0 3px 3px 0; 
    }
    
    /* Force the link inside the box to be orange and underlined */
    .substack-box a {
        color: #FF6719 !important;
        font-weight: 600 !important;
        text-decoration: underline !important;
    }
    
    /* ── Section headers — Inter 800, all-caps, navy ── */
    .section-header {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        font-weight: 800;
        letter-spacing: 0.06em; /* Tighter letter spacing for better readability */
        text-transform: uppercase;
        color: #003366;
        margin-top: 3.5rem;
        margin-bottom: 0.6rem;
    }

    /* ── Status bar ── */
    .status-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.80rem;
        font-weight: 600;
        color: #003366;
        letter-spacing: 0.01em;
    }
    .status-mtime {
        font-family: 'Inter', sans-serif;
        font-size: 0.73rem;
        font-weight: 400;
        font-style: italic;
        color: #888888;
        text-align: right;
    }

    
    
    /* ── Tab bar ── */
    button[data-baseweb="tab"], 
    button[data-baseweb="tab"] p, 
    button[data-baseweb="tab"] span {
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.80rem !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
    }

    /* ── App & Sidebar Background Color ── */
    .stApp, [data-testid="stHeader"] {
        background-color: #FFFFF0;
    }

    /* ── Institutional dark sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #0D1B2E;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        padding-top: 0.5rem;
    }
    /* Force all default Streamlit text inside sidebar to white */
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown {
        color: #C8D3E0 !important;
    }
    /* Sidebar logo container */
    .sb-logo-wrap {
        text-align: center;
        padding: 1.0rem 0 0.4rem 0;
    }
    /* Publication title block */
    .sb-pub-name {
        font-family: 'Merriweather', Georgia, serif;
        font-size: 0.92rem;
        font-weight: 700;
        color: #FFFFFF;
        text-align: center;
        letter-spacing: 0.02em;
        margin: 0;
        line-height: 1.3;
    }
    .sb-pub-tagline {
        font-family: 'Inter', sans-serif;
        font-size: 0.63rem;
        font-weight: 500;
        color: #7A9BB5;
        text-align: center;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        margin: 0.15rem 0 0 0;
    }
    /* Thin rule in sidebar */
    .sb-rule {
        border: none;
        border-top: 1px solid #1E3352;
        margin: 0.65rem 0;
    }
    /* Section label (e.g. "About", "Data Sources") */
    .sb-section-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.60rem;
        font-weight: 700;
        color: #4A7FA5;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin: 0.55rem 0 0.25rem 0;
    }
    /* Body text inside sidebar */
    .sb-body {
        font-family: 'Inter', sans-serif;
        font-size: 0.71rem;
        font-weight: 400;
        color: #B0BEC5;
        line-height: 1.5;
        margin: 0;
    }
    /* Links */
    .sb-link {
        font-family: 'Inter', sans-serif;
        font-size: 0.71rem;
        font-weight: 500;
        color: #7EB6D9;
        text-decoration: none;
        display: block;
        margin-bottom: 0.25rem;
    }
    .sb-link:hover { color: #FFFFFF; text-decoration: none; }
    /* Pipeline admin label */
    .sb-admin-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.60rem;
        font-weight: 700;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: #E8A030;
        margin-bottom: 0.15rem;
    }
    /* Pipeline run buttons */
    [data-testid="stSidebar"] .stButton > button {
        background-color: #1E3352;
        color: #C8D3E0;
        border: 1px solid #2A4A70;
        border-radius: 3px;
        font-family: 'Inter', sans-serif;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: #2A4A70;
        color: #FFFFFF;
        border-color: #4A7FA5;
    }
    /* Sidebar expander header color */
    [data-testid="stSidebar"] .streamlit-expanderHeader {
        background-color: transparent;
        color: #C8D3E0 !important;
        font-size: 0.72rem;
        font-weight: 600;
    }
    /* Legacy sidebar link class — keep for backward compat */
    .sidebar-link {
        font-family: 'Inter', sans-serif;
        font-size: 0.73rem;
        font-weight: 500;
        color: #7EB6D9;
        text-decoration: none;
    }
    .sidebar-link:hover { text-decoration: underline; }

    /* ── Chart cards: white cards elevated over the grey background ── */
    .main [data-testid="stImage"] img,
    .main img {
        background: #FFFFFF;
        border-radius: 3px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
    }

    /* ── India notice ── */
    .india-notice {
        background-color: #FFF8F0;
        border-left: 2px solid #CC6600;
        padding: 0.45rem 0.80rem;
        font-family: 'Inter', sans-serif;
        font-size: 0.76rem;
        font-weight: 400;
        font-style: italic;
        color: #666666;
        margin-bottom: 1rem;
    }

    /* ── Image captions ── */
    [data-testid="caption"] {
        font-family: 'Inter', sans-serif;
        font-size: 0.68rem;
        font-weight: 500;
        color: #999999;
        text-align: center;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    # ── Logo ────────────────────────────────────────────────────────────────────
    logo_path = PROJECT_ROOT / "charts" / "Econhub_logo.jpg"
    if logo_path.exists():
        st.markdown('<div class="sb-logo-wrap">', unsafe_allow_html=True)
        st.image(str(logo_path), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Publication name ────────────────────────────────────────────────────────
    st.markdown(
        '<p class="sb-pub-name">The Economics Hub</p>'
        '<p class="sb-pub-tagline">Global Macro &amp; Cross-Asset</p>',
        unsafe_allow_html=True,
    )

    # ── Divider ─────────────────────────────────────────────────────────────────
    st.markdown('<hr class="sb-rule">', unsafe_allow_html=True)

    # ── About ───────────────────────────────────────────────────────────────────
    st.markdown('<p class="sb-section-label">About</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sb-body">Independent macro research by <strong style="color:#FFFFFF;">Shreyas Urgunde</strong>. '
        'Charts published weekly — covering equities, rates, FX, commodities, and India.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<a class="sb-link" href="https://economicshub.substack.com/" target="_blank">'
        '&#x2709; Substack Newsletter</a>'
        '<a class="sb-link" href="https://shreyasxi.github.io/" target="_blank">'
        '&#x1F310; shreyasxi.github.io</a>',
        unsafe_allow_html=True,
    )

    # ── Data sources ────────────────────────────────────────────────────────────
    st.markdown('<hr class="sb-rule">', unsafe_allow_html=True)
    st.markdown('<p class="sb-section-label">Data Sources</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sb-body">'
        'Markets: Yahoo Finance<br>'
        'Macro: FRED · St. Louis Fed<br>'
        'International: IMF · OECD · DBnomics<br>'
        'India: RBI · MoSPI · NSDL · CAG<br>'
        'RBI text: Anthropic Claude (LLM scoring)'
        '</p>',
        unsafe_allow_html=True,
    )

    # ── License ─────────────────────────────────────────────────────────────────
    st.markdown('<hr class="sb-rule">', unsafe_allow_html=True)
    st.markdown(
        '<p class="sb-body" style="color:#4A6680;">Licensed under CC BY-NC 4.0 &nbsp;·&nbsp; '
        'Not investment advice</p>',
        unsafe_allow_html=True,
    )

    # ── Pipeline control — only visible when PIPELINE_KEY secret is set ─────────
    if is_pipeline_admin():
        st.markdown('<hr class="sb-rule">', unsafe_allow_html=True)
        st.markdown('<p class="sb-admin-label">Pipeline Control</p>', unsafe_allow_html=True)
        st.markdown('<p class="sb-body" style="color:#7A9BB5;margin-bottom:0.4rem;">Publisher access only.</p>',
                    unsafe_allow_html=True)

        with st.expander("Run Generators", expanded=False):
            _GENERATORS = {
                "Weekly Markets":  ("generate_weekly.py",       True),
                "Macro Pulse":     ("generate_macro.py",        True),
                "India Dashboard": ("generate_india.py",        False),
                "RBI Sentinel":    ("generate_rbi_sentinel.py", False),
            }
            for label, (script, has_mode) in _GENERATORS.items():
                if st.button(f"▶  {label}", key=f"btn_{script}", use_container_width=True):
                    cmd = [sys.executable, script]
                    if has_mode:
                        cmd += ["--mode", "dashboard"]
                    with st.spinner(f"Running {label} generator…"):
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            cwd=str(PROJECT_ROOT),
                        )
                    if result.returncode == 0:
                        st.success(f"{label} charts generated.")
                        st.rerun()
                    else:
                        st.error(
                            f"Generator failed (exit {result.returncode}):\n\n"
                            + result.stderr[-600:]
                        )

# ---------------------------------------------------------------------------
# Masthead
# ---------------------------------------------------------------------------

st.markdown(
    '<h1 class="insti-masthead">Global Macro & Cross-Asset Monitor</h1>'
    '<p class="insti-tagline">Maintained by Shreyas Urgunde</p>'
    '<div class="substack-center-container">'
        '<div class="substack-box">'
            '<a href="https://economicshub.substack.com/" target="_blank">'
            'Subscribe on Substack →</a>'
        '</div>'
    '</div>'
    '<div class="insti-rule"></div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_weekly, tab_macro, tab_india, tab_rbi = st.tabs(
    ["Weekly Markets", "Macro Pulse", "India Dashboard", "RBI Sentinel"]
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _render_status_bar(date_label: str | None, subdir: str) -> None:
    mtime = get_folder_mtime(subdir)
    col_label, col_mtime = st.columns([3, 1])
    with col_label:
        if date_label:
            st.markdown(
                f'<p class="status-label">{date_label}</p>',
                unsafe_allow_html=True,
            )
    with col_mtime:
        if mtime:
            st.markdown(
                f'<p class="status-mtime">Last updated: {mtime.strftime("%Y-%m-%d %H:%M")}</p>',
                unsafe_allow_html=True,
            )


def _render_grid(charts: list[Path], cols: int = 2) -> None:
    columns = st.columns(cols)
    for i, chart_path in enumerate(charts):
        with columns[i % cols]:
            st.image(
                str(chart_path),
                caption=clean_title(chart_path.name),
                use_container_width=True,
            )
            insight = get_insight(chart_path.name)
            if insight:
                with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                    st.markdown(insight)
    
def _section(title: str) -> None:
    st.markdown(
        f'<div class="section-divider"></div>'
        f'<p class="section-header">{title}</p>',
        unsafe_allow_html=True,
    )

def _render_summary(chart_path: Path) -> None:
    """Summary table constrained to 80% of page width."""
    _, col_img, _ = st.columns([1, 4, 1])
    with col_img:
        st.image(str(chart_path), use_container_width=True)


def _pop_summary(charts: list[Path], keywords: list[str]) -> tuple[Path | None, list[Path]]:
    for kw in keywords:
        for c in charts:
            if kw in c.name:
                remaining = [x for x in charts if x != c]
                return c, remaining
    return None, charts


def _group(charts: list[Path], keyword: str) -> tuple[list[Path], list[Path]]:
    matched = [c for c in charts if keyword in c.name]
    rest = [c for c in charts if keyword not in c.name]
    return matched, rest


# ── Weekly Markets tab ─────────────────────────────────────────────────────

with tab_weekly:
    charts, date_label = get_charts("weekly")

    if not charts:
        st.warning(
            "No weekly charts found. Run **generate_weekly.py** locally "
            "or trigger the Weekly Markets workflow on GitHub Actions."
        )
    else:
        _render_status_bar(f"Week of {date_label}", "weekly")

        summary, charts = _pop_summary(charts, ["summary_table", "00_"])
        if summary:
            _render_summary(summary)

        # 1. Equities
        equities_kws = ["equities"]
        equities = [c for c in charts if any(k in c.name for k in equities_kws)]
        charts = [c for c in charts if c not in equities]
        if equities:
            _section("Equities")
            _render_grid(equities)

        # 2. Fixed Income & Credit
        rates_kws = ["yield", "credit_spreads", "bond_etf"]
        rates = [c for c in charts if any(k in c.name for k in rates_kws)]
        charts = [c for c in charts if c not in rates]
        if rates:
            _section("Fixed Income & Credit")
            _render_grid(rates)
            
        # 3. Commodities
        commo_kws = ["commodities", "brent", "wti", "agri", "oil", "gold", "copper"]
        commo = [c for c in charts if any(k in c.name for k in commo_kws) and "btc" not in c.name]
        charts = [c for c in charts if c not in commo]
        if commo:
            _section("Commodities")
            _render_grid(commo)

        # 4. Inflation Signals
        inflation_kws = ["breakeven", "real_yield"]
        inflation_sig = [c for c in charts if any(k in c.name for k in inflation_kws)]
        charts = [c for c in charts if c not in inflation_sig]
        if inflation_sig:
            _section("Inflation Signals")
            _render_grid(inflation_sig)

        # 5. Foreign Exchange (excluding EM FX)
        fx = [c for c in charts if "fx" in c.name and "em_fx" not in c.name]
        charts = [c for c in charts if c not in fx]
        if fx:
            _section("Foreign Exchange")
            _render_grid(fx)

        # 6. Volatility & Sentiment
        vol_kws = ["vix", "move", "sector_rotation", "india_vix"]
        volatility = [c for c in charts if any(k in c.name for k in vol_kws)]
        charts = [c for c in charts if c not in volatility]
        if volatility:
            _section("Volatility & Sentiment")
            _render_grid(volatility)

        # 7. Cross-Asset Risk & Breadth
        risk_kws = ["spy_tlt", "risk_appetite", "breadth", "gold_spx", "copper_gold"]
        risk = [c for c in charts if any(k in c.name for k in risk_kws)]
        charts = [c for c in charts if c not in risk]
        if risk:
            _section("Cross-Asset Risk & Breadth")
            _render_grid(risk)


        # 8. Emerging Markets
        em_kws = ["em_fx", "em_equity", "india_vs_em", "nifty", "stress_monitor"]
        em = [c for c in charts if any(k in c.name for k in em_kws)]
        charts = [c for c in charts if c not in em]
        if em:
            _section("Emerging Markets")
            _render_grid(em)

        # 9. Crypto Assets
        crypto_kws = ["eth_btc", "btc_gold", "btc_global", "stablecoin"]
        crypto = [c for c in charts if any(k in c.name for k in crypto_kws)]
        charts = [c for c in charts if c not in crypto]
        if crypto:
            _section("Crypto Assets")
            _render_grid(crypto)

        # Catch-all
        if charts:
            _section("Other")
            _render_grid(charts)


# ── Macro Pulse tab ────────────────────────────────────────────────────────

with tab_macro:
    charts, date_label = get_charts("macro")

    if not charts:
        st.warning(
            "No macro charts found. Run **generate_macro.py** locally "
            "or trigger the Macro Pulse workflow on GitHub Actions."
        )
    else:
        _render_status_bar(date_label, "macro")

        summary, charts = _pop_summary(charts, ["macro_table", "00_"])
        if summary:
            _render_summary(summary)

        # Inflation
        inflation_charts, charts = _group(charts, "inflation")
        if inflation_charts:
            _section("Inflation")
            _render_grid(inflation_charts)

        # Labour Market
        labour_charts = [c for c in charts if any(k in c.name for k in ["labour", "labor", "sahm", "payroll"])]
        charts = [c for c in charts if not any(k in c.name for k in ["labour", "labor", "sahm", "payroll"])]
        if labour_charts:
            _section("Labour Market")
            _render_grid(labour_charts)

        # Financial Conditions
        financial_charts = [c for c in charts if any(k in c.name for k in ["financial", "credit", "money", "balance_sheet", "yield_spread"])]
        charts = [c for c in charts if not any(k in c.name for k in ["financial", "credit", "money", "balance_sheet", "yield_spread"])]
        if financial_charts:
            _section("Financial Conditions & Credit")
            _render_grid(financial_charts)

        # Emerging Markets
        em_charts, charts = _group(charts, "em")
        if em_charts:
            _section("Emerging Markets")
            _render_grid(em_charts)

        # Housing & Consumer
        housing_charts = [c for c in charts if any(k in c.name for k in ["housing", "mortgage", "consumer", "sentiment"])]
        charts = [c for c in charts if not any(k in c.name for k in ["housing", "mortgage", "consumer", "sentiment"])]
        if housing_charts:
            _section("Housing & Consumer")
            _render_grid(housing_charts)

        # Catch-all
        if charts:
            _section("Other")
            _render_grid(charts)


# ── India Dashboard tab ────────────────────────────────────────────────────

with tab_india:
    charts, date_label = get_charts("india")

    if not charts:
        st.warning(
            "No India charts found. Update **data/india_manual.csv** and "
            "**data/cag_monthly_accounts.xlsx**, then run **generate_india.py** "
            "or trigger the India Dashboard workflow on GitHub Actions."
        )
    else:
        _render_status_bar(date_label, "india")

        st.markdown(
            '<div class="india-notice">'
            "India data is manually curated. Charts reflect the latest data "
            "update committed to the repository by Shreyas Urgunde."
            "</div>",
            unsafe_allow_html=True,
        )

        summary, charts = _pop_summary(charts, ["india_table", "05_india"])
        if summary:
            _render_summary(summary)

        # 1. High-Frequency Growth Indicators
        growth_kws = ["pmi", "credit"]
        growth = [c for c in charts if any(k in c.name for k in growth_kws)]
        charts = [c for c in charts if c not in growth]
        if growth:
            _section("Growth Indicators")
            _render_grid(growth)

        # 2. Inflation Dynamics
        inflation_kws = ["inflation", "cpi", "wpi"]
        inflation = [c for c in charts if any(k in c.name for k in inflation_kws)]
        charts = [c for c in charts if c not in inflation]
        if inflation:
            _section("Inflation Dynamics")
            _render_grid(inflation)

        # 3. Fiscal Policy & Public Finances
        fiscal_kws = ["fiscal", "deficit", "capex", "expenditure", "gst", "tax", "revenue", "consolidation"]
        fiscal = [c for c in charts if any(k in c.name for k in fiscal_kws)]
        charts = [c for c in charts if c not in fiscal]
        if fiscal:
            _section("Fiscal Policy & Public Finances")
            _render_grid(fiscal)

        # 4. Capital Flows
        flows_kws = ["flows", "fii", "fpi", "portfolio"]
        flows = [c for c in charts if any(k in c.name for k in flows_kws)]
        charts = [c for c in charts if c not in flows]
        if flows:
            _section("Capital Flows")
            _render_grid(flows)

        # Catch-all
        if charts:
            _section("Other")
            _render_grid(charts)

        if charts:
            _render_grid(charts, cols=2)


# ── RBI Sentinel tab ────────────────────────────────────────────────────────

with tab_rbi:
    charts, date_label = get_charts("rbi_sentinel")

    if not charts:
        st.warning(
            "No RBI Sentinel charts found. Run **generate_rbi_sentinel.py** locally "
            "or trigger the RBI Sentinel workflow on GitHub Actions."
        )
    else:
        _render_status_bar(date_label, "rbi_sentinel")

        # Disclaimer
        st.markdown(
            '<div class="india-notice">'
            "RBI Sentinel scores are generated by a hybrid lexicon + Claude AI model. "
            "All scores are quantitative estimates — not investment advice. "
            "Scores reflect language analysis only; always read the primary MPC documents."
            "</div>",
            unsafe_allow_html=True,
        )

        # Hero: Stance Meter (full width)
        stance, charts = _pop_summary(charts, ["01_rbi_stance_meter"])
        if stance:
            _section("Current MPC Stance")
            _, col_mid, _ = st.columns([1, 2, 1])
            with col_mid:
                st.image(str(stance), use_container_width=True)
                insight = get_insight(stance.name)
                if insight:
                    with st.expander("ℹ️ How to read the Stance Meter"):
                        st.markdown(insight)

        # Sentiment Over Time
        trajectory, charts = _pop_summary(charts, ["02_rbi_sentiment_trajectory"])
        if trajectory:
            _section("Sentiment Over Time")
            st.image(str(trajectory), use_container_width=True)
            insight = get_insight(trajectory.name)
            if insight:
                with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                    st.markdown(insight)

        # Meeting Analysis: doc comparison + radar side by side
        _section("Meeting Analysis")
        comparison, charts = _pop_summary(charts, ["03_rbi_resolution_vs_minutes"])
        radar, charts = _pop_summary(charts, ["04_rbi_subdimension_radar"])

        col_left, col_right = st.columns(2)
        if comparison:
            with col_left:
                st.image(str(comparison), use_container_width=True)
                insight = get_insight(comparison.name)
                if insight:
                    with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                        st.markdown(insight)
        if radar:
            with col_right:
                st.image(str(radar), use_container_width=True)
                insight = get_insight(radar.name)
                if insight:
                    with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                        st.markdown(insight)

        # Repo Rate vs Sentiment
        rate_chart, charts = _pop_summary(charts, ["05_rbi_rate_and_sentiment"])
        if rate_chart:
            _section("Repo Rate vs. Sentiment")
            st.image(str(rate_chart), use_container_width=True)

        # Meeting Timeline
        timeline, charts = _pop_summary(charts, ["06_rbi_meeting_timeline"])
        if timeline:
            _section("Meeting History")
            st.image(str(timeline), use_container_width=True)

        # Catch-all
        if charts:
            _section("Other")
            _render_grid(charts)
