# Official CPI regression observations

`official_2025_2026.json` contains the 260 exact aggregate API observations
from the source audit, Jan 2025–Aug 2026, Base 2024 / Current / All India /
Combined. They matched `data/CPI/cpi_1814.xlsx` in all 15 source fields.
Only JSON-null group/class/sub_class/item observations qualify.

Source: https://api.mospi.gov.in/api/cpi/getCPIData
These are frozen regression observations, not a production fallback.
Tests construct synthetic lower-level responses only to exercise pagination
and rejection behavior. Production data always comes from saved official responses.

`official_2012_history.json` is the exact old-base response retrieved on
5 October 2026 from the same endpoint with:
`base_year=2012&series=Current&state_code=99&sector_code=3&year=2024,2025&level=Group&group_code=0,1,7&subgroup_code=0.99,1.99,7.99&limit=100&page=1&Format=JSON`.
It contains 72 records. General and Food and Beverages feed historical chart
rates; Consumer Food Price is audit evidence of the legacy CFPI mismatch and
must never be mapped to the requested Food and beverages measure.
