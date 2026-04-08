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
    page_icon="📊",
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

    /* ── Masthead — Merriweather, editorial weight ── */
    .hub-masthead {
        font-family: 'Merriweather', Georgia, "Times New Roman", serif;
        font-size: 2.05rem;
        font-weight: 900;
        letter-spacing: -0.01em;
        color: #000000;
        margin-bottom: 0;
        line-height: 1.1;
    }
    .hub-tagline {
        font-family: 'Inter', sans-serif;
        font-size: 0.76rem;
        font-weight: 400;
        color: #777777;
        text-transform: uppercase;
        letter-spacing: 0.11em;
        margin-top: 0.22rem;
        margin-bottom: 0.2rem;
    }
    .hub-substack {
        font-family: 'Inter', sans-serif;
        font-size: 0.76rem;
        font-weight: 500;
        color: #FF6719;
        text-decoration: none;
        letter-spacing: 0.02em;
        margin-bottom: 0.35rem;
        display: inline-block;
    }
    .hub-substack:hover { text-decoration: underline; }
    .hub-rule {
        border: none;
        border-top: 2px solid #000000;
        margin-top: 0.4rem;
        margin-bottom: 0.5rem;
    }

    /* ── Section headers — Inter 800, all-caps, navy, generous spacing ── */
    .section-header {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        font-weight: 800;
        letter-spacing: 0.14em;
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
        color: #888888;
        text-align: right;
    }

    /* ── Tab bar ── */
    button[data-baseweb="tab"] {
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.80rem !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #ECEEF1;
    }
    .sidebar-masthead {
        font-family: 'Merriweather', Georgia, serif;
        font-size: 0.95rem;
        font-weight: 700;
        color: #000000;
    }
    .sidebar-byline {
        font-family: 'Inter', sans-serif;
        font-size: 0.73rem;
        font-weight: 400;
        color: #888888;
        margin-top: 0.1rem;
    }
    .sidebar-link {
        font-family: 'Inter', sans-serif;
        font-size: 0.73rem;
        font-weight: 500;
        color: #003366;
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
    st.markdown(
        '<p class="sidebar-masthead">The Economics Hub</p>'
        '<p class="sidebar-byline">Shreyas Urgunde</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    with st.expander("About", expanded=False):
        st.markdown(
            """
            **Author**
            Shreyas Urgunde

            **Links**
            """
        )
        st.markdown(
            '<a class="sidebar-link" href="https://shreyasxi.github.io/" target="_blank">🌐 shreyasxi.github.io</a><br>'
            '<a class="sidebar-link" href="https://economicshub.substack.com/" target="_blank">📬 The Economics Hub — Substack</a>',
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            ---
            **Data sources**
            - Market data: Yahoo Finance
            - Macro series: FRED (St. Louis Fed)
            - International: DBnomics · IMF · OECD
            - India: RBI · MoSPI · NSDL · CAG

            **License**
            CC BY-NC 4.0
            """
        )

    # Pipeline control — only visible when PIPELINE_KEY secret is set
    if is_pipeline_admin():
        st.markdown("---")
        st.markdown(
            '<p style="font-family:\'Inter\',sans-serif;font-size:0.72rem;'
            'font-weight:700;letter-spacing:0.09em;text-transform:uppercase;'
            'color:#003366;margin-bottom:0.2rem;">Pipeline Control</p>',
            unsafe_allow_html=True,
        )
        st.caption("Publisher access only.")

        with st.expander("Run Generators", expanded=False):
            _GENERATORS = {
                "Weekly Markets":  ("generate_weekly.py",  True),
                "Macro Pulse":     ("generate_macro.py",   True),
                "India Dashboard": ("generate_india.py",   False),
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
    '<h1 class="hub-masthead">THE ECONOMICS HUB</h1>'
    '<p class="hub-tagline">A visual dashboard tracking global macroeconomics and financial markets.</p>'
    '<a class="hub-substack" href="https://economicshub.substack.com/" target="_blank">'
    'Subscribe on Substack →</a>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="hub-rule">', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_weekly, tab_macro, tab_india = st.tabs(
    ["Weekly Markets", "Macro Pulse", "India Dashboard"]
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

        # Equities
        equities, charts = _group(charts, "equities")
        if equities:
            _section("Equities")
            _render_grid(equities)

        # Foreign Exchange (major pairs only — EM FX handled separately below)
        fx = [c for c in charts if "fx" in c.name and "em_fx" not in c.name]
        charts = [c for c in charts if not ("fx" in c.name and "em_fx" not in c.name)]
        if fx:
            _section("Foreign Exchange")
            _render_grid(fx)

        # Government Bond Yields (excludes real_yields which goes to Inflation Signals)
        yields = [c for c in charts if "yield" in c.name and "real_yield" not in c.name]
        charts = [c for c in charts if not ("yield" in c.name and "real_yield" not in c.name)]
        if yields:
            _section("Government Bond Yields")
            _render_grid(yields)

        # Commodities
        commodities, charts = _group(charts, "commodities")
        if commodities:
            _section("Commodities")
            _render_grid(commodities)

        # Volatility & Sentiment
        vol_kws = ["vix", "sector_rotation"]
        vol = [c for c in charts if any(k in c.name for k in vol_kws) and "india_vix" not in c.name]
        charts = [c for c in charts if not (any(k in c.name for k in vol_kws) and "india_vix" not in c.name)]
        if vol:
            _section("Volatility & Sentiment")
            _render_grid(vol)

        # Labour & Wages
        labour = [c for c in charts if any(k in c.name for k in ["wage", "labour", "labor"])]
        charts = [c for c in charts if not any(k in c.name for k in ["wage", "labour", "labor"])]
        if labour:
            _section("Labour & Wages")
            _render_grid(labour)

        # Credit Markets
        credit_kws = ["credit_spreads", "bond_etf"]
        credit = [c for c in charts if any(k in c.name for k in credit_kws)]
        charts = [c for c in charts if not any(k in c.name for k in credit_kws)]
        if credit:
            _section("Credit Markets")
            _render_grid(credit)

        # Inflation Signals
        inflation_kws = ["breakeven", "real_yield"]
        inflation_sig = [c for c in charts if any(k in c.name for k in inflation_kws)]
        charts = [c for c in charts if not any(k in c.name for k in inflation_kws)]
        if inflation_sig:
            _section("Inflation Signals")
            _render_grid(inflation_sig)

        # Cross-Asset Risk
        cross_kws = ["spy_tlt", "risk_appetite", "breadth", "gold_spx", "copper_gold"]
        cross = [c for c in charts if any(k in c.name for k in cross_kws)]
        charts = [c for c in charts if not any(k in c.name for k in cross_kws)]
        if cross:
            _section("Cross-Asset Risk")
            _render_grid(cross)

        # Emerging Markets
        em_kws = ["em_fx", "em_equity", "india_vs_em"]
        em = [c for c in charts if any(k in c.name for k in em_kws)]
        charts = [c for c in charts if not any(k in c.name for k in em_kws)]
        if em:
            _section("Emerging Markets")
            _render_grid(em)

        # Energy & Agriculture
        energy_kws = ["brent_wti", "agri"]
        energy_ag = [c for c in charts if any(k in c.name for k in energy_kws)]
        charts = [c for c in charts if not any(k in c.name for k in energy_kws)]
        if energy_ag:
            _section("Energy & Agriculture")
            _render_grid(energy_ag)

        # India Volatility
        india_vix = [c for c in charts if "india_vix" in c.name]
        charts = [c for c in charts if "india_vix" not in c.name]
        if india_vix:
            _section("India Volatility")
            _render_grid(india_vix)

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

        if charts:
            _render_grid(charts, cols=2)
