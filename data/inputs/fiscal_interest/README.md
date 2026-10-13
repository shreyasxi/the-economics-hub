# Interest / revenue receipts

The single chart has annual and cumulative current-fiscal-year panels.

`annual.csv` contains FY2015-16 through FY2024-25 Budget-reported actuals and
FY2025-26 CGA provisional accounts. Each actual uses the first (Actuals) column
in the Budget two years after that fiscal year's start; FY2024-25 therefore uses
Budget 2026-27. The July 2024 Budget has an extra provisional-actuals column:
FY2022-23 still uses the first column, not the provisional FY2023-24 column.
Sources and report text are archived in `sources/`, with URLs in the manifest
and each annual row. Provisional figures must not silently replace audited
Budget actuals.

Monthly data and the current BE row use `data/inputs/cag/cag_manual_accounts.csv`:
`interest_payments`, `net_tax_revenue`, `non_tax_revenue`, and `revenue_source`.
All monthly amounts are April-to-month cumulative Rs crore; BE is full year.
Revenue receipts equal net central taxes plus non-tax revenue and exclude
borrowing, loan recoveries and disinvestment. Annual and monthly ratios are
interest payments / revenue receipts * 100; do not average monthly percentages.

The monthly series requires every month from April through the latest CGA row.
Missing figures omit the chart with a warning, rather than falling back to an
older period. Tax receipts can fall following refunds or accounting revisions;
they are not forced to be monotonic. Receipt timing can cause large swings in
the cumulative ratio. The annual Budget reference is not a monthly forecast.

On the next Budget release, replace the preceding provisional annual row with
Budget actuals when available; add the newly completed year as provisional
once March CGA accounts are published, and enter the new fiscal year's BE in
the existing fiscal CSV. Preserve source URLs and archives. Monthly maintenance
is manual; this chart makes no new network calls during generation.
