"""
The Economics Hub — Streamlit Dashboard
Author: Shreyas

Three-tab publication dashboard:
  Weekly Markets  · Macro Pulse  · India Dashboard

Charts are served from assets/ (git-tracked, deployed) with a local
fallback to output/ for development. The sidebar exposes pipeline
control buttons when running locally (hidden on Streamlit Cloud).
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
    is_streamlit_cloud,
)

PROJECT_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="The Economics Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — institutional serif aesthetic matching EconStyle
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* ── Global font ── */
    html, body, [class*="css"] {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
    }

    /* ── Masthead ── */
    .hub-masthead {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 2.4rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #003366;
        margin-bottom: 0;
        line-height: 1.1;
    }
    .hub-tagline {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 1.0rem;
        font-style: italic;
        color: #444444;
        margin-top: 0.2rem;
        margin-bottom: 0.6rem;
    }
    .hub-rule {
        border: none;
        border-top: 2.5px solid #000000;
        margin-top: 0.5rem;
        margin-bottom: 1.2rem;
    }

    /* ── Section headers ── */
    .section-header {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 1.05rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #003366;
        border-bottom: 1px solid #CCCCCC;
        padding-bottom: 0.3rem;
        margin-top: 1.2rem;
        margin-bottom: 0.6rem;
    }

    /* ── Status bar ── */
    .status-label {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 0.85rem;
        font-weight: 600;
        color: #003366;
    }
    .status-mtime {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 0.78rem;
        color: #666666;
        text-align: right;
    }

    /* ── Tab styling ── */
    button[data-baseweb="tab"] {
        font-family: "Cambria", Georgia, "Times New Roman", serif !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.02em;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #F4F4F4;
    }
    .sidebar-masthead {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 1.1rem;
        font-weight: 700;
        color: #003366;
        letter-spacing: 0.04em;
    }
    .sidebar-byline {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 0.82rem;
        color: #555555;
        font-style: italic;
        margin-top: -0.3rem;
    }

    /* ── India notice ── */
    .india-notice {
        background-color: #FFF8E6;
        border-left: 3px solid #CC6600;
        padding: 0.55rem 0.85rem;
        font-size: 0.82rem;
        font-style: italic;
        color: #555555;
        margin-bottom: 1rem;
    }

    /* ── Image captions ── */
    [data-testid="caption"] {
        font-family: "Cambria", Georgia, "Times New Roman", serif;
        font-size: 0.75rem;
        color: #777777;
        text-align: center;
        letter-spacing: 0.02em;
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
        '<p class="sidebar-masthead">THE ECONOMICS HUB</p>'
        '<p class="sidebar-byline">by Shreyas</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    with st.expander("About", expanded=False):
        st.markdown(
            """
            **Data sources**
            - Market data: Yahoo Finance
            - Macro series: FRED (St. Louis Fed)
            - International: DBnomics · IMF · OECD
            - India: RBI · MoSPI · NSDL · CAG

            **Charts**
            The Economics Hub · CC BY-NC 4.0
            """
        )

    st.markdown("---")

    # Pipeline control — local only
    if not is_streamlit_cloud():
        st.markdown("**Pipeline Control**")
        st.caption("Local use only — not available on Streamlit Cloud.")

        with st.expander("Run Generators", expanded=False):
            _GENERATORS = {
                "Weekly Markets": "generate_weekly.py",
                "Macro Pulse": "generate_macro.py",
                "India Dashboard": "generate_india.py",
            }
            for label, script in _GENERATORS.items():
                if st.button(f"▶  {label}", key=f"btn_{script}", use_container_width=True):
                    with st.spinner(f"Running {label} generator…"):
                        result = subprocess.run(
                            [sys.executable, script],
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
    '<p class="hub-tagline">Global finance through multiple lenses</p>',
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
    """Render the date label and last-updated timestamp row."""
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
    """Render a list of PNG paths in an evenly-spaced column grid."""
    columns = st.columns(cols)
    for i, chart_path in enumerate(charts):
        with columns[i % cols]:
            st.image(
                str(chart_path),
                caption=clean_title(chart_path.name),
                use_container_width=True,
            )


def _section(title: str) -> None:
    st.markdown(
        f'<p class="section-header">{title}</p>',
        unsafe_allow_html=True,
    )


def _pop_summary(charts: list[Path], keywords: list[str]) -> tuple[Path | None, list[Path]]:
    """
    Extract the first chart whose name matches any of the given keywords.
    Returns (summary_chart_or_None, remaining_charts).
    """
    for kw in keywords:
        for c in charts:
            if kw in c.name:
                remaining = [x for x in charts if x != c]
                return c, remaining
    return None, charts


def _group(charts: list[Path], keyword: str) -> tuple[list[Path], list[Path]]:
    """Partition charts into (matching, non_matching) by filename keyword."""
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
        st.markdown('<hr style="border-top:1px solid #DDDDDD; margin:0.4rem 0 1rem 0">', unsafe_allow_html=True)

        # Summary table — full width, no caption
        summary, charts = _pop_summary(charts, ["summary_table", "00_"])
        if summary:
            st.image(str(summary), use_container_width=True)
            st.markdown("---")

        # Equities
        equities, charts = _group(charts, "equities")
        if equities:
            _section("Equities")
            _render_grid(equities)

        # Foreign Exchange
        fx, charts = _group(charts, "fx")
        if fx:
            _section("Foreign Exchange")
            _render_grid(fx)

        # Government Bond Yields
        yields = [c for c in charts if "yield" in c.name]
        charts = [c for c in charts if "yield" not in c.name]
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
        vol = [c for c in charts if any(k in c.name for k in vol_kws)]
        charts = [c for c in charts if not any(k in c.name for k in vol_kws)]
        if vol:
            _section("Volatility & Sentiment")
            _render_grid(vol)

        # Labour & Wages
        labour = [c for c in charts if any(k in c.name for k in ["wage", "labour", "labor"])]
        charts = [c for c in charts if not any(k in c.name for k in ["wage", "labour", "labor"])]
        if labour:
            _section("Labour & Wages")
            _render_grid(labour)

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
        st.markdown('<hr style="border-top:1px solid #DDDDDD; margin:0.4rem 0 1rem 0">', unsafe_allow_html=True)

        # Summary table — full width
        summary, charts = _pop_summary(charts, ["macro_table", "00_"])
        if summary:
            st.image(str(summary), use_container_width=True)
            st.markdown("---")

        # All remaining charts in 2-column grid
        if charts:
            _render_grid(charts, cols=2)


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
        st.markdown('<hr style="border-top:1px solid #DDDDDD; margin:0.4rem 0 1rem 0">', unsafe_allow_html=True)

        st.markdown(
            '<div class="india-notice">'
            "India data is manually curated. Charts reflect the latest data "
            "update committed to the repository by Shreyas."
            "</div>",
            unsafe_allow_html=True,
        )

        # India summary table — full width
        summary, charts = _pop_summary(charts, ["india_table", "05_india"])
        if summary:
            st.image(str(summary), use_container_width=True)
            st.markdown("---")

        # All remaining charts in 2-column grid
        if charts:
            _render_grid(charts, cols=2)
