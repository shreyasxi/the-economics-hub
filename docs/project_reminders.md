# Project Reminders

Read this first when coming back after a break. How everything is built:
`docs/project_context.md`.

---

## Coming back after months? Check these 4 things

1. **GitHub → Actions tab.** Any red runs? Any workflow marked *disabled*? (GitHub switches off
   schedules after 60 days without repo activity — click *Enable workflow*.)
2. **GitHub → Issues.** An open "10-year G-sec close needed" issue means an RBI meeting is waiting for you.
3. **[Monetaria](https://monetaria.streamlit.app/).** Do the pages show recent dates? If not: Streamlit dashboard → Reboot app.
4. **Anthropic console.** Is there credit left? RBI scoring fails without it.

---

## What runs by itself

| What | When | You do |
|---|---|---|
| Weekly Markets | Saturdays (keeps the last 4 weeks) | nothing |
| World | Saturdays 15:30 IST (keeps the last 4 months) | 7 numbers a month (below); calendars and US CPI weights once a year |
| India | Saturdays 13:30 IST (keeps the last 4 months) | monthly data entry (below) |
| RBI Sentinel | weekdays 18:15 IST; extra checks on MPC decision day | supply yield closes only if requested (below) |
| World policy rates | weekdays 12:00 IST and 02:30 IST the following day | nothing |
| World bond yields retry | Mondays 17:47 IST | nothing |
| India monetary charts | daily 20:40 IST, including weekends; local workflow, deployment pending | verify deployment before relying on it |
| Keep-alive | 3× a day | nothing |
| Analysis: Signal or noise board | Saturdays, with Weekly Markets | nothing |
| Analysis: newsletter shelf | read from Substack every 3 hours | nothing |
| Analysis: What I'm watching | **never by itself** | charts and threads (below) |

Schedules can start late. New local collectors/workflows are not live until published and verified in Actions.
Weekly cards reuse the entries below; the market matrix needs no manual entry. Missing evidence stays unavailable.

---

## RBI Sentinel

**Automatic:** finds new MPC documents on rbi.org.in, scores them with Claude Opus, records the
rate decision, redraws charts, pushes to Streamlit.

**After each MPC decision day, only if automatic yield collection fails:**
1. GitHub emails you an issue: *"10-year G-sec close needed"*.
2. Get the 10-year yield close for the decision day and the day before
   (Investing.com → India 10-Year Bond Yield → Historical Data).
3. On GitHub open `data/stores/rbi_sentinel/rbi_live_market.csv` → pencil icon → add one line → Commit changes:
   ```
   2026-10-07,<previous day close>,<decision day close>,Investing.com
   ```
4. The next evening run closes the issue.

**When Claude is used (costs money):**
- Decision day: 2 calls (Resolution + Governor's Statement)
- Minutes day, 14 days later: 1 call
- Every other run: 0
- About $0.15 per meeting. The code refuses short documents, non-MPC documents, and more than 4 at once.
- **Never run `python generate_rbi_sentinel.py --full` casually** — it rescores ten years of documents.

**Meeting dates:** read automatically from each Resolution ("The next meeting of the MPC is
scheduled for …"). The **Oct 5–7, 2026** meeting has passed; its Minutes are due **Oct 21**.
Check the latest stored Resolution for the next meeting; decision-day checks are 10:45, 11:45, 13:15 and 14:45 IST.

**Why the 10-year close matters:** past data shows Resolution tone lines up with the decision-day
10-year move, but the scores might carry hindsight. Meetings from Oct 2026 are the clean test.
After 4–6 meetings (mid-2027), `data/stores/rbi_sentinel/rbi_live_log.csv` answers whether it holds.

**Open to-dos:**
- [ ] Verify `ANTHROPIC_API_KEY` in GitHub → Settings → Secrets and variables → Actions (not checked here)
- [ ] Check new decision wording against existing `tests/test_rbi_rate_decisions.py`; extend fixtures if needed
- [ ] Redraw chart 07 (`rbi_sentinel/research/tone_vs_10y_chart.py`) once enough live meetings exist

**If a run is red:** Actions → RBI Sentinel → the run → job `rbi-sentinel` → step *Run pipeline*.
The last line says `FINISHED WITH PROBLEMS: …`:
- `discovery found no documents` → rbi.org.in blocked GitHub or changed its page
- `document(s) could not be scored` → API key or Anthropic credit
- `Refusing to score N documents` → more than 4 new documents at once; nothing was spent. Check them, then run locally
- `rate decision conflict` → the Resolution's wording didn't match the stored rate; fix the list in `rbi_sentinel/seed_rates.py`, then `python -m rbi_sentinel.seed_rates`

---

## World page — monthly data

Almost everything is automatic (FRED, OECD, BIS, Eurostat, Bundesbank, Bank of England, Japan MoF, Yahoo, and your
India database / DBIE workbook / RBI Sentinel database). These cells have no free API and show **"awaiting entry"**
until you type them in:

**Monthly checklist: five manufacturing PMIs (US, euro area, UK, Japan, China),
plus China's unemployment and 10-year yield — seven entries total.** India's PMI
is maintained through the India entry tool. These World PMIs do not refresh
automatically; enter the final manufacturing release for the reference month,
not the flash estimate or services/composite PMI. Check `status` after each month's releases.

```bash
PYTHONPATH=. .venv/bin/python -m data.processors.world_manual_entry status
PYTHONPATH=. .venv/bin/python -m data.processors.world_manual_entry set 2026-08 --country US --pmi 52.4
```

| When | What | Command (month = the month the figure is FOR) |
|---|---|---|
| 1st business day | Manufacturing PMI: US, euro area (HCOB), UK, Japan, China (all S&P Global) | `set YYYY-MM --country US --pmi 52.4` (then EA, UK, JP, CN) |
| ~3rd week | Japan CPI, all items, % YoY (Statistics Bureau via OECD) | Automatic in the normal World generator; no monthly manual entry |
| ~mid-month | China surveyed urban unemployment rate (NBS) | `set YYYY-MM --country CN --unemployment 5.3` |
| month-end | China 10-year government bond yield (ChinaBond) | `set YYYY-MM --country CN --ten-year 1.78` |

Add `--dry-run` to preview. India’s figures come from its database: PMI and headline unemployment need manual entry; headline CPI refreshes automatically. Its scoreboard 10-year yield needs the DBIE workbook.
**Japan CPI:** the World generator reads monthly national all-items CPI from OECD automatically. Historical manual entries are retained for compatibility and are not used as a fallback.
**CFNAI:** monthly CFNAI bars and the published CFNAI-MA3 line are fetched from FRED
by the normal World generator. No monthly data entry or workbook replacement is needed.
**NFCI:** the normal World generator automatically retrieves the Chicago Fed's official weekly contribution workbook and NFCI files. All contributions are grouped once, including HH and NFC within Leverage. No manual entries are needed; source or reconciliation failures require investigation rather than adjusting values. Standalone refresh: `python -m data.fetchers.nfci`.
Sources: <https://www.pmi.spglobal.com/Public/Release/PressReleases> · <https://www.stat.go.jp/english/data/cpi/> ·
<https://www.stats.gov.cn/english/PressRelease/> · <https://yield.chinabond.com.cn/>

**Publish:** commit `data/stores/world/world_manual.csv` and push, then GitHub → Actions → *World Generator* → Run workflow
(or wait for Saturday). Pushing alone doesn't redraw the page.

**Once a year (by December):** add next year's decision dates for the Fed, ECB, BoE and BoJ in
`config/world_settings.py` (`CENTRAL_BANKS`; URLs in `MEETING_SOURCES`). Listed through Dec 2027 now.
`tests/test_world.py` fails when a bank's list runs out.

**Once a year (mid-February): US CPI weights.** The US Inflation Metrics chart splits CPI inflation
by category using each category's BLS weight ("relative importance") for December. BLS publishes
them with January's CPI, around mid-February, and bls.gov blocks automated downloads, so they are
typed in by hand. Until the new year is added, the World run fails with
`add BLS relative importance for December <year> to CPI_RELATIVE_IMPORTANCE`.
1. Open <https://www.bls.gov/cpi/tables/relative-importance/2026.htm> (the year just ended), or ask
   Claude to fetch it.
2. Copy five numbers from the **CPI-U** column, U.S. city average: *Food*, *Energy*, *Commodities
   less food and energy commodities*, *Services less energy services*, *Shelter*.
3. Add a line to `CPI_RELATIVE_IMPORTANCE` in `config/macro_settings.py`, same layout as the years above.
4. `.venv/bin/python tests/test_world.py` must end "0 failed". It catches a typo: the first four must
   add up to 100. The run itself also fails with `categories miss the headline rate` on a wrong figure.
5. Commit, push, then Actions → *World Generator* → Run workflow.

**If the World run is red:** Actions → World Generator → step *Generate World charts and snapshot*. The log ends with
`FINISHED WITH PROBLEMS` and one line per source, e.g. `... is 130 days old (limit 110) — the source may have stopped
updating` (the series was discontinued or renamed: find the replacement) or `OECD CPI: HTTPError` (usually temporary:
re-run). Nothing is published until it's fixed, by design. The CAPE, equity risk premium and country risk spreadsheets are
downloaded automatically (Shiller, Damodaran) — nothing to do by hand; if a line says `no ie_data.xls link`, `no ctryprem
links`, `renamed?` or `the layout changed`, the site or file moved and `data/processors/valuations.py` needs a small update.

**Localhost versus the published app:** localhost prefers the current edition in `output/macro/`,
while Streamlit Cloud reads published `assets/macro/`. A failed local refresh can therefore show a
source warning (for example, a missing BoJ statement link) that is absent from the older successful
published snapshot. Check each snapshot's `generated_at` and `problems`; a clean older edition
does not verify that today's fetch works. Fix/retry the source rather than deleting the warning.

---

## India page — monthly data

Run from the project root. Prefix Python commands with `PYTHONPATH=. .venv/bin/python`.

**Start here:**
```bash
PYTHONPATH=. .venv/bin/python -m data.processors.india_manual_entry status
```
Shows the last 12 months and what's missing (`ok` vs `..`).

Full command: `python -m data.processors.india_manual_entry set 2026-09 --gst 2.04`.

| When | Released | Command |
|---|---|---|
| ~1st of following month | Gross/net GST (GSTN) | Add the prior month's amounts to `data/inputs/gst/gst_monthly.csv` (₹ crore; details below); `--gst 2.04` still updates the summary's gross level (₹ lakh crore) |
| month-end / 1st | FPI final monthly net investment (NSDL) | `set YYYY-MM --fpi -34574` (₹ crore, total of all segments) |
| during current month, optional | FPI month-to-date (NSDL) | `set YYYY-MM --fpi-mtd -9508 --fpi-mtd-asof YYYY-MM-DD` |
| 1st business day | Manufacturing PMI | `set YYYY-MM --mfg-pmi 53.1` |
| ~3rd business day | Services PMI | `set YYYY-MM --svc-pmi 54.6` |
| ~5th | DBIE workbook (credit/deposits, trade; M3 retained without a chart) | replace file, run fetcher (below) |
| when officially released | Headline/food CPI, General/industry IIP, monthly urban youth PLFS | automated collectors; no routine manual entry |
| monthly, if sourced consistently | Core CPI; legacy unemployment field if still maintained | `set YYYY-MM --core-cpi 3.8`; `--unemployment` is not the new youth series |
| bi-monthly RBI release | Inflation expectations + Urban/Rural confidence | replace official workbooks (below) |
| when published | CAG monthly accounts | replace workbook, or type figures (below) |
| ~22nd–25th | RBI Bulletin, State of the Economy | nothing — the Saturday run reads it (below) |

Full command: `PYTHONPATH=. .venv/bin/python -m data.processors.india_manual_entry set 2026-09 --gst 2.04`.
Values are range-checked; add `--dry-run` to preview. Composite PMI is calculated — never enter it.
Keep each command on one line (a stray trailing `\` leaves the shell waiting).

**GST:** <https://www.gst.gov.in/newsandupdates> → "Gross and Net GST revenue collections" → report PDF.
In `data/inputs/gst/gst_monthly.csv`, add `month` (`YYYY-MM`), `gross_gst_crore`, `net_gst_crore`, `refunds_crore`
from the **Monthly** totals, excluding compensation cess; copy `basis` from the previous row and fill
`source_report_month`, `source_url`, `notes`. Check the year-earlier figures for revisions. Save the PDF in
`data/inputs/gst/sources/`, then run `generate_india.py`; growth and the latest 12-month window update themselves.

**DBIE workbook (~5th):** download from <https://data.rbi.org.in/DBIE/#/dbie/ind1>, replace
`data/50 Macroeconomic Indicators.xlsx` (same filename), then:
```bash
PYTHONPATH=. .venv/bin/python data/fetchers/india_fetcher.py --dry-run
PYTHONPATH=. .venv/bin/python data/fetchers/india_fetcher.py --append
```
`REJECTED` in the log = RBI changed a column or unit. Check the workbook before trusting it.
Published reserves use canonical RBI WSS, not this workbook. Trade uses DBIE first; verified releases in
`data/stores/india/india_trade_releases.json` supplement missing months. Never type over official fetched observations.

**FPI:** the published chart uses NSDL only and is manual by design — do not expect the
fetcher to update it. Enter the final completed-month Total with `--fpi`. During the
current month you may optionally enter an MTD figure with `--fpi-mtd` and
`--fpi-mtd-asof YYYY-MM-DD`; it appears as a grey `*` bar and is excluded from the
completed-month cumulative total. Once the final `--fpi` value exists for that month,
the MTD bar disappears automatically. RBI DBIE's portfolio-investment series remains
in the database for reference only and is never substituted into the published chart.

**State of the Economy (nothing to do normally):** the Saturday India run reads RBI's monthly article itself —
the briefing at the top of the India page and the rate-transmission chart both come from it. Published in the
Bulletin's fourth week at <https://rbi.org.in/scripts/BS_ViewBulletin.aspx> (Article → State of the Economy).
Both steps are optional in the workflow, so a bad week costs the briefing, never the charts.
Worth knowing:
- The briefing is RBI's own words, quoted. Question summaries elsewhere on the page are generated from stored data.
- If the page shows no briefing, RBI's page could not be read that Saturday; the next run picks it up.
- To catch up by hand, or after a run that reported problems:
  ```bash
  PYTHONPATH=. .venv/bin/python generate_soe.py --history      # transmission table, any missing editions
  PYTHONPATH=. .venv/bin/python generate_soe.py                # briefing into the newest edition folder
  ```
- A run that says the table's **columns have changed** means RBI reshaped Table IV.3. That is deliberate: the
  figures are never guessed at. Send the edition to Claude and the column map in `config/soe_settings.py` is updated.
- HTML is tried first. If the article is PDF-only, or HTML cannot be parsed, the
  PDF linked in the same Bulletin row is downloaded and parsed. A CAPTCHA response
  is rejected with an explicit error; it cannot update the briefing or rate history.
- If RBI blocks the PDF download, save the report in your browser, then run:
  `PYTHONPATH=. .venv/bin/python generate_soe.py --month YYYY-MM --pdf-file /path/to/report.pdf`
  The contents page still supplies the official source URL. The PDF's printed
  month and the date in its official filename must match the requested edition.
  Unrecognised PDF layouts stop the run for review rather than guessing figures.

**CAG workbook:** <https://cga.nic.in/MonthDashboardReport/Published/list.aspx> → replace
`data/inputs/cag/cag_monthly_accounts.xlsx` (same filename, values in ₹ crore — don't convert).
**Workbook not updated but figures on the CGA web page?** Fill `docs/templates/cag_fill.xlsx` each month
("Actuals up to" column, ₹ crore) and send it to Claude:
- *Accounts at a glance:* Revenue Expenditure (row 8), Interest Payments (9), Capital Expenditure (10), Fiscal Deficit (13)
- Interest/revenue chart: also fill `net_tax_revenue` (row 2), `non_tax_revenue` (row 3), and `revenue_source` in `data/inputs/cag/cag_manual_accounts.csv` (YTD ₹ crore, including the BE row). Annual actuals in `data/inputs/fiscal_interest/annual.csv` update once a year.
- *Sources of financing the deficit:* External, Domestic total, and every domestic row (a) to the last row below Cash Balance
- The sheet's check rows should read 0: external + domestic = fiscal deficit, and the domestic rows add up to their total
A new financial year also needs the BE column (same pages) and nominal GDP from the Budget.
The financing rows feed the Deficit Financing chart; a month without them simply isn't drawn.
The run stops with a message if a figure looks wrong.

**Publish:**
```bash
PYTHONPATH=. .venv/bin/python generate_india.py --mode dashboard   # open 2–3 charts in output/india/ and look
git add data/stores/india/india_macro.db "data/50 Macroeconomic Indicators.xlsx" data/inputs/cag/cag_monthly_accounts.xlsx
# Also stage changed canonical stores, raw archives and manifests used by your update (context §6).
git commit -m "data: India series through <month>"
git push
```
Pushing does **not** redraw the live charts. Either wait for Saturday or GitHub → Actions →
India Dashboard Generator → Run workflow.

**Official data and unavailable panels:** General IIP and headline/food CPI are automated; industry IIP
and monthly urban youth PLFS refresh in Saturday India. Their separate stores are validated before use.
A failed optional refresh omits its affected chart; check Actions/source status, not an old PNG.
Do not switch IIP back to DBIE. Emergency manual rendering requires `IIP_MANUAL_FALLBACK=true` or
`CPI_MANUAL_FALLBACK=true`; resolve CPI conflicts through the audited bridge (§0.1 of project context).

**CPI items, REER and external vulnerability:** now wired locally into Saturday India, pending publication
and a successful Actions run. No routine manual entry after deployment; failed refreshes omit only the affected
panels. WSS reserves already refresh on Saturdays. CPI items show price movers, not inflation contributions.

**Investment rate:** still an explicit snapshot refresh when new annual data are available:
`PYTHONPATH=. .venv/bin/python -m data.fetchers.gmd_investment`, then regenerate and publish India.

**RBI bi-monthly workbooks:** replace official Excel releases in
`data/inputs/rbi/rbi_bimonthly_manual/inflation_survey/` and `data/inputs/rbi/rbi_bimonthly_manual/consumer_survey/` (both Urban and Rural).
Use dedicated folders; avoid duplicate newest releases. Dates come from workbook contents, not filenames.
Run `generate_india.py`, inspect all six survey charts, and validate with:
```bash
.venv/bin/python -m unittest discover -s tests -p 'test_rbi*.py'
```
Missing/misaligned workbooks omit that survey family; never substitute an older chart.

| Source | URL |
|---|---|
| GST | <https://www.gst.gov.in/newsandupdates> — "Gross and Net GST revenue collections" |
| Manufacturing PMI | <https://www.spglobal.com/marketintelligence/en/mi/research-analysis/india-manufacturing-pmi.html> |
| Services PMI | <https://www.spglobal.com/marketintelligence/en/mi/research-analysis/india-services-pmi.html> |
| CPI | <https://mospi.gov.in/web/cpi> |
| IIP | Official MoSPI monthly release/annexure; collector discovers the current release |
| PLFS | <https://mospi.gov.in/web/plfs> |
| FPI (NSDL) | <https://www.fpi.nsdl.co.in/Reports/Yearwise.aspx?RptType=6> |
| CGA monthly accounts | <https://cga.nic.in> → Monthly Accounts |

---

## Analysis page — the part you write

Two of the three blocks on /analysis run themselves: the **Signal or noise** board (built every
Saturday with Weekly Markets) and **From the newsletter** (read from Substack). **What I'm watching**
is chart-only and yours alone: the threads and their charts are written by hand, in one file,
`config/analysis.py`, plus the chart images you save in `assets/analysis/`. Nothing else changes.

| On the page | In `config/analysis.py` |
|---|---|
| Page title and the line under it | `TITLE`, `DEK` |
| A thread's heading and the sentence under it | `"theme"`, `"why"` |
| A thread's charts and their captions | its `"charts"` list |
| Which essays the shelf shows, in order | `PINNED` |

Order in the file is order on the page: the first thread shows first, the first chart first.
Threads contain titles, context and explicitly added charts; they do not support articles or links.

**Replace a chart** (e.g. a newer EIA Brent chart):
1. Save it as a PNG in `assets/analysis/`. Name it `source_subject_date.png`, lower case, no spaces
   (`eia_brent_2026-10.png`). A Mac screenshot (Cmd+Shift+4) is fine — crop out browser bars,
   cookie banners and the site's own buttons. About 1200–1600 px wide.
2. In `config/analysis.py`, find the chart's entry (search for the old file name) and change:
   `"image"` → the new file name · `"title"` → what the chart shows · `"source"` → who made it,
   in words (no link or date: the caption shows the source as text) ·
   `"note"` → one line, in your words, on what to see in it.
3. Delete the old PNG if no thread uses it any more (git keeps the history).

**Use one of your own charts instead:** `{"dashboard": "crude_oil_curve", "note": "..."}`. The name
is the chart's file name without its number and `.png`
(`assets/weekly/…/23_crude_oil_curve.png` → `crude_oil_curve`); Weekly Markets, World and India
charts all work. It always shows the newest edition, so it never goes stale.

**Start a thread:** copy a whole thread, from `{` before `"theme"` to its matching `},`, paste it
into `WATCHING` where it should appear, and rewrite it. **Retire one:** delete its block. Keep its
context and charts current while you are following it.

**The "why" lines** under each thread are my drafts. Rewrite them in your own words: a sentence or
two on why it matters and what would change your mind.

**Pinned essays:** each entry in `PINNED` is the end of the post's address
(`economicshub.substack.com/p/`**`iran-war-is-more-than-just-oil`**). A new post leads the shelf
by itself with a *New* tag for 30 days (`NEW_FOR_DAYS`), then drops back.

**Check, look, publish** — every time:
```bash
.venv/bin/python tests/test_analysis.py        # must end "0 failed"
.venv/bin/streamlit run app.py                 # then open http://localhost:8501/analysis
git add assets/analysis config/analysis.py
git commit -m "analysis: <what changed>"
git push
```
The check says what is wrong and where: a chart file that isn't in `assets/analysis/`, a
misspelt field (`"tittle"`), unsupported article/link data in a thread, or a
missing comma or quote (with its line number). No workflow is needed: the live page picks the
change up a few minutes after the push. If it hasn't after ten minutes, Streamlit → Reboot app.

**No laptop?** On github.com: `assets/analysis` → *Add file* → *Upload files* → Commit; then
`config/analysis.py` → pencil icon → edit → Commit changes. Nothing checks it there, so open
/analysis afterwards: if it says *This page is being updated*, the small line under it names the
line of the file with the slip. The rest of the site keeps working meanwhile.

**Python slips that bite:** every entry ends with a comma, including after each `}` in a list ·
text sits inside `"double quotes"` — an apostrophe inside is fine (`"Iran's"`), a straight double
quote is not (use curly “ ” instead) · `True` has a capital T · a long line can be split as
`("first half " "second half")`, as the "why" lines are.

**Signal or noise, if it goes quiet:** the page says an edition "was published without" the
board when the Saturday step failed (Actions → Weekly Markets Generator → step *Rank the week's
unusual moves*); the charts publish either way. Series that stop trading are listed under the
board as *Left out this week*; the list of 52 is `config/signals_settings.py`.

---

## If something looks wrong

| Symptom | Likely cause |
|---|---|
| New chart or text missing on Streamlit only | Cloud kept old code in memory → Reboot app |
| Chart values off by 100× / 1000× | unit change at source |
| A series flatlines or goes blank | source stopped publishing or a column moved |
| Rupee sign shows as a box | `DejaVu Sans` missing from the font list |
| `status` shows `..` you thought you entered | the command never ran |
| A run fails with "FRED_API_KEY is not set" | the secret expired or was removed; there is no fallback by design |
| Tabs lose bold styling | Streamlit version changed — keep `streamlit==1.50.0` in requirements.txt |
| /analysis says "This page is being updated" | a slip in `config/analysis.py`; the line under it names where |
| A run fails at *Commit and push charts* | inspect the log; for an old-checkout push collision start a **new** Run workflow. Dashboard publication jobs share a branch-specific repository lock |
| Matrix, CPI items, heatmap or external chart missing | inspect its source/generator status and same-edition artifact; no fabricated or prior-edition substitute |

---

## Keys and secrets (where they live)

- **GitHub Actions secrets:** `FRED_API_KEY`, `ANTHROPIC_API_KEY`
- **Streamlit Cloud secrets:** `FRED_API_KEY` only
- **Local `.env`:** both keys · **local `.streamlit/secrets.toml`:** `PIPELINE_KEY` (never on Cloud)
