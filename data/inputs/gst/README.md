# GST monthly amounts

`gst_monthly.csv` contains 24 months, November 2024 through October 2026,
supporting 12 monthly year-on-year readings, November 2025 through October 2026.
Amounts are exact published integer rupees crore, rather than the older rounded
lakh-crore manual series. These figures cover the GST system, not net tax receipts
of the Union government.

Each observation is taken from the first-page monthly column of an official GSTN
report. The current and corresponding prior-year months are retained together.
`source_report_month` identifies that vintage; `source_url` and the archived PDFs,
extracted text and manifest in `sources/` provide provenance.

## Comparable basis

All amounts **exclude compensation cess**. Reports from November 2025 onward
report cess separately (where applicable), and restate the comparison month on
the same basis. The October 2026 report restates October 2025 to gross 188125,
net 161900 and refunds 26225; the CSV points to that newer vintage.

Growth is unadjusted: May 2025 contains an approximately Rs 10000 crore one-off
spectrum payment, flagged by GSTN's May 2026 report. Do not silently replace it
with the approximate adjusted growth reported in the note.

Official amounts are provisional. Gross minus refunds reconciles to net within
Rs 2 crore because the published figures are independently rounded. Compare
months by calendar date, not row position.

## Updating

Archive each new official report and add its current-month values on the same
basis. If its prior-year comparison revises an existing observation, retain that
provenance and review the change before replacing it. Add the source to the
manifest. Run `python generate_india.py`; the GST chart automatically uses the
latest 12 months with a complete 24-month source window. No missing values are
interpolated or borrowed from the rounded gross-only series.

No missing input is outstanding for the initial 12-month chart.
