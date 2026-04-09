"""
seed_rbi_rates.py

Seeds repo_rate_pct, rate_action, and rate_change_bps into all mpc_meetings rows.
Derived from RBI official rate history (Oct 2016 – Apr 2026).

For each meeting date, the effective rate is the most recent decision at or
before that date. Holds are inferred (any meeting not in the change list gets
the current prevailing rate with action='hold').
"""

import sqlite3
from datetime import date

DB_PATH = "data/rbi_sentinel.db"

# Rate change events: (date_string, new_rate, action, change_bps)
# Source: RBI official rate history
RATE_CHANGES = [
    # MPC inception
    ("2016-10-04", 6.25, "cut",  -25),   # Oct 2016: 6.50 → 6.25
    # Cut cycle 2017
    ("2017-08-02", 6.00, "cut",  -25),   # Aug 2017: 6.25 → 6.00
    # Hike cycle 2018
    ("2018-06-06", 6.25, "hike", +25),   # Jun 2018: 6.00 → 6.25
    ("2018-08-01", 6.50, "hike", +25),   # Aug 2018: 6.25 → 6.50
    # Cut cycle 2019
    ("2019-02-07", 6.25, "cut",  -25),   # Feb 2019: 6.50 → 6.25
    ("2019-04-04", 6.00, "cut",  -25),   # Apr 2019: 6.25 → 6.00
    ("2019-06-06", 5.75, "cut",  -25),   # Jun 2019: 6.00 → 5.75
    ("2019-08-07", 5.40, "cut",  -35),   # Aug 2019: 5.75 → 5.40
    ("2019-10-04", 5.15, "cut",  -25),   # Oct 2019: 5.40 → 5.15
    # COVID emergency cuts 2020
    ("2020-03-27", 4.40, "cut",  -75),   # Mar 2020 emergency: 5.15 → 4.40
    ("2020-05-22", 4.00, "cut",  -40),   # May 2020 emergency: 4.40 → 4.00
    # Hike cycle 2022 (tightening)
    ("2022-05-04", 4.40, "hike", +40),   # May 2022 off-cycle: 4.00 → 4.40
    ("2022-06-08", 4.90, "hike", +50),   # Jun 2022: 4.40 → 4.90
    ("2022-08-05", 5.40, "hike", +50),   # Aug 2022: 4.90 → 5.40
    ("2022-09-30", 5.90, "hike", +50),   # Sep 2022: 5.40 → 5.90
    ("2022-12-07", 6.25, "hike", +35),   # Dec 2022: 5.90 → 6.25
    ("2023-02-08", 6.50, "hike", +25),   # Feb 2023: 6.25 → 6.50
    # Cut cycle 2025
    ("2025-02-07", 6.25, "cut",  -25),   # Feb 2025: 6.50 → 6.25
    ("2025-04-09", 6.00, "cut",  -25),   # Apr 2025: 6.25 → 6.00
    ("2025-06-06", 5.50, "cut",  -50),   # Jun 2025: 6.00 → 5.50
    ("2025-12-05", 5.25, "cut",  -25),   # Dec 2025: 5.50 → 5.25
]

# Convert to sorted list of (date_obj, rate, action, bps)
CHANGES_SORTED = sorted(
    [(date.fromisoformat(d), r, a, b) for d, r, a, b in RATE_CHANGES],
    key=lambda x: x[0],
)


def get_effective_rate(meeting_date_str: str):
    """
    Return (rate, action, change_bps) for a given meeting date.
    Walks backwards through CHANGES_SORTED to find the prevailing rate.
    Meetings not on a change date are assigned action='hold', change_bps=0.
    """
    d = date.fromisoformat(meeting_date_str)

    effective_rate = None
    effective_action = "hold"
    effective_bps = 0

    for change_date, rate, action, bps in CHANGES_SORTED:
        if change_date <= d:
            effective_rate = rate
            # Check if this meeting IS the change date
            if change_date == d:
                effective_action = action
                effective_bps = bps
            else:
                effective_action = "hold"
                effective_bps = 0
        else:
            break

    return effective_rate, effective_action, effective_bps


def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    meetings = conn.execute(
        "SELECT meeting_id, meeting_date FROM mpc_meetings ORDER BY meeting_date"
    ).fetchall()

    updated = 0
    for m in meetings:
        rate, action, bps = get_effective_rate(m["meeting_date"])
        if rate is None:
            continue
        conn.execute(
            """
            UPDATE mpc_meetings
            SET repo_rate_pct = ?, rate_action = ?, rate_change_bps = ?,
                updated_at = datetime('now')
            WHERE meeting_id = ?
            """,
            (rate, action, bps if bps != 0 else None, m["meeting_id"]),
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"Seeded {updated} meeting rows with repo rate data.")


if __name__ == "__main__":
    seed()
