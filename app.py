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

from rbi_sentinel.db.manager import get_latest_composite

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
    /* ── Google Fonts: Inter (UI) + Merriweather (body) + Playfair Display (Masthead) ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Merriweather:ital,wght@0,700;0,900;1,400&family=Playfair+Display:wght@700;900&display=swap');

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
    /* ── Substack Callout Box (Institutional Upgrade) ── */
    .substack-box {
        background-color: #F4F6F9; /* Ice-grey to match the RBI/India abstract */
        border-left: 3px solid #003366; /* Signature Navy border */
        padding: 0.40rem 0.85rem;
        margin-top: 0.5rem;
        margin-bottom: 0.8rem;
        display: inline-block; 
        border-radius: 0 3px 3px 0; 
        transition: all 0.2s ease;
    }
    
    .substack-box a {
        color: #003366 !important; 
        font-family: 'Inter', sans-serif;
        font-weight: 700 !important;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        text-decoration: underline !important; /* Forces the underline to always show */
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

    /* ── App Background Color (The Seamless Canvas) ── */
    .stApp, [data-testid="stHeader"] {
        background-color: #FFFFF0; /* Keeps the main chart area crisp cream */
    }

    /* ── Editorial Print Sidebar (FT Salmon Pink) ── */
    [data-testid="stSidebar"] {
        background-color: #FFFFF0; /* BANGER: The subtle tinted pink! */
        border-right: 2px solid #111111; /* A complementary darker salmon border */
    }
    
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        padding-top: 1.5rem;
    }
    
    /* Force default Streamlit text to deep charcoal, not harsh black */
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown {
        color: #222222 !important;
    }
    
    /* 1. Header Block & Logo */
    .sb-logo-wrap {
        text-align: center;
        padding: 0 1rem 1rem 1rem;
    }
    .sb-logo-wrap img {
        mix-blend-mode: multiply; /* MAGICAL: Dissolves the white background of the image! */
        width: 65%; /* Shrinks it to a tasteful, premium size */
        margin: 0 auto;
    }
    
  
    /* ── The High-Finance Masthead Title (Sidebar) ── */
    .sb-pub-name {
        font-family: 'Playfair Display', Georgia, serif; 
        font-size: 1.65rem !important; /* Scaled up for dominance */
        font-weight: 900 !important;
        color: #0A1128; /* Deep navy/black to match the main header */
        text-align: center;
        letter-spacing: -0.04em; /* Aggressively tight tracking, just like the main header */
        text-transform: uppercase;
        margin: 0.5rem 0 0 0;
        line-height: 1.1;
    }
    .sb-pub-tagline {
        font-family: 'Inter', sans-serif;
        font-size: 0.60rem;
        font-weight: 700;
        color: #666666;
        text-align: center;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        margin: 0.3rem 0 1rem 0;
    }

    /* Rules */
    .sb-rule-thick {
        border: none;
        border-top: 2px solid #111111;
        margin: 1.2rem 0;
    }
    .sb-rule-thin {
        border: none;
        border-top: 1px solid #E2DFD8;
        margin: 1rem 0;
    }

    /* 2. The Byline Block */
    .sb-byline-label {
        font-family: 'Merriweather', Georgia, serif;
        font-size: 0.85rem;
        font-style: italic;
        color: #444444;
        margin: 0 0 0.1rem 0;
        text-align: center;
    }
    .sb-byline-name {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        font-weight: 800;
        color: #111111;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 0 0 0.5rem 0;
        text-align: center;
    }
    .sb-coverage {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        color: #666666;
        text-align: center;
        line-height: 1.4;
        margin-bottom: 1.5rem;
    }

    /* 3. Action Buttons (Editorial Style) */
    .sb-btn {
        display: block;
        width: 100%;
        text-align: center;
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #111111 !important;
        background-color: transparent;
        border: 1px solid #111111;
        padding: 0.6rem 0;
        margin-bottom: 0.5rem;
        text-decoration: none !important;
        transition: all 0.2s ease;
    }
    .sb-btn:hover {
        background-color: #111111;
        color: #FFFFF0 !important;
    }

    /* 4. Data Matrix (Institutional Upgrade) */
    .sb-section-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        font-weight: 800;
        color: #111111;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        margin: 0 0 0.8rem 0;
        border-bottom: 2px solid #111111; /* BANGER: A heavy structural underline */
        padding-bottom: 0.4rem;
    }
    .sb-data-row {
        display: flex;
        justify-content: space-between;
        align-items: center; /* Perfectly centers the text vertically */
        border-bottom: 1px solid #E2DFD8; /* Swapped dotted for a clean, elegant solid line */
        padding: 0.45rem 0;
        margin: 0;
    }
    /* Targets the last row to remove the bottom border so it looks like a clean table */
    .sb-data-row:last-of-type {
        border-bottom: none; 
    }
    .sb-data-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem; /* INCREASED from 0.55rem */
        font-weight: 700;
        color: #666666;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .sb-data-val {
        font-family: 'Merriweather', Georgia, serif;
        font-size: 0.75rem; /* INCREASED from 0.65rem */
        font-style: italic; 
        color: #111111;
        text-align: right;
    }
    
    /* Pipeline Buttons (Light mode adjustments) */
    [data-testid="stSidebar"] .stButton > button {
        background-color: #F5F3EC;
        color: #111111;
        border: 1px solid #D1CDC4;
        border-radius: 0px;
        font-family: 'Inter', sans-serif;
        font-size: 0.70rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        border-color: #111111;
    }

    /* ── Chart cards: white cards elevated over the grey background ── */
    .main [data-testid="stImage"] img,
    .main img {
        background: #FFFFFF;
        border-radius: 3px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
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
    # ── 1. Logo & Masthead ─────────────────────────────────────────────────────
    # (Once you make your logo transparent, save it as a PNG and update the filename here if needed!)
    logo_path = PROJECT_ROOT / "charts" / "Econhub_logo.jpg" 
    if logo_path.exists():
        st.markdown('<div class="sb-logo-wrap">', unsafe_allow_html=True)
        st.image(str(logo_path), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # REMOVED: The Global Macro tagline is gone.
    st.markdown(
        '<p class="sb-pub-name">The Economics Hub</p>'
        '<hr class="sb-rule-thick">',
        unsafe_allow_html=True,
    )

    # ── 2. The Byline ──────────────────────────────────────────────────────────
    st.markdown(
        '<p class="sb-byline-label">Research by</p>'
        '<p class="sb-byline-name">Shreyas Urgunde</p>'
        '<p class="sb-coverage">Weekly coverage of global equities, rates, FX, commodities, and the Indian economy.</p>',
        unsafe_allow_html=True,
    )

    # ── 3. Premium Action Buttons ──────────────────────────────────────────────
    st.markdown(
        '<a class="sb-btn" href="https://economicshub.substack.com/" target="_blank">Subscribe on Substack ↗</a>'
        '<a class="sb-btn" href="https://shreyasxi.github.io/" target="_blank">Academic Website ↗</a>'
        '<hr class="sb-rule-thick">', # CHANGED: Using a thick rule here to firmly separate sections
        unsafe_allow_html=True,
    )

    # ── 4. The Data Matrix ─────────────────────────────────────────────────────
    st.markdown('<p class="sb-section-label">Data Architecture</p>', unsafe_allow_html=True)
    
    st.markdown(
        '<div class="sb-data-row"><span class="sb-data-label">Markets</span><span class="sb-data-val">Yahoo Finance</span></div>'
        '<div class="sb-data-row"><span class="sb-data-label">Global Macro</span><span class="sb-data-val">FRED &middot; OECD</span></div>'
        '<div class="sb-data-row"><span class="sb-data-label">India Macro</span><span class="sb-data-val">RBI &middot; MoSPI</span></div>'
        '<div class="sb-data-row"><span class="sb-data-label">NLP Engine</span><span class="sb-data-val">Anthropic Claude</span></div>',
        unsafe_allow_html=True
    )

    # ── License ─────────────────────────────────────────────────────────────────
    st.markdown('<hr class="sb-rule-thin">', unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:Inter; font-size:0.55rem; color:#888888; text-align:center; text-transform:uppercase; letter-spacing:0.05em;">'
        'CC BY-NC 4.0 &middot; Not Investment Advice</p>',
        unsafe_allow_html=True,
    )

    # ── Pipeline control ────────────────────────────────────────────────────────
    if is_pipeline_admin():
        st.markdown('<hr class="sb-rule-thick">', unsafe_allow_html=True)
        st.markdown('<p class="sb-section-label" style="color:#CC0000;">Pipeline Control</p>', unsafe_allow_html=True)

        with st.expander("Run Generators", expanded=False):
            _GENERATORS = {
                "Weekly Markets":  ("generate_weekly.py",       True),
                "Macro Pulse":     ("generate_macro.py",        True),
                "India Dashboard": ("generate_india.py",        False),
                "RBI Sentinel":    ("generate_rbi_sentinel.py", False),
            }
            for label, (script, has_mode) in _GENERATORS.items():
                if st.button(f"▶ {label}", key=f"btn_{script}", use_container_width=True):
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
            'Subscribe on Substack ↗</a>'
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

        # The Institutional Callout Box for India Data
        st.markdown(
            '<div style="background-color: #F4F6F9; border-left: 3px solid #003366; padding: 0.8rem 1.2rem; margin-bottom: 1.0rem; border-radius: 0 4px 4px 0;">'
            '<p style="font-family: \'Merriweather\', Georgia, serif; font-size: 0.90rem; font-style: italic; color: #111111; line-height: 1.6; margin: 0;">'
            '<strong style="font-family: \'Inter\', sans-serif; font-style: normal; font-size: 0.80rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #111111; margin-right: 0.3rem;">Data Curation</strong> '
            "This dashboard relies on manually curated macroeconomic datasets from the RBI, MoSPI, and CAG. Charts strictly reflect the most recent data commits pushed to the repository."
            '</p>'
            '</div>',
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

        # ── Methodology Abstract & Deep Dive ──────────────────────────────────────
        
       # 1. The High-End Editorial Abstract (Institutional Callout Box)
        st.markdown(
            '<div style="background-color: #F4F6F9; border-left: 3px solid #003366; padding: 0.8rem 1.2rem; margin-bottom: 1.0rem; border-radius: 0 4px 4px 0;">'
            '<p style="font-family: \'Merriweather\', Georgia, serif; font-size: 0.90rem; font-style: italic; color: #111111; line-height: 1.6; margin: 0;">'
            '<strong style="font-family: \'Inter\', sans-serif; font-style: normal; font-size: 0.80rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #111111; margin-right: 0.3rem;">The RBI Sentinel</strong> '
            "quantifies shifts in India's monetary policy by parsing all three classes of official MPC communication — the Monetary Policy Resolution, the MPC Meeting Minutes, and the Governor's Statement — through a domain-specific hybrid text-mining model. "
            "It fuses a curated central-bank lexicon with a large language model to score each document on a bounded hawkish/dovish scale, producing both a per-document signal and a composite meeting score. All outputs are quantitative estimates intended for research purposes."
            '</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        # 2. The Technical Expander (The Methodology "Button")
        with st.expander("⚙️ Scoring Methodology & Pipeline Architecture", expanded=False):
            st.markdown(
                "### Scoring Methodology\n\n"
                "**Corpus**\n\n"
                "The engine processes three official documents per Monetary Policy Committee (MPC) cycle: "
                "the *Monetary Policy Resolution* (published on the rate-decision date), "
                "the *MPC Meeting Minutes* (published approximately 14 days post-decision), "
                "and the *Governor's Statement* (published on the rate-decision date alongside the Resolution). "
                "This tripartite corpus captures the full communication spectrum: the formal committee decision, "
                "the deliberative record of individual member views and dissents, and the Governor's personal "
                "forward guidance — three analytically distinct signals that frequently diverge.\n\n"
                "**Why Standard Lexicons Are Insufficient**\n\n"
                "Standard financial word-lists, including the widely cited Loughran-McDonald dictionary "
                "(see [Loughran & McDonald, 2011](https://doi.org/10.1111/j.1540-6261.2010.01625.x)), "
                "perform well on corporate filings but systematically fail on central bank transcripts. "
                "Policymakers rely on deliberate linguistic hedging: a phrase such as "
                "*\"remaining vigilant on inflation\"* conveys clear hawkish intent without a single term "
                "appearing in any standard financial dictionary. This problem is well-documented in the "
                "automated analysis of FOMC statements "
                "(see [Lucca & Trebbi, 2009](https://www.nber.org/papers/w15367)), where context-sensitivity "
                "and negation handling are shown to be prerequisites, not refinements.\n\n"
                "**Two-Stage Hybrid Pipeline**\n\n"
                "*Stage 1 — Domain Lexicon:* A bespoke lexicon of 30+ hawkish and 30+ dovish phrases, "
                "each weighted to reflect diagnostic value in RBI communications. A 5-token negation window "
                "reverses phrase polarity when a negation operator precedes a scored term (e.g., "
                "*\"not concerned about inflation\"* scores dovish, not hawkish). The raw count score is "
                "normalized via tanh(score / √word\\_count × 3) to correct for document length variance. "
                "Weight in fusion: **25%**.\n\n"
                "*Stage 2 — LLM Semantic Parsing:* Each document is submitted to a large language model "
                "under a structured prompt. Large language models substantially outperform lexicon-based "
                "methods on nuanced, context-dependent financial text "
                "(see [López-Lira & Tang, 2023](https://doi.org/10.2139/ssrn.4412788)). "
                "The prompt returns a validated JSON payload containing six sub-dimension scores "
                "(inflation stance, growth stance, liquidity stance, rate guidance, FX/external stance, "
                "overall), a confidence estimate, a ranked list of pivotal phrases, and a two-paragraph "
                "narrative summary, drawing on domain-adapted NLP methods for structured financial output "
                "(see [Araci, 2019](https://arxiv.org/abs/1908.10063)). "
                "When model confidence falls below 0.55, a higher-capacity model is invoked as a fallback. "
                "Weight in fusion: **75%**.\n\n"
                "*Conflict Detection:* When |lexicon score − LLM score| > 0.40, a conflict flag is raised "
                "and confidence is capped at 0.45, signalling that the document warrants manual review.\n\n"
                "**Composite Meeting Score**\n\n"
                "Individual document scores are aggregated into a per-meeting composite using a fixed "
                "weighting scheme reflecting each document's informational hierarchy:\n\n"
                "| Document | Weight | Rationale |\n"
                "|---|---|---|\n"
                "| MPC Minutes | 50% | Captures individual member deliberation and dissent votes |\n"
                "| Monetary Policy Resolution | 35% | The formal committee decision statement |\n"
                "| Governor's Statement | 15% | Governor's personal forward guidance overlay |\n\n"
                "All scores are expressed on a bounded [−1.0, +1.0] scale. "
                "−1.0 denotes maximum dovishness; +1.0 denotes maximum hawkishness.\n\n"
                "---\n\n"
                "### Pipeline Architecture\n"
            )
            st.markdown("""
<style>
/* 1. Aligned to Inter font */
.arch-wrap { font-family: 'Inter', sans-serif; font-size: 13px; color: #111; padding: 8px 0; }

/* 2. Added subtle elevation shadow and rounded the container */
.arch-stage { display: flex; align-items: stretch; margin-bottom: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.04); border-radius: 4px; }

.arch-label { background: #003366; color: #fff; font-weight: 700; font-size: 11px;
              writing-mode: vertical-rl; text-orientation: mixed; transform: rotate(180deg);
              min-width: 32px; display: flex; align-items: center; justify-content: center;
              border-radius: 4px 0 0 4px; padding: 4px 2px; letter-spacing: 0.5px; }

/* 3. Softened the structural border to match your custom grey */
.arch-content { background: #F4F6F9; border: 1px solid #E2DFD8; border-left: none;
                border-radius: 0 4px 4px 0; flex: 1; display: flex;
                align-items: center; gap: 6px; padding: 10px 14px; flex-wrap: wrap; }

.arch-box { background: #D6E4F0; border: 1px solid #003366; border-radius: 5px;
            padding: 6px 12px; text-align: center; min-width: 130px; }
.arch-box b { display: block; font-size: 12px; color: #111; }
.arch-box span { font-size: 10.5px; color: #444; }

.arch-box-db { background: #A8C8E8; border: 1px solid #003366; border-radius: 5px;
               padding: 6px 12px; text-align: center; min-width: 130px; }
.arch-box-db b { display: block; font-size: 12px; color: #111; }
.arch-box-db span { font-size: 10.5px; color: #333; }

.arch-box-dark { background: #003366; border: 1px solid #003366; border-radius: 5px;
                 padding: 6px 12px; text-align: center; min-width: 130px; }
.arch-box-dark b { display: block; font-size: 12px; color: #fff; }
.arch-box-dark span { font-size: 10.5px; color: #cce; }

/* Softened the flow arrows so they don't compete with the data */
.arch-arrow { font-size: 18px; color: #888888; font-weight: 300; flex-shrink: 0; padding: 0 2px; }
.arch-branch { display: flex; flex-direction: column; gap: 6px; }
.arch-down { text-align: center; font-size: 20px; color: #888888; font-weight: 300; line-height: 1; margin: 4px 0; }
</style>
<div class="arch-wrap">

  <div class="arch-stage">
    <div class="arch-label">Fetch</div>
    <div class="arch-content">
      <div class="arch-box"><b>rbi.org.in</b><span>MPC Documents Catalogue</span></div>
      <div class="arch-arrow">→</div>
      <div class="arch-box"><b>Master Fetcher</b><span>HTTP + ASP.NET Pagination</span></div>
      <div class="arch-arrow">→</div>
      <div class="arch-box"><b>File Cache</b><span>HTML / PDF</span></div>
    </div>
  </div>

  <div class="arch-down">↓</div>

  <div class="arch-stage">
    <div class="arch-label">Extract</div>
    <div class="arch-content">
      <div class="arch-box"><b>Document Extractor</b><span>HTML (CSS selectors) + PDF (pdfplumber)</span></div>
      <div class="arch-arrow">→</div>
      <div class="arch-box"><b>Text Normalizer</b><span>Dedup + sentence splitting</span></div>
    </div>
  </div>

  <div class="arch-down">↓</div>

  <div class="arch-stage">
    <div class="arch-label">Score</div>
    <div class="arch-content">
      <div class="arch-branch">
        <div class="arch-box"><b>Domain Lexicon — 25%</b><span>30+ phrases · 5-token negation window</span></div>
        <div class="arch-box"><b>LLM Semantic Parser — 75%</b><span>Claude API · 6 sub-dimensions · structured JSON</span></div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-box"><b>Score Fusion</b><span>0.25×lex + 0.75×llm · conflict flag: |Δ| &gt; 0.40</span></div>
    </div>
  </div>

  <div class="arch-down">↓</div>

  <div class="arch-stage">
    <div class="arch-label">Store</div>
    <div class="arch-content">
      <div class="arch-box-db"><b>sentiment_scores</b><span>SQLite — raw per-doc scores</span></div>
      <div class="arch-arrow">→</div>
      <div class="arch-box"><b>Composite Engine</b><span>Minutes 50% · Resolution 35% · Governor 15%</span></div>
      <div class="arch-arrow">→</div>
      <div class="arch-box-db"><b>meeting_composites</b><span>SQLite — per-meeting aggregates</span></div>
    </div>
  </div>

  <div class="arch-down">↓</div>

  <div class="arch-stage">
    <div class="arch-label">Visualise</div>
    <div class="arch-content">
      <div class="arch-box"><b>Chart Generator</b><span>7 EconStyle matplotlib charts</span></div>
      <div class="arch-arrow">→</div>
      <div class="arch-box-dark"><b>Streamlit Dashboard</b><span>The RBI Sentinel Tab</span></div>
    </div>
  </div>

</div>
""", unsafe_allow_html=True)

        # ── Hero: Stance Meter & AI Briefing (Side-by-Side) ──
        stance, charts = _pop_summary(charts, ["01_rbi_stance_meter"])
        if stance:
            _section("Current MPC Stance & Executive Summary")
            
            # Fetch the latest qualitative narrative from the database
            latest_comp = get_latest_composite()
            ai_summary = latest_comp.get("composite_narrative") if latest_comp else None
            
            # If no summary exists, default to a clean placeholder
            if not ai_summary:
                ai_summary = "Awaiting narrative generation for the current policy cycle."

            # Split the layout: 55% for the chart, 45% for the text widget
            col_chart, col_text = st.columns([1.2, 1])
            
            with col_chart:
                st.image(str(stance), use_container_width=True)
                insight = get_insight(stance.name)
                if insight:
                    with st.expander("ℹ️ How to read the Stance Meter"):
                        st.markdown(insight)
                        
            with col_text:
                # ── Format the pure AI Summary for HTML ──
                clean_summary = ai_summary
                if clean_summary and "Awaiting narrative" not in clean_summary:
                    import re
                    
                    # 1. Strip Claude's hardcoded labels (with and without markdown bolding)
                    labels_to_remove = [
                        "**How to read this document:**", "How to read this document:",
                        "**Practical takeaway:**", "Practical takeaway:"
                    ]
                    for label in labels_to_remove:
                        clean_summary = clean_summary.replace(label, "")
                    
                    # Clean up any leading whitespace left behind after stripping
                    clean_summary = clean_summary.strip()
                    
                    # 2. Safely convert any remaining accidental markdown bolding
                    clean_summary = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', clean_summary)
                    
                    # 3. Preserve Claude's natural paragraph breaks
                    clean_summary = clean_summary.replace('\n\n', '<br><br>')
                    
                    # 4. Strip stray single newlines so the text justifies perfectly
                    clean_summary = clean_summary.replace('\n', ' ')

                st.markdown(
                    f"""
                    <div style="background-color: #F4F6F9; padding: 0.8rem 1.4rem 1.4rem 1.4rem; border-radius: 4px; border: 1px solid #E2DFD8; height: 100%;">
                        <p style="font-family: 'Inter', sans-serif; font-size: 0.95rem; font-weight: 800; color: #003366; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0; margin-bottom: 0.2rem;">
                            Executive Summary
                        </p>
                        <p style="font-family: 'Inter', sans-serif; font-size: 0.70rem; font-weight: 700; color: #666666; letter-spacing: 0.05em; margin-top: 0; margin-bottom: 1.2rem;">
                            NLP-driven narrative synthesis of the current policy cycle
                        </p>
                        <p style="font-family: 'Inter', sans-serif; font-size: 0.85rem; color: #222222; line-height: 1.65; text-align: justify; margin-bottom: 0;">
                            {clean_summary}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        # ── Sentiment Over Time (PRIMARY) ──
        trajectory, charts = _pop_summary(charts, ["02_rbi_sentiment_trajectory"])
        if trajectory:
            _section("Sentiment Over Time")
            st.image(str(trajectory), use_container_width=True)
            insight = get_insight(trajectory.name)
            if insight:
                with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                    st.markdown(insight)


        # ── Meeting Analysis ──
        _section("Meeting Analysis")

        comparison, charts = _pop_summary(charts, ["03_rbi_resolution_vs_minutes"])
        radar, charts = _pop_summary(charts, ["04_rbi_subdimension_radar"])

        # Main analytical chart (FULL WIDTH)
        if comparison:
            st.image(str(comparison), use_container_width=True)
            insight = get_insight(comparison.name)
            if insight:
                with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                    st.markdown(insight)

        # Supporting chart (CENTERED)
        if radar:
            _, col_mid, _ = st.columns([1, 2, 1])
            with col_mid:
                st.image(str(radar), use_container_width=True)
                insight = get_insight(radar.name)
                if insight:
                    with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                        st.markdown(insight)
                        
        # ── Repo Rate vs Sentiment (PRIMARY) ──
        rate_chart, charts = _pop_summary(charts, ["05_rbi_rate_and_sentiment"])
        if rate_chart:
            _section("Repo Rate vs. Sentiment")
            st.image(str(rate_chart), use_container_width=True)
            insight = get_insight(rate_chart.name)
            if insight:
                with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                    st.markdown(insight)

        # ── Governor Signal Analysis ──
        gov_divergence, charts = _pop_summary(charts, ["07_rbi_governor_divergence"])

        if gov_divergence:
            _section("Governor Signal Analysis")
            st.image(str(gov_divergence), use_container_width=True)
            insight = get_insight(gov_divergence.name)
            if insight:
                with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                    st.markdown(insight)

        # ── Meeting History ──
        timeline, charts = _pop_summary(charts, ["06_rbi_meeting_timeline"])
        if timeline:
            _section("Meeting History")
            st.image(str(timeline), use_container_width=True)
            insight = get_insight(timeline.name)
            if insight:
                with st.expander("ℹ️ Chart Insights & Practical Takeaways"):
                    st.markdown(insight)

        # ── Catch-all ──
        if charts:
            _section("Other")
            _render_grid(charts)