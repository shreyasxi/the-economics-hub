"""
Backfill policy_cycle on mpc_meetings, and classify documents by source.

Why this exists
---------------
pipeline.py set `meeting_date = publication_date` for every document. Because
RBI publishes one policy decision across several dates, a single MPC meeting
was split into two or three separate "meetings":

    2025-10-01   resolution + governor statement   (the decision)
    2025-10-15   minutes                           (+14 days, always)
    2025-10-20   resolution + governor statement   (Monthly Bulletin reprint)

The third group is the same text again: the Bulletin republishes the
resolution and the governor's statement weeks later. 94 of 272 documents
(35%) are those reprints, and 56 of 195 "meetings" consist of nothing else.

The effect on the published charts was that composites advertised as
50% minutes / 35% resolution / 15% governor were, for 119 of 195 meetings,
a single document renormalised to 100%.

The rule
--------
A policy cycle is anchored on a press-release `resolution` that actually
extracted text. Documents are attached to the nearest anchor at or before
their publication date, within 30 days — the next decision is ~57 days out,
so the window cannot bleed forward.

Anchors with no extracted text are RBI's advance schedule notices, published
3-5 days before the decision; they carry no analysis and are left unassigned.

Result: 59 cycles from 2016-10-04, 34 of them with all three document types.

Idempotent — safe to re-run.

    python -m rbi_sentinel.db.migrate_policy_cycle --dry-run
    python -m rbi_sentinel.db.migrate_policy_cycle
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from datetime import date

from rbi_sentinel.config import DB_PATH

# The next decision is ~57 days after the previous one, so a 30-day window
# captures minutes (+14d) and Bulletin reprints (+12-22d) without reaching
# into the following cycle.
CYCLE_WINDOW_DAYS = 30

SOURCE_PRESS_RELEASE = "press_release"
SOURCE_BULLETIN = "bulletin_reprint"
SOURCE_OTHER = "other"


def classify_source(source_url: str | None) -> str:
    """Press release is authoritative; the Bulletin reprints it weeks later."""
    if not source_url:
        return SOURCE_OTHER
    if "BS_PressReleaseDisplay" in source_url:
        return SOURCE_PRESS_RELEASE
    if "BS_ViewBulletin" in source_url:
        return SOURCE_BULLETIN
    return SOURCE_OTHER


def _ensure_source_kind_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(rbi_documents)")}
    if "source_kind" not in cols:
        conn.execute("ALTER TABLE rbi_documents ADD COLUMN source_kind TEXT")
        print("  added rbi_documents.source_kind")


def _iso(value: str) -> date:
    return date.fromisoformat(value)


def find_cycle_anchors(conn: sqlite3.Connection) -> list[str]:
    """Decision dates: press-release resolutions that extracted text."""
    rows = conn.execute(
        """
        SELECT DISTINCT publication_date
        FROM rbi_documents
        WHERE doc_type = 'resolution'
          AND source_kind = ?
          AND word_count IS NOT NULL
          AND word_count > 0
        ORDER BY publication_date
        """,
        (SOURCE_PRESS_RELEASE,),
    ).fetchall()
    return [r[0] for r in rows]


def assign_cycle(pub_date: str, anchors: list[str]) -> str | None:
    """Nearest anchor at or before pub_date, within the window."""
    best, best_offset = None, None
    target = _iso(pub_date)
    for anchor in anchors:
        offset = (target - _iso(anchor)).days
        if 0 <= offset <= CYCLE_WINDOW_DAYS:
            if best_offset is None or offset < best_offset:
                best, best_offset = anchor, offset
        elif offset < 0:
            break
    return best


def migrate(dry_run: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print(f"  database: {DB_PATH}")
    if not dry_run:
        _ensure_source_kind_column(conn)
    else:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(rbi_documents)")}
        if "source_kind" not in cols:
            print("  [dry-run] would add rbi_documents.source_kind")
            conn.execute("ALTER TABLE rbi_documents ADD COLUMN source_kind TEXT")

    # ── classify every document by source ──
    kinds = Counter()
    for row in conn.execute("SELECT doc_id, source_url FROM rbi_documents").fetchall():
        kind = classify_source(row["source_url"])
        kinds[kind] += 1
        conn.execute(
            "UPDATE rbi_documents SET source_kind = ? WHERE doc_id = ?",
            (kind, row["doc_id"]),
        )
    print(f"  classified {sum(kinds.values())} documents: " +
          ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))

    anchors = find_cycle_anchors(conn)
    print(f"  policy cycles: {len(anchors)}  ({anchors[0]} -> {anchors[-1]})")

    # ── assign each meeting to a cycle, via its documents ──
    meetings = conn.execute(
        """
        SELECT m.meeting_id, m.meeting_date, MIN(d.publication_date) AS first_pub
        FROM mpc_meetings m
        LEFT JOIN rbi_documents d ON d.meeting_id = m.meeting_id
        GROUP BY m.meeting_id
        ORDER BY m.meeting_date
        """
    ).fetchall()

    assigned = orphaned = 0
    for m in meetings:
        basis = m["first_pub"] or m["meeting_date"]
        cycle = assign_cycle(basis, anchors)
        if cycle:
            conn.execute(
                "UPDATE mpc_meetings SET policy_cycle = ? WHERE meeting_id = ?",
                (cycle, m["meeting_id"]),
            )
            assigned += 1
        else:
            orphaned += 1
    print(f"  meetings assigned to a cycle: {assigned}   left unassigned: {orphaned}")

    # ── report coverage, counting only usable press-release documents ──
    coverage = Counter()
    for anchor in anchors:
        types = {
            r[0] for r in conn.execute(
                """
                SELECT DISTINCT d.doc_type
                FROM rbi_documents d
                JOIN mpc_meetings m ON m.meeting_id = d.meeting_id
                WHERE m.policy_cycle = ?
                  AND d.source_kind = ?
                  AND d.word_count IS NOT NULL AND d.word_count > 0
                """,
                (anchor, SOURCE_PRESS_RELEASE),
            )
        }
        coverage[len(types)] += 1
    print("  usable document types per cycle:")
    for n in sorted(coverage):
        print(f"    {n} type(s): {coverage[n]:>3} cycles")

    if dry_run:
        conn.rollback()
        print("\n  [dry-run] rolled back — nothing written.")
    else:
        conn.commit()
        print("\n  Committed. Next: recompute composites.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change, write nothing")
    migrate(**vars(parser.parse_args()))
