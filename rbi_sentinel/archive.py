"""Read-only executive-summary archive. No fetchers or scoring calls."""
from datetime import datetime
import html
import re
import sqlite3
from pathlib import Path
import importlib

import streamlit as st

from rbi_sentinel.db import manager


STYLE = """
<style>
.rba-back {display:inline-block;color:#4A5262!important;font:500 .82rem Inter,sans-serif;
    text-decoration:none;margin:0 0 1.4rem;}
.rba-back:hover {color:#0A1F3D!important;text-decoration:underline;}
.rba-intro {display:flex;justify-content:space-between;align-items:flex-end;gap:2rem;
    padding-bottom:1.4rem;border-bottom:3px solid #0A1F3D;margin-bottom:1.5rem;}
.rba-kicker {font:700 .68rem Inter,sans-serif!important;letter-spacing:.13em;text-transform:uppercase;
    color:#8D2635;margin:0 0 .65rem;}
.rba-title {font:600 clamp(2rem,4vw,2.8rem) Newsreader,Georgia,serif!important;color:#0A1F3D;
    line-height:1.12;margin:0 0 .7rem;}
.rba-dek {font:400 .95rem/1.6 Inter,sans-serif;color:#4A5262;max-width:40rem;margin:0;}
.rba-count {font:500 .78rem/1.7 Inter,sans-serif;color:#4A5262;text-align:right;white-space:nowrap;}
.rba-count strong {display:block;font:600 2rem Newsreader,Georgia,serif;color:#0A1F3D;}
[class*="st-key-rbi-archive-controls"] {max-width:48rem;margin:0 auto 1.5rem;}
.rba-paper {max-width:48rem;margin:0 auto;padding:2rem 0 1rem;border-top:1px solid #CBD2DC;}
.rba-paper h2 {font:600 clamp(1.8rem,3vw,2.35rem)/1.2 Newsreader,Georgia,serif!important;
    color:#0A1F3D;margin:0 0 1rem;}
.rba-meta {display:flex;flex-wrap:wrap;gap:.85rem 1.8rem;
    padding-bottom:1.1rem;font:500 1rem/1.75 Inter,sans-serif;color:#24282F;}
.rba-meta b {color:#0A1F3D;font-weight:700;}
.rba-docs {font:500 1rem/1.75 Inter,sans-serif;color:#24282F;display:flex;flex-wrap:wrap;
    gap:.55rem 1.4rem;border-bottom:1px solid #CBD2DC;padding-bottom:1.35rem;margin-bottom:1.6rem;}
.rba-docs b {color:#0A1F3D;font-weight:700;}
.rba-docs a {color:#1F4E79!important;text-decoration:underline;text-underline-offset:3px;}
.rba-docs a:hover {color:#8D2635!important;}
.rba-paper h3.rba-label {font:600 1.4rem/1.35 Newsreader,Georgia,serif!important;
    color:#0A1F3D;margin:0 0 1.15rem;padding:0 0 .65rem;border-bottom:2px solid #0A1F3D;}
.rba-copy p {font:400 1.12rem/1.85 Newsreader,Georgia,serif;color:#24282F;margin:0 0 1.4rem;}
.rba-copy strong {font-weight:650;color:#0A1F3D;}
.rba-note {border-top:1px solid #E3E7EC;padding-top:1rem;margin-top:1.6rem;
    font:400 .76rem/1.65 Inter,sans-serif;color:#697480;}
@media(max-width:640px) {.rba-intro{align-items:flex-start;flex-direction:column;gap:1rem;}
    .rba-count{text-align:left;}.rba-count strong{display:inline;font-size:1rem;margin-right:.4rem;}
    .rba-paper{padding-top:1.5rem;}.rba-copy p{font-size:1.05rem;line-height:1.75;}}
</style>
"""


def narrative_html(text: str) -> str:
    """Preserve saved prose, while matching the live summary's label treatment."""
    for label in ("How to read this document:", "Practical takeaway:"):
        text = text.replace("**" + label + "**", "").replace(label, "")
    paragraphs = re.split(r"\n\s*\n", text.strip())
    safe = [re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>",
                   html.escape(p.strip()).replace("\n", " ")) for p in paragraphs if p.strip()]
    return "".join("<p>" + p + "</p>" for p in safe)


def meeting_label(row: dict) -> str:
    when = datetime.strptime(row["meeting_date"], "%Y-%m-%d")
    return f"{when.day} {when:%B %Y}"


def render() -> None:
    st.markdown(STYLE, unsafe_allow_html=True)
    st.markdown('<a class="rba-back" href="/rbi-sentinel" target="_self">← Back to RBI Sentinel</a>',
                unsafe_allow_html=True)
    try:
        mtime = Path(manager.__file__).stat().st_mtime
        if getattr(manager, '_archive_loaded_mtime', None) != mtime:
            importlib.reload(manager)
            manager._archive_loaded_mtime = mtime
        rows = manager.get_summary_archive()
    except (sqlite3.Error, OSError):
        st.warning("The executive-summary archive is temporarily unavailable.")
        return
    if not rows:
        st.info("No saved executive summaries are available yet.")
        return
    years = list(dict.fromkeys(r["meeting_date"][:4] for r in rows))
    st.markdown(
        '<header class="rba-intro"><div>'
        '<h1 class="rba-title">RBI Sentiment Archive</h1>'
        '<p class="rba-dek">Executive summaries from each monetary policy meeting. '
        'Browse the decisions, the reasoning and the implications across policy cycles.</p></div>'
        f'<div class="rba-count"><strong>{len(rows)}</strong>saved summaries<br>'
        f'{years[-1]}–{years[0]}</div></header>', unsafe_allow_html=True,
    )
    with st.container(key="rbi-archive-controls"):
        left, right = st.columns([1, 3], gap="medium")
        with left:
            year = st.selectbox("Year", years, key="rbi-archive-year")
        meetings = [r for r in rows if r["meeting_date"].startswith(year)]
        with right:
            cycle = st.selectbox("MPC meeting", [r["policy_cycle"] for r in meetings],
                                 format_func=lambda c: meeting_label(next(r for r in meetings if r["policy_cycle"] == c)),
                                 key="rbi-archive-meeting-" + year)
    row = next(r for r in meetings if r["policy_cycle"] == cycle)
    rate = row.get("repo_rate_pct")
    action = {"hike": "Hike", "cut": "Cut", "hold": "Hold"}.get(row.get("rate_action"), "Unavailable")
    bps = row.get('rate_change_bps')
    if action in ('Hike', 'Cut') and bps is not None:
        action += f' {abs(bps):g} bp'
    fields = [('Repo rate', f'{rate:.2f}%' if rate is not None else 'Unavailable'),
              ('Decision', action), ('Stated stance', (row.get('stated_stance') or 'Unavailable').capitalize()),
              ('Voting split', (row.get('voting_split') + ' (rate decision)') if row.get('voting_split') else 'Unavailable')]
    score = row.get('composite_overall_score')
    tone = ('Hawkish' if score > .05 else 'Dovish' if score < -.05 else 'Neutral') if score is not None else ''
    fields.append(('Sentiment score', f'{score:+.2f} · {tone}' if score is not None else 'Unavailable'))
    meta = ''.join(f'<span><b>{label}:</b> {html.escape(value)}</span>' for label, value in fields)
    names = {'resolution': 'Resolution', 'minutes': 'Minutes', 'governor_statement': 'Governor’s Statement'}
    links = []
    for kind, name in names.items():
        doc = next((d for d in row.get('documents', []) if d['doc_type'] == kind), None)
        if doc and doc['source_url'].startswith(('https://', 'http://')):
            links.append(f'<a href="{html.escape(doc["source_url"], quote=True)}" target="_blank" rel="noopener noreferrer">{name}</a>')
    documents = '<div class="rba-docs"><b>Policy documents:</b>' + (''.join(links) or '<span>Unavailable</span>') + '</div>'
    st.markdown(
        '<article class="rba-paper">'
        f'<h2>{meeting_label(row)}</h2><div class="rba-meta">{meta}</div>'
        + documents + '<h3 class="rba-label">Executive Summary</h3><div class="rba-copy">'
        + narrative_html(row["composite_narrative"]) + '</div>'
        '<div class="rba-note">Earlier meetings were analysed retrospectively. This archive displays the saved analysis '
        'for each meeting; it does not reproduce every previous publication or revision.</div></article>',
        unsafe_allow_html=True,
    )
