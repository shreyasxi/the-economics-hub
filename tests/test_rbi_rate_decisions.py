"""
Rate decision extraction regression test.

The automated RBI Sentinel workflow records each new repo rate decision by
reading the Resolution text, replacing the hand-edited list in
seed_rbi_rates.py. This test pins the extractor to every decision since the
MPC began: rate, action and size must match the recorded history exactly, both
when each meeting is completed from the true previous rate and when it is
chained on the extractor's own previous output (as the pipeline does).

Run:  python -m pytest tests/ -q      (or: python tests/test_rbi_rate_decisions.py)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rbi_sentinel.cleaners.policy_facts import complete_rate_decision, extract_policy_facts
from rbi_sentinel.config import DB_PATH

RATE_BEFORE_FIRST_MPC = 6.50   # the October 2016 decision cut from 6.50 to 6.25


def _history():
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """SELECT m.policy_cycle, m.repo_rate_pct, m.rate_action, m.rate_change_bps, d.raw_text
           FROM mpc_meetings m
           JOIN rbi_documents d ON d.meeting_id = m.meeting_id
            AND d.doc_type = 'resolution' AND d.source_kind = 'press_release' AND d.word_count > 0
           WHERE m.meeting_date = m.policy_cycle
           ORDER BY m.policy_cycle"""
    ).fetchall()
    con.close()
    return rows


def _matches(found, rate, action, bps):
    expected_bps = 0 if action == "hold" else bps
    return (found is not None and abs(found["repo_rate_pct"] - rate) < 1e-9
            and found["rate_action"] == action and found["rate_change_bps"] == expected_bps)


def test_every_decision_from_true_previous_rate():
    prev, misses = RATE_BEFORE_FIRST_MPC, []
    rows = _history()
    for cycle, rate, action, bps, text in rows:
        found = complete_rate_decision(extract_policy_facts(text)["rate_decision"], prev)
        if not _matches(found, rate, action, bps):
            misses.append((cycle, (rate, action, bps), found))
        prev = rate
    assert len(rows) >= 61
    assert not misses, misses


def test_every_decision_chained_on_own_output():
    prev, misses = RATE_BEFORE_FIRST_MPC, []
    for cycle, rate, action, bps, text in _history():
        found = complete_rate_decision(extract_policy_facts(text)["rate_decision"], prev)
        if not _matches(found, rate, action, bps):
            misses.append(cycle)
        prev = found["repo_rate_pct"] if found else prev
    assert not misses, misses


def test_reverse_repo_sentence_is_not_the_decision():
    text = ("the MPC decided to: reduce the policy repo rate under the liquidity adjustment facility (LAF) "
            "by 40 bps to 4.0 per cent from 4.40 per cent with immediate effect; accordingly, the reverse "
            "repo rate under the LAF stands reduced to 3.35 per cent from 3.75 per cent.")
    d = extract_policy_facts(text)["rate_decision"]
    assert d == {"repo_rate_pct": 4.0, "rate_action": "cut", "rate_change_bps": -40}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
