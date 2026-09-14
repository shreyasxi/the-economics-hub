"""
rbi_sentinel/cleaners/policy_facts.py

Structured facts read out of a Monetary Policy Resolution's text: the
full-year CPI and real GDP projections, the stance the MPC states, and the
dates of the next meeting.

Every Resolution carries these in a small set of recurring phrasings, so a
few patterns cover the modern documents without an LLM call. Anything that
does not match comes back as None — the dashboard shows a dash rather than
a guess.
"""

import re
from datetime import date
from typing import Optional

_FY = r"(?P<fy>20\d\d-\d\d)"
_PCT = r"\(?(?P<sign>[-+])?\)?(?P<value>\d+(?:\.\d+)?) per ?cent"
_VERB = r"(?:is|are|has been|have been)(?: now)? (?:projected|retained|revised(?: \w+)?)(?: to be)?(?: at)?"

# Full-year figures only: the (?<!:) guard rejects quarterly "Q1:2026-27".
# "Estimated" is left out on purpose — it introduces the NSO's outturn for
# the year just ended, not the MPC's projection.
_PROJECTION = {
    key: [
        # "CPI inflation for 2026-27 is projected at 5.0 per cent"
        re.compile(rf"{label} (?:for|in) (?:the (?:financial )?year )?(?<!:){_FY} {_VERB} {_PCT}", re.I),
        # "CPI inflation is projected at 5.4 per cent for 2023-24"
        re.compile(rf"{label} {_VERB} {_PCT} (?:for|in) (?:the (?:financial )?year )?(?<!:){_FY}", re.I),
    ]
    for key, label in (("cpi", r"CPI inflation"), ("gdp", r"(?:real )?GDP growth"))
}

_STANCE_WORDS = r"['‘’\"]?(?P<stance>neutral|accommodative|withdrawal of accommodation|calibrated tightening)"
# Anchored on the committee's decision verbs. Dissents are phrased as named
# members who "voted for a change in stance to neutral", which a bare
# "stance ... to X" pattern would otherwise report as the decision.
_DECIDED = r"(?:decided|considers it appropriate|voted unanimously|unanimously voted) to (?:(?!\. [A-Z]).){0,120}?"
_STANCE = [
    # "decided to change the monetary policy stance from withdrawal of accommodation to 'neutral'"
    re.compile(rf"{_DECIDED}stance(?: of monetary policy)? (?:from [a-z ]+? )?to {_STANCE_WORDS}", re.I),
    # "continue with the disinflationary stance of withdrawal of accommodation"
    re.compile(rf"{_DECIDED}continue with the [a-z]+ stance of {_STANCE_WORDS}", re.I),
    # "decided to continue with the neutral stance" · "remain focused on withdrawal of accommodation"
    re.compile(rf"{_DECIDED}(?:continue with|remain focused on|retain) (?:the |a )?{_STANCE_WORDS}", re.I),
]

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
_M = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
# "October 5 to 7, 2026" · "April 6 - 8, 2026" · "September 29 to October 1, 2025"
_NEXT = re.compile(
    rf"next meeting of the MPC (?:is|will be) scheduled (?:for|during|from|on) "
    rf"{_M} (\d{{1,2}})(?:\s*(?:-|–|to|and)\s*(?:{_M} )?(\d{{1,2}}))?,? (\d{{4}})",
    re.I,
)


def _projection(text: str, key: str) -> Optional[dict]:
    """The full-year projection for the latest fiscal year the document names."""
    found = []
    for pattern in _PROJECTION[key]:
        for m in pattern.finditer(text):
            value = float(m["value"]) * (-1 if m["sign"] == "-" else 1)
            found.append({"fy": m["fy"], "value": value})
    if not found:
        return None
    # A February Resolution can project both the closing and the coming year;
    # the coming year is the forward-looking figure. First mention wins a tie.
    latest = max(f["fy"] for f in found)
    return next(f for f in found if f["fy"] == latest)


def _stated_stance(text: str) -> Optional[str]:
    """The stance in the first decision sentence that states one."""
    matches = [m for p in _STANCE for m in [p.search(text)] if m]
    if not matches:
        return None
    return min(matches, key=lambda m: m.start())["stance"].lower()


def _next_meeting(text: str) -> Optional[dict]:
    m = _NEXT.search(text)
    if not m:
        return None
    month1, day1, month2, day2, year = m.groups()
    year = int(year)
    start = date(year, _MONTHS[month1.lower()], int(day1))
    end_month = _MONTHS[(month2 or month1).lower()]
    end = date(year, end_month, int(day2)) if day2 else start
    return {"start": start, "end": end}


def extract_policy_facts(text: Optional[str]) -> dict:
    """CPI and GDP projections, stated stance and next meeting from a Resolution."""
    if not text:
        return {"cpi": None, "gdp": None, "stated_stance": None, "next_meeting": None}
    flat = " ".join(text.split())
    return {
        "cpi": _projection(flat, "cpi"),
        "gdp": _projection(flat, "gdp"),
        "stated_stance": _stated_stance(flat),
        "next_meeting": _next_meeting(flat),
    }
