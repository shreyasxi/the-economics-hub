"""
The Economics Hub — Streamlit Dashboard
Author: Shreyas Urgunde  |  shreyasxi.github.io

Four-tab publication dashboard:
  Weekly Markets  · World  · India  · RBI Sentinel

Charts are served from assets/ (git-tracked, deployed) with a local
fallback to output/ for development. Pipeline controls are gated
behind PIPELINE_KEY — only visible to the publisher.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

from charts.loader import (
    clean_title,
    get_charts,
    is_pipeline_admin,
)
import config.insights as _insights
import config.world_settings as _world_settings

from rbi_sentinel.config import DOC_GOVERNOR, DOC_MINUTES, DOC_RESOLUTION
import rbi_sentinel.cleaners.policy_facts as _policy_facts
import rbi_sentinel.db.manager as _manager
from rbi_sentinel.db.manager import get_latest_composite
from rbi_sentinel.sentiment.score_normalizer import _DOC_WEIGHTS

PROJECT_ROOT = Path(__file__).resolve().parent


def get_insight(filename: str) -> str | None:
    """
    Chart insight text, always from the current config/insights.py.

    Streamlit Cloud re-runs app.py after a push without re-importing modules,
    so a cached config.insights lacks any chart text added since and the
    chart's expander silently disappears. Reload when the file has changed.
    """
    mtime = Path(_insights.__file__).stat().st_mtime
    if getattr(_insights, "_loaded_mtime", None) != mtime:
        importlib.reload(_insights)
        _insights._loaded_mtime = mtime
    return _insights.get_insight(filename)

# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="The Economics Hub",
    page_icon=str(PROJECT_ROOT / "assets" / "brand" / "econhub_logo.jpg"),
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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Merriweather:ital,wght@0,700;0,900;1,400&family=Playfair+Display:wght@700;900&display=swap');

    /* ── Global base ── */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* ── Reduce Streamlit's default top padding ── */
    .main .block-container {
        padding-top: 1.0rem;
        padding-bottom: 2rem;
    }
    
    /* ═══ RBI policy panel ═══════════════════════════════════════════ */

    /* ── Tab header ──────────────────────────────────────────────────────
       Replaces the italic abstract callout and the separate masthead bar:
       a title and one-line standfirst on the left, the latest meeting on
       the right, closed by a navy rule. The full method stays one click
       away in the expander below. */
    .rbi-head {
        display: flex; justify-content: space-between; align-items: flex-end;
        gap: 0.8rem 2rem; flex-wrap: wrap;
        margin: 0.4rem 0 1rem 0; padding-bottom: 0.85rem;
        border-bottom: 2px solid #0A1F3D;
    }
    .rbi-head-text { flex: 1 1 28rem; min-width: 0; }
    .rbi-head-title {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 1.45rem; font-weight: 800; letter-spacing: 0.04em;
        text-transform: uppercase; color: #0A1F3D;
        line-height: 1.15; margin: 0 0 0.35rem 0;
    }
    .rbi-head-dek {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.9rem; font-weight: 400; color: #4A5262;
        line-height: 1.5; margin: 0; max-width: 46rem;
    }
    .rbi-head-meta {
        display: flex; flex-direction: column; align-items: flex-end;
        gap: 0.2rem; white-space: nowrap;
    }
    .rbi-head-meta-label {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.62rem; font-weight: 700; letter-spacing: 0.13em;
        text-transform: uppercase; color: #7A828F;
    }
    .rbi-head-meta-value {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 1.0rem; font-weight: 700; color: #0A1F3D;
        font-variant-numeric: tabular-nums;
    }

    /* ── Methodology tables: navy header row, white text ── */
    .method-table {
        width: 100%; border-collapse: collapse; margin: 0.4rem 0 1.1rem 0;
        font-family: 'Inter', sans-serif; font-size: 0.86rem;
    }
    .method-table th {
        background: #003366; color: #FFFFFF; font-weight: 700;
        text-align: left; padding: 0.55rem 0.8rem; border: 1px solid #003366;
    }
    .method-table td {
        padding: 0.5rem 0.8rem; border: 1px solid #DDE2E9; color: #24282F;
        vertical-align: top;
    }
    .method-table tbody tr:nth-child(even) td { background: rgba(0,51,102,0.03); }

    /* ── Decision strip ──────────────────────────────────────────────────
       The cycle's facts in one row between the method note and the charts.
       Separation is carried by whitespace, not rules: no dividers between
       cells or groups, a wide column gap, and a faint outer edge only so the
       panel reads as one object on the page ground. Figures are tabular
       lining numerals; colour appears only where it carries direction. */
    .mpc-exec-head, .mpc-exec-body, .mpc-sources { --mpc-gap: 1.15rem; }
    .dx {
        display: grid; grid-template-columns: 2fr 2fr 2fr 1.1fr;
        column-gap: 2.6rem; row-gap: 1.4rem;
        background: #FCFCFD;
        border: 1px solid #E8EBF0; border-radius: 12px;
        box-shadow: 0 8px 26px -20px rgba(10,31,61,0.16);
        padding: 1.15rem 1.7rem 1.25rem 1.7rem;
        margin: 0.9rem 0 1.6rem 0;
    }
    .dx-group { min-width: 0; }
    .dx-group-label {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em;
        text-transform: uppercase; color: #0A1F3D;
        margin: 0 0 0.8rem 0; white-space: nowrap;
    }
    .dx-cells {
        display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr));
        column-gap: 1.5rem;
    }
    .dx-cell { display: flex; flex-direction: column; gap: 0.3rem; min-width: 0; }
    .dx-label {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.64rem; font-weight: 600; letter-spacing: 0.08em;
        text-transform: uppercase; color: #7A828F; white-space: nowrap;
    }
    .dx-value {
        font-family: 'Inter', 'SF Pro Display', -apple-system, 'Helvetica Neue', Arial, sans-serif;
        font-size: clamp(1.35rem, 1.6vw, 1.75rem); font-weight: 600; letter-spacing: -0.025em;
        line-height: 1.05; color: #0A1F3D; white-space: nowrap;
        font-variant-numeric: tabular-nums lining-nums;
        font-feature-settings: 'tnum' 1, 'lnum' 1;
    }
    .dx-unit {
        font-size: 0.95rem; font-weight: 500; letter-spacing: 0;
        color: #7A828F; margin-left: 0.1rem;
    }
    .dx-date { font-size: clamp(1.1rem, 1.25vw, 1.35rem); letter-spacing: -0.015em; }
    .dx-missing { color: #B4BAC3; font-weight: 400; }
    .dx-sub {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.74rem; font-weight: 500; color: #6B7380;
        line-height: 1.35; font-variant-numeric: tabular-nums;
    }
    .dx-sub b { font-weight: 700; }
    @media (max-width: 1200px) {
        .dx { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 640px) {
        .dx { grid-template-columns: 1fr; padding: 1rem 1.1rem; }
        .dx-value { font-size: 1.5rem; }
    }
    .mpc-d-hike { color: #A61B29; }
    .mpc-d-cut  { color: #1F4E79; }
    .mpc-hawkish { color: #A61B29; }
    .mpc-dovish  { color: #1F4E79; }
    .mpc-neutral { color: #4A5262; }

    /* ── Executive summary ──────────────────────────────────────────────
       Heading sits on the page with a rule beneath it rather than in a
       tinted box; the narrative below keeps the locked body typography. */
    .mpc-exec-head {
        padding: 0 0 0.65rem 0; margin-bottom: 1rem;
        border-bottom: 2px solid #0A1F3D;
    }
    .mpc-exec-title {
        font-family: 'Inter', sans-serif; font-size: 1.02rem; font-weight: 900;
        color: #0A1F3D; text-transform: uppercase; letter-spacing: 0.07em;
        margin: 0 0 0.25rem 0; line-height: 1.2;
    }
    .mpc-exec-sub {
        font-family: 'Inter', sans-serif; font-size: 0.8rem; font-weight: 400;
        font-style: italic; color: #4A5262; margin: 0; line-height: 1.4;
    }
    .mpc-exec-body { margin-bottom: var(--mpc-gap); padding: 0 0.1rem; }

    /* ── Key takeaways ───────────────────────────────────────────────────
       Five scannable lines ahead of the narrative. A fixed label column
       lets the eye run down the topics, then across to the one fact that
       matters; spacing, not bullets or rules, separates the rows. */
    .mpc-tk {
        list-style: none; margin: 0 0 1.35rem 0; padding: 0 0 1.1rem 0;
        border-bottom: 1px solid #E3E7EC;
    }
    .mpc-tk li {
        display: grid; grid-template-columns: 7.4rem minmax(0, 1fr);
        column-gap: 0.9rem; align-items: baseline;
        margin: 0 0 0.62rem 0; padding: 0;
    }
    .mpc-tk li:last-child { margin-bottom: 0; }
    .mpc-tk-label {
        font-family: 'Inter', sans-serif; font-size: 0.66rem; font-weight: 700;
        letter-spacing: 0.1em; text-transform: uppercase; color: #0A1F3D;
    }
    .mpc-tk-text {
        font-family: 'Inter', sans-serif; font-size: 0.9rem; color: #24282F;
        line-height: 1.5; font-variant-numeric: tabular-nums;
    }
    .mpc-tk-text b { font-weight: 700; color: #0A1F3D; }
    .mpc-tk-text b.mpc-hawkish { color: #A61B29; }
    .mpc-tk-text b.mpc-dovish { color: #1F4E79; }
    .mpc-tk-text q { font-style: italic; quotes: "\\201C" "\\201D"; }
    .mpc-tk-src { color: #6B7380; font-size: 0.8rem; white-space: nowrap; }
    .mpc-tk-fig {
        color: #4A5262; white-space: nowrap; cursor: help;
        text-decoration: underline dotted #B4BAC3; text-underline-offset: 3px;
    }
    @media (max-width: 640px) {
        .mpc-tk li { grid-template-columns: 1fr; row-gap: 0.15rem; }
    }

    /* LOCKED — approved typography for the narrative paragraphs. */
    .mpc-body {
        font-family: 'Inter', sans-serif; font-size: 0.9rem; color: #24282F;
        line-height: 1.72; text-align: left; margin: 0 0 0.85rem 0;
    }
    .mpc-body:last-of-type { margin-bottom: 0; }

    /* ── Source documents ──────────────────────────────────────────────
       Sits under the Stance Meter as a references strip rather than a
       white card: no fill, no shadow. A short navy rule and eyebrow open
       it, and the three documents run as columns divided by hairlines —
       the chart column is wide enough that a stacked list wasted it. */
    .mpc-sources { margin-top: 1.1rem; }
    .mpc-sources-label {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.13em;
        text-transform: uppercase; color: #7A828F;
        margin: 0 0 0.7rem 0; padding-top: 0.6rem;
        border-top: 2px solid #0A1F3D; display: inline-block;
    }
    .mpc-prov {
        list-style: none; padding: 0; margin: 0;
        display: grid; grid-template-columns: repeat(3, 1fr);
        border-top: 1px solid #D5DAE1; border-bottom: 1px solid #D5DAE1;
    }
    .mpc-prov li {
        display: flex; flex-direction: column; gap: 0.45rem;
        padding: 0.85rem 1rem 0.9rem 1rem; margin: 0;
        border-left: 1px solid #E3E7EC; min-width: 0;
    }
    /* Share row tracks across the three columns so a name that wraps to
       two lines does not push its score out of line with the others. */
    @supports (grid-template-rows: subgrid) {
        .mpc-prov li {
            display: grid; grid-row: span 4; grid-template-rows: subgrid;
            row-gap: 0.45rem; align-items: end;
        }
        .mpc-prov li > .mpc-doc-top { align-self: start; }
    }
    .mpc-prov li:first-child { border-left: none; padding-left: 0.1rem; }
    /* Row 1: document name, with its weight in the composite beneath —
       stacked rather than side by side so "Governor's Statement" never
       wraps the weight and knocks the three columns out of line. */
    .mpc-doc-top {
        display: flex; flex-direction: column; align-items: flex-start;
        gap: 0.18rem;
    }
    .mpc-prov a {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.98rem; font-weight: 600; color: #0A1F3D;
        text-decoration: none;
        border-bottom: 1px solid rgba(10,31,61,0.22);
    }
    .mpc-prov a::after { content: " \\2197"; font-size: 0.8rem; color: #7A828F; }
    .mpc-prov a:hover { border-bottom-color: #0A1F3D; }
    .mpc-doc-weight {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em;
        text-transform: uppercase; color: #7A828F; white-space: nowrap;
    }
    /* Row 2: the document's own stance score */
    .mpc-doc-score {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 1.75rem; font-weight: 600; letter-spacing: -0.02em;
        line-height: 1; font-variant-numeric: tabular-nums lining-nums;
    }
    .mpc-doc-dir {
        font-size: 0.78rem; font-weight: 700; letter-spacing: 0.04em;
        margin-left: 0.45rem; vertical-align: 0.2em;
    }
    /* Row 3: position on the bounded [-1, +1] scale, centre tick at 0 */
    .mpc-doc-track {
        position: relative; display: block; height: 10px; margin: 0.1rem 0;
    }
    .mpc-doc-track::before {
        content: ""; position: absolute; left: 0; right: 0; top: 50%;
        height: 2px; margin-top: -1px; border-radius: 1px;
        background: linear-gradient(90deg, #1F4E79 0%, #D5DAE1 50%, #A61B29 100%);
        opacity: 0.35;
    }
    .mpc-doc-track::after {
        content: ""; position: absolute; left: 50%; top: 0;
        width: 1px; height: 10px; background: #9AA2AD;
    }
    .mpc-doc-track i {
        position: absolute; top: 50%; width: 9px; height: 9px;
        margin: -4.5px 0 0 -4.5px; border-radius: 50%;
        border: 1.5px solid #F4F5F7; z-index: 1;
    }
    .mpc-dot-hawkish { background: #A61B29; }
    .mpc-dot-dovish  { background: #1F4E79; }
    .mpc-dot-neutral { background: #4A5262; }
    /* Row 4: provenance */
    .mpc-prov-meta {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.8rem; font-weight: 500; color: #6B7380;
        white-space: nowrap; font-variant-numeric: tabular-nums;
    }

    @media (max-width: 640px) {
        .mpc-prov { grid-template-columns: 1fr; }
        .mpc-prov li { display: flex; grid-row: auto; }
        .mpc-prov li { border-left: none; border-top: 1px solid #E3E7EC; padding-left: 0.1rem; }
        .mpc-prov li:first-child { border-top: none; }
    }

    /* ═══ World tab ═══════════════════════════════════════════════════ */

    /* ── Panel eyebrow: small caps label over each HTML panel ── */
    .w-eyebrow {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em;
        text-transform: uppercase; color: #0A1F3D; margin: 0 0 0.6rem 0;
    }
    .w-foot {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.72rem; color: #6B7380; line-height: 1.5; margin: 0.55rem 0 0 0;
    }
    /* Eyebrow with the tab header's heavy navy rule beneath it */
    .w-eyebrow.is-ruled { padding-bottom: 0.55rem; border-bottom: 2px solid #0A1F3D; }

    /* ── Central bank strip: same card and figures as the RBI decision
       strip, one column per bank; colour only on hike/cut. ── */
    .wcb {
        display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
        column-gap: 1.6rem; row-gap: 1.3rem;
        background: #FCFCFD; border: 1px solid #E8EBF0; border-radius: 12px;
        box-shadow: 0 8px 26px -20px rgba(10,31,61,0.16);
        padding: 1.1rem 1.5rem 1.2rem 1.5rem; margin: 0.3rem 0 1.8rem 0;
    }
    .wcb-tile { display: flex; flex-direction: column; gap: 0.28rem; min-width: 0; }
    .wcb-tile.is-india { border-left: 3px solid #FF9933; padding-left: 0.8rem; }
    .wcb-bank {
        line-height: 1.2;
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 1.05rem; font-weight: 800; letter-spacing: 0.01em;
        color: #0A1F3D; margin: 0 0 0.1rem 0;
    }
    .wcb-rate {
        font-family: 'Inter', 'SF Pro Display', -apple-system, sans-serif;
        font-size: clamp(1.25rem, 1.45vw, 1.6rem); font-weight: 600; letter-spacing: -0.025em;
        line-height: 1.1; color: #0A1F3D; white-space: nowrap; margin: 0.1rem 0 0 0;
        font-variant-numeric: tabular-nums lining-nums;
    }
    .wcb-label, .wcb-sub, .wcb-next {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.73rem; line-height: 1.35; margin: 0; color: #6B7380;
        font-variant-numeric: tabular-nums;
    }
    .wcb-label { font-size: 0.64rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: #7A828F; }
    .wcb-next { color: #24282F; font-weight: 600; }
    @media (max-width: 1200px) { .wcb { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    @media (max-width: 640px)  { .wcb { grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 1rem; } }

    /* ── Calendar: date column + event, spacing not rules ── */
    .wcal { list-style: none; margin: 0; padding: 0; }
    .wcal li {
        display: grid; grid-template-columns: 5.6rem minmax(0, 1fr);
        column-gap: 0.8rem; align-items: baseline;
        padding: 0.42rem 0; border-bottom: 1px solid #ECEFF3;
    }
    .wcal li:last-child { border-bottom: none; }
    .wcal-date {
        font-family: 'Inter', sans-serif; font-size: 0.78rem; font-weight: 700;
        color: #0A1F3D; font-variant-numeric: tabular-nums; white-space: nowrap;
    }
    .wcal-what { font-family: 'Inter', sans-serif; font-size: 0.86rem; color: #24282F; }
    .wcal-what small { color: #7A828F; font-size: 0.74rem; margin-left: 0.35rem; }
    .wcal-cb .wcal-what { font-weight: 600; color: #0A1F3D; }
    .wcal-in .wcal-what { color: #B35C00; }

    /* ── Scoreboard ── */
    .wsb-wrap { overflow-x: auto; margin: 0.2rem 0 0 0; }
    .wsb {
        width: 100%; min-width: 760px; border-collapse: collapse;
        font-family: 'Inter', -apple-system, sans-serif; background: #FFFFFF;
        border-top: 2px solid #0A1F3D; border-bottom: 1px solid #D5DAE1;
    }
    /* Column titles: white on navy, as large as the economy names beside them */
    .wsb thead th {
        font-size: 0.9rem; font-weight: 700; letter-spacing: 0.01em;
        color: #FFFFFF; background: #0A1F3D; text-align: right;
        padding: 0.7rem 0.8rem; white-space: nowrap;
    }
    .wsb th:first-child, .wsb tbody th { text-align: left; }
    .wsb tbody th {
        font-size: 0.9rem; font-weight: 700; letter-spacing: 0;
        color: #0A1F3D; padding: 0.55rem 0.8rem; border-bottom: 1px solid #ECEFF3;
        white-space: nowrap;
    }
    .wsb tr.is-india th, .wsb tr.is-india td { background: rgba(255,153,51,0.06); }
    .wsb td {
        text-align: right; padding: 0.55rem 0.8rem; border-bottom: 1px solid #ECEFF3;
        vertical-align: top; white-space: nowrap;
    }
    .wsb-v {
        display: block; font-size: 1.02rem; font-weight: 600; color: #0A1F3D;
        font-variant-numeric: tabular-nums lining-nums; letter-spacing: -0.01em;
    }
    .wsb-m { display: block; font-size: 0.7rem; color: #7A828F; font-variant-numeric: tabular-nums; margin-top: 0.1rem; }
    .wsb-good { color: #1E7B45; font-weight: 600; }
    .wsb-bad  { color: #A61B29; font-weight: 600; }
    .wsb-flat { color: #7A828F; }
    .wsb-na { color: #B4BAC3; font-size: 0.78rem; font-style: italic; }
    .wsb-stale .wsb-v { color: #9AA2AD; }
    .wsb-flag { color: #B35C00; font-weight: 600; }

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
    /* ── Substack call-to-action: navy button, external-link arrow ── */
    a.substack-cta {
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        margin-top: 0.4rem;
        margin-bottom: 0.8rem;
        padding: 0.62rem 1.1rem 0.62rem 1.25rem;
        background: #003366;
        border: 1px solid #003366;
        border-radius: 6px;
        box-shadow: 0 1px 2px rgba(0, 31, 63, 0.12), 0 4px 12px rgba(0, 31, 63, 0.10);
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif;
        text-decoration: none !important;
        transition: background-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
    }
    a.substack-cta:hover {
        background: #00264D;
        box-shadow: 0 2px 4px rgba(0, 31, 63, 0.16), 0 10px 24px rgba(0, 31, 63, 0.18);
        transform: translateY(-1px);
        color: #FFFFFF !important;
    }
    a.substack-cta:focus-visible {
        outline: 2px solid #FF6719;
        outline-offset: 3px;
    }
    .substack-cta__label {
        font-size: 0.86rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        line-height: 1;
        color: #FFFFFF;
    }
    .substack-cta__arrow {
        display: block;
        width: 0.9rem;
        height: 0.9rem;
        flex-shrink: 0;
        transition: transform 0.2s ease;
    }
    a.substack-cta:hover .substack-cta__arrow { transform: translate(2px, -2px); }
    
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

    
    
    /* ── Tab bar ──
       Two selectors: Streamlit up to 1.50 renders tabs as BaseWeb buttons
       (data-baseweb="tab"); later releases replaced them with a new
       component that carries data-testid="stTab" and no BaseWeb attribute. */
    button[data-baseweb="tab"],
    button[data-baseweb="tab"] p,
    button[data-baseweb="tab"] span,
    [data-testid="stTab"],
    [data-testid="stTab"] p,
    [data-testid="stTab"] span {
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

    /* ── Chart insight expanders ─────────────────────────────────────────
       A quiet toggle under each chart, never a card: the chart is the point
       and the note is one click away. No box and no fill — a hairline rule
       and a small navy label, legible but recessive, opening onto body text
       set for reading. (The 1px transparent border stays: Streamlit measures
       it when it animates the panel open.) */
    [data-testid="stMain"] [data-testid="stExpander"] {
        background: transparent;
        border: 1px solid transparent;
        border-top: 1px solid #DCE2E9;
        border-radius: 0;
        box-shadow: none;
        margin-top: 0.35rem;
    }
    [data-testid="stMain"] [data-testid="stExpander"] details,
    [data-testid="stMain"] [data-testid="stExpander"] summary,
    [data-testid="stMain"] [data-testid="stExpander"] summary:hover {
        background: transparent;
        border: none;
        border-radius: 0;
        box-shadow: none;
    }
    [data-testid="stMain"] [data-testid="stExpander"] summary {
        padding: 0.42rem 0 0.42rem 0.1rem;
    }
    [data-testid="stMain"] [data-testid="stExpander"] summary p {
        font-family: 'Inter', sans-serif;
        font-size: 0.73rem !important;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #33415A !important;
        margin: 0;
    }
    [data-testid="stMain"] [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
        font-size: 1.1rem !important;
        width: 1.1rem; height: 1.1rem;
        color: #5E6B7E;
        margin-right: 0.3rem !important;
    }
    [data-testid="stMain"] [data-testid="stExpander"] summary:hover p,
    [data-testid="stMain"] [data-testid="stExpander"] summary:hover [data-testid="stIconMaterial"] {
        color: #0A1F3D !important;
    }
    [data-testid="stMain"] [data-testid="stExpanderDetails"] {
        padding: 0.2rem 0.5rem 0.4rem 1rem;
        margin: 0 0 0.5rem 0.25rem;
        border-left: 3px solid #C3CEDB;
    }
    [data-testid="stMain"] [data-testid="stExpanderDetails"] p {
        font-family: 'Inter', sans-serif;
        font-size: 0.9rem;
        line-height: 1.68;
        color: #26303F;
        margin-bottom: 0.65rem;
    }
    [data-testid="stMain"] [data-testid="stExpanderDetails"] strong {
        color: #0A1F3D;
        font-weight: 700;
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
    logo_path = PROJECT_ROOT / "assets" / "brand" / "econhub_logo.jpg" 
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
        '<a class="sb-btn" href="https://shreyasxi.github.io/economics-hub/" target="_blank">System Architecture ↗</a>'
        '<a class="sb-btn" href="https://shreyasxi.github.io/" target="_blank">Academic Website ↗</a>'
        '<hr class="sb-rule-thick">', # CHANGED: Using a thick rule here to firmly separate sections
        unsafe_allow_html=True,
    )

    # ── 4. The Data Matrix ─────────────────────────────────────────────────────
    st.markdown('<p class="sb-section-label">Data Architecture</p>', unsafe_allow_html=True)
    
    st.markdown(
        '<div class="sb-data-row"><span class="sb-data-label">Markets</span><span class="sb-data-val">Yahoo Finance</span></div>'
        '<div class="sb-data-row"><span class="sb-data-label">World</span><span class="sb-data-val">FRED &middot; OECD &middot; BIS</span></div>'
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
                "World":           ("generate_macro.py",        True),
                "India":           ("generate_india.py",        False),
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
        '<a class="substack-cta" href="https://economicshub.substack.com/" target="_blank" rel="noopener">'
            '<span class="substack-cta__label">Subscribe on Substack</span>'
            '<svg class="substack-cta__arrow" viewBox="0 0 16 16" fill="none" stroke="#FFFFFF" '
                'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                '<path d="M4.5 11.5 11.5 4.5M5.5 4.5h6v6"/>'
            '</svg>'
        '</a>'
    '</div>'
    '<div class="insti-rule"></div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_weekly, tab_world, tab_india, tab_rbi = st.tabs(
    ["Weekly Markets", "World", "India", "RBI Sentinel"]
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _render_chart(chart_path: Path) -> None:
    st.image(
        str(chart_path),
        caption=clean_title(chart_path.name),
        use_container_width=True,
    )
    insight = get_insight(chart_path.name)
    if insight:
        with st.expander("Chart insights"):
            st.markdown(insight)


def _render_grid(charts: list[Path], cols: int = 2, center_odd: bool = False) -> None:
    """Charts in a grid; with center_odd, a last chart that would sit alone is centred instead of left in half a row."""
    lone = charts[-1] if center_odd and cols == 2 and len(charts) % 2 == 1 else None
    grid = charts[:-1] if lone else charts
    if grid:
        columns = st.columns(cols)
        for i, chart_path in enumerate(grid):
            with columns[i % cols]:
                _render_chart(chart_path)
    if lone:
        _, col_mid, _ = st.columns([1, 2, 1])
        with col_mid:
            _render_chart(lone)


def _render_wide(chart_path: Path) -> None:
    """A multi-panel chart drawn wider than a grid cell so its panels stay legible."""
    _, col_mid, _ = st.columns([1, 5, 1])
    with col_mid:
        _render_chart(chart_path)
    
# Fields the RBI tab reads from the cycle brief beyond the original set.
_BRIEF_KEYS = frozenset({
    "previous_cycle", "facts", "previous_facts", "last_rate_move",
    "decision_streak", "signals", "previous_signals",
})


def _load_cycle_brief() -> dict | None:
    """
    The latest cycle brief, guaranteed to come from the current code.

    Streamlit Cloud applies a push by re-running app.py inside the same
    Python process, so modules imported earlier stay in memory at their old
    version. A new app.py then calls an old get_latest_cycle_brief() and the
    fields added since are silently absent. If any expected field is missing,
    reload the modules that build the brief and fetch it again.
    """
    brief = _manager.get_latest_cycle_brief()
    if brief is not None and not _BRIEF_KEYS <= brief.keys():
        importlib.reload(_policy_facts)
        importlib.reload(_manager)
        brief = _manager.get_latest_cycle_brief()
    return brief


def _stance_dir(score: float) -> str:
    return "hawkish" if score > 0.05 else ("dovish" if score < -0.05 else "neutral")


def _decision_strip_html(brief: dict) -> str:
    """
    The RBI tab's decision strip: rate and decision, the Sentinel reading
    and its change, the MPC's own projections and their revision, and the
    next meeting — four labelled groups in one row.

    Every figure comes from the database or the Resolution text; anything
    missing renders as a dash rather than being inferred.
    """
    dash = '<span class="dx-missing">&mdash;</span>'
    facts = brief.get("facts") or {}
    prev_facts = brief.get("previous_facts") or {}
    prev_label = (
        datetime.strptime(brief["previous_cycle"], "%Y-%m-%d").strftime("%b %Y")
        if brief.get("previous_cycle") else "previous meeting"
    )

    def cell(label: str, value: str, sub: str = "") -> str:
        return (
            '<div class="dx-cell">'
            f'<span class="dx-label">{label}</span>'
            f'<span class="dx-value">{value}</span>'
            f'<span class="dx-sub">{sub or "&nbsp;"}</span>'
            '</div>'
        )

    def group(label: str, cells: list[str]) -> str:
        return (
            '<div class="dx-group">'
            f'<p class="dx-group-label">{label}</p>'
            f'<div class="dx-cells" style="--n:{len(cells)}">{"".join(cells)}</div>'
            '</div>'
        )

    def arrow(delta: float) -> str:
        return "&uarr;" if delta > 0 else ("&darr;" if delta < 0 else "&rarr;")

    # ── Policy decision ──
    rate = brief.get("repo_rate_pct")
    rate_value = f'{rate:.2f}<span class="dx-unit">%</span>' if rate is not None else dash
    action = (brief.get("rate_action") or "").lower()
    bps = brief.get("rate_change_bps")
    move = brief.get("last_rate_move")
    if action == "hold":
        status_value = "Unchanged"
        if move:
            _md = datetime.strptime(move["policy_cycle"], "%Y-%m-%d")
            status_sub = (
                f'Last move: {move["rate_action"]} {abs(int(move["rate_change_bps"] or 0))} bps, '
                f'{_md:%b %Y}'
            )
        else:
            status_sub = "No change on record"
    elif action in ("hike", "cut") and bps:
        status_value = (
            f'<span class="mpc-d-{action}">{"Raised" if action == "hike" else "Cut"} '
            f'{abs(int(bps))}<span class="dx-unit">bps</span></span>'
        )
        status_sub = f"From {rate - bps / 100:.2f}%" if rate is not None else ""
    else:
        status_value, status_sub = dash, ""
    stated = facts.get("stated_stance")
    rate_sub = f"Stated stance: {stated.capitalize()}" if stated else ""

    # ── Sentinel reading ──
    score = brief.get("composite_overall_score")
    prev_score = brief.get("previous_score")
    if score is not None:
        sdir = _stance_dir(score)
        score_value = f'<span class="mpc-{sdir}">{score:+.2f}</span>'
        score_sub = f'<b class="mpc-{sdir}">{sdir.title()}</b> on a &minus;1 to +1 scale'
    else:
        score_value, score_sub = dash, ""
    if score is not None and prev_score is not None:
        chg = score - prev_score
        cdir = _stance_dir(chg * 20)  # colour any visible move, not only |0.05|+
        chg_value = f'<span class="mpc-{cdir}">{arrow(chg)} {abs(chg):.2f}</span>'
        chg_sub = f"vs {prev_label} ({prev_score:+.2f})"
    else:
        chg_value, chg_sub = dash, "First scored cycle"

    # ── RBI projections ──
    def projection(key: str) -> tuple[str, str, str]:
        cur, old = facts.get(key), prev_facts.get(key)
        if not cur:
            return "", dash, ""
        fy = f'FY{cur["fy"][-2:]}'
        value = f'{cur["value"]:.1f}<span class="dx-unit">%</span>'
        if old and old["fy"] == cur["fy"]:
            d = round(cur["value"] - old["value"], 1)
            sub = (
                f'{arrow(d)} {abs(d):.1f} pp vs {prev_label}' if d
                else f"Unchanged vs {prev_label}"
            )
        else:
            sub = f"First projection for {fy}"
        return fy, value, sub

    cpi_fy, cpi_value, cpi_sub = projection("cpi")
    gdp_fy, gdp_value, gdp_sub = projection("gdp")
    proj_fy = cpi_fy or gdp_fy

    # ── Next meeting ──
    nxt = facts.get("next_meeting")
    if nxt:
        s, e = nxt["start"], nxt["end"]
        if s == e:
            when = f"{e.day} {e:%b %Y}"
        elif s.month == e.month:
            when = f"{s.day}&ndash;{e.day} {e:%b %Y}"
        else:
            when = f"{s.day} {s:%b} &ndash; {e.day} {e:%b %Y}"
        days = (e - date.today()).days
        if s > date.today():
            next_sub = f"Decision in {days} day{'s' if days != 1 else ''}"
        elif days >= 0:
            next_sub = "Meeting in session"
        else:
            next_sub = "Decision awaited in data"
        next_value = f'<span class="dx-date">{when}</span>'
    else:
        next_value, next_sub = dash, ""

    return (
        '<div class="dx">'
        + group("Policy decision", [
            cell("Repo rate", rate_value, rate_sub),
            cell("Status", status_value, status_sub),
        ])
        + group("Sentiment", [
            cell("Stance score", score_value, score_sub),
            cell("Change", chg_value, chg_sub),
        ])
        + group(f"RBI projections{' &middot; ' + proj_fy if proj_fy else ''}", [
            cell("CPI inflation", cpi_value, cpi_sub),
            cell("Real GDP growth", gdp_value, gdp_sub),
        ])
        + group("Next meeting", [
            cell("MPC dates", next_value, next_sub),
        ])
        + '</div>'
    )


_DIMENSIONS = {
    # key: (label, what -1 / +1 mean, reading when the score rises, when it falls)
    "inflation_stance":   ("Inflation concern", "−1 unconcerned · +1 alarmed",
                           "more alarmed", "less concerned"),
    "growth_stance":      ("Growth assessment", "−1 worried about growth · +1 confident",
                           "more confident", "more concerned"),
    "liquidity_stance":   ("Liquidity stance", "−1 easy liquidity · +1 tight",
                           "tighter", "easier"),
    "rate_guidance":      ("Rate guidance", "−1 cuts ahead · +1 hikes ahead",
                           "tilting toward hikes", "tilting toward cuts"),
    "fx_external_stance": ("External stance", "−1 tolerant of rupee weakness · +1 defensive",
                           "more defensive", "more tolerant"),
}
_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}


def _signed(x: float) -> str:
    """+0.42 / −0.02 with a true minus sign."""
    return f"{x:+.2f}".replace("-", "&minus;")


def _weighted_dimensions(signals: dict) -> dict:
    """Sub-dimension scores combined with the composite's document weights."""
    out = {}
    for dim in _DIMENSIONS:
        parts = [
            (_DOC_WEIGHTS[t], sig[dim]) for t, sig in signals.items()
            if t in _DOC_WEIGHTS and sig.get(dim) is not None
        ]
        if parts:
            total = sum(w for w, _ in parts)
            out[dim] = sum(w * v for w, v in parts) / total
    return out


def _takeaways_html(brief: dict) -> str:
    """
    Key takeaways for the cycle, built only from stored data so every
    meeting gets the same six lines without another model call:
    the decision, the tone against it, what moved, the MPC's projections,
    the analyst's bottom line, and one verbatim line from the most
    emphatic document.
    """
    facts = brief.get("facts") or {}
    prev_facts = brief.get("previous_facts") or {}
    if brief.get("previous_cycle"):
        _month = datetime.strptime(brief["previous_cycle"], "%Y-%m-%d").strftime("%B")
        prev_in, prev_since = f"in {_month}", f"since {_month}"
    else:
        prev_in, prev_since = "at the previous meeting", "since the previous meeting"
    rows = []

    # Decision
    rate, action = brief.get("repo_rate_pct"), (brief.get("rate_action") or "").lower()
    streak = brief.get("decision_streak") or 0
    stated = facts.get("stated_stance")
    if rate is not None and action:
        if action == "hold":
            lead = f"Repo rate held at <b>{rate:.2f}%</b>"
            if streak > 1:
                lead += f" for a {_ORDINAL.get(streak, f'{streak}th')} straight meeting"
        else:
            bps = abs(int(brief.get("rate_change_bps") or 0))
            lead = f'Repo rate {"raised" if action == "hike" else "cut"} {bps} bps to <b>{rate:.2f}%</b>'
        if stated:
            lead += f"; {stated} stance retained" if action == "hold" else f"; stance: {stated}"
        rows.append(("Decision", lead + "."))

    # Tone
    score, prev = brief.get("composite_overall_score"), brief.get("previous_score")
    if score is not None:
        sdir = _stance_dir(score)
        text = f'Language reads <b class="mpc-{sdir}">{sdir} ({score:+.2f})</b>'
        if stated and stated != sdir:
            text += f", firmer than the stated {stated} stance" if sdir == "hawkish" and stated in ("neutral", "accommodative") \
                else f", at odds with the stated {stated} stance"
        if prev is not None:
            verb = "up" if score > prev else ("down" if score < prev else "unchanged")
            text += f"; {verb} from {prev:+.2f} {prev_in}" if verb != "unchanged" else f"; unchanged {prev_since}"
        rows.append(("Tone", text + "."))

    # What moved
    cur_dims = _weighted_dimensions(brief.get("signals") or {})
    old_dims = _weighted_dimensions(brief.get("previous_signals") or {})
    moves = sorted(
        ((d, old_dims[d], cur_dims[d]) for d in cur_dims if d in old_dims),
        key=lambda m: -abs(m[2] - m[1]),
    )
    moves = [m for m in moves if abs(m[2] - m[1]) >= 0.10][:2]
    if moves:
        parts = []
        for d, old, new in moves:
            label, scale, up, down = _DIMENSIONS[d]
            # The figures carry a hover note giving the sub-dimension's scale.
            parts.append(
                f'<b>{label if not parts else label.lower()}</b> '
                f'<span class="mpc-tk-fig" title="{label}: {scale}">{_signed(old)} &rarr; {_signed(new)}</span> '
                f'({up if new > old else down})'
            )
        rows.append(("Shift", " and ".join(parts) + f" {prev_since}."))
    elif old_dims:
        rows.append(("Shift", "No sub-dimension moved by more than 0.10 since the previous meeting."))

    # Projections
    proj = []
    for key, name in (("cpi", "CPI"), ("gdp", "GDP growth")):
        cur, old = facts.get(key), prev_facts.get(key)
        if not cur:
            continue
        fy = f'FY{cur["fy"][-2:]}'
        if old and old["fy"] == cur["fy"] and round(cur["value"] - old["value"], 1):
            verb = "raised" if cur["value"] > old["value"] else "trimmed"
            proj.append(f'{fy} {name} {verb} to <b>{cur["value"]:.1f}%</b> from {old["value"]:.1f}%')
        elif old and old["fy"] == cur["fy"]:
            proj.append(f'{fy} {name} kept at <b>{cur["value"]:.1f}%</b>')
        else:
            proj.append(f'{fy} {name} projected at <b>{cur["value"]:.1f}%</b>')
    if proj:
        text = "; ".join(proj)
        rows.append(("Outlook", text[0].upper() + text[1:] + "."))

    # Implication: the opening sentence of the narrative's "Practical
    # takeaway" paragraph, which the scoring prompt requires on every
    # document and which states the analyst's bottom line first.
    narrative = brief.get("composite_narrative") or ""
    m = re.search(r"Practical takeaway:\*{0,2}\s*(.+)", narrative, re.S)
    if m:
        body = " ".join(m.group(1).replace("**", "").split())
        # Split at a sentence end followed by a capital, so "5.25 per cent" and
        # "Q3:2026-27" do not break the sentence early.
        first = re.split(r"(?<=[.!?])\s+(?=[A-Z])", body, maxsplit=1)[0]
        if first:
            rows.append(("Implication", first))

    # In their words: first key phrase of the document leaning furthest
    # in the composite's direction
    signals = brief.get("signals") or {}
    if signals and score is not None:
        doc_type, sig = max(
            signals.items(),
            key=lambda kv: (kv[1].get("overall_score") or 0) * (1 if score >= 0 else -1),
        )
        phrases = sig.get("key_phrases") or []
        if phrases:
            names = {DOC_MINUTES: "Minutes", DOC_RESOLUTION: "Resolution", DOC_GOVERNOR: "Governor&rsquo;s Statement"}
            quote = phrases[0].strip().rstrip(".")
            rows.append((
                "In their words",
                f'<q>{quote}</q> <span class="mpc-tk-src">&mdash; {names.get(doc_type, doc_type)}</span>',
            ))

    if not rows:
        return ""
    return (
        '<ul class="mpc-tk">'
        + "".join(
            f'<li><span class="mpc-tk-label">{label}</span><span class="mpc-tk-text">{text}</span></li>'
            for label, text in rows
        )
        + "</ul>"
    )


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


# ── World tab helpers ──────────────────────────────────────────────────────

def _world_config():
    """
    config/world_settings.py, reloaded when the file changes: Streamlit Cloud
    re-runs app.py after a push without re-importing modules, so a yearly
    meeting-calendar update would otherwise not show until a reboot.
    """
    mtime = Path(_world_settings.__file__).stat().st_mtime
    if getattr(_world_settings, "_loaded_mtime", None) != mtime:
        importlib.reload(_world_settings)
        _world_settings._loaded_mtime = mtime
    return _world_settings


def _load_world_snapshot(charts: list[Path]) -> dict | None:
    """world_snapshot.json from the same folder as the World charts."""
    if not charts:
        return None
    path = charts[0].parent / "world_snapshot.json"
    if not path.exists():
        return None
    import json
    with path.open() as fh:
        return json.load(fh)


def _fmt_day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _next_lpr_date(today: date) -> date:
    """
    Next Loan Prime Rate fixing: the 20th, moved to the Monday when it falls on
    a weekend. Chinese public holidays can move it further, so the page says
    "around".
    """
    def fixing(year: int, month: int) -> date:
        d = date(year, month, 20)
        return d + timedelta(days=(7 - d.weekday()) % 7) if d.weekday() >= 5 else d

    this_month = fixing(today.year, today.month)
    if this_month >= today:
        return this_month
    nxt = today.replace(day=1) + timedelta(days=32)
    return fixing(nxt.year, nxt.month)


def _next_meeting(meetings: list[str] | None) -> date | None:
    today = date.today()
    for m in meetings or []:
        d = date.fromisoformat(m)
        if d >= today:
            return d
    return None


def _move_phrase(bps: int, when: date) -> str:
    verb, cls = ("hike", "mpc-d-hike") if bps > 0 else ("cut", "mpc-d-cut")
    return f'Last move: <b class="{cls}">{verb} {abs(bps)} bps</b>, {when:%b %Y}'


def _central_bank_strip_html(snapshot: dict, brief: dict | None) -> str:
    """Six tiles: rate, last move and next decision for each bank. Missing data renders as a dash."""
    cfg = _world_config()
    dash = '<span class="dx-missing">&mdash;</span>'
    fetched = {b["id"]: b for b in snapshot.get("central_banks", [])}
    tiles = []
    for bank in cfg.CENTRAL_BANKS:
        rate, move, nxt = dash, "", ""
        if bank["id"] == "rbi":
            if brief and brief.get("repo_rate_pct") is not None:
                rate = f'{brief["repo_rate_pct"]:.2f}<span class="dx-unit">%</span>'
                lm = brief.get("last_rate_move")
                if lm and lm.get("rate_change_bps"):
                    bps = int(lm["rate_change_bps"])
                    bps = abs(bps) if lm.get("rate_action") == "hike" else -abs(bps)
                    move = _move_phrase(bps, date.fromisoformat(lm["policy_cycle"]))
                facts = brief.get("facts") or {}
                nm = facts.get("next_meeting")
                if nm and nm["end"] >= date.today():
                    nxt = f'Next: {_fmt_day(nm["end"])}'
        else:
            b = fetched.get(bank["id"], {})
            if b.get("status") == "ok":
                rate = f'{b["display"]}<span class="dx-unit">%</span>'
                if b.get("last_move"):
                    move = _move_phrase(b["last_move"]["bps"], date.fromisoformat(b["last_move"]["date"]))
            if bank["id"] == "pboc":
                nxt = f"Next: around {_fmt_day(_next_lpr_date(date.today()))}"
            else:
                d = _next_meeting(bank["meetings"])
                nxt = f"Next: {_fmt_day(d)}" if d else "Next date not yet published"
        tiles.append(
            f'<div class="wcb-tile{" is-india" if bank["id"] == "rbi" else ""}">'
            f'<div class="wcb-bank" title="{bank["name"]}">{bank["short"]}</div>'
            f'<div class="wcb-rate">{rate}</div>'
            f'<div class="wcb-label">{bank["rate_label"]}</div>'
            f'<div class="wcb-sub">{move or "&nbsp;"}</div>'
            f'<div class="wcb-next">{nxt or "&nbsp;"}</div>'
            '</div>'
        )
    return '<div class="wcb">' + "".join(tiles) + "</div>"


def _calendar_html(snapshot: dict, brief: dict | None, days: int = 35) -> str:
    """Central bank decisions and US data releases in the next `days` days."""
    cfg = _world_config()
    today, horizon = date.today(), date.today() + timedelta(days=days)
    events: list[tuple[date, str, str, str]] = []
    for bank in cfg.CENTRAL_BANKS:
        for m in bank["meetings"] or []:
            d = date.fromisoformat(m)
            if today <= d <= horizon:
                events.append((d, bank["meeting_label"], "", "wcal-cb"))
    lpr = _next_lpr_date(today)
    if lpr <= horizon:
        events.append((lpr, "China loan prime rate", "around this date", "wcal-cb"))
    if brief:
        nm = (brief.get("facts") or {}).get("next_meeting")
        if nm and today <= nm["end"] <= horizon:
            events.append((nm["end"], "RBI MPC decision", "", "wcal-cb wcal-in"))
    for e in snapshot.get("calendar", []):
        d = date.fromisoformat(e["date"])
        if today <= d <= horizon:
            events.append((d, e["label"], "", ""))
    if not events:
        return '<p class="w-foot">No scheduled decisions or US releases in the next five weeks.</p>'
    events.sort(key=lambda e: (e[0], "wcal-cb" not in e[3]))
    items = "".join(
        f'<li class="{cls}"><span class="wcal-date">{d:%a %d %b}</span>'
        f'<span class="wcal-what">{label}{f"<small>{note}</small>" if note else ""}</span></li>'
        for d, label, note, cls in events
    )
    return f'<ul class="wcal">{items}</ul>'


def _scoreboard_html(snapshot: dict) -> str:
    """Six economies by six indicators; each cell shows its own period and change."""
    cfg = _world_config()
    cols = cfg.SCOREBOARD_COLUMNS

    def fmt_period(period: str, column: str, country: str) -> str:
        if column == "fx_ytd":
            return "DXY, year to date" if country == "US" else "year to date"
        if column == "policy_rate" and country == "IN":
            return f"{datetime.strptime(period, '%Y-%m-%d'):%b} MPC"
        if len(period) == 7:
            return datetime.strptime(period, "%Y-%m").strftime("%b")
        return datetime.strptime(period, "%Y-%m-%d").strftime("%-d %b")

    def cell_html(country: str, column: str, cell: dict) -> str:
        title = f' title="{cell.get("source", "")}"'
        status = cell.get("status")
        if status == "awaiting":
            return f'<td{title}><span class="wsb-na">awaiting entry</span></td>'
        if status == "unavailable" or cell.get("value") is None:
            return f'<td{title}><span class="wsb-na">source failed</span></td>'
        v = cell["value"]
        if column == "fx_ytd":
            text = f"{v:+.1f}%"
        elif column == "policy_rate":
            text = f'{cell.get("display") or f"{v:.2f}"}%'
        elif column == "ten_year":
            text = f"{v:.2f}%"
        elif column == "mfg_pmi":
            text = f"{v:.1f}"
        else:
            text = f"{v:.1f}%"

        meta = [fmt_period(cell["period"], column, country)]
        ch = cell.get("change")
        if ch is not None:
            if column == "ten_year":
                bps = round(ch * 100)
                meta.append(f'<span class="wsb-flat">{bps:+d} bps / 1m</span>' if bps else '<span class="wsb-flat">unch 1m</span>')
            else:
                good = cols[column]["good"]
                if abs(ch) < 0.05:
                    meta.append('<span class="wsb-flat">unch</span>')
                else:
                    cls = "wsb-flat" if good is None else ("wsb-good" if (ch > 0) == (good == "up") else "wsb-bad")
                    meta.append(f'<span class="{cls}">{"&#9650;" if ch > 0 else "&#9660;"} {abs(ch):.1f}</span>')
        if column == "fx_ytd" and country != "US":
            cls = "wsb-good" if v > 0 else "wsb-bad"
            text = f'<span class="{cls}">{text}</span>'
        stale = status == "stale"
        if stale:
            meta.append('<span class="wsb-flag">not updated</span>')
        return (f'<td class="{"wsb-stale" if stale else ""}"{title}>'
                f'<span class="wsb-v">{text}</span><span class="wsb-m">{" &middot; ".join(meta)}</span></td>')

    head = "<th>Economy</th>" + "".join(f"<th>{c['label']}</th>" for c in cols.values())
    body = ""
    for row in snapshot.get("scoreboard", []):
        cells = "".join(cell_html(row["country"], k, row["cells"][k]) for k in cols)
        body += (f'<tr class="{"is-india" if row["country"] == "IN" else ""}">'
                 f'<th scope="row">{row["label"]}</th>{cells}</tr>')
    return f'<div class="wsb-wrap"><table class="wsb"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _tab_header_html(title: str, dek: str, meta_label: str, meta_value: str) -> str:
    return (
        '<div class="rbi-head">'
        '<div class="rbi-head-text">'
        f'<p class="rbi-head-title">{title}</p>'
        f'<p class="rbi-head-dek">{dek}</p>'
        '</div>'
        '<div class="rbi-head-meta">'
        f'<span class="rbi-head-meta-label">{meta_label}</span>'
        f'<span class="rbi-head-meta-value">{meta_value}</span>'
        '</div>'
        '</div>'
    )


# ── Weekly Markets tab ─────────────────────────────────────────────────────

with tab_weekly:
    charts, date_label = get_charts("weekly")

    if not charts:
        st.warning(
            "No weekly charts found. Run **generate_weekly.py** locally "
            "or trigger the Weekly Markets workflow on GitHub Actions."
        )
    else:
        st.markdown(
            _tab_header_html(
                "The Week in Markets",
                "Weekly moves and the trends behind equities, bonds, currencies, commodities "
                "and crypto across the major markets.",
                "Last updated", _fmt_day(datetime.strptime(date_label, "%Y-%m-%d").date()),
            ),
            unsafe_allow_html=True,
        )

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

        # 2. Commodities
        commo_kws = ["commodities", "brent", "wti", "agri", "oil", "gold", "copper"]
        commo = [c for c in charts if any(k in c.name for k in commo_kws) and "btc" not in c.name]
        charts = [c for c in charts if c not in commo]
        if commo:
            _section("Commodities")
            _render_grid(commo)

        # 3. Fixed Income & Credit
        rates_kws = ["yield", "credit_spreads", "bond_etf"]
        rates = [c for c in charts if any(k in c.name for k in rates_kws)]
        charts = [c for c in charts if c not in rates]
        if rates:
            _section("Fixed Income & Credit")
            _render_grid(rates)

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
        risk_kws = ["stock_bond_correlation", "defensives_cyclicals", "risk_appetite", "breadth", "gold_spx", "copper_gold"]
        risk = [c for c in charts if any(k in c.name for k in risk_kws)]
        charts = [c for c in charts if c not in risk]
        if risk:
            _section("Cross-Asset Risk & Breadth")
            _render_grid(risk)


        # 8. Emerging Markets
        em_kws = ["em_fx", "em_equity", "india_vs_em", "stress_monitor"]
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


# ── World tab ──────────────────────────────────────────────────────────────

with tab_world:
    charts, date_label = get_charts("macro")
    snapshot = _load_world_snapshot(charts)

    if not charts or snapshot is None:
        st.warning(
            "No World data found. Run **generate_macro.py** locally "
            "or trigger the World workflow on GitHub Actions."
        )
    else:
        _as_of = datetime.strptime(snapshot["generated_at"], "%Y-%m-%d %H:%M")
        st.markdown(
            _tab_header_html(
                "The World Economy",
                "Central banks, growth and inflation, equity valuations and country risk "
                "across the world&rsquo;s major economies.",
                "Data as of", _fmt_day(_as_of.date()),
            ),
            unsafe_allow_html=True,
        )
        if snapshot.get("problems"):
            st.warning(
                "This snapshot was built with source problems, so some figures may be missing:\n\n"
                + "\n".join(f"- {p}" for p in snapshot["problems"])
            )
        world_brief = _load_cycle_brief()

        # 1. Central banks
        st.markdown('<p class="w-eyebrow">Central banks</p>', unsafe_allow_html=True)
        st.markdown(_central_bank_strip_html(snapshot, world_brief), unsafe_allow_html=True)

        # 2. Regime and calendar
        regime, charts = _pop_summary(charts, ["world_regime"])
        col_regime, col_cal = st.columns([3, 2], gap="large")
        with col_regime:
            st.markdown('<p class="w-eyebrow">Where each economy is heading</p>', unsafe_allow_html=True)
            if regime:
                st.image(str(regime), use_container_width=True)
                _regime_insight = get_insight(regime.name)
                if _regime_insight:
                    with st.expander("Chart insights"):
                        st.markdown(_regime_insight)
        with col_cal:
            st.markdown('<p class="w-eyebrow is-ruled">Coming up &middot; next five weeks</p>', unsafe_allow_html=True)
            st.markdown(_calendar_html(snapshot, world_brief), unsafe_allow_html=True)

        # 3. Scoreboard
        _section("Six Economies at a Glance")
        st.markdown(_scoreboard_html(snapshot), unsafe_allow_html=True)
        st.markdown(
            '<p class="w-foot">Change beside each figure is vs the previous month (10-year: vs a month earlier). '
            'Green = better, red = worse: rising inflation or unemployment is red, a stronger currency against '
            'the dollar is green. The US currency cell is the dollar index itself. Euro area 10-year = German Bund.</p>',
            unsafe_allow_html=True,
        )

        # 4. United States
        us_kws = ["inflation", "labour", "balance_sheet"]
        us_charts = [c for c in charts if any(k in c.name for k in us_kws)]
        charts = [c for c in charts if c not in us_charts]
        if us_charts:
            _section("United States")
            _render_grid(us_charts, center_odd=True)

        # 5. US equity valuations
        valuations = [c for c in charts if any(k in c.name for k in ["macro_cape", "equity_risk_premium"])]
        charts = [c for c in charts if c not in valuations]
        if valuations:
            _section("US Equity Valuations")
            _render_grid(valuations, center_odd=True)

        # 5b. Country risk (Damodaran's country and regional equity risk premiums)
        country_risk = [c for c in charts if any(k in c.name for k in ["country_erp", "regional_erp", "ratings_vs_markets"])]
        charts = [c for c in charts if c not in country_risk]
        if country_risk:
            _section("Country Risk")
            _render_grid(country_risk, center_odd=True)

        # 6. Emerging markets
        em = [c for c in charts if "macro_em_" in c.name]
        charts = [c for c in charts if c not in em]
        if em:
            _section("Emerging Markets")
            _render_grid(em, center_odd=True)

        # 7. Global growth: one wide ranked chart of every OECD leading indicator
        growth = [c for c in charts if "oecd_cli" in c.name]
        charts = [c for c in charts if c not in growth]
        if growth:
            _section("Global Growth")
            for chart_path in growth:
                _render_wide(chart_path)

        # Catch-all
        if charts:
            _section("Other")
            _render_grid(charts)


# ── India tab ──────────────────────────────────────────────────────────────

with tab_india:
    charts, date_label = get_charts("india")

    if not charts:
        st.warning(
            "No India charts found. Run **generate_india.py** locally "
            "or trigger the India Dashboard workflow on GitHub Actions."
        )
    else:
        st.markdown(
            _tab_header_html(
                "The Indian Economy",
                "Growth, prices, money, trade, capital flows and public finances, from RBI, MoSPI, "
                "NSDL and CAG data. Charts reflect the latest data committed to the repository.",
                "Edition", datetime.strptime(date_label, "%Y-%m").strftime("%B %Y"),
            ),
            unsafe_allow_html=True,
        )

        summary, charts = _pop_summary(charts, ["india_table", "05_india"])
        if summary:
            _render_summary(summary)

        # 1. High-Frequency Growth Indicators
        growth_kws = ["pmi", "iip"]
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

        # 3. Monetary Conditions
        monetary_kws = ["money", "supply", "credit", "deposit", "m3"]
        monetary = [c for c in charts if any(k in c.name for k in monetary_kws)]
        charts = [c for c in charts if c not in monetary]
        if monetary:
            _section("Monetary Conditions")
            _render_grid(monetary)

        # 4. External Sector
        external_kws = ["forex", "reserves", "trade", "export", "import"]
        external = [c for c in charts if any(k in c.name for k in external_kws)]
        charts = [c for c in charts if c not in external]
        if external:
            _section("External Sector")
            _render_grid(external)

        # 5. Capital Flows (FPI flows, and the NIFTY IT index moved here from Weekly Markets)
        flows_kws = ["flows", "fii", "fpi", "portfolio", "nifty"]
        flows = [c for c in charts if any(k in c.name for k in flows_kws)]
        charts = [c for c in charts if c not in flows]
        if flows:
            _section("Capital Flows")
            _render_grid(flows)

        # 6. Fiscal Policy & Public Finances
        fiscal_kws = ["fiscal", "deficit", "capex", "expenditure", "gst", "tax", "revenue", "consolidation"]
        fiscal = [c for c in charts if any(k in c.name for k in fiscal_kws)]
        charts = [c for c in charts if c not in fiscal]
        if fiscal:
            _section("Fiscal Policy & Public Finances")
            _render_grid(fiscal)

        # Catch-all
        if charts:
            _section("Other")
            _render_grid(charts)


# ── RBI Sentinel tab ────────────────────────────────────────────────────────

with tab_rbi:
    charts, date_label = get_charts("rbi_sentinel")

    if not charts:
        st.warning(
            "No RBI Sentinel charts found. Run **generate_rbi_sentinel.py** locally "
            "or trigger the RBI Sentinel workflow on GitHub Actions."
        )
    else:
        brief = _load_cycle_brief()

        # ── Header: title, one-line standfirst, latest meeting ──
        _meeting_meta = ""
        if brief:
            _d = datetime.strptime(brief["meeting_date"], "%Y-%m-%d")
            _meeting_meta = (
                '<div class="rbi-head-meta">'
                '<span class="rbi-head-meta-label">Latest MPC meeting</span>'
                f'<span class="rbi-head-meta-value">{_d.day} {_d.strftime("%B %Y")}</span>'
                '</div>'
            )
        st.markdown(
            '<div class="rbi-head">'
            '<div class="rbi-head-text">'
            '<p class="rbi-head-title">The RBI Sentinel</p>'
            '<p class="rbi-head-dek">Quantitative tracking of India&rsquo;s monetary policy stance '
            'across all three classes of MPC communication: the Resolution, the Minutes '
            'and the Governor&rsquo;s Statement.</p>'
            '</div>'
            f'{_meeting_meta}'
            '</div>',
            unsafe_allow_html=True,
        )

        # 2. The Technical Expander (The Methodology "Button")
        with st.expander("⚙️ Scoring Methodology & Pipeline Architecture", expanded=False):
            st.markdown(
                "### Scoring Methodology\n\n"
                "**Corpus**\n\n"
                "The engine reads three official documents for every Monetary Policy Committee (MPC) "
                "decision: the *Monetary Policy Resolution* and the *Governor's Statement*, both published "
                "on the decision date, and the *MPC Minutes*, published about 14 days later. Documents are "
                "grouped by **policy cycle**, so Minutes released a fortnight after a meeting are scored "
                "against the decision they record rather than as a separate event. The current corpus is "
                "159 documents across 61 cycles, October 2016 to date, each scored from its full text — "
                "no excerpt or summary is used.\n\n"
                "**Why standard lexicons are insufficient**\n\n"
                "Standard financial word-lists, including the widely cited Loughran-McDonald dictionary "
                "(see [Loughran & McDonald, 2011](https://doi.org/10.1111/j.1540-6261.2010.01625.x)), "
                "perform well on corporate filings but systematically fail on central bank communication. "
                "Policymakers rely on deliberate hedging: *\"remaining vigilant on inflation\"* conveys "
                "hawkish intent without a single term from a standard dictionary. The same problem is "
                "documented for FOMC statements "
                "(see [Lucca & Trebbi, 2009](https://www.nber.org/papers/w15367)), where context and "
                "negation handling are prerequisites, not refinements.\n\n"
                "**Stage 1 — Domain lexicon (10% of each document score)**\n\n"
                "A bespoke RBI lexicon of 62 hawkish and 61 dovish phrases, each weighted by diagnostic "
                "value. A 5-word negation window reverses a phrase's polarity when a negation precedes it "
                "(*\"not concerned about inflation\"* scores dovish). The count is normalised by "
                "tanh(score / √word\\_count × 3) so long and short documents are comparable.\n\n"
                "*Why only 10%:* across the corpus the lexicon's scores have a standard deviation of 0.263 "
                "against the language model's 0.587 — tanh normalisation compresses it toward zero. A "
                "heavier weight would drag every confident reading toward the midpoint. It is kept as an "
                "independent, fully deterministic cross-check on the model.\n\n"
                "**Stage 2 — Claude Opus 5 (90% of each document score)**\n\n"
                "Each document is read in full by **Claude Opus 5**, Anthropic's frontier Opus-class model, under "
                "a structured prompt. Scoring a policy document is a judgement task rather than an "
                "extraction task, and model choice changes the answer: in testing, Opus correctly read "
                "*\"downside risks to growth\"* as dovish where a smaller model read it as marginally "
                "hawkish. Large language models substantially outperform lexicon methods on nuanced "
                "financial text (see [López-Lira & Tang, 2023](https://doi.org/10.2139/ssrn.4412788)). "
                "Documents are sent whole — up to 32,000 tokens, which clears the longest Minutes — and "
                "the model returns validated JSON: an overall score, five sub-dimension scores, a "
                "confidence estimate, the 3–5 phrases that most influenced its reading, and a "
                "two-paragraph narrative (*How to read this document* and *Practical takeaway*). "
                "Every score in the current model version (`hybrid_v2`) was produced by Opus 5.\n\n"
                "*Failure handling:* if the model cannot return a valid score after a re-prompt, the "
                "document is left unscored. It is never silently replaced by a lexicon-only number.\n\n"
                "*Conflict detection:* when |lexicon − model| > 0.60 the document is flagged and its stored "
                "confidence capped at 0.45. This fires on about 9% of documents; a sudden rise across many "
                "documents signals an upstream change — a revised prompt, a model substitution, or a shift "
                "in how the RBI writes.\n\n"
                "**Composite meeting score**\n\n"
                "Document scores are combined into one score per policy cycle with fixed weights:\n\n"
                '<table class="method-table"><thead><tr>'
                '<th>Document</th><th>Weight</th><th>Rationale</th></tr></thead><tbody>'
                '<tr><td>MPC Minutes</td><td>50%</td><td>Individual member deliberation, reasoning and dissent</td></tr>'
                '<tr><td>Monetary Policy Resolution</td><td>35%</td><td>The formal committee decision statement</td></tr>'
                '<tr><td>Governor&rsquo;s Statement</td><td>15%</td><td>The Governor&rsquo;s forward-guidance overlay</td></tr>'
                '</tbody></table>\n\n'
                "**Reading the scores**\n\n"
                "Every score runs from **−1.0** to **+1.0**. The overall and composite scores measure "
                "policy tone: −1 is maximally dovish (leaning toward cuts), +1 maximally hawkish (leaning "
                "toward hikes), 0 balanced. A score near zero is not an absence of view; it often means the "
                "committee is actively weighing competing risks. The five sub-dimensions each isolate one "
                "part of the committee's reasoning:\n\n"
                '<table class="method-table"><thead><tr>'
                '<th>Sub-dimension</th><th>&minus;1.0 means</th><th>+1.0 means</th></tr></thead><tbody>'
                '<tr><td>Inflation concern</td><td>Unconcerned about inflation</td><td>Alarmed about inflation</td></tr>'
                '<tr><td>Growth assessment</td><td>Worried about India&rsquo;s growth</td><td>Confident about India&rsquo;s growth</td></tr>'
                '<tr><td>Liquidity stance</td><td>Adding liquidity, easy conditions</td><td>Draining liquidity, tight conditions</td></tr>'
                '<tr><td>Rate guidance</td><td>Signalling cuts ahead</td><td>Signalling hikes ahead</td></tr>'
                '<tr><td>External stance</td><td>Tolerant of rupee weakness</td><td>Defensive of the rupee</td></tr>'
                '</tbody></table>\n\n'
                "Growth assessment is read in the committee's own framing of the domestic economy (real GDP "
                "and activity), not as a GDP number. A more confident growth reading leans hawkish in effect: "
                "the less the economy needs support, the more room the MPC has to focus on inflation.\n\n"
                "**Decision strip and key takeaways**\n\n"
                "The repo rate, decision and rate history come from the Sentinel database. The RBI's stated "
                "stance, its full-year CPI and real GDP projections, and the next meeting dates are read "
                "directly from each Resolution's text by fixed patterns — no model is involved, and anything "
                "that does not match is shown as a dash. The six takeaways are assembled from these facts, "
                "the scores above and the model's own output: *Implication* is the opening line of the "
                "Practical takeaway paragraph, and *In their words* is the lead pivotal phrase from the "
                "document leaning furthest in the composite's direction. Every line regenerates "
                "automatically for each new meeting.\n\n"
                "**Limitations**\n\n"
                "Scores for historical meetings were produced by a model whose training data post-dates "
                "those meetings, so they may carry hindsight about what the RBI did next; live scores for "
                "new meetings do not. All outputs are quantitative estimates intended for research, not "
                "investment advice.\n\n"
                "---\n\n"
                "### Pipeline Architecture\n",
                unsafe_allow_html=True,
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
      <div class="arch-arrow">→</div>
      <div class="arch-box"><b>Policy-Cycle Grouping</b><span>Minutes attached to their decision</span></div>
    </div>
  </div>

  <div class="arch-down">↓</div>

  <div class="arch-stage">
    <div class="arch-label">Score</div>
    <div class="arch-content">
      <div class="arch-branch">
        <div class="arch-box"><b>Domain Lexicon — 10%</b><span>123 phrases · 5-word negation window</span></div>
        <div class="arch-box"><b>Claude Opus 5 — 90%</b><span>Anthropic · full text · 5 sub-dimensions · JSON</span></div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-box"><b>Score Fusion</b><span>0.10×lexicon + 0.90×Opus · conflict flag: |Δ| &gt; 0.60</span></div>
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
      <div class="arch-box-db"><b>meeting_composites</b><span>SQLite — per-cycle aggregates</span></div>
      <div class="arch-arrow">+</div>
      <div class="arch-box"><b>Fact Extractor</b><span>Projections · stated stance · next meeting</span></div>
    </div>
  </div>

  <div class="arch-down">↓</div>

  <div class="arch-stage">
    <div class="arch-label">Visualise</div>
    <div class="arch-content">
      <div class="arch-box"><b>Chart Generator</b><span>EconStyle matplotlib charts</span></div>
      <div class="arch-arrow">→</div>
      <div class="arch-box-dark"><b>Streamlit Dashboard</b><span>Decision strip · takeaways · charts</span></div>
    </div>
  </div>

</div>
""", unsafe_allow_html=True)

        # ── Decision strip: the cycle's facts in one row, ahead of any chart ──
        if brief:
            st.markdown(_decision_strip_html(brief), unsafe_allow_html=True)

        # ── Hero: Stance Meter & AI Briefing (Side-by-Side) ──
        stance, charts = _pop_summary(charts, ["01_rbi_stance_meter"])
        if stance:
            col_chart, col_text = st.columns([1.2, 1], gap="large")

            with col_chart:
                st.image(str(stance), use_container_width=True)

                # ── Source documents: one column per document, same row
                #    structure in each, ordered by weight in the composite ──
                if brief and brief.get("documents"):
                    _names = {
                        DOC_MINUTES: "Minutes",
                        DOC_RESOLUTION: "Resolution",
                        DOC_GOVERNOR: "Governor&rsquo;s Statement",
                    }
                    _doc_scores = {
                        DOC_MINUTES: brief.get("minutes_score"),
                        DOC_RESOLUTION: brief.get("resolution_score"),
                        DOC_GOVERNOR: brief.get("governor_score"),
                    }
                    _rows = []
                    for _doc in sorted(
                        brief["documents"],
                        key=lambda d: -_DOC_WEIGHTS.get(d["doc_type"], 0),
                    ):
                        _type = _doc["doc_type"]
                        _dd = datetime.strptime(_doc["publication_date"], "%Y-%m-%d")
                        _ds = _doc_scores.get(_type)
                        if _ds is None:
                            _score_html = '<span class="mpc-doc-score mpc-neutral">&mdash;</span>'
                            _track_html = ""
                        else:
                            _ddir = "hawkish" if _ds > 0.05 else ("dovish" if _ds < -0.05 else "neutral")
                            _score_html = (
                                f'<span class="mpc-doc-score mpc-{_ddir}">{_ds:+.2f}'
                                f'<span class="mpc-doc-dir">{_ddir.title()}</span></span>'
                            )
                            # Position on the bounded [-1, +1] scale, centre tick at 0.
                            _pos = (max(-1.0, min(1.0, _ds)) + 1) * 50
                            _track_html = (
                                f'<span class="mpc-doc-track"><i class="mpc-dot-{_ddir}" '
                                f'style="left:{_pos:.1f}%"></i></span>'
                            )
                        _weight = _DOC_WEIGHTS.get(_type)
                        _weight_html = (
                            f'<span class="mpc-doc-weight">{_weight:.0%} weight</span>'
                            if _weight is not None else ""
                        )
                        _rows.append(
                            '<li>'
                            '<span class="mpc-doc-top">'
                            f'<a href="{_doc["source_url"]}" target="_blank" rel="noopener">'
                            f'{_names.get(_type, _type)}</a>{_weight_html}'
                            '</span>'
                            f'{_score_html}{_track_html}'
                            f'<span class="mpc-prov-meta">{_dd.day} {_dd.strftime("%b %Y")} '
                            f'&middot; {_doc["word_count"]:,} words</span>'
                            '</li>'
                        )
                    st.markdown(
                        '<div class="mpc-sources">'
                        '<p class="mpc-sources-label">Source documents</p>'
                        '<ul class="mpc-prov">' + "".join(_rows) + "</ul>"
                        '</div>',
                        unsafe_allow_html=True,
                    )

            with col_text:
                # ── Executive summary ──
                ai_summary = (brief or {}).get("composite_narrative")
                if not ai_summary:
                    ai_summary = "Awaiting narrative generation for the current policy cycle."

                clean_summary = ai_summary
                if "Awaiting narrative" not in clean_summary:
                    for _label in (
                        "**How to read this document:**", "How to read this document:",
                        "**Practical takeaway:**", "Practical takeaway:",
                    ):
                        clean_summary = clean_summary.replace(_label, "")
                    clean_summary = clean_summary.strip()
                    clean_summary = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", clean_summary)
                    clean_summary = clean_summary.replace("\n\n", "</p><p class='mpc-body'>")
                    clean_summary = clean_summary.replace("\n", " ")

                st.markdown(
                    f"""
<div class="mpc-exec-head">
  <p class="mpc-exec-title">Executive Summary</p>
  <p class="mpc-exec-sub">NLP-driven narrative synthesis of the current policy cycle</p>
</div>
<div class="mpc-exec-body">{_takeaways_html(brief) if brief else ""}<p class="mpc-body">{clean_summary}</p></div>
""",
                    unsafe_allow_html=True,
                )

        # ── Sentiment Over Time (PRIMARY) ──
        trajectory, charts = _pop_summary(charts, ["02_rbi_sentiment_trajectory"])
        if trajectory:
            _section("Sentiment Over Time")
            st.image(str(trajectory), use_container_width=True)
            insight = get_insight(trajectory.name)
            if insight:
                with st.expander("Chart insights"):
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
                with st.expander("Chart insights"):
                    st.markdown(insight)

        # Supporting chart (CENTERED)
        if radar:
            _, col_mid, _ = st.columns([1, 2, 1])
            with col_mid:
                st.image(str(radar), use_container_width=True)
                insight = get_insight(radar.name)
                if insight:
                    with st.expander("Chart insights"):
                        st.markdown(insight)
                        
        # ── Repo Rate vs Sentiment (PRIMARY) ──
        rate_chart, charts = _pop_summary(charts, ["05_rbi_rate_and_sentiment"])
        if rate_chart:
            _section("Repo Rate vs. Sentiment")
            st.image(str(rate_chart), use_container_width=True)
            insight = get_insight(rate_chart.name)
            if insight:
                with st.expander("Chart insights"):
                    st.markdown(insight)

        # ── Tone and the bond market ──
        # A static research chart (rbi_sentinel/research/tone_vs_10y_chart.py); it is not
        # part of the automated pipeline's month folders.
        _tone_chart = PROJECT_ROOT / "assets" / "rbi_research" / "07_rbi_tone_vs_10y.png"
        if _tone_chart.exists():
            _section("Tone and the Bond Market")
            st.image(str(_tone_chart), use_container_width=True)
            insight = get_insight(_tone_chart.name)
            if insight:
                with st.expander("Chart insights and testing method"):
                    st.markdown(insight)

        # ── Governor Signal Analysis ──
        gov_divergence, charts = _pop_summary(charts, ["07_rbi_governor_divergence"])

        if gov_divergence:
            _section("Governor Signal Analysis")
            st.image(str(gov_divergence), use_container_width=True)
            insight = get_insight(gov_divergence.name)
            if insight:
                with st.expander("Chart insights"):
                    st.markdown(insight)

        # ── Catch-all ──
        if charts:
            _section("Other")
            _render_grid(charts)