# Institutional Flows & Ownership: all equity sectors and AI Catalysts

The India page focuses on sector flows and a searchable, sortable company explorer,
with a searchable selector for all 22 named NSDL equity sectors and the separate AI Catalysts theme.
Sectors are ranked by six-month net buying, latest-fortnight buying or buying relative
to opening FPI holdings; AI Catalysts is listed separately as a theme. The introduction
uses two labelled sentences, and the cumulative buying chart is removed. The selector ranks sectors by six-month net buying, latest-fortnight buying or relative buying.
Sovereign debt and the unclassified Others residual are excluded. Ownership selectors
cover DII, FPI, mutual funds and insurers, with largest increases/decreases ranked by
percentage-point ownership change. Company history is not displayed in this view.
The app reads the committed audited snapshot; it never fetches financial data live.
The breadth/concentration tab and FPI/DII scatter are retired from the dashboard.

## Reproduce

```sh
python -m data.fetchers.emerging_opportunity --as-of 2026-09-30 --sector all
python -m unittest discover -s tests -p 'test_emerging_opportunity.py'
streamlit run app.py
```

The collector defaults to the latest completed quarter. `--refresh` retrieves sources
again rather than reusing archived reports, including newly available quarterly filings.
The standalone weekly workflow updates the store independently of PNG generation.
Use `--sector Services` or `--sector Textiles` to collect only that sector; the default
remains Consumer Services for compatibility. All stores are independently audited. AI Catalysts uses the official Nifty theme constituent list;
it spans existing sectors and has no separate NSDL sector cash-flow series. Its explorer
shows quarterly ownership only. Theme membership identifies AI enablers, not AI revenue
exposure, and current membership is not reconstructed historically.

## Scope and evidence

The initial snapshot contains all twelve April–September 2026 fortnights and an opening
March-end AUC. It tracks **43 verified companies** appearing in accessible official
NIFTY Total Market/Microcap company lists, deduplicated by NSE symbol. This is **not the
complete NSE/BSE Consumer Services universe**. BSE's company-list request returned 403,
and the full official per-security classification endpoint was inaccessible. BSE-only
listings and NSE companies outside the verified lists are excluded. Full-sector company
breadth remains unresolved until a complete, documented classification master is available.
The UI reports this limitation before displaying results.

The same source-list scope tracks **24 Services companies** and **12 Textiles companies**.
All three sectors have complete April–September 2026 flow windows. This does not expand
the company universe beyond the accessible official index lists.

Five quarter-end ownership snapshots allow four sequential comparisons. September
2026 had 11/43 filings available at collection, so the default comparison is June 2026,
with complete filing coverage. The newer sector inflows should not be attributed to
the older company ownership observations. Current membership is not historical membership.

FPI shares are category aggregates (I + II), never the sum of named-investor details.
Domestic ownership is the filing's public-shareholding `InstitutionsDomesticMember`
aggregate, never the sum of that aggregate and its components. MF/UTI and insurance
are shown separately. The domestic aggregate can include banks, pensions, AIFs and
other domestic institutions; it is a proxy for domestic institutional ownership,
not the exchange's daily DII trading-participant flow measure. Government, promoter,
ordinary domestic corporate and retail holdings are excluded. An absent component
is unavailable rather than inferred as zero. MF includes active and passive funds.
Total capital is reconciled against the mutually exclusive promoter/public/non-public
categories and available reported category percentages. Source identity and quarter
are checked, including BSE numeric entity identifiers with a declared NSE symbol.

Any change in total shares excludes a company from comparable breadth, addition value
and accumulation streak calculations. Reported ownership is still visible with a review
flag. This conservative treatment excludes ESOP issuance as well as splits, bonuses,
buybacks and larger corporate actions; it avoids implying that such events are purchases,
but reduces the comparable sample. A reviewed corporate-action adjustment ledger is a
future extension; no automatic pro-rata adjustment or guessed factor is applied.

Positive changes exceeding 0.01 percentage point count as increases. Concentration
values positive share-count changes at one common September-end closing price; all
positive priced additions are the denominator, including small changes labelled Flat.
These are ownership valuation estimates, not cash flows or the actual cost of purchases.
Business buckets are editorial navigation aids, not exchange sub-industry classifications.

## Files

`data/stores/india/emerging_opportunity/consumer_services/` holds normalized flow,
universe and ownership CSVs, `snapshot.json`, and the original source archive. XBRL is
losslessly gzip-compressed to keep the archive small. Source checksums and a normalized
snapshot digest are validated before display; failed collection stages appear in the
snapshot and UI. Missing filings never become zero ownership.
The `services/` and `textiles/` siblings use the identical format, with their own
source receipts and normalized snapshots. Sector labels are checked explicitly on load.

The extended sectors use Industry from the official constituent CSV for business filtering.
Media and Oil/Gas labels are reconciled by punctuation only. Non-equity dummy ISINs are excluded.
Shared source archives are reused byte-for-byte across datasets, including overlapping
AI companies. Symbols are URL-encoded when requesting official quarterly filings.

Ownership uses the official SCRR A+B+C2 denominator. Custodian/DR C1 shares
are excluded from that denominator; reported category percentages must reconcile.
The legacy `total_shares` field stores this ownership denominator and is used to
flag changes for capital review. It is not a separately verified issued-capital series.

As collected on 14 October 2026, all 22 sectors have twelve April–September
fortnights. The ordinary-equity universe contains 748 unique stocks, with 3,090
verified quarterly ownership observations; REIT units and dummy index placeholders
are excluded, while EQ and BE equity series are included. The official AI Catalysts
basket contains all 48 constituents, each with a June 2026 filing. Missing foreign
institution categories do not discard valid domestic observations and remain null.

The persistence chart is capped at 480px and centered, with categorical teal buying,
 ochre selling and neutral no-flow colors. The sector comparison and company ownership
history expanders are removed; sector ranking controls and stock rankings remain.

Chart currency controls sit beside Flow frequency and offer INR crore or US dollar
million, using the corresponding published NSDL columns (not an inferred FX rate).
The chart frame has a 1.5px charcoal border. The section introduction describes its
purpose and coverage below the main heading; per-sector coverage boilerplate is removed.

This view is an Equity Markets subsection, following the sector valuation and
rotation charts. It has no separate page navigation button. Previously shared
`india-emerging-opportunity` fragments still resolve to the renamed subsection.

## Independent weekly cutoffs

The Saturday 08:30 UTC (14:00 IST) workflow runs regression checks, then
`--refresh --latest-flows --sector all`, followed by `--validate-only --sector all`.
FPI uses the latest completed 15th/month-end target and publishes the newest
contiguous twelve-fortnight window actually available; ownership uses the latest
completed quarter and refreshes additional filings weekly. Mid-month reports contain
the prior second half plus the current first half, checked against explicit AUC dates.
Missing releases and source outages retain validated history, never zero-fill flows.
Available observations refresh old values, while already collected holdings survive
missing listings or retrieval failures; all retained records must reconcile to archives.
Cached sources and fresh responses are shared within the all-sector run. Unavailable
URLs are attempted once per run, avoiding repeated long timeouts across 22 sectors.
FPI/ownership cutoffs appear separately in the UI and validation log. Inconsistent
sector cutoffs or invalid archives block GitHub publication. Missing quarterly
filings remain unavailable and are retried in the next weekly run.
