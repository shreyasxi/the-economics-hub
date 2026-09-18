"""
The Economics Hub — Streamlit Dashboard
Author: Shreyas Urgunde  |  shreyasxi.github.io

Publication dashboard of four pages, each with its own link:
  Weekly Markets (/)  · World (/world)  · India (/india)  · RBI Sentinel (/rbi-sentinel)

Charts are served from assets/ (git-tracked, deployed) with a local
fallback to output/ for development. Pipeline controls are gated
behind PIPELINE_KEY — only visible to the publisher.
"""

from __future__ import annotations

import html
import importlib
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from charts.loader import (
    chart_key,
    clean_title,
    get_charts,
    group_charts,
    is_pipeline_admin,
)
import config.insights as _insights
import config.news_settings as _news_settings
import config.soe_settings as _soe_settings
import config.weekly_settings as _weekly_settings
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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Merriweather:ital,wght@0,700;0,900;1,400&family=Playfair+Display:wght@700;900&family=Newsreader:ital,opsz,wght@0,6..72,400..700;1,6..72,400..600&display=swap');

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
    /* Jump links under a page's standfirst (Weekly Markets) */
    .tab-jump {
        display: flex; flex-wrap: wrap; gap: 0.4rem 0.45rem;
        margin: 0.75rem 0 0 0;
    }
    .tab-jump a {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
        color: #0A1F3D !important; text-decoration: none !important;
        border: 1px solid #C9D2DE; border-radius: 999px; background: #FFFFFF;
        padding: 0.28rem 0.7rem; white-space: nowrap;
        transition: background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease;
    }
    .tab-jump a:hover, .tab-jump a:focus-visible {
        background: #0A1F3D; border-color: #0A1F3D; color: #FFFFFF !important;
    }
    /* Land a jumped-to section below Streamlit's fixed top bar, and glide there */
    .section-header[id] { scroll-margin-top: 4.5rem; }
    html, [data-testid="stAppViewContainer"], [data-testid="stMain"] { scroll-behavior: smooth; }
    @media (prefers-reduced-motion: reduce) {
        html, [data-testid="stAppViewContainer"], [data-testid="stMain"] { scroll-behavior: auto; }
    }

    .rbi-head-note {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.82rem; font-style: italic; font-weight: 400; color: #6B7280;
        line-height: 1.5; margin: 0.45rem 0 0 0; max-width: 46rem;
    }
    .rbi-head-note a { color: #6B7280; text-decoration: underline; }
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

    /* ═══ World page ═══════════════════════════════════════════════════ */

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
    /* Eyebrow with the page header's heavy navy rule beneath it */
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

    /* ═══ News strip: The week in headlines ══════════════════════════════
       Drawn only when the weekly edition folder has a news.json (generate_news.py).
       Editorial, not a card: it sits on the page background and is built from
       type, hairline rules and spacing. Headlines are set in Newsreader, a serif
       drawn for news; everything around them stays in the site's Inter.
       World leads (lead story over a two-by-two grid); India runs as a narrower
       column. Plain p, a and heading elements are avoided or scoped, because
       Streamlit's markdown styles those elements with higher specificity. */
    .nh {
        --nh-ink: #0A1F3D;          /* headlines */
        --nh-text: #2B3340;
        --nh-muted: #6A7280;        /* meta */
        --nh-faint: #A2AAB5;        /* separators, icons */
        --nh-rule: #D7DDE4;         /* hairlines on the page background */
        --nh-world: #1F4E79;
        --nh-india: #A85600;
        --nh-india-mark: #EE8A1F;
        margin: 2.2rem 0 3.2rem 0;
        font-family: 'Inter', -apple-system, sans-serif;
    }

    /* ── Header: title and week on the left, method on the right ── */
    .nh-head {
        position: relative;
        display: flex; align-items: flex-end; justify-content: space-between;
        gap: 0.6rem 2rem; flex-wrap: wrap;
        padding-bottom: 0.85rem; border-bottom: 1px solid var(--nh-ink);
    }
    .nh-head-l { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.2rem 0; min-width: 0; }
    .nh-title {
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif; font-optical-sizing: auto;
        font-size: 1.46rem; font-weight: 600; line-height: 1.1; letter-spacing: -0.01em;
        color: var(--nh-ink);
    }
    .nh-week {
        font-size: 0.8rem; font-weight: 500; color: var(--nh-muted); white-space: nowrap;
        font-variant-numeric: tabular-nums lining-nums;
        margin-left: 1rem; padding-left: 1rem; border-left: 1px solid var(--nh-rule);
    }
    .nh-how { position: static; }
    .nh-how > summary {
        list-style: none; cursor: pointer; user-select: none;
        display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0;
        font-size: 0.76rem; font-weight: 600; color: var(--nh-text);
        transition: color 0.15s ease;
    }
    .nh-how > summary::-webkit-details-marker { display: none; }
    .nh-how > summary::marker { content: ""; }
    .nh-how > summary svg { width: 15px; height: 15px; color: var(--nh-muted); transition: color 0.15s ease; }
    .nh-how > summary:hover, .nh-how[open] > summary { color: var(--nh-world); }
    .nh-how > summary:hover svg, .nh-how[open] > summary svg { color: var(--nh-world); }
    .nh-how > summary:focus-visible { outline: 2px solid var(--nh-world); outline-offset: 3px; border-radius: 3px; }
    .nh-how-panel {
        position: absolute; right: 0; top: calc(100% + 0.65rem); z-index: 30;
        width: min(27rem, 100%); box-sizing: border-box;
        background: #FFFFFF; border: 1px solid #E2E7ED; border-radius: 10px;
        box-shadow: 0 22px 48px -22px rgba(10,31,61,0.30), 0 2px 6px -2px rgba(10,31,61,0.06);
        padding: 0.95rem 1.1rem 1rem 1.1rem;
        font-size: 0.8rem; line-height: 1.55; color: var(--nh-text);
    }
    .nh-how-panel span { display: block; }
    .nh-how-panel span + span { margin-top: 0.55rem; }
    .nh-how-panel b { font-weight: 600; color: var(--nh-ink); }
    .nh-how-panel .nh-how-foot { color: var(--nh-muted); font-size: 0.74rem; text-wrap: balance; }

    /* ── Columns: World wide, India narrow, a hairline centred in the gap ── */
    .nh-grid {
        display: grid; grid-template-columns: minmax(0, 1.62fr) minmax(0, 1fr);
        column-gap: 3.5rem; margin-top: 1.6rem;
    }
    .nh-grid.is-single { grid-template-columns: minmax(0, 1fr); }
    .nh-col { position: relative; min-width: 0; }
    .nh-col + .nh-col::before {
        content: ""; position: absolute; left: -1.75rem; top: 0.25rem; bottom: 0.4rem;
        width: 1px; background: var(--nh-rule);
    }
    .nh-region {
        display: flex; align-items: center; gap: 0.6rem; margin: 0 0 1.15rem 0;
        font-size: 0.8rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase;
        color: var(--nh-ink);
    }
    .nh-region::before { content: ""; flex: none; width: 9px; height: 9px; border-radius: 1px; background: var(--nh-world); }
    .nh-region::after { content: ""; flex: 1; height: 1px; background: var(--nh-rule); }
    .nh-col.is-india .nh-region { color: var(--nh-india); }
    .nh-col.is-india .nh-region::before { background: var(--nh-india-mark); }

    /* ── A story: kicker, headline, meta. The whole block is the link. ── */
    .nh-story { position: relative; min-width: 0; }
    .nh-kicker {
        display: flex; align-items: center; gap: 0.55rem; margin: 0 0 0.45rem 0;
        font-size: 0.64rem; font-weight: 700; letter-spacing: 0.13em; text-transform: uppercase;
        color: var(--nh-world);
    }
    .nh-col.is-india .nh-kicker { color: var(--nh-india); }
    .nh-rank {
        font-weight: 600; letter-spacing: 0.04em; color: var(--nh-ink);
        font-variant-numeric: tabular-nums lining-nums;
    }
    .nh-rank::after {
        content: ""; display: inline-block; width: 16px; height: 1px; margin-left: 0.55rem;
        vertical-align: middle; background: var(--nh-faint);
    }
    .nh a.nh-link { color: inherit !important; text-decoration: none !important; }
    .nh a.nh-link::after { content: ""; position: absolute; inset: 0; z-index: 1; }
    .nh a.nh-link:focus-visible { outline: none; }
    .nh-story:focus-within { outline: 2px solid var(--nh-world); outline-offset: 5px; border-radius: 2px; }
    .nh-hl {
        display: block;
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif; font-optical-sizing: auto;
        font-weight: 560; color: var(--nh-ink); text-wrap: balance;
        transition: color 0.15s ease;
    }
    .nh-lead .nh-hl { font-size: 1.78rem; line-height: 1.14; letter-spacing: -0.017em; }
    .nh-col.is-india .nh-lead .nh-hl { font-size: 1.36rem; line-height: 1.2; letter-spacing: -0.012em; }
    .nh-item .nh-hl { font-size: 1.12rem; line-height: 1.3; letter-spacing: -0.006em; }
    .nh-hl-text {
        text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 0.17em;
        text-decoration-color: transparent; transition: text-decoration-color 0.15s ease;
    }
    .nh-story:hover .nh-hl { color: #0F3563; }
    .nh-story:hover .nh-hl-text { text-decoration-color: rgba(15,53,99,0.4); }
    .nh-nowrap { white-space: nowrap; }
    .nh-ext {
        display: inline-block; width: 0.46em; height: 0.46em; margin-left: 0.28em; vertical-align: 0.3em;
        color: var(--nh-faint); transition: transform 0.18s ease, color 0.18s ease;
    }
    .nh-story:hover .nh-ext { color: var(--nh-world); transform: translate(1.5px, -1.5px); }
    .nh-col.is-india .nh-story:hover .nh-ext { color: var(--nh-india); }

    .nh-meta {
        display: flex; align-items: center; flex-wrap: wrap; gap: 0.3rem 0.6rem; margin: 0.6rem 0 0 0;
        font-size: 0.74rem; line-height: 1.3; color: var(--nh-muted);
        font-variant-numeric: tabular-nums lining-nums;
    }
    .nh-pub { display: inline-flex; align-items: center; gap: 0.3rem; font-weight: 600; color: var(--nh-text); }
    .nh-lock { width: 9px; height: 10px; color: var(--nh-faint); flex: none; }
    .nh-sep { flex: none; width: 3px; height: 3px; border-radius: 50%; background: var(--nh-faint); }
    .nh-cov { position: relative; z-index: 2; display: inline-flex; align-items: center; gap: 0.45rem; cursor: help; }
    .nh-pips { display: inline-flex; gap: 2px; }
    .nh-pips i { display: block; width: 9px; height: 3px; border-radius: 1px; background: var(--nh-rule); }
    .nh-pips i.on { background: var(--nh-world); }
    .nh-col.is-india .nh-pips i.on { background: var(--nh-india-mark); }
    .nh-sr {
        position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden;
        clip: rect(0 0 0 0); white-space: nowrap; border: 0;
    }

    .nh-lead { padding: 0 0 1.4rem 0; }
    .nh-rest { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 2.4rem; }
    .nh-col.is-india .nh-rest { grid-template-columns: minmax(0, 1fr); }
    .nh-item { border-top: 1px solid var(--nh-rule); padding: 1.05rem 0 1.2rem 0; }

    @media (prefers-reduced-motion: reduce) {
        .soe-more > summary svg { transition: none; }
        .nh-hl, .nh-hl-text, .nh-ext, .nh-how > summary { transition: none; }
        .nh-story:hover .nh-ext { transform: none; }
    }
    @media (max-width: 1180px) {
        .nh-grid { grid-template-columns: minmax(0, 1fr); row-gap: 2.3rem; }
        .nh-col + .nh-col::before { display: none; }
        .nh-col.is-india .nh-rest { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .nh-col.is-india .nh-lead .nh-hl { font-size: 1.55rem; }
    }
    @media (max-width: 680px) {
        .nh { margin: 1.1rem 0 2.4rem 0; }
        .nh-title { font-size: 1.3rem; }
        .nh-week { margin-left: 0; padding-left: 0; border-left: none; flex-basis: 100%; margin-top: 0.3rem; }
        .nh-how { width: 100%; }
        .nh-how-panel { width: 100%; }
        .nh-lead .nh-hl, .nh-col.is-india .nh-lead .nh-hl { font-size: 1.38rem; line-height: 1.2; }
        .nh-item .nh-hl { font-size: 1.06rem; }
        .nh-rest, .nh-col.is-india .nh-rest { grid-template-columns: minmax(0, 1fr); }
    }
    /* ═══ end news strip ═══════════════════════════════════════════════ */

    /* ═══ State of the Economy: the RBI's monthly read, top of the India tab ══
       Drawn only when the India edition folder has a soe.json (generate_soe.py).
       Editorial like the headlines strip: no card, hairline rules, the RBI's own
       opening summary set in Newsreader. Every word inside is RBI's, so nothing
       here styles an interpretation — only the quote, its date and its source. */
    /* The palette is declared on both blocks, not only on the section: the
       month-on-month comparison is drawn in its own Streamlit column, beside the
       snapshot table, so it inherits nothing from the briefing above it. */
    .soe, .soe-changes {
        --soe-ink: #0A1F3D;
        --soe-text: #2B3340;
        --soe-muted: #6A7280;
        --soe-faint: #A2AAB5;
        --soe-rule: #D7DDE4;
        --soe-mark: #A85600;        /* the India tab's accent, as used by the headlines column */
        font-family: 'Inter', -apple-system, sans-serif;
    }
    .soe { margin: 1.6rem 0 2.6rem 0; }
    /* Inline-flex, so the rule under the title runs to the end of the edition
       date and stops there rather than across the whole column. */
    .soe-head {
        position: relative;
        display: inline-flex; align-items: flex-end;
        gap: 0.6rem 2rem; flex-wrap: wrap; max-width: 100%;
        padding-bottom: 0.7rem; border-bottom: 1px solid var(--soe-ink);
    }
    .soe-head-l { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.2rem 0; min-width: 0; }
    .soe-title {
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif; font-optical-sizing: auto;
        font-size: 1.46rem; font-weight: 600; line-height: 1.1; letter-spacing: -0.01em;
        color: var(--soe-ink);
    }
    .soe-edition {
        font-size: 0.8rem; font-weight: 500; color: var(--soe-muted); white-space: nowrap;
        font-variant-numeric: tabular-nums lining-nums;
        margin-left: 1rem; padding-left: 1rem; border-left: 1px solid var(--soe-rule);
    }
    /* RBI's opening summary, set exactly as the Sentinel's executive-summary
       paragraphs (.mpc-body): same face, size, colour and leading. The two are
       the only long passages of prose on the site and they now read as one. */
    .soe-lede {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.9rem; font-weight: 400; line-height: 1.72; color: #24282F;
        margin: 1.1rem 0 0 0; max-width: 62rem;
    }
    /* What changed since last month: RBI's sentence on a topic above the one it
       wrote a month earlier, one topic to a row, each quote dated. It sits in
       the column beside the snapshot table, so it is set narrow: the month's
       numbers on the left, the month's words on the right. */
    .soe-changes { max-width: 62rem; }
    /* Set like the article's own title, a size down: the two are a pair, the
       briefing above and the month-on-month read beside the table. */
    .soe-chg-head {
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif; font-optical-sizing: auto;
        font-size: 1.15rem; font-weight: 600; line-height: 1.15; letter-spacing: -0.01em;
        color: var(--soe-ink);
        padding-bottom: 0.6rem; border-bottom: 1px solid var(--soe-ink);
    }
    .soe-chg {
        display: grid; gap: 0.4rem 0;
        padding: 0.9rem 0 0.95rem 0; border-bottom: 1px solid var(--soe-rule);
    }
    .soe-chg-topic {
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
        color: var(--soe-mark);
    }
    .soe-chg-lines { display: grid; gap: 0.55rem; }
    /* The date sits in its own column so a wrapped line does not run back under
       it: each quote keeps one straight left edge. */
    .soe-chg-now, .soe-chg-was {
        display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0 0.55rem;
        align-items: start;
    }
    /* Both quotes are set in the body face rather than the title serif: five
       bold serif sentences stacked in a narrow column read as a slab. This
       month's is the same Inter as the summary above, a step heavier and in the
       darker ink, which separates it from last month's without the weight. */
    .soe-chg-now {
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 0.9rem; font-weight: 600; line-height: 1.6; color: var(--soe-ink);
    }
    .soe-chg-was { font-size: 0.83rem; line-height: 1.55; color: var(--soe-muted); }
    .soe-chg-when {
        padding: 0.06rem 0.34rem; border: 1px solid var(--soe-rule); border-radius: 3px;
        font-size: 0.64rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
        color: var(--soe-faint); white-space: nowrap;
    }
    .soe-chg-now .soe-chg-when { margin-top: 0.22rem; }
    .soe-chg-was .soe-chg-when { margin-top: 0.1rem; }
    /* This month's date is filled in the accent and last month's stays a faint
       outline, so which quote is current is read at a glance, not by comparing
       two months set in nearly the same weight. */
    .soe-chg-when.is-now {
        background: var(--soe-mark); border-color: var(--soe-mark);
        color: #FFFFFF; font-weight: 800;
    }

    .soe-more { margin-top: 0.9rem; }
    .soe-more > summary {
        list-style: none; cursor: pointer; user-select: none;
        display: inline-flex; align-items: center; gap: 0.4rem;
        font-size: 0.78rem; font-weight: 600; color: var(--soe-mark);
    }
    .soe-more > summary svg { width: 10px; height: 10px; transition: transform 0.15s ease; }
    .soe-more[open] > summary svg { transform: rotate(90deg); }
    .soe-more > summary:hover { text-decoration: underline; }
    .soe-more > summary::-webkit-details-marker { display: none; }
    .soe-more > summary::marker { content: ""; }
    .soe-more > summary:focus-visible { outline: 2px solid var(--soe-mark); outline-offset: 3px; border-radius: 3px; }
    .soe-concl {
        border-left: 2px solid var(--soe-rule); padding: 0.1rem 0 0.1rem 1rem; margin-top: 0.7rem;
        display: grid; gap: 0.7rem; max-width: 62rem;
        font-size: 0.9rem; line-height: 1.72; color: #24282F;
    }
    .soe-meta {
        display: flex; align-items: center; flex-wrap: wrap; gap: 0.45rem;
        margin-top: 1rem; padding-top: 0.7rem; border-top: 1px solid var(--soe-rule);
        font-size: 0.74rem; line-height: 1.3; color: var(--soe-muted);
        font-variant-numeric: tabular-nums lining-nums;
    }
    .soe-src { font-weight: 600; color: var(--soe-text); }
    .soe-dot { flex: none; width: 3px; height: 3px; border-radius: 50%; background: var(--soe-faint); }
    .soe-stale { color: var(--soe-mark); font-weight: 600; }
    .soe-link {
        display: inline-flex; align-items: center; gap: 0.28rem;
        color: var(--soe-mark) !important; font-weight: 600; text-decoration: none !important;
    }
    .soe-link:hover { text-decoration: underline !important; }
    .soe-link svg { width: 10px; height: 10px; }
    @media (max-width: 680px) {
        .soe { margin: 1rem 0 2rem 0; }
        .soe-title { font-size: 1.3rem; }
        .soe-edition { margin-left: 0; padding-left: 0; border-left: none; flex-basis: 100%; margin-top: 0.3rem; }
        .soe-changes { margin-top: 0.4rem; }
        /* The meta line wraps on a phone, which left a separator dot stranded
           at the end of a line; spacing carries the separation instead. */
        .soe-dot { display: none; }
        .soe-meta { column-gap: 0.9rem; }
    }
    /* ═══ end State of the Economy ═════════════════════════════════════ */

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

    /* ── Institutional masthead ──────────────────────────────────────────────
       Three levels, deliberately unalike, so a first-time reader takes them in
       order: the nameplate, then what the publication is, then who writes it.
       The descriptor is the one a stranger needs, so it is navy and banded
       between rules; the byline is grey sentence case and recedes.          */
    /* Streamlit styles h1 and p inside its markdown container, and those rules
       beat a bare class selector: every declaration it sets is forced here. */
    .insti-masthead {
        font-family: 'Playfair Display', Georgia, serif !important;
        font-size: 2.55rem !important;
        font-weight: 900 !important;
        letter-spacing: -0.005em !important;
        color: #0A1128 !important;
        text-align: center;
        text-transform: uppercase;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.04 !important;
    }

    /* The band hugs its text (fit-content), so the rules read as a deliberate
       device rather than as a stray divider the width of the column. */
    .insti-descriptor {
        width: fit-content;
        max-width: 92%;
        margin: 1.15rem auto 0 auto !important;
        padding: 0.5rem 1.8rem 0.55rem 1.8rem !important;
        border-top: 1px solid rgba(0, 51, 102, 0.3);
        border-bottom: 1px solid rgba(0, 51, 102, 0.3);
        font-family: 'Inter', sans-serif !important;
        font-size: 0.84rem !important;
        font-weight: 700 !important;
        color: #003366 !important;
        text-align: center;
        letter-spacing: 0.2em !important;
        text-transform: uppercase;
        line-height: 1.45 !important;
    }

    /* The author's name is the one thing in the masthead a reader may want to
       follow, so it is a link — but it must not out-shout the strip it sits in,
       hence the same colour and a rule that only appears on hover. */
    a.insti-author, a.insti-author:visited {
        color: inherit !important;
        text-decoration: none !important;
        border-bottom: 1px solid rgba(0, 51, 102, 0.35);
        padding-bottom: 1px;
        transition: border-color 0.15s ease-in-out;
    }
    a.insti-author:hover {
        border-bottom-color: #003366;
    }

    .insti-byline {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.79rem !important;
        font-weight: 400 !important;
        color: #6B7280 !important;
        text-align: center;
        letter-spacing: 0.01em !important;
        margin: 0.8rem 0 1.35rem 0 !important;
    }

    /* A phone cannot hold 0.2em of tracking across that descriptor without
       breaking it into three ragged lines. */
    @media (max-width: 680px) {
        .insti-masthead { font-size: 1.62rem !important; }
        .insti-descriptor {
            font-size: 0.68rem !important;
            letter-spacing: 0.1em !important;
            padding: 0.45rem 0.9rem 0.5rem 0.9rem !important;
            margin-top: 0.9rem !important;
        }
        .insti-byline { font-size: 0.72rem !important; }
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

    
    
    /* ── Section navigation ──
       Each section is a page of its own (see the foot of this file), so these
       are links with their own URLs, not tabs. They keep the tab bar's look:
       uppercase Inter, a navy underline under the page being read and a
       hairline across the row. The row scrolls sideways on a phone rather
       than wrapping, as the tabs did. */
    .st-key-ehnav {
        gap: 0 !important;
        flex-wrap: nowrap !important;
        overflow-x: auto;
        scrollbar-width: none;
        border-bottom: 1px solid rgba(10, 31, 61, 0.18);
        margin: 0.2rem 0 0 0;
    }
    .st-key-ehnav::-webkit-scrollbar { display: none; }
    /* Streamlit pulls elements together with a negative margin; inside this row
       it would clip the underline, because a sideways-scrolling row also clips
       what overflows it vertically. */
    .st-key-ehnav [data-testid="stLayoutWrapper"],
    .st-key-ehnav [data-testid="stVerticalBlock"],
    .st-key-ehnav [data-testid="stElementContainer"] {
        width: auto !important; flex: 0 0 auto !important; gap: 0 !important; margin: 0 !important;
    }
    .st-key-ehnav [data-testid="stPageLink"] { width: auto !important; }
    .st-key-ehnav [data-testid="stPageLink"] a {
        background: transparent !important;
        border-radius: 0;
        gap: 0;
        padding: 0.1rem 0 0.5rem 0;
        margin: 0 1rem 0 0;
        border-bottom: 3px solid transparent !important;
        transition: color 0.15s ease, border-color 0.15s ease;
    }
    .st-key-ehnav [data-testid="stPageLink"] a p,
    .st-key-ehnav [data-testid="stPageLink"] a span,
    .st-key-ehnav [data-testid="stPageLink"] a div {
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.80rem !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        color: #0A0A0A;
        white-space: nowrap;
    }
    .st-key-ehnav [data-testid="stPageLink"] a:hover p,
    .st-key-ehnav [data-testid="stPageLink"] a:hover span,
    .st-key-ehnav [data-testid="stPageLink"] a:hover div { color: #003366; }
    .st-key-ehnav [data-testid="stPageLink"] a:hover { border-bottom-color: rgba(0, 51, 102, 0.35) !important; }
    .st-key-ehnav [class*="-current"] [data-testid="stPageLink"] a { border-bottom-color: #003366 !important; }
    .st-key-ehnav [class*="-current"] [data-testid="stPageLink"] a p,
    .st-key-ehnav [class*="-current"] [data-testid="stPageLink"] a span,
    .st-key-ehnav [class*="-current"] [data-testid="stPageLink"] a div { color: #003366; }

    /* ── Chart search ──
       One field under the page links, the width of a column of results. The
       field itself is drawn inside a component frame (see _search_box_html):
       suggestions have to appear as the reader types, and Streamlit's own text
       input only reports back on Enter. All that is styled here is the space
       the frame sits in; the box and its list carry their own styles. */
    .st-key-ehsearch { max-width: 560px; margin: 0.9rem auto 0.55rem auto; }
    .st-key-ehsearch iframe { background: transparent; display: block; }
    /* Where a result lands: an empty target above the chart, held clear of the
       top of the window so the chart's title is not tucked under it. */
    .chart-anchor { display: block; height: 0; scroll-margin-top: 4.5rem; }

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
    /* The four pipelines that build the site, one row each: the section in the
       label face, what it is built from in the serif beneath it, and when it
       runs as a small outlined chip. A left rule ties the rows into a stack, so
       the block reads as a colophon rather than a table of two columns. */
    .sb-arch-note {
        font-family: 'Inter', sans-serif;
        font-size: 0.62rem; font-style: italic; color: #7A7A72;
        line-height: 1.45; margin: -0.45rem 0 0.8rem 0;
    }
    .sb-arch-row {
        display: grid; gap: 0.2rem;
        padding: 0.5rem 0 0.55rem 0.7rem; margin: 0;
        border-left: 2px solid #E2DFD8;
        border-bottom: 1px solid #EDEBE4;
    }
    .sb-arch-row:hover { border-left-color: #111111; }
    .sb-arch-row:last-of-type { border-bottom: none; padding-bottom: 0.2rem; }
    .sb-arch-top {
        display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
    }
    .sb-arch-name {
        font-family: 'Inter', sans-serif;
        font-size: 0.62rem; font-weight: 800; color: #111111;
        letter-spacing: 0.1em; text-transform: uppercase;
    }
    .sb-arch-when {
        font-family: 'Inter', sans-serif;
        font-size: 0.5rem; font-weight: 700; color: #8A8A80;
        letter-spacing: 0.07em; text-transform: uppercase; white-space: nowrap;
        border: 1px solid #DAD6CD; border-radius: 2px; padding: 0.1rem 0.28rem;
    }
    .sb-arch-src {
        font-family: 'Merriweather', Georgia, serif;
        font-size: 0.72rem; font-style: italic; color: #333333; line-height: 1.45;
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
        '<p class="sb-coverage">Automated weekly analysis of global markets, the world and Indian '
        'economy. Also contains sentiment analysis of RBI policy.</p>',
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
    
    # What each section is actually built from, and when its pipeline runs. The
    # schedules are the crons in .github/workflows; the sources are the fetchers
    # each generator calls. Keep both in step with those files when either moves.
    _ARCHITECTURE = [
        ("Weekly Markets", "Saturdays", "Yahoo Finance &middot; NSE"),
        ("World",          "Saturdays", "FRED &middot; OECD &middot; BIS"),
        ("India",          "Saturdays", "RBI Bulletin &amp; DBIE &middot; MoSPI &middot; CGA &middot; NSDL"),
        ("RBI Sentinel",   "Weekdays",  "RBI policy documents, scored by Claude"),
        ("Headlines",      "4-hourly",  "Nine publishers&rsquo; news feeds"),
    ]
    st.markdown(
        '<p class="sb-arch-note">What each section is built from, and when it refreshes.</p>'
        + "".join(
            '<div class="sb-arch-row">'
            f'<div class="sb-arch-top"><span class="sb-arch-name">{name}</span>'
            f'<span class="sb-arch-when">{when}</span></div>'
            f'<div class="sb-arch-src">{sources}</div>'
            '</div>'
            for name, when, sources in _ARCHITECTURE
        ),
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


# ── Helpers ────────────────────────────────────────────────────────────────

def _chart_anchor(chart_path: Path) -> None:
    """An empty target above a chart, so a search result can link straight to it."""
    st.markdown(f'<div class="chart-anchor" id="{_chart_anchor_id(chart_path.name)}"></div>',
                unsafe_allow_html=True)


def _chart_slug(filename: str) -> str:
    """'14_india_credit_deposit.png' -> 'india-credit-deposit'."""
    return chart_key(filename).replace("_", "-")


def _chart_anchor_id(filename: str) -> str:
    """The id a search result scrolls to."""
    return f"chart-{_chart_slug(filename)}"


def _render_chart(chart_path: Path) -> None:
    _chart_anchor(chart_path)
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
    
# Fields the RBI page reads from the cycle brief beyond the original set.
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
    The RBI page's decision strip: rate and decision, the Sentinel reading
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


def _section(title: str, anchor: str | None = None) -> None:
    anchor_attr = f' id="{anchor}"' if anchor else ""
    st.markdown(
        f'<div class="section-divider"></div>'
        f'<p class="section-header"{anchor_attr}>{title}</p>',
        unsafe_allow_html=True,
    )


def _anchor(prefix: str, title: str) -> str:
    """'Rates, Inflation & Credit' -> 'weekly-rates-inflation-credit'. Ids carry the page, so links
    shared before the pages were split still find their section."""
    return f"{prefix}-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

def _render_summary(chart_path: Path) -> None:
    """Summary table constrained to 80% of page width."""
    _, col_img, _ = st.columns([1, 4, 1])
    with col_img:
        _chart_anchor(chart_path)
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


# ── World page helpers ──────────────────────────────────────────────────────

def _fresh_config(module):
    """
    A config module, reloaded when its file changes: Streamlit Cloud re-runs
    app.py after a push without re-importing modules, so a yearly
    meeting-calendar update would otherwise not show until a reboot.
    """
    mtime = Path(module.__file__).stat().st_mtime
    if getattr(module, "_loaded_mtime", None) != mtime:
        module = importlib.reload(module)
        module._loaded_mtime = mtime
    return module


def _world_config():
    return _fresh_config(_world_settings)


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


# ── News strip ─────────────────────────────────────────────────────────────
# The week in headlines, on the Weekly Markets page, from the news.json that
# generate_news.py writes into each weekly edition folder. An edition without
# one (an older edition, or a run where every feed failed) shows no strip.
# Feed text is untrusted: every title is escaped and only http(s) links are kept.

_NH_ARROW = ('<svg class="nh-ext" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.7" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M2.6 7.4 7.3 2.7"/><path d="M3.6 2.6h3.8v3.8"/></svg>')
_NH_LOCK = ('<svg class="nh-lock" viewBox="0 0 9 10" aria-hidden="true">'
            '<path d="M2.75 4.4V3.1a1.75 1.75 0 0 1 3.5 0v1.3" fill="none" stroke="currentColor" stroke-width="1.2"/>'
            '<rect x="1" y="4.3" width="7" height="5.2" rx="1.1" fill="currentColor"/></svg>')
_NH_INFO = ('<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true">'
            '<circle cx="8" cy="8" r="6.4"/><path d="M8 7.3v3.7" stroke-linecap="round"/>'
            '<circle cx="8" cy="5.05" r="0.2" fill="currentColor" stroke-width="1.1"/></svg>')


def _load_news(charts: list[Path]) -> dict | None:
    """news.json from the same edition folder as the Weekly charts, so headlines and charts always match."""
    path = charts[0].parent / "news.json" if charts else None
    if path is None or not path.exists():
        return None
    try:
        with path.open() as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _esc(text: str | None) -> str:
    """Feed text for st.markdown's HTML: escaped, with '$' kept from opening a maths span."""
    return html.escape(text or "").replace("$", "&#36;")


def _safe_url(url: str | None) -> str | None:
    return html.escape(url, quote=True) if re.match(r"https?://", url or "") else None


def _fmt_week(start: str, end: str) -> str:
    """'2026-09-10', '2026-09-17' -> '10–17 September 2026'."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a.year != b.year:
        return f"{a.day} {a:%B %Y} &ndash; {b.day} {b:%B %Y}"
    if a.month != b.month:
        return f"{a.day} {a:%B} &ndash; {b.day} {b:%B %Y}"
    return f"{a.day}&ndash;{b.day} {b:%B %Y}"


def _and_list(names: list[str]) -> str:
    return names[0] if len(names) < 2 else ", ".join(names[:-1]) + " and " + names[-1]


def _nh_story_html(it: dict, rank: int, outlets_read: int, paywalled: set[str], lead: bool) -> str:
    """One headline: rank and theme, the linked headline, then outlet, date and how widely it was covered."""
    url = _safe_url(it.get("url"))
    first, _, last = _esc(it.get("title")).rpartition(" ")
    # The last word travels with the link arrow, so the arrow never sits alone on a line.
    text = ((f'<span class="nh-hl-text">{first} </span>' if first else "")
            + f'<span class="nh-nowrap"><span class="nh-hl-text">{last}</span>{_NH_ARROW if url else ""}</span>')
    headline = f'<span class="nh-hl">{text}</span>'
    if url:
        headline = (f'<a class="nh-link" href="{url}" target="_blank" rel="noopener noreferrer">'
                    f'{headline}<span class="nh-sr"> (opens in a new tab)</span></a>')

    also = it.get("also") or []
    covered = 1 + len(also)
    total = max(outlets_read, covered)
    pips = "".join('<i class="on"></i>' if k < covered else "<i></i>" for k in range(total))
    tip = f"Also covered by {_and_list(also)}" if also else "No other outlet read carried this story"
    if (it.get("days") or 0) > 1:
        tip += f"; in the news on {it['days']} days"
    tip = _esc(tip)
    lock = (f'{_NH_LOCK}<span class="nh-sr"> (may require a subscription)</span>'
            if it.get("publisher") in paywalled else "")
    day = date.fromisoformat(it["date"])
    return (
        f'<article class="nh-story {"nh-lead" if lead else "nh-item"}">'
        f'<div class="nh-kicker"><span class="nh-rank">{rank:02d}</span><span>{_esc(it.get("theme"))}</span></div>'
        f'{headline}'
        '<div class="nh-meta">'
        f'<span class="nh-pub">{_esc(it.get("publisher"))}{lock}</span><span class="nh-sep"></span>'
        f'<span>{day.day} {day:%b}</span><span class="nh-sep"></span>'
        f'<span class="nh-cov" title="{tip}"><span class="nh-pips" aria-hidden="true">{pips}</span>'
        f'{covered} of {total} outlets<span class="nh-sr">. {tip}.</span></span>'
        '</div></article>'
    )


def _headlines_html(news: dict) -> str | None:
    """
    The week in headlines: World (a lead story over a two-by-two grid) beside a
    narrower India column. A column with no headlines is left out.
    """
    h = news.get("headlines") or {}
    cfg = _fresh_config(_news_settings)
    paywalled = set(cfg.PAYWALLED_PUBLISHERS)
    cols, read = [], []
    for region, label in (("world", "World"), ("india", "India")):
        block = h.get(region) or {}
        items = block.get("items") or []
        if not items:
            continue
        outlets = block.get("publishers") or []
        read.append(f"<b>{label}:</b> {_esc(_and_list(outlets))}." if outlets else "")
        stories = [_nh_story_html(it, i + 1, len(outlets), paywalled, lead=i == 0) for i, it in enumerate(items)]
        rest = f'<div class="nh-rest">{"".join(stories[1:])}</div>' if len(stories) > 1 else ""
        cols.append(f'<div class="nh-col is-{region}"><div class="nh-region">{label}</div>{stories[0]}{rest}</div>')
    if not cols:
        return None

    themes = _and_list([name.lower() for name, _ in cfg.HEADLINE_THEMES])
    method = "".join(f"<span>{line.format(themes=themes)}</span>" for line in cfg.HEADLINE_METHOD)
    updated = ""
    try:
        stamp = datetime.strptime(news.get("generated_at", ""), "%Y-%m-%d %H:%M UTC")
        last = f"{_fmt_day(stamp.date())}, {stamp:%H:%M}&nbsp;UTC"
        reads = news.get("reads") or {}
        if (reads.get("count") or 0) > 1:
            first = datetime.strptime(reads["first"], "%Y-%m-%d %H:%M UTC")
            updated = f"Collected {reads['count']} times since {_fmt_day(first.date())}; last read {last}"
        else:
            updated = f"Read {last}"
        updated = f'<span class="nh-how-foot">{updated}</span>'
    except (ValueError, KeyError, TypeError):
        pass
    return (
        '<section class="nh" aria-labelledby="nh-title">'
        '<div class="nh-head">'
        '<div class="nh-head-l">'
        '<div class="nh-title" id="nh-title" role="heading" aria-level="2">The Week in Headlines</div>'
        f'<span class="nh-week">{_fmt_week(h["from"], h["to"])}</span>'
        '</div>'
        f'<details class="nh-how"><summary>{_NH_INFO}How these are chosen</summary>'
        f'<div class="nh-how-panel">{method}<span>{" ".join(r for r in read if r)}</span>{updated}</div></details>'
        '</div>'
        f'<div class="nh-grid{" is-single" if len(cols) == 1 else ""}">{"".join(cols)}</div>'
        '</section>'
    )


# ── State of the Economy, at the top of the India tab ──────────────────────
# The RBI's monthly article, from the soe.json that generate_soe.py writes into
# each India edition folder. An edition without one shows no briefing. Every
# sentence is RBI's own, quoted verbatim and dated: nothing here is summarised.

_SOE_CHEVRON = ('<svg class="soe-chev" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" '
                'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.4 1.8 6.9 5 3.4 8.2"/></svg>')


def _load_soe(charts: list[Path]) -> dict | None:
    """soe.json from the same edition folder as the India charts, so text and charts match."""
    path = charts[0].parent / "soe.json" if charts else None
    if path is None or not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _soe_changes_html(changes: list[dict], compared_with: str | None,
                      edition: datetime) -> str:
    """
    What changed since last month: RBI's sentence on each topic above the one it
    wrote a month earlier. Both sides are quoted and both are dated, so the
    reader compares the Bank's own wording rather than a verdict formed here.
    """
    if not changes or not compared_with:
        return ""
    try:
        before_month = datetime.strptime(compared_with, "%Y-%m")
    except (TypeError, ValueError):
        return ""

    rows = []
    for change in changes:
        now, before = _esc(change.get("now")), _esc(change.get("before"))
        if not now or not before:
            continue
        rows.append(
            '<div class="soe-chg">'
            f'<div class="soe-chg-topic">{_esc(change.get("topic"))}</div>'
            '<div class="soe-chg-lines">'
            f'<div class="soe-chg-now">'
            f'<span class="soe-chg-when is-now">{edition:%b}</span>{now}</div>'
            f'<div class="soe-chg-was">'
            f'<span class="soe-chg-when">{before_month:%b}</span>{before}</div>'
            '</div></div>'
        )
    if not rows:
        return ""
    return ('<div class="soe-changes">'
            f'<div class="soe-chg-head">What changed since {before_month:%B}</div>'
            f'<div>{"".join(rows)}</div></div>')


def _soe_changes_block(soe: dict) -> str:
    """The month-on-month comparison alone, for the column beside the snapshot table."""
    try:
        edition = datetime.strptime(soe["month"], "%Y-%m")
    except (KeyError, TypeError, ValueError):
        return ""
    return _soe_changes_html(soe.get("changes") or [], soe.get("compared_with"), edition)


def _soe_html(soe: dict) -> str | None:
    """
    RBI's opening summary, its concluding assessment behind a disclosure, and
    where it came from. The month-on-month comparison is drawn separately, in the
    column beside the snapshot table (`_soe_changes_block`). Returns None when
    the file is not what it should be, so a bad read leaves the tab without a
    briefing rather than with a fragment.

    The publication date is read but not printed: the edition month is already
    beside the title, and the date is only needed to tell a stale edition.
    """
    cfg = _fresh_config(_soe_settings)
    try:
        published = date.fromisoformat(soe["published"])
        edition = datetime.strptime(soe["month"], "%Y-%m")
        summary = _esc(soe["summary"]).strip()
    except (KeyError, TypeError, ValueError):
        return None
    if not summary:
        return None

    conclusion = [_esc(p) for p in (soe.get("conclusion") or []) if str(p).strip()]
    more = ""
    if conclusion:
        paragraphs = "".join(f"<span>{p}</span>" for p in conclusion)
        more = ('<details class="soe-more">'
                f'<summary>{_SOE_CHEVRON}RBI&rsquo;s concluding assessment</summary>'
                f'<div class="soe-concl">{paragraphs}</div></details>')

    url = _safe_url(soe.get("url"))
    link = (f'<a class="soe-link" href="{url}" target="_blank" rel="noopener noreferrer">'
            f'Read the full article{_NH_ARROW}<span class="nh-sr"> (opens in a new tab)</span></a>'
            if url else "")

    # The article is monthly; past the limit, say so rather than let a dated
    # quote read as this month's view.
    stale = ""
    if (date.today() - published).days > cfg.MAX_EDITION_AGE_DAYS:
        stale = ('<span class="soe-dot"></span>'
                 '<span class="soe-stale">Latest edition published; no newer one yet</span>')

    return (
        '<section class="soe" aria-labelledby="soe-title">'
        '<div class="soe-head">'
        '<div class="soe-head-l">'
        '<div class="soe-title" id="soe-title" role="heading" aria-level="2">State of the Economy</div>'
        f'<span class="soe-edition">{edition:%B %Y}</span>'
        '</div>'
        '</div>'
        f'<div class="soe-lede">{summary}</div>'
        f'{more}'
        '<div class="soe-meta">'
        f'<span class="soe-src">{cfg.ATTRIBUTION}</span>'
        f'{stale}'
        f'{"<span class=" + chr(34) + "soe-dot" + chr(34) + "></span>" + link if link else ""}'
        '</div>'
        '</section>'
    )


# ── Chart search ───────────────────────────────────────────────────────────
# Every chart on the site, findable by name from any page. The index is built
# from the chart files themselves, so a chart a generator adds is searchable as
# soon as it is published and one that is dropped disappears with it: no list of
# charts is kept by hand here. A result links to the chart's own anchor.

_SEARCH_PAGES: list[tuple[str, str, str]] = [
    # (chart folder, page name, url path)
    ("weekly",       "Weekly Markets", "weekly"),
    ("macro",        "World",          "world"),
    ("india",        "India",          "india"),
    ("rbi_sentinel", "RBI Sentinel",   "rbi-sentinel"),
]

# What a reader types, against what the chart files are called. Every term on the
# right appears in a filename; nothing here renames a chart or invents a subject
# the site does not cover.
_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "cpi": ("inflation",), "wpi": ("inflation",), "prices": ("inflation",),
    "jobs": ("labour",), "employment": ("labour",), "unemployment": ("labour",),
    "stocks": ("equities", "sector", "nifty", "breadth"), "shares": ("equities", "nifty"),
    "bonds": ("yield", "bond", "spreads"), "gsec": ("yield", "bond"), "gilts": ("yield", "bond"),
    "rates": ("rate", "yield", "transmission"), "repo": ("rate", "transmission", "stance"),
    "policy": ("rbi", "stance", "rate"), "mpc": ("rbi", "stance", "sentiment"),
    "passthrough": ("transmission",), "borrowers": ("transmission", "credit"),
    "currency": ("fx", "forex", "dollar"), "rupee": ("fx", "forex"), "dollar": ("fx", "dollar"),
    "growth": ("pmi", "iip", "cli"), "activity": ("pmi", "iip"), "industrial": ("iip",),
    "budget": ("fiscal", "expenditure", "capex", "gst"), "tax": ("gst",),
    "liquidity": ("money", "credit"), "loans": ("credit", "transmission"),
    "lending": ("credit", "transmission"), "deposits": ("credit", "transmission"),
    "foreign": ("fpi", "forex", "em"), "fii": ("fpi",), "flows": ("fpi",),
    "crude": ("oil",), "energy": ("oil", "commodities"),
    "crypto": ("btc", "eth"), "bitcoin": ("btc",),
    "valuation": ("cape", "erp", "premium"), "valuations": ("cape", "erp", "premium"),
    "volatility": ("vix", "move"), "emerging": ("em",),
}

_SEARCH_MIN_CHARS = 2
_SEARCH_MAX_HITS = 7


# Chart titles are built from filenames, which title-cases an acronym into
# "India Pmi". Every caption on the site is set in capitals by CSS, so this has
# never shown; in a list of suggestions it does, and only there.
_SEARCH_ACRONYMS = {
    "Btc": "BTC", "Cape": "CAPE", "Cli": "CLI", "Em": "EM", "Erp": "ERP", "Eth": "ETH",
    "Etf": "ETF", "Fpi": "FPI", "Fx": "FX", "Gdp": "GDP", "Gst": "GST", "Iip": "IIP",
    "It": "IT", "M2": "M2", "Move": "MOVE", "Nifty": "NIFTY", "Oecd": "OECD",
    "Pmi": "PMI", "Rbi": "RBI", "Spx": "SPX", "Us": "US", "Vix": "VIX", "Vs": "vs",
}


def _search_title(filename: str) -> str:
    """The chart's name as a suggestion shows it."""
    return " ".join(_SEARCH_ACRONYMS.get(word, word) for word in clean_title(filename).split())


@st.cache_data(ttl=600, show_spinner=False)
def _search_index() -> list[dict]:
    """Every published chart: what it is called, which page it is on, where it sits."""
    index = []
    for folder, page, url_path in _SEARCH_PAGES:
        charts, _ = get_charts(folder)
        for chart in charts:
            title = _search_title(chart.name)
            index.append({
                "title": title,
                "page": page,
                "path": url_path,
                "slug": _chart_slug(chart.name),
                "terms": f"{title} {chart_key(chart.name)} {page}".lower().replace("_", " "),
            })
    return index


# The scroll that puts a chart on screen, used both by the search box and by a
# ?chart= link someone has kept. The page is still being built when it starts,
# so it waits for the chart's anchor to appear; the page then keeps growing as
# the charts above it load, so it holds the position until the layout settles.
# A reader who scrolls takes over at once.
#
# Streamlit scrolls a container of its own rather than the window, so the offset
# is worked out against that container and not against the document.
_SCROLL_JS = r"""
function ehScrollToChart(outer, slug) {
  const doc = outer.document, id = "chart-" + slug;
  const box = () => doc.querySelector('[data-testid="stMain"]');
  const place = () => {
    const target = doc.getElementById(id);
    if (!target) return false;
    const main = box();
    if (main) {
      const top = target.getBoundingClientRect().top - main.getBoundingClientRect().top
                  + main.scrollTop - 24;
      main.scrollTo({top: Math.max(top, 0), behavior: "auto"});
    } else {
      target.scrollIntoView({block: "start"});
    }
    return true;
  };
  if (outer.__ehScrollTimer) clearInterval(outer.__ehScrollTimer);
  let tries = 0;
  outer.__ehScrollTimer = setInterval(() => {
    if (place()) {
      clearInterval(outer.__ehScrollTimer);
      const holds = [300, 900, 1800, 3000].map((ms) => setTimeout(place, ms));
      const release = () => holds.forEach(clearTimeout);
      const main = box() || outer;
      ["wheel", "touchstart", "keydown"].forEach(
        (e) => main.addEventListener(e, release, {once: true, passive: true}));
      const url = new URL(outer.location.href);
      url.searchParams.delete("chart");
      outer.history.replaceState(null, "", url);
    } else if (++tries > 150) {
      clearInterval(outer.__ehScrollTimer);
    }
  }, 100);
}
"""


def _scroll_to_chart_html(slug: str) -> str:
    """The scroll on its own, for ?chart=<slug> arriving in the URL."""
    return ("<script>" + _SCROLL_JS
            + f"ehScrollToChart(window.parent, {json.dumps(slug)});</script>")


# ── The search box ─────────────────────────────────────────────────────────
# Streamlit's own text input only reports what was typed once Enter is pressed,
# which is not how a search box behaves anywhere else, so the field is drawn in
# a component frame with the whole chart index inside it and matches the reader
# as they type. Two things follow from that frame:
#
#   * the list of suggestions is drawn in the page rather than in the frame —
#     an iframe cannot paint outside itself, and the list has to lie over the
#     page instead of pushing it down;
#   * choosing a chart on another page clicks that page's own link, so the app
#     moves as it does when the reader clicks it, and the scroll above waits
#     for the chart to arrive. A full page load is the fallback if that link
#     is not there.
_SEARCH_TEMPLATE = r"""
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body { margin: 0; padding: 0; background: transparent; overflow: hidden; }
.ehs-box {
  display: flex; align-items: center; gap: 0.5rem;
  background: #FFFFFF; border: 1px solid rgba(10, 31, 61, 0.22); border-radius: 2px;
  padding: 0.4rem 0.6rem; transition: border-color 0.15s ease;
}
.ehs-box:focus-within { border-color: #0A1F3D; }
.ehs-icon { flex: none; width: 15px; height: 15px; display: block; }
#ehs-q {
  flex: 1 1 auto; min-width: 0; border: 0; outline: 0; background: transparent;
  font-family: 'Inter', -apple-system, sans-serif; font-size: 0.85rem;
  color: #0A1F3D; line-height: 1.45; padding: 0;
}
#ehs-q::placeholder { color: #8A929E; }
#ehs-q::-webkit-search-cancel-button { display: none; }
.ehs-clear {
  flex: none; display: none; border: 0; background: transparent; cursor: pointer;
  padding: 0 0 0 0.2rem; line-height: 1; color: #8A929E;
  font-family: 'Inter', -apple-system, sans-serif; font-size: 1rem; font-weight: 600;
}
.ehs-clear:hover { color: #0A1F3D; }
.ehs-box.has-text .ehs-clear { display: block; }
</style></head><body>
<div class="ehs-box" id="ehs-box">
  <svg class="ehs-icon" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.4"
       stroke-linecap="round" aria-hidden="true">
    <circle cx="10.4" cy="10.4" r="7.1"/><path d="M15.6 15.6 L21 21"/>
  </svg>
  <input id="ehs-q" type="text" autocomplete="off" spellcheck="false"
         placeholder="__PLACEHOLDER__" aria-label="Search charts"
         role="combobox" aria-expanded="false" aria-autocomplete="list">
  <button class="ehs-clear" id="ehs-clear" type="button" aria-label="Clear search">&times;</button>
</div>
<script>
__SCROLL__
(() => {
  const INDEX = __INDEX__, ALIASES = __ALIASES__, PATHS = __PATHS__;
  const MAX = __MAX__, MIN = __MIN__;
  const outer = window.parent, doc = outer.document, frame = window.frameElement;
  const box = document.getElementById("ehs-box");
  const input = document.getElementById("ehs-q");
  const clearBtn = document.getElementById("ehs-clear");

  const PANEL_CSS = `
#ehs-panel {
  position: fixed; z-index: 2000000; display: none;
  background: #FFFFFF; border: 1px solid rgba(10, 31, 61, 0.22); border-top: none;
  box-shadow: 0 12px 30px rgba(10, 31, 61, 0.14);
  max-height: 21rem; overflow-y: auto;
}
#ehs-panel.is-open { display: block; }
.ehs-hit {
  display: flex; align-items: baseline; justify-content: space-between; gap: 1rem;
  padding: 0.44rem 0.72rem 0.48rem 0.72rem; cursor: pointer;
  border-bottom: 1px solid rgba(10, 31, 61, 0.07);
}
.ehs-hit:last-child { border-bottom: none; }
.ehs-hit.is-active { background: #F4F2E9; }
.ehs-hit-name {
  font-family: 'Newsreader', Georgia, 'Times New Roman', serif; font-optical-sizing: auto;
  font-size: 0.95rem; font-weight: 400; line-height: 1.3; color: #0A1F3D; min-width: 0;
}
.ehs-hit-name b { font-weight: 700; color: #000000; }
.ehs-hit-page {
  font-family: 'Inter', -apple-system, sans-serif; font-size: 0.58rem; font-weight: 700;
  letter-spacing: 0.07em; text-transform: uppercase; color: #A85600; white-space: nowrap;
}
.ehs-empty {
  font-family: 'Inter', -apple-system, sans-serif; font-size: 0.78rem; color: #6A7280;
  padding: 0.55rem 0.72rem 0.6rem 0.72rem;
}
.ehs-foot {
  font-family: 'Inter', -apple-system, sans-serif; font-size: 0.55rem; font-weight: 600;
  letter-spacing: 0.06em; text-transform: uppercase; color: #9AA2AD;
  padding: 0.4rem 0.72rem 0.45rem 0.72rem; border-top: 1px solid rgba(10, 31, 61, 0.07);
}
`;

  // A rerun rebuilds this frame; anything the last one left in the page goes first.
  if (outer.__ehsCleanup) { try { outer.__ehsCleanup(); } catch (e) {} }
  if (!doc.getElementById("ehs-panel-style")) {
    const style = doc.createElement("style");
    style.id = "ehs-panel-style";
    style.textContent = PANEL_CSS;
    doc.head.appendChild(style);
  }
  const panel = doc.createElement("div");
  panel.id = "ehs-panel";
  panel.setAttribute("role", "listbox");
  doc.body.appendChild(panel);

  const esc = (s) => String(s).replace(/[&<>"]/g,
    (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  // What the reader typed, shown in bold where it matched the chart's name.
  const mark = (title, words) => {
    let out = esc(title);
    for (const w of words) {
      if (w.length < 2) continue;
      const safe = w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      out = out.replace(new RegExp("(" + safe + ")", "ig"), "<b>$1</b>");
    }
    return out;
  };

  // A typo still finds the chart: one edit for a short word, two for a long one.
  const near = (a, b) => {
    if (Math.abs(a.length - b.length) > 2) return false;
    let prev = Array.from({length: b.length + 1}, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      for (let j = 1; j <= b.length; j++) {
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1,
                          prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
      prev = cur;
    }
    return prev[b.length] <= (Math.max(a.length, b.length) >= 8 ? 2 : 1);
  };

  // Every word has to match something, so a second word narrows the list
  // rather than widening it. A word matches a chart's name, its page, or one
  // of the aliases; the start of a word counts for more than the middle of one.
  const search = (text) => {
    const words = text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    if (!words.length || words.join("").length < MIN) return {words: words, hits: []};
    const found = [];
    for (const item of INDEX) {
      const terms = item.terms, vocab = terms.split(" ");
      let score = 0, ok = true;
      for (const word of words) {
        if (vocab.some((v) => v.startsWith(word))) score += 3;
        else if (terms.indexOf(word) >= 0) score += 2;
        else {
          const aliases = (ALIASES[word] || []).filter((a) => terms.indexOf(a) >= 0).length;
          if (aliases) score += aliases;
          else if (word.length >= 4 && vocab.some((v) => near(word, v))) score += 1;
          else { ok = false; break; }
        }
      }
      if (ok && score) found.push([score, item]);
    }
    found.sort((a, b) => b[0] - a[0] || a[1].title.localeCompare(b[1].title));
    return {words: words, hits: found.slice(0, MAX).map((h) => h[1])};
  };

  let shown = [], active = -1, open = false;

  const place = () => {
    const r = frame.getBoundingClientRect();
    const b = box.getBoundingClientRect();
    if (r.bottom < 0 || r.top > outer.innerHeight) { panel.classList.remove("is-open"); return; }
    panel.style.left = r.left + "px";
    panel.style.top = (r.top + b.height) + "px";
    panel.style.width = r.width + "px";
    if (open) panel.classList.add("is-open");
  };

  const show = () => { open = true; input.setAttribute("aria-expanded", "true"); place(); };
  const hide = () => {
    open = false; active = -1;
    input.setAttribute("aria-expanded", "false");
    panel.classList.remove("is-open");
  };

  const paint = () => {
    const rows = panel.querySelectorAll(".ehs-hit");
    rows.forEach((row, i) => row.classList.toggle("is-active", i === active));
    if (active >= 0 && rows[active]) rows[active].scrollIntoView({block: "nearest"});
  };

  const render = () => {
    const text = input.value;
    box.classList.toggle("has-text", text.length > 0);
    if (!text.trim()) { panel.innerHTML = ""; hide(); return; }
    const {words, hits} = search(text);
    shown = hits;
    active = hits.length ? 0 : -1;
    panel.innerHTML = hits.length
      ? hits.map((h, i) =>
          '<div class="ehs-hit' + (i === 0 ? " is-active" : "") + '" data-i="' + i + '"'
          + ' role="option" aria-selected="' + (i === 0) + '">'
          + '<span class="ehs-hit-name">' + mark(h.title, words) + "</span>"
          + '<span class="ehs-hit-page">' + esc(h.page) + "</span></div>").join("")
        + '<div class="ehs-foot">&uarr;&darr; to move &middot; Enter to open</div>'
      : '<div class="ehs-empty">No chart matches &ldquo;' + esc(text.trim()) + "&rdquo;.</div>";
    show();
  };

  // Which page is on screen: the app's default page answers to the root URL,
  // so anything that is not one of the other paths is the default.
  const currentPath = () => {
    const seg = outer.location.pathname.replace(/\/+$/, "").split("/").pop() || "";
    return PATHS.indexOf(seg) >= 0 ? seg : PATHS[0];
  };

  const hardNav = (item) => {
    let base = outer.location.pathname.replace(/\/+$/, "");
    const seg = base.split("/").pop();
    if (PATHS.indexOf(seg) >= 0) base = base.slice(0, -(seg.length + 1));
    outer.location.assign(base + "/" + (item.path === PATHS[0] ? "" : item.path)
                          + "?chart=" + encodeURIComponent(item.slug));
  };

  const go = (item) => {
    if (!item) return;
    hide();
    input.blur();
    if (currentPath() === item.path) { ehScrollToChart(outer, item.slug); return; }
    const link = doc.querySelector('[class*="st-key-ehnav-' + item.path + '"] a');
    if (!link) { hardNav(item); return; }
    link.click();
    // The scroll is armed only once the app has actually changed page: two
    // pages can hold a chart of the same name, and it should be the new one.
    let waited = 0;
    const timer = setInterval(() => {
      if (currentPath() === item.path) { clearInterval(timer); ehScrollToChart(outer, item.slug); }
      else if ((waited += 100) > 2500) { clearInterval(timer); hardNav(item); }
    }, 100);
  };

  input.addEventListener("input", render);
  input.addEventListener("focus", () => { if (input.value.trim()) render(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!open || !shown.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length;
      paint();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (shown.length) go(shown[Math.max(active, 0)]);
    } else if (e.key === "Escape") {
      if (open) hide();
      else { input.value = ""; render(); }
    }
  });
  clearBtn.addEventListener("click", () => { input.value = ""; render(); input.focus(); });

  // mousedown, not click: the field must not lose focus before the choice is read.
  const onPanelDown = (e) => {
    const row = e.target.closest(".ehs-hit");
    if (!row) return;
    e.preventDefault();
    go(shown[+row.dataset.i]);
  };
  const onPanelMove = (e) => {
    const row = e.target.closest(".ehs-hit");
    if (!row) return;
    active = +row.dataset.i;
    paint();
  };
  const onDocDown = (e) => { if (!panel.contains(e.target)) hide(); };
  const onMove = () => { if (open) place(); };

  panel.addEventListener("mousedown", onPanelDown);
  panel.addEventListener("mousemove", onPanelMove);
  doc.addEventListener("mousedown", onDocDown);
  outer.addEventListener("scroll", onMove, true);
  outer.addEventListener("resize", onMove);

  outer.__ehsCleanup = () => {
    doc.removeEventListener("mousedown", onDocDown);
    outer.removeEventListener("scroll", onMove, true);
    outer.removeEventListener("resize", onMove);
    const stale = doc.getElementById("ehs-panel");
    if (stale) stale.remove();
  };
})();
</script></body></html>
"""

_SEARCH_PLACEHOLDER = "Search charts — try credit, PMI, inflation, gold"
_SEARCH_BOX_HEIGHT = 44          # the field, drawn at the top of its frame


def _search_box_html() -> str:
    """The search field, with every chart on the site inside it."""
    return (_SEARCH_TEMPLATE
            .replace("__SCROLL__", _SCROLL_JS)
            .replace("__INDEX__", json.dumps(_search_index(), separators=(",", ":")))
            .replace("__ALIASES__", json.dumps({k: list(v) for k, v in _SEARCH_ALIASES.items()},
                                               separators=(",", ":")))
            .replace("__PATHS__", json.dumps([p for _, _, p in _SEARCH_PAGES],
                                             separators=(",", ":")))
            .replace("__MAX__", str(_SEARCH_MAX_HITS))
            .replace("__MIN__", str(_SEARCH_MIN_CHARS))
            .replace("__PLACEHOLDER__", _SEARCH_PLACEHOLDER))


def _page_header_html(title: str, dek: str, meta_label: str, meta_value: str,
                      nav: list[tuple[str, str]] | None = None) -> str:
    """Page masthead; `nav` is (label, anchor id) pairs drawn as jump links under the standfirst."""
    links = ""
    if nav:
        links = ('<nav class="tab-jump" aria-label="Sections">'
                 + "".join(f'<a href="#{anchor}">{label}</a>' for label, anchor in nav)
                 + '</nav>')
    return (
        '<div class="rbi-head">'
        '<div class="rbi-head-text">'
        f'<p class="rbi-head-title">{title}</p>'
        f'<p class="rbi-head-dek">{dek}</p>'
        f'{links}'
        '</div>'
        '<div class="rbi-head-meta">'
        f'<span class="rbi-head-meta-label">{meta_label}</span>'
        f'<span class="rbi-head-meta-value">{meta_value}</span>'
        '</div>'
        '</div>'
    )


# ── Weekly Markets page ────────────────────────────────────────────────────

def page_weekly() -> None:
    charts, date_label = get_charts("weekly")

    if not charts:
        st.warning(
            "No weekly charts found. Run **generate_weekly.py** locally "
            "or trigger the Weekly Markets workflow on GitHub Actions."
        )
    else:
        weekly_cfg = _fresh_config(_weekly_settings)
        summary, charts = _pop_summary(charts, [weekly_cfg.SUMMARY_CHART, "00_"])
        # Sections and their chart order live in config/weekly_settings.py.
        sections, unlisted = group_charts(charts, weekly_cfg.WEEKLY_SECTIONS)

        st.markdown(
            _page_header_html(
                "The Week in Markets",
                "Weekly moves and the trends behind equities, bonds, currencies, commodities "
                "and crypto across the major markets.",
                "Last updated", _fmt_day(datetime.strptime(date_label, "%Y-%m-%d").date()),
                nav=[(title, _anchor("weekly", title)) for title, _ in sections],
            ),
            unsafe_allow_html=True,
        )

        # The week in headlines, when this edition has them.
        news = _load_news(charts)
        headlines = _headlines_html(news) if news else None
        if headlines:
            st.markdown(headlines, unsafe_allow_html=True)

        if summary:
            _render_summary(summary)

        for title, section_charts in sections:
            _section(title, anchor=_anchor("weekly", title))
            _render_grid(section_charts, center_odd=True)

        # A chart the generator writes but the config does not list yet.
        if unlisted:
            _section("Other")
            _render_grid(unlisted, center_odd=True)


# ── World page ─────────────────────────────────────────────────────────────

def page_world() -> None:
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
            _page_header_html(
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
                _chart_anchor(regime)
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


# ── India page ─────────────────────────────────────────────────────────────

def page_india() -> None:
    charts, date_label = get_charts("india")

    if not charts:
        st.warning(
            "No India charts found. Run **generate_india.py** locally "
            "or trigger the India Dashboard workflow on GitHub Actions."
        )
    else:
        st.markdown(
            _page_header_html(
                "The Indian Economy",
                "Growth, prices, money, trade, capital flows and public finances, from RBI, MoSPI, "
                "NSDL and CAG data. Charts reflect the latest data committed to the repository.",
                "Edition", datetime.strptime(date_label, "%Y-%m").strftime("%B %Y"),
            ),
            unsafe_allow_html=True,
        )

        # RBI's own read of the month, when this edition was published with one.
        soe = _load_soe(charts)
        briefing = _soe_html(soe) if soe else None
        if briefing:
            st.markdown(briefing, unsafe_allow_html=True)

        # The month's numbers beside the month's words: the snapshot table on the
        # left, RBI's verdict on each topic against last month's on the right.
        # Either half stands on its own when the other is missing.
        summary, charts = _pop_summary(charts, ["india_table", "05_india"])
        changed = _soe_changes_block(soe) if soe else ""
        if summary and changed:
            col_table, col_changed = st.columns([1.2, 1], gap="large")
            with col_table:
                _chart_anchor(summary)
                st.image(str(summary), use_container_width=True)
            with col_changed:
                st.markdown(changed, unsafe_allow_html=True)
        elif summary:
            _render_summary(summary)
        elif changed:
            st.markdown(changed, unsafe_allow_html=True)

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
        monetary_kws = ["money", "supply", "credit", "deposit", "m3", "transmission"]
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


# ── RBI Sentinel page ───────────────────────────────────────────────────────

def page_rbi() -> None:
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
<p class="rbi-head-note" style="margin-top: 1.1rem;">The scored database behind these charts took ten years of MPC
documents and a large language model to build. If you would like to use it in your own research, please get in
touch at <a href="mailto:shreyasurgunde20@gmail.com">shreyasurgunde20@gmail.com</a> &mdash; glad to share it,
I would just like to know where it goes.</p>
""", unsafe_allow_html=True)

        # ── Decision strip: the cycle's facts in one row, ahead of any chart ──
        if brief:
            st.markdown(_decision_strip_html(brief), unsafe_allow_html=True)

        # ── Hero: Stance Meter & AI Briefing (Side-by-Side) ──
        stance, charts = _pop_summary(charts, ["01_rbi_stance_meter"])
        if stance:
            col_chart, col_text = st.columns([1.2, 1], gap="large")

            with col_chart:
                _chart_anchor(stance)
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
            _chart_anchor(trajectory)
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
            _chart_anchor(comparison)
            st.image(str(comparison), use_container_width=True)
            insight = get_insight(comparison.name)
            if insight:
                with st.expander("Chart insights"):
                    st.markdown(insight)

        # Supporting chart (CENTERED)
        if radar:
            _, col_mid, _ = st.columns([1, 2, 1])
            with col_mid:
                _chart_anchor(radar)
                st.image(str(radar), use_container_width=True)
                insight = get_insight(radar.name)
                if insight:
                    with st.expander("Chart insights"):
                        st.markdown(insight)
                        
        # ── Repo Rate vs Sentiment (PRIMARY) ──
        rate_chart, charts = _pop_summary(charts, ["05_rbi_rate_and_sentiment"])
        if rate_chart:
            _section("Repo Rate vs. Sentiment")
            _chart_anchor(rate_chart)
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
            _chart_anchor(_tone_chart)
            st.image(str(_tone_chart), use_container_width=True)
            insight = get_insight(_tone_chart.name)
            if insight:
                with st.expander("Chart insights and testing method"):
                    st.markdown(insight)

        # ── Governor Signal Analysis ──
        gov_divergence, charts = _pop_summary(charts, ["07_rbi_governor_divergence"])

        if gov_divergence:
            _section("Governor Signal Analysis")
            _chart_anchor(gov_divergence)
            st.image(str(gov_divergence), use_container_width=True)
            insight = get_insight(gov_divergence.name)
            if insight:
                with st.expander("Chart insights"):
                    st.markdown(insight)

        # ── Catch-all ──
        if charts:
            _section("Other")
            _render_grid(charts)


# ---------------------------------------------------------------------------
# Masthead, navigation, page
# ---------------------------------------------------------------------------
# Each page has its own URL (/world, /india, /rbi-sentinel), so a section can be
# linked to and the browser's back button works. Weekly Markets is the default
# page and keeps the app's root URL, so older links still open it.
#
# The navigation is drawn here rather than by Streamlit (position="hidden"):
# in the sidebar it would be hidden behind the collapsed sidebar, and at the
# top of the app it would sit above the masthead. These links keep the tabs'
# place under the masthead and are styled to match.

PAGES = [
    st.Page(page_weekly, title="Weekly Markets", url_path="weekly", default=True),
    st.Page(page_world, title="World", url_path="world"),
    st.Page(page_india, title="India", url_path="india"),
    st.Page(page_rbi, title="RBI Sentinel", url_path="rbi-sentinel"),
]
current = st.navigation(PAGES, position="hidden")
if current.url_path:                      # the default page keeps the plain title
    st.set_page_config(page_title=f"{current.title} · The Economics Hub")

st.markdown(
    '<h1 class="insti-masthead">Global Macro &amp; Cross-Asset Monitor</h1>'
    '<p class="insti-descriptor">Research &amp; Maintained by '
    '<a class="insti-author" href="https://shreyasxi.github.io/" target="_blank" rel="noopener">'
    'Shreyas Urgunde</a></p>'
    '<p class="insti-byline">Updated every Saturday</p>'
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

nav = st.container(key="ehnav", horizontal=True, gap="medium")
for page in PAGES:
    with nav.container(key=f"ehnav-{page.url_path or 'weekly'}"
                           f"{'-current' if page.url_path == current.url_path else ''}"):
        st.page_link(page, label=page.title)

# One box for all four pages: type what you want to see, land on the chart.
# The suggestions appear as the reader types and lie over the page, so nothing
# below moves until a chart is chosen.
with st.container(key="ehsearch"):
    components.html(_search_box_html(), height=_SEARCH_BOX_HEIGHT)

current.run()

# The chart a search result asked for, put on screen now the page has been
# built. ?chart=<slug> does the same thing from a link someone has kept.
_wanted = st.session_state.pop("_scroll_to", "") or st.query_params.get("chart", "")
if re.fullmatch(r"[a-z0-9-]{2,64}", _wanted or ""):
    components.html(_scroll_to_chart_html(_wanted), height=0)
