Official MoSPI / NSO workbooks downloaded 4 October 2026, kept unchanged for parser regression tests.

- `nas_2026_8.18.1.xlsx`: https://www.mospi.gov.in/uploads/publications_reports/NAS-2026-Statements/8.18.1.xlsx
- `quarterly_constant_2026-08-31.xlsx`: https://api.mospi.gov.in/api/esankhyiki/file/download/datacatalogue/NASdata/AEQE/AEQE_as%20on%2031.08.2026/Statement_Quarterly_Constant_31.08.2026.xlsx
- `catalogue_entry.json`: relevant fields from https://api.mospi.gov.in/api/esankhyiki/cms/golden-sheet/list?product=NAS&page=1&limit=100

Both workbooks are from the 31 August 2026 release vintage. The release confirms
that NAS 2026 revises the complete FY2022-23–FY2025-26 quarterly history:
https://www.mospi.gov.in/uploads/latestreleasesfiles/1788174301107-Press%20Note%20on%20GDP%20Estimates%20for%20Q1%202026-27.pdf

The catalogue's `20122-23 SERIES` is a publication typo; the release and historical
workbook explicitly confirm the 2022-23 base. No 2011-12-base observations are used.

Operations: run `python -m data.fetchers.mospi_gva` to refresh the database, or
`python -m data.fetchers.mospi_gva --dry-run` to validate without writing. The
existing India fetcher's `--append` invokes this step; chart rendering reads only
`india_gva_quarterly`. On an inconsistent historical revision, update the official
history source after inspecting the new release, then rerun; never suppress the
reconciliation check or fill missing quarters. Contributions are available from
FY2023-24 Q1 because earlier quarters lack year-earlier levels in the new series.
