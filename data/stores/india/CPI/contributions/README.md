# CPI 2024 contributions

Official All India Combined / Current-series CPI. Separate from india_macro.db.

Run from the repository root:

```
PYTHONPATH=. .venv/bin/python -m data.fetchers.mospi_cpi --update
PYTHONPATH=. .venv/bin/python -m data.fetchers.mospi_cpi --backfill
PYTHONPATH=. .venv/bin/python -m data.fetchers.mospi_cpi --verify
PYTHONPATH=. .venv/bin/python -m data.fetchers.mospi_cpi --file data/inputs/mospi/cpi_1814.xlsx
```

`--update` discovers the latest month using official metadata and a General-index
probe, then refreshes that month and its predecessor, plus any missing intervening
months. The first update backfills January 2025 onward. `--backfill` explicitly
refreshes all history and detects older revisions. `--file` is an explicit official
workbook import with the same validation; never a silent fallback.

`raw/blobs/<sha256>.bin` preserves exact response bytes, content addressed and
written exclusively. `raw/retrievals/<id>.json` preserves UTC retrieval times,
URL/query, observation months, checksums, page count and scope. Failed retrievals
are retained as well. No token is required or stored.
Each response also has an immediately saved immutable request record, so an
interruption before the final manifest cannot lose its URL/query provenance.

Each immutable `runs/<id>/` contains normalized observations with source retrieval
IDs, full-precision weights/mapping, derived contributions, revision differences
and a checksum manifest. `current.json` atomically selects the latest validated
run. `last_attempt.json` is the release gate: a failed or unfinished refresh
prohibits rendering the previous successful vintage as a current chart.

Offline verification recomputes every derived observation, checks all referenced
source bytes and manifests, and matches every normalized observation to an exact
immutable response. The chart renderer performs this verification before drawing.
The workflow's existing source/chart commit step retains this directory across
weekly runs; no new workflow or schedule is introduced.

MoSPI provides no provisional/final status or vintage timestamp. Newest/prior-month
refreshes cannot detect revisions to older history; use explicit backfill for those.
Only published indices are used, with no interpolation, rescaling or residual bucket.
Weights and the six-bucket assignment are defined in `data/processors/cpi_contributions.py`.
