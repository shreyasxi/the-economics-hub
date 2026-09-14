"""
Gate for the RBI Sentinel workflow: decide whether this run does the full work.

Runs in seconds with the standard library only, before any dependency install.

  manual runs                         always run
  evening schedule (18:15 IST)        always run — Minutes, off-cycle meetings, market closes
  decision-day schedules (daytime)    run only on the announcement day — the last day of
                                      the scheduled meeting, read from the latest
                                      Resolution's "next meeting" sentence

Writes run=true|false (and a reason) to $GITHUB_OUTPUT.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rbi_sentinel.cleaners.policy_facts import extract_policy_facts  # noqa: E402  (stdlib-only module)

DAYTIME_CRONS = {"15 5 * * 1-5", "15 6 * * 1-5", "45 7 * * 1-5", "15 9 * * 1-5"}
IST = timezone(timedelta(hours=5, minutes=30))


def decide() -> tuple[bool, str]:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    schedule = os.environ.get("SCHEDULE", "")
    if event != "schedule":
        return True, f"event '{event}'"
    if schedule not in DAYTIME_CRONS:
        return True, f"evening schedule '{schedule}'"

    con = sqlite3.connect(ROOT / "data" / "rbi_sentinel.db")
    row = con.execute(
        """SELECT raw_text FROM rbi_documents
           WHERE doc_type = 'resolution' AND source_kind = 'press_release' AND word_count > 0
           ORDER BY publication_date DESC LIMIT 1"""
    ).fetchone()
    con.close()
    nxt = extract_policy_facts(row[0] if row else None)["next_meeting"]
    today = datetime.now(IST).date()
    if not nxt:
        return True, "next meeting date unreadable — running to be safe"
    if today == nxt["end"]:
        return True, f"MPC decision day ({nxt['end']})"
    return False, f"no MPC decision today (next decision {nxt['end']})"


if __name__ == "__main__":
    run, reason = decide()
    print(f"run={run}: {reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if run else 'false'}\nreason={reason}\n")
