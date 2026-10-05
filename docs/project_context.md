# The Economics Hub — Project Context

> The single reference for how this project is built, run and changed. It is written so that an assistant
> with **no access to the code** — a future Claude session, or any chatbot the owner uploads this file to —
> can help change a chart, correct a figure or publish a change. Sections 1–12 describe the project as it is;
> section 13 keeps the dated history of decisions. Core architecture and India pipeline refreshed against the working tree on 5 Oct 2026. Older dated history is background; current code and the update below take precedence.
>
> Companion file: `docs/project_reminders.md`, the owner's short monthly checklist (release dates, source
> URLs, the Analysis page how-to). Upload it as well when the task is monthly data entry.

---

## 0. Read this first (for an assistant helping the owner)

**For agents with repository access:** inspect the current source and Git status before editing; this file
provides orientation, while code/workflows establish current behavior. Preserve existing uncommitted work.
**For assistants without code access:** ask the owner for the function or block named in §4 before proposing
an edit. Do not write code against variable names you have not seen.

**The owner's setup.** A Mac (zsh) and VS Code, with the project at `~/Documents/economics_hub` and a virtual
environment in `.venv`. Commands in this file are run from that folder in VS Code's terminal, as
`.venv/bin/python …` (scripts that import the project's packages also need `PYTHONPATH=.` in front). Local
Python is **3.9**; GitHub Actions uses 3.11, so code must run on both — no `match` statements, no backslashes
or reused quote characters inside f-string `{}` expressions. API keys live in `.env` (loaded automatically by
`config/settings.py`). The owner also works with Claude Code inside VS Code, which *can* read the repository.

**Rules that are not negotiable** (full list §12):
1. Never invent, mock, estimate or fill in data. A missing source fails the run or leaves a chart out.
2. Never edit `.github/workflows/*.yml` unless the owner explicitly asks for that change.
3. Every chart is styled through `charts/style.py` (`EconStyle`) and saved with `EconStyle.save_chart`.
4. Try it locally first — run the generator, look at the picture, run the tests (§5.6) — then publish (§5.7).
5. Changes to layout, navigation or workflows go on a git branch; the owner approves every commit, merge,
   push and workflow run.

**How a change reaches the live site** (details §5.7): Streamlit Cloud serves the `main` branch of the GitHub
repo. Chart images only change when a workflow redraws them; captions, chart explanations and the words kept
in the `config/` files the app re-reads update on their own a few minutes after a push; a change to `app.py`
needs the app rebooted.

---

## 0.1 Current architecture and India contracts — 5 Oct 2026

Read this before the older detailed sections. This describes the local implementation; deployment is confirmed
only after commit/push and a successful GitHub Actions run. Source code and workflow files are authoritative.

- **Publication:** generators write `output/`; workflows copy validated charts/JSON to tracked `assets/`, prune
  to four editions and commit source stores. Streamlit reads the newest edition, with local output taking precedence
  on equal dates. `site/` is the separate GitHub Pages link-preview landing page, deployed by `pages.yml`.
- **Saturday India job:** 08:00 UTC / 13:30 IST. GVA/IIP contract tests → `india_fetcher.py --append` (including GVA)
  → official IIP → RBI transmission → NSE checks/risk appetite/rotation/valuations → CPI checks/collector → main
  inflation bridge → dashboard → RBI briefing → copy/prune/persist. Check `india.yml` for exact conditions:
  `skip_fetch` skips the initial India/IIP updates, but does not skip every independent source updater.
- **GVA:** dynamically discover newest official NAS history and quarterly constant-price releases, base 2022–23.
  Accept validated newer revisions and recalculate affected growth/contributions. Archive previous observations,
  source bytes and revision differences. Changed methodology text/base/schema/units or inconsistent levels fail
  before observation writes and require review. Do not pin a yearly workbook as the production discovery path.
- **SQLite:** database-manager operations commit/roll back and explicitly close connections. A connection
  context alone does not close SQLite; delayed WAL checkpoints can invalidate dry-run byte checks.
- **IIP:** General, base 2022–23, published `growth_rate` (% YoY), continuous history from Apr 2023. Official
  observations live in `india_iip_monthly`; legacy values remain separately archived and are never spliced.
  `--iip` writes a separate emergency table; rendering needs `IIP_MANUAL_FALLBACK=true`. Despite its name,
  `mospi_iip_audit.py` supplies the production validator and must remain available.
- **CPI:** official All India Combined. Main headline and Food and beverages rates use base 2012 through
  Dec 2025 and base 2024 from Jan 2026; food is not CFPI. Conflicting manual values block the bridge transaction
  unless explicitly accepted with an archived before/after record. Manual chart fallback needs
  `CPI_MANUAL_FALLBACK=true`. The separate six-bucket contribution chart uses verified base-2024 indices,
  weights, immutable responses and run manifests; its validity is independent of a main-CPI manual conflict.
- **NSE:** valuation P/E starts Apr 2021, P/B uses up to ten years, and every sector needs at least 60 valid
  observations. Risk appetite uses matched price-index closes, Smallcap 250 / NIFTY 50, rebased to 4 Oct 2016 = 100;
  retained raw seed exports make the original ignored export folders unnecessary for routine updates. Valuations
  use approved per-sector metrics and verified historical CSVs; generated coverage/extracted/metric-detail files
  are checksum dependencies of the production updater. Rotation uses the official snapshot timestamp as its
  observation date; `previousDay` is a previous-close reference. Require all sectors and NIFTY 50, consistent
  references, finite prices and freshness; returns exclude dividends. Retain its provenance JSON with the PNG.
- **Failure behavior:** optional source failures leave independent charts usable, but failed/pending status or
  per-source workflow gates omit affected charts. Never silently publish stale optional images from an earlier
  run; preserve source status, current pointers and raw archives with the code/database changes.
- **Analysis:** `WATCHING` threads are chart-only (dashboard references or saved images), with a consistent
  image frame. Reading-link cards were removed; the Substack essay shelf remains separate.
- **Cleanup:** promoter holdings and money-supply charts are retired. Audit reports and the standalone Saturday
  simulation were removed; current operating contracts live here. Owner reminders and older research reports
  may still contain historical instructions. Keep tests/fixtures and checksum-linked archives; do not blanket
  ignore `data/`, `assets/`, or CPI `runs/`. Secrets, caches, temp/lock files and `output/` stay ignored.

---

## 1. What the project is

**The Economics Hub**, by Shreyas Urgunde: an institutional-style macro and markets dashboard, plus a Substack
newsletter. Written for an international audience (UK employers, global readers) as well as Indian ones, so
the World page stays global rather than India-first.

- **Live site:** <https://weekly-macro-dashboard.streamlit.app> (Streamlit Community Cloud, deployed from
  `main` of the public repo `shreyasxi/the-economics-hub`)
- **Newsletter:** <https://economicshub.substack.com/> · **Owner's site:** <https://shreyasxi.github.io> ·
  **Architecture write-up:** <https://shreyasxi.github.io/economics-hub/>
- **Look:** Bloomberg/FT-style charts — white background, black rules, bold titles, no decoration, no emoji
  in outputs or logs. The site itself sits on an ivory page (#FFFFF0) with Inter for text.

| Page | URL | Built by | Refreshed | Published files |
|---|---|---|---|---|
| Weekly Markets | `/` (default) | `generate_weekly.py`, `generate_news.py`, `generate_signals.py` | `weekly.yml`, Saturday 06:00 UTC | 40 charts + `news.json` + `signals.json` |
| World | `/world` | `generate_macro.py` | `macro.yml`, Saturday 10:00 UTC; rates only: `rates.yml`, weekdays 06:30 and 21:00 UTC | 12 charts + `world_snapshot.json` |
| India | `/india` | `generate_india.py`, `generate_soe.py` | `india.yml`, Saturday 08:00 UTC, plus manual runs | core + optional charts and provenance sidecars + `soe.json` |
| RBI Sentinel | `/rbi-sentinel` | `generate_rbi_sentinel.py --auto` | `rbi_sentinel.yml`, weekday evenings + MPC decision days | 5 charts + 1 research chart |
| Analysis | `/analysis` | reads `signals.json`, `config/analysis.py` and the Substack archive | live | — (no charts of its own) |
| About | `/about` | `config/resources.py` | live | — |

Weekly Markets, World, India, RBI Sentinel and (after a hairline) Analysis form the tab row under the
masthead; About is linked from the masthead. Every page ends in the same black footer.

---

## 2. How data becomes a dashboard

```
yfinance · FRED · OECD · BIS · Eurostat · central banks · RBI DBIE workbook · CAG workbook · manual entries · rbi.org.in
        │
        ▼
generate_*.py  (GitHub Actions or local)
        │
        ▼
output/<pipeline>/<date>/*.png      git-ignored, local
        │   workflow copies
        ▼
assets/<pipeline>/<date>/*.png      git-tracked, what Streamlit Cloud serves
        │
        ▼
charts/loader.py  → latest dated folder, natural sort, no hard-coded file lists
        │
        ▼
app.py  → 5 pages + About; each chart gets a "Chart insights" toggle from config/insights.py
```

Streamlit Cloud never runs a generator. It serves what is committed in `assets/` (and reads
`rbi_sentinel.db` for the RBI page's live text, and the Substack archive for the Analysis page).
A push to `main` is pulled within a few minutes, but the running app is **not** restarted: which
changes need a workflow run or a reboot is in §5.7.

---

## 3. Directory map

```
app.py                      the whole website: masthead, navigation, every page, the footer, all custom CSS
generate_weekly.py          Weekly Markets: 40 charts (every chart in one function, generate_with_live_data)
generate_news.py            Weekly Markets: "The Week in Headlines" (news.json); --collect feeds the week-long pool
generate_signals.py         Analysis page "Signal or noise" board: writes signals.json into a weekly edition
generate_macro.py           World page: 12 charts (one chart_* function each) + world_snapshot.json
generate_india.py           India page: core charts plus optional validated-source charts (chart_* functions)
generate_soe.py             India page: RBI's "State of the Economy" briefing (soe.json) + rate-transmission history
generate_rbi_sentinel.py    RBI Sentinel (--auto in CI; see §8)

config/
  settings.py               INDICATORS (Weekly tickers and FRED series, by id), US_YIELD_CURVE_TENORS,
                            FRED_API_KEY (from .env), paths
  weekly_settings.py        WEEKLY_SECTIONS: which Weekly chart sits in which section, in page order
  macro_settings.py         MACRO_INDICATORS: the World page's FRED series (transform, good direction, max age)
  world_settings.py         World page: countries, scoreboard cell sources, freshness limits, manual fields,
                            central bank meeting calendars (CENTRAL_BANKS), OECD CLI countries
  news_settings.py          headline feeds, themes, filters
  soe_settings.py           State of the Economy: URLs, table column map, freshness limits
  insights.py               CHART_INSIGHTS: chart key → the "Chart insights" text under each chart
  resources.py              About page lists and copy; FOOTER_* (the footer's links and lines)
  analysis.py               Analysis page: title, standfirst, WATCHING threads, PINNED essays (edited by hand)
  signals_settings.py       Analysis page: the 52 series on the Signal or noise board, thresholds

charts/
  style.py                  EconStyle — every colour, size, font and chart helper; the wordmark credit
  loader.py                 get_charts() (newest edition folder), chart_key(), group_charts(),
                            clean_title() + _ACRONYMS + _TITLE_OVERRIDES (captions), is_pipeline_admin()
  templates/                change_bars.py, weekly_bar.py (legacy), trend_line.py, yield_curve.py, summary_table.py
  india_cpi_contributions.py CPI contribution chart; verifies its independent source store
  make_chart.py             one-off charts from any CSV/Excel file, into output/custom/ (never published):
                            .venv/bin/python charts/make_chart.py data.csv --title "…" --type line

data/
  fetchers/                 market/macro clients; MoSPI GVA, IIP, CPI and inflation bridge;
                            NSE risk appetite, sector rotation, nse_valuations/{collector,production}.py;
                            india_source_archive.py (GVA/IIP journals), mospi_http.py (HTTP retries)
  india_macro.db            India series, SQLite (tracked): monthly/weekly projections, GVA, official IIP,
                            legacy IIP archive, emergency IIP and CPI observation audit tables (§5.4)
  india_db_manager.py       India database schema and upsert helpers
  india_manual_entry.py     CLI for PMI, GST, FPI, unemployment, core CPI; guarded CPI/emergency IIP entries
  india_manual.csv          legacy India manual data (fallback only)
  50 Macroeconomic Indicators.xlsx   RBI DBIE workbook (replaced by hand monthly)
  cag_monthly_accounts.xlsx          CAG monthly accounts workbook (replaced when CGA publishes one)
  cag_manual_accounts.csv            CAG months typed from the CGA web page, incl. deficit financing (fin_*)
  rbi_soe.py                State of the Economy: fetch and parse
  rbi_transmission.csv      rate-transmission history (Table IV.3), one row per edition and cycle (tracked)
  cpi_contributions.py      validated CPI observations, weights, contribution arithmetic and archive checks
  CPI/contributions/        immutable CPI raw responses, retrieval journals and run vintages; current pointer
  CPI/main/                 headline/food history, proposed writes and conflict/status journals
  IIP/, gva/                official source bytes, accepted/bootstrap manifests and revision journals
  nse_indices/              retained seed/daily index sources, manifest and rebased risk-appetite signal
  nse_rotation/             date-validated NSE snapshot, raw bytes and status
  nse_valuations/           verified monthly history, source CSVs, derived audit outputs and readiness status
  gmd_investment.csv/json    saved India investment-rate series and provenance
  world_snapshot.py         World page fetch + build (FRED, OECD, BIS, Eurostat, Bundesbank, BoE, MoF Japan, Yahoo,
                            and the central banks' own announcements: FOMC, ECB, BoE, BoJ, PBoC)
  pboc_reverse_repo.csv     PBoC 7-day reverse repo changes since 2019, one sourced row per change (tracked;
                            rates.yml appends new changes)
  world_manual_entry.py     CLI for World cells with no free API
  world_manual.csv          World manual figures (month, country, field, value, source)
  valuations.py             Shiller CAPE and Damodaran ERP / country risk downloads (every run)
  news.py                   headlines: RSS reading, theme sorting, story ranking
  signals.py                Signal or noise arithmetic
  substack.py               the newsletter shelf (Substack archive API, RSS fallback)
  rbi_sentinel.db           RBI documents, scores, composites, decisions (tracked)
  rbi_live_market.csv       hand-entered 10-year closes for the live test (tracked)
  rbi_live_log.csv          live test log (created from Oct 2026)
  rbi_sentinel_cache/, rbi_soe_cache/   downloaded pages (git-ignored)

rbi_sentinel/               RBI Sentinel package (§8): config.py, fetchers/, cleaners/, sentiment/, db/, charts/,
                            pipeline.py, live_log.py, seed_rates.py, research/tone_vs_10y_chart.py
tests/                      offline regression scripts/unittest suites (§5.6); fixtures/{soe,mospi_gva,
                            cpi,iip,nse_rotation}/ preserve official parser inputs

assets/                     what the live site serves (tracked): weekly/YYYY-MM-DD/, macro/YYYY-MM/,
                            india/YYYY-MM/, rbi_sentinel/YYYY-MM/ — newest 4 editions each;
                            rbi_research/ (chart 07), analysis/ (charts saved by hand for Analysis threads,
                            never pruned), brand/ (sidebar logo), fonts/ (Dancing Script, Playfair Display,
                            used by the chart wordmark), readme_showcase/ (6 fixed-name charts for the README)
output/                     local generator output and logs/ (git-ignored)
docs/                       project_context.md tracked; other owner notes/templates ignored, not served:
                            project_reminders.md,
                            templates/ (cag_fill.xlsx, fpi_nsdl_fill, rbi_sentinel/ price files behind chart 07),
                            "Manual Data Feeding (6th and 23rd).png"

site/                       static link-preview landing page, CSS/brand assets and social preview card
.github/workflows/          weekly.yml, macro.yml, rates.yml, india.yml, rbi_sentinel.yml, headlines.yml, keep_alive.yml, pages.yml
.github/scripts/            prune_assets.py (keeps 4 editions), rbi_should_run.py (RBI gate), keep_alive.py
.streamlit/config.toml      theme; .streamlit/secrets.toml is local only
```

Local only, never committed: `.env`, `.streamlit/secrets.toml`, `output/` and other ignored `docs/` files.
`docs/project_context.md` is retained in Git for future agents.

---

## 4. Chart index — where every chart comes from

Every published chart is a PNG named `NN_<key>.png`. The **key** (the name without its number) is what ties a
chart to its section, its caption and its "Chart insights" text; the number only sets the order within a
World or India section. Captions are the words under each chart on the site (also what the search box finds).

### 4.1 Weekly Markets — `generate_weekly.py`

All 40 are drawn inside one function, `generate_with_live_data()`, one block per chart. **To find a chart's
code, search the file for its file name** (e.g. `23_crude_oil_curve.png`): the block that draws it ends on that
line and starts at the `# ──` heading above. Most titles and subtitles come from `WEEKLY_TITLES` near the top of
the file (key = the chart key, with a `dashboard` and a `newsletter` title); six set theirs in the call that
draws them instead — the snapshot table (00), the trend lines (02, 04, 08) and the sector charts (10, 10b). Instrument ids such as `sp500` are defined in `config/settings.py` `INDICATORS`
(name, ticker, colour). Sections come from `config/weekly_settings.py`.

| File | Caption | Section | What it shows | Data |
|---|---|---|---|---|
| `00_summary_table` | (Market Snapshot table) | top of page | Latest levels and weekly changes across assets, US real wage growth | Yahoo Finance + FRED (DGS2/10/30; CES0500000003 and CPIAUCSL for real wages) |
| `01_equities_weekly` | Equities Weekly | Equities | Week's % change, nine indices | Yahoo: ^GSPC ^DJI ^IXIC ^FTSE ^STOXX50E ^NSEI 000001.SS ^HSI ^N225 |
| `02_equities_trend` | Equities Trend | Equities | 12 months, indexed to 100 | Yahoo: S&P 500, FTSE 100, Euro Stoxx 50, Nifty 50, Nikkei 225 |
| `10_sector_rotation` | Sector Rotation | Equities | S&P 500 sectors, week's return | Yahoo: SPDR sector ETFs (`SECTOR_ETFS`) |
| `10a_sector_rotation_12m` | S&P 500 Sector Rotation (12 Months) | Equities | Same sectors, trailing 12-month **total** return | Yahoo (dividend-adjusted) |
| `15b_defensives_cyclicals` | Defensive vs Cyclical Sectors | Equities | XLP+XLU+XLV against XLY+XLK+XLI, rebased, 26-week mean | Yahoo |
| `17_market_breadth` | Market Breadth | Equities | RSP/SPY equal-weight vs cap-weight ratio, 20-week average | Yahoo |
| `16_risk_appetite_ratio` | Risk Appetite Ratio | Equities | SPHB/SPLV high beta vs low volatility | Yahoo |
| `07_commodities_weekly` | Commodities Weekly | Commodities | Week's % change | Yahoo: BZ=F CL=F GC=F SI=F HG=F NG=F SRUUF |
| `08_commodities_trend` | Commodities Trend | Commodities | 12 months, indexed | Yahoo: Brent, gold, silver, copper |
| `23_crude_oil_curve` | Crude Oil Curve | Commodities | WTI futures curve today and a month ago; backwardation band | Yahoo: `CL<month><yy>.NYM` contracts, up to 15 |
| `24_agri_weekly` | Agri Weekly | Commodities | Week's % change | Yahoo: ZW=F ZC=F ZS=F KC=F CC=F SB=F |
| `23d_commodity_cycle` | Commodity Cycle | Commodities | S&P GSCI deflated by US CPI since 1984, average = 100 | Yahoo ^SPGSCI + FRED CPIAUCSL |
| `23c_commodities_breadth` | Commodities Breadth | Commodities | Share of 13 futures above their 200-day average, since 2008 | Yahoo (13 futures) |
| `23b_gold_real_rates` | Gold vs Real Rates | Commodities | Gold against the 10-year TIPS yield, quarterly path | Yahoo GC=F + FRED DFII10 |
| `06_yield_curve` | Yield Curve | Rates, Inflation & Credit | US Treasury curve now, 4 and 52 weeks ago | FRED DGS1MO…DGS30 (`US_YIELD_CURVE_TENORS`) |
| `09_move_index` | MOVE Index | Rates, Inflation & Credit | Bond-market volatility | Yahoo ^MOVE |
| `13_real_yields` | Real Yields | Rates, Inflation & Credit | 5- and 10-year TIPS yields | FRED DFII5 DFII10 |
| `12_breakeven_inflation` | Breakeven Inflation | Rates, Inflation & Credit | 5- and 10-year breakevens | FRED T5YIE T10YIE |
| `11_credit_spreads` | Credit Spreads | Rates, Inflation & Credit | IG and HY option-adjusted spreads, 2 years | FRED BAMLC0A0CM BAMLH0A0HYM2 |
| `18_bond_etf_returns` | Bond ETF Returns | Rates, Inflation & Credit | Trailing 12-month total returns | Yahoo: TLT, LQD, HYG |
| `03_fx_weekly` | FX Weekly | Currencies | Week's % change | Yahoo: DXY, EUR/USD, GBP/USD, USD/INR, USD/JPY, USD/CNY |
| `04_fx_trend` | FX Trend | Currencies | 12 months, indexed | Yahoo: DXY, EUR/USD, USD/INR, USD/JPY |
| `21_em_equity_weekly` | EM Equity Weekly | Emerging Markets & India | Week's % change of EM country ETFs | Yahoo: INDA MCHI EWZ EWY EWT EWW EZA |
| `20_em_fx_weekly` | EM FX Weekly | Emerging Markets & India | Week's % change vs USD | Yahoo: INR KRW IDR BRL MXN ZAR TRY |
| `10b_india_sector_rotation` | India Sector Rotation | Emerging Markets & India | NIFTY sector indices, week | NSE `allIndices` |
| `10c_india_sector_rotation_12m` | NIFTY Sector Rotation (12 Months) | Emerging Markets & India | Same, 12 months, price return | NSE `allIndices` |
| `22_india_vs_em_peers` | India vs EM Peers | Emerging Markets & India | 12 months, indexed | Yahoo: INDA, EEM, MCHI, EWY |
| `25_india_vix_vs_us` | India VIX vs US VIX | Emerging Markets & India | 12 months | Yahoo ^INDIAVIX ^VIX |
| `22b_em_stress_monitor` | EM Stress Monitor | Emerging Markets & India | EM corporate spreads against the EM dollar index | FRED BAMLEMCBPIOAS BAMLEMHBHYCRPIOAS DTWEXEMEGS |
| `22c_em_vix` | EM VIX | Emerging Markets & India | CBOE EM ETF volatility | FRED VXEEMCLS |
| `09_vix_trend` | VIX Trend | Cross-Asset Signals | VIX and 3-month VIX, 12 months | Yahoo ^VIX + FRED VXVCLS |
| `15_stock_bond_correlation` | Stock–Bond Correlation | Cross-Asset Signals | 60-day correlation of SPY and TLT returns since 2002 | Yahoo SPY TLT |
| `14_copper_gold_ratio` | Copper / Gold Ratio | Cross-Asset Signals | Copper/gold against the 10-year yield | Yahoo HG=F GC=F + FRED DGS10 |
| `19_gold_spx_ratio` | Gold / S&P 500 Ratio | Cross-Asset Signals | Gold ÷ S&P 500 | Yahoo GC=F ^GSPC |
| `19b_commodities_vs_equities` | Commodities vs Equities | Cross-Asset Signals | GSCI ÷ S&P 500 since 1984, log scale, recessions shaded | Yahoo ^SPGSCI ^GSPC + FRED USREC |
| `26_eth_btc_ratio` | ETH / BTC Ratio | Crypto | Ether priced in bitcoin | Yahoo ETH-USD BTC-USD |
| `27_btc_gold_ratio` | Bitcoin Priced in Gold | Crypto | Ounces of gold per bitcoin, weekly since 2015, log | Coin Metrics (price) + Yahoo GC=F |
| `28_btc_global_m2` | Bitcoin vs US M2 | Crypto | Bitcoin against **US** M2 (the file name says global; it is not) | Yahoo BTC-USD + FRED M2SL |
| `29_btc_mvrv` | Bitcoin MVRV Ratio | Crypto | Market value ÷ realised value since 2011 | Coin Metrics community API (CapMVRVCur, PriceUSD) |

The table at the top of the page (`00`) and the real-wage figure in it are the only Weekly items without a
"Chart insights" text, by design. Also on this page: **The Week in Headlines** (`news.json`, §9).

### 4.2 World — `generate_macro.py`

One function per chart. Titles are in `MACRO_TITLES` near the top of the file. Sections are chosen in `app.py`
`page_world()` by words in the file name (§5.3).

| File | Caption | Section | Function | What it shows | Data |
|---|---|---|---|---|---|
| `10_macro_rate_cycle` | The Global Rate Cycle | top, beside the calendar | `chart_rate_cycle` | Central banks that raised (up) or cut (down) their policy rate each month since 2000, of the 38 in the BIS dataset | the World snapshot's `rate_cycle` (BIS WS_CBPOL daily; Fed, ECB, BoE, BoJ, RBI announcements after BIS's last day) |
| `01_macro_inflation` | US Inflation Metrics | United States | `chart_inflation` | Each CPI category's contribution to headline CPI inflation over 12 months (stacked bars: energy, food, core goods, services ex-shelter, shelter), with headline CPI and core PCE lines and the 2% target | FRED CPIAUCNS CPIUFDNS CPIENGNS CUUR0000SACL1E CUUR0000SASLE CUUR0000SAH1 PCEPILFE; BLS December relative importance, typed yearly (`CPI_RELATIVE_IMPORTANCE`) |
| `02_macro_labour` | US Labour Market | United States | `chart_labour` | Unemployment and jobless claims in two panels, payrolls badge | FRED UNRATE ICSA PAYEMS |
| `07_macro_balance_sheet` | Federal Reserve Balance Sheet | United States | `chart_fed_balance_sheet` | Total assets | FRED WALCL |
| `16_macro_cape` | Shiller CAPE and Excess CAPE Yield | US Equity Valuations | `chart_cape` | CAPE and excess CAPE yield, two panels | Shiller `ie_data.xls` (`data/valuations.py`) |
| `17_macro_equity_risk_premium` | US Equity Risk Premium | US Equity Valuations | `chart_equity_risk_premium` | Implied ERP (trailing 12 months) since 2008 | Damodaran `ERPbymonth.xlsx` |
| `18_macro_country_erp` | Equity Risk Premiums Across the G20 | Country Risk | `chart_country_erp` | Mature-market premium + country risk premium, stacked | Damodaran `ctryprem*.xlsx` |
| `19_macro_regional_erp` | Equity Risk Premiums by Region | Country Risk | `chart_regional_erp` | Every rated country as a dot on its region's row; GDP-weighted average | Damodaran |
| `20_macro_ratings_vs_markets` | Markets vs the Rating Agencies | Country Risk | `chart_ratings_vs_markets` | CDS-implied minus rating-implied country risk, diverging bars | Damodaran |
| `14_macro_em_borrowing` | EM Dollar Borrowing Costs | Emerging Markets | `chart_em_borrowing` | EM corporate HY and IG yields against the 10-year Treasury | FRED BAMLEMHBHYCRPIEY BAMLEMIBHGCRPIEY DGS10 |
| `15_macro_em_dollar` | The Dollar vs EM Currencies | Emerging Markets | `chart_em_dollar` | Fed EM dollar index, the rupee and the two most extreme movers of nine EM currencies | FRED DTWEXEMEGS DEXINUS + `DEX*US` (`EM_FX_PEERS`) |
| `11_macro_oecd_cli` | OECD Composite Leading Indicators | Global Growth | `chart_oecd_cli` | 17 countries ranked by distance from 100, with each one's phase | OECD SDMX (`OECD_CLI_COUNTRIES`) |

Not charts, but on the page and built in `app.py` from `world_snapshot.json`: the **central bank strip**, the
**five-week calendar** and the **six-economy scoreboard** (§6). `chart_macro_em_vulnerability`,
`chart_bdti_branded_screenshot` and `chart_hormuz_exposure` are old functions that nothing calls; they are not
published.

### 4.3 India — `generate_india.py`

One function per chart; titles are set inside each function. Sections are chosen in `app.py` `page_india()` by
words in the file name (§5.3). Where the data is typed by hand, §5.4 says how to enter or correct it.

| File | Caption | Section | Function | What it shows | Data |
|---|---|---|---|---|---|
| `00_india_table` | (India Economic Snapshot) | top, beside "What changed" | `chart_table` | Latest month's key indicators | `india_macro.db` (many columns) |
| `01_india_pmi` | India PMI | Growth & Activity | `chart_pmi` | Manufacturing and services PMI | `india_mfg_pmi`, `india_svc_pmi` (typed, S&P Global) |
| `15_india_iip` | India IIP | Growth & Activity | `chart_iip` | Industrial production, % YoY | official General IIP published YoY, base 2022–23; `india_iip_monthly` |
| `06_india_inflation_bar` | India Inflation | Inflation & Monetary Conditions | `chart_inflation_bar` | Headline and food CPI, % YoY | official MoSPI published headline and Food and beverages rates; `mospi_inflation.py` bridge |
| `14_india_credit_deposit` | India Credit Deposit | Inflation & Monetary Conditions | `chart_credit_deposit` | Credit against deposit growth | `india_bank_credit_yoy`, `india_deposit_growth_yoy` (DBIE) |
| `18_india_rate_transmission` | India Rate Transmission | Inflation & Monetary Conditions | `chart_rate_transmission` | How far repo changes have reached deposit and lending rates | `data/rbi_transmission.csv` (automatic, `generate_soe.py`) |
| `16_india_forex_reserves` | India Forex Reserves | External Sector | `chart_forex_reserves` | Reserves, weekly | `india_weekly.forex_reserves_usd_bn` (DBIE) |
| `17_india_trade` | India Trade | External Sector | `chart_trade_balance` | Exports, imports, deficit | `india_exports_usd_bn`, `india_imports_usd_bn` (DBIE) |
| `03_india_fpi_monthly` | India FPI Monthly | Equity Markets | `chart_fpi_flows` | Net foreign portfolio investment per month | NSDL `india_fpi_net_inr_cr` (typed, ₹ crore) when any exists, else RBI's `india_fpi_flows` (US$ bn); never mixed (`fpi_series()`) |
| `02_india_gst` | India GST | Fiscal Policy & Public Finances | `chart_gst` | Monthly GST collections | `india_gst_revenue` (typed, PIB, ₹ lakh crore) |
| `07_india_expenditure_quality` | India Expenditure Quality | Fiscal Policy & Public Finances | `chart_expenditure_quality` | Capital against revenue spending, year to date; capex Budget ÷ 12 line | `data/cag_monthly_accounts.xlsx` + `data/cag_manual_accounts.csv` |
| `09_india_deficit_financing` | India Deficit Financing | Fiscal Policy & Public Finances | `chart_deficit_financing` | How the deficit is financed | `cag_manual_accounts.csv`, `fin_*` columns |
| `11_india_fiscal_deficit_gdp` | India's Fiscal Deficit, % of GDP | Fiscal Policy & Public Finances | `chart_fiscal_deficit_gdp` | Deficit as % of GDP against the Budget target | CAG workbook/CSV + the BE row's GDP |

| `20_india_gross_fixed_capital_formation` | India Investment Rate | Growth & Activity | `chart_investment_rate` | Gross fixed capital formation as % of GDP | saved GMD CSV + JSON provenance |
| `22_india_gva_contributions` | Real GVA contributions | Growth & Activity | `chart_gva_contributions` | Primary, secondary and tertiary contributions to real growth | official MoSPI constant-price GVA, base 2022–23 |
| `21_india_risk_appetite` | Indian Risk Appetite | Equity Markets | `chart_risk_appetite` | Smallcap 250 / NIFTY 50 price ratio, rebased | verified `data/nse_indices/` |
| `22_india_sector_valuations` | NIFTY Sector Valuations | Equity Markets | `chart_sector_valuations` | Current sector multiples against validated history | `data/nse_valuations/` |
| `23_india_sector_rotation_12m_benchmark` | NIFTY Sector Rotation | Equity Markets | `chart_sector_rotation_12m` | Trailing-year price returns with NIFTY 50 benchmark | official NSE snapshot; PNG + JSON sidecar |
| `24_india_cpi_contributions` | What’s Driving Indian Inflation | Inflation & Monetary Conditions | `charts.india_cpi_contributions.generate` | Six buckets contributing to headline inflation | independent verified CPI 2024 store; PNG + JSON sidecar |

Money supply and promoter-holdings charts are retired; the loader filters leftover images.

Also on the page: RBI's **State of the Economy** briefing and "What changed since last month" (`soe.json`,
§6), both quoted from RBI, never written by the pipeline.

### 4.4 RBI Sentinel — `rbi_sentinel/charts/`

| File | Module | What it shows | Data |
|---|---|---|---|
| `01_rbi_stance_meter` | `stance_meter.py` | Gauge of the latest meeting's composite tone (top of page) | `data/rbi_sentinel.db` |
| `02_rbi_sentiment_trajectory` | `sentiment_trajectory.py` | Tone over time, rate decisions in a strip below | same |
| `03_rbi_resolution_vs_minutes` | `doc_comparison.py` | Resolution against Minutes tone, recent cycles | same |
| `04_rbi_subdimension_radar` | `subdimension_radar.py` | Five sub-dimensions, current against previous meeting | same |
| `05_rbi_rate_and_sentiment` | `rate_and_sentiment.py` | Repo rate and tone through the policy cycle | same |
| `assets/rbi_research/07_rbi_tone_vs_10y` | `rbi_sentinel/research/tone_vs_10y_chart.py` | Change in Resolution tone against the decision-day 10-year G-sec move | price files in `docs/templates/rbi_sentinel/`; drawn by hand, not by the pipeline |

Each module has a `generate(...)` function called from `run_generate_charts()` in `rbi_sentinel/pipeline.py`.

### 4.5 Analysis page — no charts of its own

**Signal or noise** is HTML drawn from `signals.json` (52 markets' weekly moves against their typical week;
series and thresholds in `config/signals_settings.py`, arithmetic in `data/signals.py`). **What I'm watching**
shows the site's own charts by key plus images saved in `assets/analysis/`, all listed in `config/analysis.py`.
**From the newsletter** reads the Substack archive when the page opens. Details §6; editing §5.10.

---

## 5. How to — the common changes, step by step

### 5.1 Change how a chart looks (title, series, time range, colours)

1. Find the chart in §4: its file, and the function (World, India, RBI) or search string (Weekly) that draws it.
2. Ask the owner to paste that code. Change only what was asked.
3. Where each thing lives:
   - **Title and subtitle** (the words inside the image): Weekly `WEEKLY_TITLES["<key>"]["dashboard"]` (also
     `["newsletter"]`, the Substack wording — keep the `# ── EDIT for each Substack issue ──` markers), or the
     `title=` in the drawing call for the six listed in §4.1; World `MACRO_TITLES`; India and RBI inside the
     function or module.
   - **Which markets appear**: the list of ids in the block (e.g. `eq_ids = ["sp500", "dow", …]`); a new id
     needs an entry in `config/settings.py` `INDICATORS` (name, ticker, colour key). World series are in
     `config/macro_settings.py` `MACRO_INDICATORS`.
   - **Time range**: the fetch call (`fred_fetcher.fetch_series("…", period_years=2)`, Yahoo `period="1y"`,
     `get_trend()` = 12 months), or a slice after it.
   - **Colours, fonts, sizes**: from `EconStyle` (§7) — `REGION_COLORS`, `LINE_*`, `POSITIVE`/`NEGATIVE`,
     `create_figure(size="wide" | "standard" | "compact")`. Never hard-code a font or a DPI.
   - **Frame**: every chart keeps `add_top_rule`, `set_title` (title + subtitle), `add_source` (source line and
     the wordmark credit) and is saved with `EconStyle.save_chart` — never `plt.savefig`.
4. The owner's taste, learned the hard way: lines about 2.5pt with bold end labels in the line's colour (as on
   Weekly); no second y-axis on new or redesigned charts; plot the difference itself rather than two marks to
   subtract; no repeated dumbbell/barbell charts; captions in normal case; Inter for body text. When proposing a
   restyle, show two or three versions drawn at real size — that is what works with this owner.
5. Run the page's generator locally and open the new PNG (§5.6). Run the tests.
6. Publish: push the code, **then** run that page's workflow on `main` (§5.7). Until the workflow redraws the
   chart, the live site keeps the old picture.

**The shapes to expect when the owner pastes code.** Title dictionaries:

```python
WEEKLY_TITLES = {                     # generate_weekly.py; MACRO_TITLES in generate_macro.py is the same shape
    "equities_weekly": {              # MACRO_TITLES keys name the subject ("inflation"), not always the chart key
        "dashboard":  ("Global Equities", "Weekly percentage change across major indices  ·  {date}"),
        "newsletter": ("…", "…"),     # under a "# ── EDIT for each Substack issue ──" marker
    },
}
```

Every chart block ends the same way:

```python
fig, ax = EconStyle.create_figure(size="wide")          # "standard" or "compact" for smaller charts
ax.plot(dates, values, color=EconStyle.LINE_BLUE, linewidth=2.5)
_t, _s = WEEKLY_TITLES["<key>"][mode]                    # or a literal title and subtitle
EconStyle.set_title(ax, _t, _s)
EconStyle.add_top_rule(ax)
fig.tight_layout(rect=[0.02, 0.04, 0.98, 0.96])
EconStyle.add_source(fig, "FRED")                        # source line + the wordmark credit
EconStyle.save_chart(fig, output_dir / "NN_<key>.png")
```

Data comes from the project's fetchers: `fred_fetcher.fetch_series("DGS10", period_years=2)` and
`yf_fetcher.get_close_series("^GSPC", period="1y")` return pandas Series indexed by date;
`yf_fetcher.weekly_change(ticker)` gives the week's move. Weekly blocks are wrapped in `try/except` that prints
`⚠ … failed`, so one broken source skips one chart rather than the run.

### 5.2 Change a caption or a chart's "Chart insights" text

- **Caption** (the words under the chart, and what search finds): `clean_title()` in `charts/loader.py` builds
  it from the file name; `_ACRONYMS` fixes capitals (GDP, BTC, NIFTY), `_TITLE_OVERRIDES["<key>"]` sets a caption
  outright. Live a few minutes after a push; no workflow, no reboot.
- **"Chart insights"** (the toggle under a chart): `CHART_INSIGHTS["<key>"]` in `config/insights.py` — Markdown,
  about two paragraphs, analyst tone, plain English, no "we" (it is one person's project). Live after a push.
- The title *inside* the picture is part of the image: §5.1.

### 5.3 Move, add or remove a chart

- **Weekly: which section** — `config/weekly_settings.py` `WEEKLY_SECTIONS`, a list of keys per section in page
  order. Every chart must appear exactly once (`tests/test_weekly_sections.py` checks); an unlisted chart shows
  under "Other". Live after a push.
- **World and India: which section** — decided in `app.py` (`page_world()`, `page_india()`) by words in the file
  name, first match wins, in this order:
  - World: `rate_cycle` (top) → United States (`inflation`, `labour`, `balance_sheet`) → US Equity Valuations
    (`macro_cape`, `equity_risk_premium`) → Country Risk (`country_erp`, `regional_erp`, `ratings_vs_markets`) →
    Emerging Markets (`macro_em_`) → Global Growth (`oecd_cli`) → Other.
  - India: snapshot at top → **Growth & Activity** (PMI, IIP, investment rate, GVA; explicit order)
    → **Equity Markets** (FPI, risk appetite, valuations, rotation) → **Inflation & Monetary Conditions**
    (headline/food CPI, CPI contributions, credit/deposits, transmission) → **External Sector** (forex, trade)
    → **Fiscal Policy & Public Finances** → Other. Read `page_india()` for exact membership and order.
  - So a file name decides where a new chart lands. Changing these lists is an `app.py` change (needs a reboot).
  - India uses explicit ordering for its growth, equity and inflation rows; other groups retain loader order.
- **Add a chart**:
  1. Write a block (Weekly) or `chart_*` function (World, India) that saves `NN_<key>.png` with `EconStyle.save_chart`.
     World and India functions must also be called from the page's main routine.
  2. Give it a title in `WEEKLY_TITLES` / `MACRO_TITLES` (both `dashboard` and `newsletter`).
  3. Place it: a `WEEKLY_SECTIONS` entry for Weekly; for World or India, a file name that matches the right keyword.
  4. Add a `CHART_INSIGHTS` entry, and a `_TITLE_OVERRIDES` caption if the file name reads badly.
  5. Run the generator locally, look at the chart, run the tests, publish (§5.6–5.7).
- **Remove a chart**: delete its block or function (and its call) and its `WEEKLY_SECTIONS` entry. The
  generators empty their output folder before each run, so a removed chart does not linger.
- **Link to one chart**: `/<page>?chart=<key-with-hyphens>` scrolls to it, e.g. `/?chart=crude-oil-curve`.

### 5.4 Enter or correct a data point

**Never type over a number the pipeline fetched** — fix the source, the mapping or the calculation instead.
Only the stores below hold hand-entered figures. Run the commands from the project folder; add `--dry-run` to
preview any `set`.

| Page | Figure | How to enter or correct it | Stored in |
|---|---|---|---|
| Weekly Markets | any | Nothing is stored: every number is fetched fresh each run (Yahoo, FRED, NSE, Coin Metrics). A wrong number means a wrong ticker or series (`config/settings.py`) or a wrong calculation (the chart's block). | — |
| World | Manufacturing PMI (US, euro area, UK, Japan, China), Japan CPI, China unemployment, China 10-year | `PYTHONPATH=. .venv/bin/python -m data.world_manual_entry set 2026-08 --country US --pmi 52.4` (`--cpi` Japan only, `--unemployment` and `--ten-year` China only). Running `set` again for the same month overwrites. `… status` lists what is missing. | `data/world_manual.csv` |
| World | everything else | Automatic, with freshness limits (`config/world_settings.py`); no overrides by design. A stale source fails the run with a message naming it. | — |
| India | PMIs, GST, core CPI, unemployment, FPI (NSDL); headline/food CPI and IIP have guarded manual fallbacks | `PYTHONPATH=. .venv/bin/python -m data.india_manual_entry set 2026-08 --gst 2.04 --cpi 4.5` — flags `--mfg-pmi --svc-pmi --gst --cpi --core-cpi --food-cpi --unemployment --iip --fpi`. Units: PMI index; GST ₹ **lakh crore** (2.04, never 204000); CPI/IIP % YoY; unemployment %; FPI ₹ **crore**. Range-checked; prints before → after; setting a month again corrects it. `… status` shows 12 months, `… show 2026-08` one. Composite PMI is calculated — never enter it. | `data/india_macro.db`, table `india_monthly` |
| India | bank credit, deposits, M3, exports, imports, forex reserves, RBI's FPI series | Download RBI's DBIE workbook, save it over `data/50 Macroeconomic Indicators.xlsx` (same name), then `PYTHONPATH=. .venv/bin/python data/fetchers/india_fetcher.py --dry-run` and `… --append` (updates the months present; other columns untouched). A wrong figure is corrected by RBI's next workbook, not by hand. | `india_monthly`, `india_weekly` |
| India | fiscal: revenue spending, capex, fiscal deficit, interest, subsidies, Budget (BE) rows, deficit financing | One row per month in `data/cag_manual_accounts.csv`, **year-to-date ₹ crore**, rules in the file's header comment (the financing rows must add up, to within ₹1 crore). A row in `data/cag_monthly_accounts.xlsx` for the same month wins, except the `fin_*` columns. Checked by `tests/test_cag_manual.py` and by `generate_india.py`, which stops on a bad figure. | the CSV / workbook |
| India | rate transmission, State of the Economy briefing | Automatic from RBI's Bulletin (`generate_soe.py`); never typed. | `data/rbi_transmission.csv`, `soe.json` |
| RBI Sentinel | 10-year G-sec close on a decision day (live test) | Add one line: `2026-10-07,<previous day close>,<decision day close>,Investing.com` | `data/rbi_live_market.csv` |
| RBI Sentinel | a repo-rate decision recorded wrongly | Correct `RATE_CHANGES` in `rbi_sentinel/seed_rates.py` (`(date, new_rate, action, change_bps)`), then `python -m rbi_sentinel.seed_rates` | `data/rbi_sentinel.db` |
| RBI Sentinel | tone scores | Never edited by hand; rescoring costs money (§8). | `data/rbi_sentinel.db` |

India's `india_monthly` table has one row per month (`month` = `YYYY-MM`) with the columns `india_mfg_pmi,
india_svc_pmi, india_composite_pmi, india_gst_revenue, india_unemployment, india_cpi_yoy, india_core_cpi_yoy,
india_food_cpi_yoy, india_bank_credit_yoy, india_deposit_growth_yoy, india_fpi_flows, india_iip_yoy,
india_m3_yoy, india_exports_usd_bn, india_imports_usd_bn, india_trade_deficit_usd_bn, india_fpi_net_inr_cr,
source_flags, fetched_at`; `india_weekly` has `week_ending, forex_reserves_usd_bn, forex_reserves_wow_chg,
fpi_net_flows_usd_bn, fetched_at`. Release dates and source links for all of the above: `project_reminders.md`.

**Then publish:** commit the changed data file, push, and run the page's workflow (India Dashboard Generator
has a `skip_fetch` option to only redraw; World Generator redraws everything). §5.7.

### 5.5 Change words on the site

| Words | Where | Live after a push? |
|---|---|---|
| Page titles and standfirsts (Weekly, World, India, RBI) | `app.py`, each `page_*()` calls `_page_header_html(title, standfirst, …)` | needs a reboot |
| Masthead, tab row, sidebar | `app.py` | needs a reboot |
| About page, footer links and lines | `config/resources.py` | yes |
| Analysis page: title, standfirst, threads, their charts, pinned essays | `config/analysis.py` + images in `assets/analysis/` (§5.10) | yes |
| Chart captions / "Chart insights" | §5.2 | yes |
| Headline feeds, themes and filters | `config/news_settings.py` | how they are shown: yes; which headlines: from the next Weekly run |

A `$` in text shown through `st.markdown` must go through `_esc()` in `app.py` (Streamlit reads `$…$` as maths).

### 5.6 Run and check it locally

```bash
.venv/bin/streamlit run app.py                                  # the site at http://localhost:8501
PYTHONPATH=. .venv/bin/python generate_weekly.py --preview      # Weekly → output/weekly/<date>/ (lower DPI)
PYTHONPATH=. .venv/bin/python generate_macro.py --preview       # World → output/macro/<month>/
PYTHONPATH=. .venv/bin/python generate_india.py --mode dashboard  # India → output/india/<month>/
PYTHONPATH=. .venv/bin/python generate_rbi_sentinel.py --charts-only  # RBI charts from the database, no API calls
PYTHONPATH=. .venv/bin/python generate_signals.py               # the Analysis board, into the newest weekly edition
for f in tests/test_*.py; do PYTHONPATH=. .venv/bin/python "$f" > /dev/null || echo "FAILED: $f"; done
```

- Weekly, World and the signals board need `FRED_API_KEY` in `.env`. No generator publishes anything — they
  write to `output/` (the signals board into the newest `output/weekly/` edition).
- On localhost the newest folder wins across `output/` and `assets/`, so after a local run the local site shows
  the local charts; the live site only ever shows committed `assets/`.
- Tests (run each `tests/test_*.py` script; unittest discovery alone misses plain-function suites): `test_weekly_sections` (every Weekly chart placed once), `test_units`
  (1,000× unit slips), `test_world`, `test_valuations`, `test_cag_manual`, `test_soe`,
  `test_news`, `test_signals`, `test_analysis` (also checks `config/analysis.py`), `test_rbi_rate_decisions`,
  `test_rbi_charts_current` (RBI charts drawn from the current database).
- For page layout changes, screenshot desktop and phone widths before calling it done.

### 5.7 Publish

1. **Git**: commit and push to `main` (structural work: a branch first, then merge). The owner approves each
   commit, merge and push. From the project folder:
   ```bash
   git pull                                     # FIRST, before changing anything: the workflows commit to main too
   # … make the change, run the checks (§5.6) …
   git status                                   # what has changed
   git add data/india_macro.db                  # the files you mean to publish, by name
   git commit -m "data: GST for Aug 2026 corrected"
   git push
   ```
   If the push is refused because a workflow pushed in the meantime: `git pull --rebase`, then `git push`. If
   that reports a conflict in a database file (`data/india_macro.db`, `data/rbi_sentinel.db`), don't try to merge
   it: run `git rebase --abort` (which puts everything back as it was) and ask for help — the figures need
   entering again on top of the newer database.
2. **What shows up when:**

| You changed | The live site shows it after |
|---|---|
| A generator, `charts/style.py`, `charts/templates/`, or a data file (`india_macro.db`, `world_manual.csv`, the CAG CSV/workbook) | the push **and** the page's workflow run — Actions → the workflow → **Run workflow** → `main` — or the Saturday run |
| `config/insights.py`, `config/resources.py`, `config/analysis.py`, `config/world_settings.py`, `config/weekly_settings.py`, `config/news_settings.py`, `config/soe_settings.py`, `config/signals_settings.py`, `charts/loader.py` captions, images in `assets/analysis/` | the push alone (Cloud pulls within minutes; these are re-read when they change) |
| `app.py`, or any other Python module | the push **and** Streamlit Cloud → Manage app → **Reboot** |

3. **Workflows** (Actions tab): Weekly Markets Generator, World Generator, India Dashboard Generator, RBI
   Sentinel, Headline Collector, Keep Streamlit App Alive. Start them with **Run workflow**, never **Re-run** on an old run: a
   re-run reuses the commit it first ran on, and its final push is refused once `main` has moved on (the World
   run of 21 Sep 2026 failed twice this way). Don't start two chart workflows at once — the second one's push
   can be refused for the same reason.
4. Check the live page after a few minutes. New charts under old captions, or new words in an old layout, mean
   the app needs a reboot.

### 5.8 Undo

- A commit: `git revert <hash>` then push. A merge: `git revert -m 1 <merge hash>` then push.
- Charts: each page keeps its newest 4 editions in `assets/`; anything older is in git history.
- The last big merge (Analysis page, footer, smaller India and RBI hero charts, 21 Sep 2026) is `3660491`.

### 5.9 When a workflow run is red

| Where it failed | Usual cause | What to do |
|---|---|---|
| Any workflow, step *Commit and push charts* | another workflow pushed to `main` first | Run workflow again (not Re-run) |
| Weekly, a chart missing but the run green | that chart's block failed; the log shows `⚠ … failed` and the rest carried on | read the warning; usually a ticker Yahoo stopped serving |
| Weekly, *Rank the week's unusual moves* | over a quarter of the 52 series could not be read | nothing is published for the board that week; the charts are fine |
| World, *Generate World charts and snapshot* | a source is stale or failed: the log ends `FINISHED WITH PROBLEMS`, one line per source | nothing is published until it is fixed, by design; a renamed/discontinued series needs a replacement |
| India, source update steps | RBI/NSE/MoSPI blocked or changed | independent charts still render; failed optional sources gate their charts and remove stale artifacts; inspect source status/logs |
| RBI Sentinel | see §8 | |
| Any, "FRED_API_KEY is not set" | the secret expired or was removed | re-add it in GitHub → Settings → Secrets; there is no fallback by design |

### 5.10 The Analysis page's hand-written parts

Everything is in `config/analysis.py` (its docstring lists every field) plus images in `assets/analysis/`.
Order in the file is order on the page.

```python
TITLE = "Connecting the Dots"
DEK = "…"                                           # the line under the title
PINNED = ["iran-war-is-more-than-just-oil", …]      # essays by the end of their Substack address, in order
NEW_FOR_DAYS = 30                                   # a new post leads the shelf, marked New, this long
WATCHING = [
    {
        "theme": "The Iran war, beyond oil",        # the thread's heading
        "why": "…",                                 # one or two sentences, the owner's own words
        "charts": [
            {"dashboard": "crude_oil_curve", "note": "…"},          # one of this site's charts, by key (§4)
            {"image": "analysis/eia_brent_2q26.png",                 # a saved chart, in assets/analysis/
             "title": "…", "source": "U.S. EIA", "url": "https://…",
             "date": "2026-07-15", "note": "…"},
        ],
    },
]
```

Replace a saved chart: put the new PNG in `assets/analysis/` (lower case, no spaces, e.g.
`eia_brent_2026-10.png`), change that entry's `image`, `title`, `source`, `url`, `date` and `note`, and delete the
old file. Then `PYTHONPATH=. .venv/bin/python tests/test_analysis.py` (must end "0 failed": it catches a missing
image, a misspelt field, a bad date or link, a missing comma), look at `/analysis` locally, commit, push. No
workflow and no reboot: the page updates a few minutes after the push. A slip that reaches the live site stops
only this page, with a note naming the line.

---

## 6. The pages in detail

The current state of each page, with the reasons behind it. The chart-by-chart list is §4.

### Weekly Markets — `generate_weekly.py`
- **Data:** yfinance + FRED + NSE `allIndices` + Coin Metrics community API (free, no key), fetched fresh every
  run (`--preview` for low DPI). There is no mock mode:
  a missing `FRED_API_KEY` or data source fails the run.
- **Charts (latest set):** summary table; global equities; FX; US yield curve; commodities;
  VIX; MOVE index; S&P sector rotation and NIFTY sector rotation (each this week and trailing 12 months, side by
  side; NIFTY's are price returns); credit spreads; breakevens;
  real yields; copper/gold; stock-bond correlation (since 2002); defensives/cyclicals; high-beta/low-vol; breadth;
  bond ETFs; gold/SPX; commodities vs equities (since 1984);
  EM FX, EM equities, India vs EM peers, EM stress monitor, EM VIX; crude futures curve, gold vs real rates,
  long commodity cycle (since 1984), commodity breadth (since 2008); agri;
  India VIX vs US; ETH/BTC, BTC/gold, BTC vs global M2, BTC MVRV
- **Titles:** `WEEKLY_TITLES` holds a `dashboard` and a `newsletter` title per chart.
  CI uses `--mode dashboard`. Newsletter strings are marked `# ── EDIT for each Substack issue ──`.

### World — `generate_macro.py` (page "World", title "The World Economy")
Replaced Macro Pulse on 15 Sep 2026. Standfirst (rewritten 16 Sep 2026, the old one named charts that no longer exist
and framed the page around India): *Central banks, growth and inflation, equity valuations and country risk across the
world's major economies.*

**Page order:** header → central bank strip → global rate cycle chart + five-week calendar → six-economy scoreboard →
United States (inflation, labour, Fed balance sheet centred alone) → US Equity Valuations (Shiller CAPE
and excess CAPE yield, Damodaran implied ERP) → Country Risk (G20 premiums and regional premiums side by side,
ratings vs markets centred) → Emerging Markets (EM dollar borrowing costs, dollar vs EM currencies and
the rupee) → Global Growth (the ranked OECD CLI chart, drawn wider than a grid cell by `_render_wide`).

**Outputs** (`output/macro/YYYY-MM/`, copied to `assets/`): `world_snapshot.json` plus
`01_macro_inflation`, `02_macro_labour`, `07_macro_balance_sheet`,
`10_macro_rate_cycle`, `11_macro_oecd_cli`, `14_macro_em_borrowing`, `15_macro_em_dollar`, `16_macro_cape`,
`17_macro_equity_risk_premium`, `18_macro_country_erp`, `19_macro_regional_erp`, `20_macro_ratings_vs_markets`.
Retired: financial conditions, money & yield spreads (Weekly already has credit spreads, curve, real yields),
housing, consumer sentiment, the EM spreads / EMLC rows, and (15–16 Sep 2026, owner's call) the China CPI vs LPR chart,
Brent in rupees (the dashboard has an international audience, not only Indian readers), the Sahm rule chart (it
misfired in 2024 and repeats the unemployment rate) and the United States summary table (every row but the Sahm rule
was already on a chart; the Sahm series was dropped from `MACRO_INDICATORS` with it).

**US Equity Valuations** (`data/valuations.py`, downloaded every run; `tests/test_valuations.py`):
- Shiller `ie_data.xls`: the link is scraped from shillerdata.com (its path changes with each upload); legacy .xls, so
  `xlrd` is in requirements.txt. Columns are found by header text (CAPE = "P/E10 or CAPE", not TR CAPE; "Excess CAPE
  Yield" is a fraction). Dates are year.month decimals (1990.1 = October). The latest row is dropped while Shiller's note
  says its price is a single day's close, and no month still in progress is used. Shiller estimates CPI where BLS data
  are missing or late (e.g. Oct 2025) — disclosed in the chart insight. Max age 100 days.
- Damodaran `ERPbymonth.xlsx`, sheet "Historical ERP", column "ERP (T12m)" (his headline series; matches the "Last 12
  months data" sheet). Start of month since Sep 2008. A few cells are text ("4.06%"), parsed by `_fraction`. Max age 70 days.

**Country Risk** (section after US Equity Valuations; owner asked 16 Sep 2026 for the G20 bars, ratings vs markets and
regional averages — "where investors might fly"): `fetch_country_risk` reads Damodaran's data page (datacurrent.html),
opens every `ctryprem*.xlsx` from the last two years (dated names like ctrypremJuly25.xlsx; the undated ctryprem.xlsx is
the January file) and uses each file's own "Date of update". Latest update + the one ~12 months earlier (9–15 months;
otherwise the run fails). Sheet "ERPs by country": the rated table only — it stops where the region column stops being
text, because unrated countries (Russia and other "Frontier Markets") follow in a PRS-scored table. Mature premium =
median(ERP − CRP), which must be the same for every country. Sheet "Regional Weighted Averages": the Region block down to
"Global" (total ERP only — the block's CRP column has a bad value for Australia & NZ). Updates come in January and July,
so max age is 260 days. Charts: `18_macro_country_erp` (G20 stacked bars, Russia unrated and left out, a renamed G20 country
fails the run), `19_macro_regional_erp` and `20_macro_ratings_vs_markets`. Both were redrawn on 16 Sep 2026: the owner
was "tired of barbell charts" and wanted the chart to do the talking rather than the reader.
- `19_macro_regional_erp` is now a **strip plot**: every rated country a dot on its region's row (deterministic beeswarm,
  `_swarm_offsets`), the GDP-weighted average a large maroon dot (a black rule was tried first and the owner asked for
  a big shaded dot instead, since the averages are already listed in the column), the year-ago comparison reduced to a
  change column. It shows
  the spread the average hides — Western Europe is tight, Africa and Asia are wide. Countries rated C sit near 31%, three
  times the next tier, so the axis is capped at `ERP_AXIS_CAP` (20%); the omitted countries are disclosed in the source
  line only (edge carets and an in-chart note were tried first and cut as clutter). `REGION_MEMBERS` maps the one region Damodaran spells differently in his two tables ("Eastern Europe" in the
  regional block, "Eastern Europe & Russia" in the country table); a region with no members fails the run.
- `20_macro_ratings_vs_markets` is now a **diverging bar chart of the gap itself** (CDS-implied CRP − rating-implied CRP,
  in percentage points), sorted, teal left / maroon right, with a caption at each end saying which way is which, so no
  one has to subtract two dots. Countries without CDS, e.g. Argentina, are noted in the source line.

**Emerging Markets section** (FRED, in `MACRO_INDICATORS`, so stale series fail the run): ICE BofA EM corporate
high-yield and high-grade effective yields (`BAMLEMHBHYCRPIEY`, `BAMLEMIBHGCRPIEY`) vs `DGS10`; the Fed's EM dollar
index `DTWEXEMEGS` vs ten EM currencies quoted per dollar (H.10 daily `DEX*US`, max age 16 days), indexed to 100 on
their first common week. The dollar chart always draws the index and the rupee `DEXINUS`, then picks the two extremes
from `EM_FX_PEERS` (Brazil, Mexico, South Africa, Korea, China, Thailand, Malaysia, Taiwan, Singapore) — whichever has
weakened most against the dollar and whichever has strengthened most, so the pair changes with the data. They are added
to `MACRO_INDICATORS` programmatically, so a retired FRED series fails the run like any other. Added 16 Sep 2026 after
the owner asked for "other currencies that have had extreme movements"; it also pulls the chart away from Weekly's
"Key FX Rates — Trailing 12 Months", which indexes DXY/EUR/JPY/INR over one year.
Deliberately different from Weekly's EM stress monitor, which charts the same ICE indices as SPREADS against the EM
dollar index: this section shows all-in yields and the rupee against the EM basket. FRED holds only 3 years of ICE data.

**US inflation by category** (24 Sep 2026, owner's request, modelled on a Conference Board chart): stacked bars of each
CPI category's contribution to the 12-month headline rate, in points, by the BLS method (`cpi_contributions`: December
relative importance carried forward by relative price change, split at December because weights change each January).
Uses NOT seasonally adjusted indexes, since only those aggregate: the bars add up to headline CPI to within 0.001 points,
and the run fails if they miss by more than 0.05 (a mistyped weight). Five categories (energy, food, core goods, services
ex-shelter, shelter) rather than the 8 BLS major groups: those hide energy inside Housing and Transportation and leave four
unreadable slivers. 12-month contributions, not month-on-month, so the bars match the core PCE line and the 2% target.
The 5y5y expectations line was dropped (Weekly charts the breakevens). BLS weights are typed each February (see
project_reminders.md); bls.gov blocks automated downloads.

**Line-chart style** (labour, both EM charts; redesigned 15 Sep 2026): `monotone_curve` draws a monotone cubic
(PCHIP) through monthly/weekly observations — passes through every value, never overshoots between neighbours (tested,
including a mutation check); daily series are shown as complete-week averages (`weekly_average`); year ticks; palette
`EconStyle.LINE_*`. The owner wants lines as heavy as the Weekly page's: both EM charts use `HEAVY_LINE` (2.5pt) with
Weekly-style bold end labels in the line's colour (`_margin_labels`, collisions spread around their average). "US Labour Market Indicators" (renamed from
Labour Market Pulse) keeps 2pt lines — the owner likes it as is — in two panels (no second y-axis), with the latest
payrolls change in a navy badge top right. The OECD CLI chart was small multiples of six economies for one day and is
now a **ranked bar chart of all 17 countries OECD publishes a CLI for** (owner's call, 16 Sep 2026): bars measure the
distance from the 100 trend line, and each row names its OECD phase (Expansion/Downturn/Slowdown/Recovery) in the phase
colour, so the phase is never carried by colour alone. `OECD_CLI_COUNTRIES` in `config/world_settings.py` holds the 17;
OECD's own aggregates (G7, G20, G4E, NAFTA, A5M) are excluded (`OECD_CLI_AREAS`, which added G4E for the retired
regime chart, went with it on 24 Sep 2026). `cli_phase(series, months=3)` judges direction over three
months rather than one, so a single month's wobble cannot flip a country between phases.
CAPE uses two panels like the labour chart; the ERP chart uses `HEAVY_LINE`. `_time_axis` picks 1/2/5/10/20-year labels
by span. The Fed balance sheet chart still uses the older style.

**Central bank strip** (HTML, app.py). Every rate is an official daily series with the bank's own latest
announcement applied on top, so a decision shows the day it is announced (owner, 24 Sep 2026: "as soon as announced
it should be reflected"), even when it takes effect later:
- Fed: FRED DFEDTARL/U + the latest FOMC statement (`apply_fomc_decision`; FRED posts the new range the morning after).
- ECB: FRED ECBDFR + the latest row of the ECB's key interest rates table (`fetch_ecb_decision`). ECBDFR is dated by
  effective day, usually the Wednesday after the decision, so without the table the 10 Sep 2026 hike showed only on 16 Sep.
  Not yet seen in action: whether the ECB adds the new row on decision day (expected) — check after the 29 Oct 2026 meeting.
- BoE: IADB IUDBEDR (~2 days behind) + the latest row of the Bank Rate history page (`fetch_boe_decision`).
- BoJ: BIS WS_CBPOL daily (~1 week behind) + the latest statement PDF on the year's decisions page
  (`fetch_boj_decision`, PyMuPDF): "The Bank will encourage the uncollateralized overnight call rate to remain at around
  X percent" (a dissent says "would", never read) and "…will be effective from <date>". Missed the 18 Sep 2026 hike
  (1.00 → 1.25% from 24 Sep) for a week before this.
- PBoC: the **7-day reverse repo rate** (owner's call, 24 Sep 2026; the PBoC calls it its main policy rate; BIS carries
  the 1-year LPR). `data/pboc_reverse_repo.csv` holds every change since Oct 2019, each dated by the first 7-day
  operation at the new rate and linked to the notice (verified by hand against the PBoC archive; the English archive
  lacks notice No.194 of 27 Sep 2024, which was 14-day only, so the Sep 2024 cut is dated 29 Sep). Each run reads the
  newest notices on the **Chinese** open market operations list (posted 09:20 Beijing, hours before the English
  translation); a new rate is walked back to its first operation and appended to the CSV. Pages declare no charset:
  decoded as UTF-8. Figures are split across spans, so `html_text` drops inline tags without a space.
- RBI: live from the Sentinel brief.
`apply_decision` adds the announced rate on its effective day when the daily series does not reach it, and raises
(the run fails) if the series later disagrees. Last move = the latest change in the combined series; a move not yet in
force reads "from 24 Sep" on the tile and in the scoreboard (`_move_phrase`, `fmt_period`). Next decision dates come from
`CENTRAL_BANKS` in `config/world_settings.py` — the banks' own calendars, verified 15 Sep 2026, listed through Dec 2027
(Fed 2027 tentative, BoE 2027 provisional). PBoC has no meetings: its tile says "No fixed meeting dates"; the LPR fixing
(20th, rolled to Monday at weekends, "around") stays on the calendar.
`tests/test_world.py` fails once a bank's list runs out. Tiles show the acronym only (full name on hover) and
"Next: 16 Sep 2026" — no countdown and no red highlight, by the owner's choice.

**Weekday rate refresh** (`rates.yml`, added 24 Sep 2026): `generate_macro.py --rates-only` rebuilds only the strip,
the scoreboard's policy-rate cells and the rate cycle chart (`build_rate_update`) and writes them into the newest
published edition, `assets/macro/<latest month>/` (never a new folder, which would hide the rest of the page). Runs
at 06:30 UTC (after the PBoC notice, BoJ and RBI) and 21:00 UTC (after the BoE, ECB and Fed), Mon–Fri, and by hand
with Run workflow. It checks every weekday rather than only on calendar dates because the PBoC has no calendar and
any bank can move between meetings. `rates_fingerprint` compares rates, last moves and monthly counts — not observation
dates — so an unchanged day writes and commits nothing. A problem writes nothing and fails the run. The page shows
"Rates updated <date>, <time> UTC" under the strip when the rates are newer than the Saturday snapshot. Pushes rebase
and retry (RBI Sentinel also pushes on weekdays).

**Scoreboard cells** (`CELL_SOURCES`):

| | Mfg PMI | CPI | Unemployment | Policy rate | 10Y | Currency YTD |
|---|---|---|---|---|---|---|
| US | manual | FRED CPIAUCSL | FRED UNRATE | FRED + FOMC statement | FRED DGS10 | DXY (Yahoo) |
| Euro area | manual | Eurostat prc_hicp_minr | Eurostat une_rt_m (EA21/EA20, latest wins) | FRED ECBDFR + ECB table | Bundesbank Bund | EURUSD |
| UK | manual | OECD | OECD | BoE IUDBEDR + Bank Rate page | BoE IUDMNPY | GBPUSD |
| Japan | manual | **manual** | OECD | BIS + BoJ statement | MoF JGB CSV | JPY |
| China | manual | OECD | **manual** | PBoC notices (7-day reverse repo) | **manual** | CNY |
| India | India DB | India DB | India DB | Sentinel DB | DBIE workbook (FBIL) | INR |

**Freshness rule:** an automatic cell that fails or is older than its limit (`SCOREBOARD_COLUMNS[...]["max_age"]`, days from
the period start; overrides in `MAX_AGE_OVERRIDES`) is a *problem*: the generator writes what it has, prints
`FINISHED WITH PROBLEMS`, exits 1, and the workflow publishes nothing. Manual cells show "awaiting entry"; manual or
hand-refreshed (India DB, DBIE) cells past the limit show "not updated" — neither fails the run. US FRED series have the
same check (`max_age` in `macro_settings.py`).

**Global rate cycle chart** (`10_macro_rate_cycle`, replaced the growth-vs-inflation regime chart on 24 Sep 2026 at
the owner's request, after the regime chart was judged noisy and a repeat of the OECD CLI chart): diverging monthly bars
since 2000 — how many of the 38 central banks in BIS WS_CBPOL raised (red, up) or cut (blue, down) their policy rate,
each bank counted once a month by its month-end rate against the previous month-end (`rate_moves_by_month`). One BIS
call, `detail=dataonly` (7 MB since 1999; the default response repeats long notes on every row and passes 70 MB).
BIS runs ~1 week behind (India ~2 months), so for the banks the page reads directly (`BIS_EXTENDED_AREAS`: Fed, ECB,
BoE, BoJ, RBI) moves after BIS's last day are carried on from those series (`extend_series`: the changes only, since BIS
takes the middle of the Fed's range). China stays as BIS records it (1-year LPR). A month still in progress or not yet
reported by every bank is drawn faded and labelled "so far". Episode labels: 2001 recession, 2004–06 tightening,
financial crisis, pandemic, post-pandemic inflation. A problem if fewer than 30 banks reported in 120 days or most
banks' data are over 45 days old. The monthly counts live in the snapshot as `rate_cycle` (lists of numbers written on
one line by `write_snapshot`).

**Calendar:** next 35 days, computed at page load: bank meetings (config), RBI (brief), PBoC LPR, US CPI / jobs / GDP / PCE
(FRED release calendar, stored in the snapshot). Heavy navy rule under its heading; no source footnote on the page.
The scoreboard's column titles are white on navy, the same size as the economy names.

**Bugs fixed on the way (15 Sep 2026):** US CPI YoY read 3.71% instead of 3.35% — FRED has no Oct 2025 CPI or
unemployment (shutdown) and YoY counted 12 rows; now matched by calendar month (`yoy_by_date`). UK CPI
(GBRCPIALLMINMEI) and EZ unemployment on FRED had stopped in 2025/2023 but were shown as current. Table colours were by
sign; now by meaning (`good` per column in `SCOREBOARD_COLUMNS`, applied in `_scoreboard_html`).

### India Dashboard — `generate_india.py`
- **Automatic series** (`india_fetcher.py --append` → `india_macro.db`): bank credit/deposits,
  M3, exports/imports, forex reserves (DBIE workbook), plus RBI's net portfolio investment (`india_fpi_flows`, US$ bn)
- **FPI chart and table:** NSDL net investment (`india_fpi_net_inr_cr`, ₹ crore, entered with `--fpi`) when any
  NSDL figure exists, otherwise RBI's series. `fpi_series()` in `generate_india.py` picks one; they are never mixed
- **NIFTY IT standalone chart:** function retained, but not called by the current dashboard; sector rotation includes IT.
- **Manual series** (`python -m data.india_manual_entry set …`): manufacturing and services PMI,
  GST, core CPI, PLFS unemployment and **FPI** (NSDL, ₹ crore). Headline/food CPI and IIP are official automated series; emergency manual rules are in §0.1
- **CAG fiscal charts (4 since Sep 2026):** GST, expenditure quality (with a capex Budget ÷ 12 line and a
  "capex to date, % of Budget" badge), deficit financing, fiscal deficit % of GDP.
  Tax composition and monthly capex were retired (CGA stopped publishing tax by head; monthly capex repeated the others);
  the fiscal consolidation tracker was replaced by deficit financing on 15 Sep 2026.
  While CGA does not publish the workbook, months typed from its web page go in `data/cag_manual_accounts.csv`
  (year-to-date ₹ crore: revenue expenditure, capex, fiscal deficit required; interest, subsidies optional;
  BE rows with GDP, and a BE fiscal deficit sets the deficit chart's target line). `load_cag_tables()` merges them, the workbook wins on overlap,
  and bad figures stop the run (`tests/test_cag_manual.py`)
- **Deficit financing (`09_india_deficit_financing.png`):** `fin_*` columns in the same CSV, from CGA's "Sources of
  financing the deficit" page (monthly rows and the BE row). Checked to ₹1 crore: external + domestic = fiscal deficit,
  and rows (a)–(i) = domestic total; (h) surplus cash and (i) WMA may be blank. Chart groups: market borrowings,
  small savings (b + e), other domestic (c + d + f), cash (g + h + i), external. The workbook has no financing page,
  so `load_cag_financing()` keeps using these rows even after a workbook supersedes the month's other figures
- **State of the Economy (added 18 Sep 2026):** RBI's monthly article in the Bulletin, read by `generate_soe.py`
  (fetch and parse: `data/rbi_soe.py`; settings: `config/soe_settings.py`; tests: `tests/test_soe.py`, offline, with
  saved editions in `tests/fixtures/soe/`). Two outputs:
  - `soe.json` — the opening summary, the concluding assessment and a month-on-month comparison, all **quoted
    verbatim**, written into the India edition folder and published with its charts, the way `news.json` is on Weekly.
    An edition without one shows no briefing.
  - **What changed since last month:** the first sentence under each of five section headings (Inflation, Aggregate
    Demand, Aggregate Supply, Financial Conditions, Global) beside the same sentence from the previous edition
    (`parse_topics`, `compare_editions`; `TOPIC_SECTIONS` in `config/soe_settings.py`). Sections are used rather than
    the summary for two reasons: the summary is already shown in full above it, and a section's opening sentence
    carries the month's figures in RBI's own words ("inflation increased marginally to 4.45 per cent (y-o-y) in July
    2026 from 4.38 per cent in June"), so no figure is ever parsed out of prose and re-presented on its own.
    Chart pointers ("(Chart III.5a)") are stripped; nothing else in a quoted sentence is touched. A topic missing from
    either month is left out, and a previous edition that cannot be read simply means no comparison. `generate_soe.py`
    fetches the previous edition too, trying two months back before giving up.
  - `data/rbi_transmission.csv` — Table IV.3 (pass-through of policy rate changes to bank deposit and lending rates)
    from every edition, which draws `18_india_rate_transmission.png`. Backfilled to Feb 2025 (16 points in the
    current cycle); `python generate_soe.py --history` reads any editions missing from the file. The chart follows
    whichever cycle is current, easing or tightening, and the title says which; a new cycle with only one month behind
    it leaves the finished cycle up until it has two, because one point is not a path.
  - **Access:** the article's web page on rbi.org.in answers a normal request; the PDF and the Current Statistics
    spreadsheets sit on rbidocs.rbi.org.in, which serves scripts a CAPTCHA, so nothing asks for them. Past editions
    come from the Bulletin page's own month archive (an ASP.NET postback). The article starts in November 2020.
  - **Layout traps** (all seen between 2021 and 2026, all covered by tests): charts and the high-frequency tables
    III.1–III.5 are images, so only four HTML tables can be read; the transmission table has been numbered Table 5,
    Table 4 and Table IV.3, so it is found by caption; its columns are matched by pattern and a renamed or reordered
    column stops the run; the "overall interest rate effect" column only exists from 2025; some editions put the
    cycle's name on one row and its dates on the next; month cells carry footnote marks ("Jul* 2025"); and two
    editions can restate the same month, where the newer figure wins.
  - **Cross-check:** RBI's own repo column is compared with the Sentinel's rate history (`data/rbi_sentinel.db`)
    for every cycle; a disagreement is a problem and fails the run. Both cycles matched on 18 Sep 2026.
- **Workflow:** Saturday 08:00 UTC fetches then regenerates charts; a failed fetch still regenerates
  from the last good database. A push does **not** trigger it — use Actions → Run workflow. The two State of the
  Economy steps are `continue-on-error`: RBI being slow or reshaping its table never stops the charts.
- Monthly routine and source URLs: `docs/project_reminders.md`

### Analysis — `/analysis` (added 21 Sep 2026)
Title "Connecting the Dots" (`config/analysis.py` `TITLE`, `DEK`), no date in its header. Three blocks:
- **Signal or noise** — `signals.json` from the newest weekly edition, written by `generate_signals.py` in
  `weekly.yml`: each of 52 series' weekly move divided by its typical week (root mean square of three years of
  weekly moves), ranked; top 8 as rows with a diverging bar, the rest in a table; method and the week's dates in
  the "How this is measured" popover. An edition without the file shows a one-line note instead.
- **What I'm watching** — threads written by hand in `config/analysis.py` `WATCHING` (theme, why, charts);
  a thread chart is either one of this site's charts by key (always its newest edition) or an image saved in
  `assets/analysis/`. No counts, numbers or "following since" lines in the heads, by the owner's choice.
  `app.py` imports the file lazily (`_analysis_config()`), so a typing slip in it stops this page only, with a note
  naming the line; `tests/test_analysis.py` checks the file (missing images, misspelt fields, dates, links).
- **From the newsletter** — the Substack archive, read when the page opens and kept 3 hours; `PINNED` essays in
  order, led by a new post marked New for `NEW_FOR_DAYS` (30).

### About and the footer
- `/about` ("About & Resources"): every word and list is in `config/resources.py`; the page only renders them.
- The black **footer** on every page (`_footer_html()` in `app.py`, drawn after the page): the wordmark with its
  underline, Sections / The project / Connect link columns and the licence line, all from `config/resources.py`
  `FOOTER_*`. No contact form, by choice: readers write through the Connect column.

---

## 7. Styling (EconStyle)

All styling lives in `charts/style.py`. Never hard-code colours, sizes or DPI elsewhere.

**Every chart has:** `add_top_rule(ax)` · `set_title(ax, title, subtitle)` (18pt bold / 10pt) ·
`add_source(fig, "Source")` (also draws the wordmark credit — script "The" + letter-spaced "ECONOMICS HUB"
with an underline, `draw_credit`; the underline is part of the owner's logo) · saved with
`save_chart(fig, path)` — never `plt.savefig()`.

| Constant | Value |
|---|---|
| Background | `#FFFFFF` |
| Text / rules | `#000000`; muted `#404040` |
| Grid | `#D6D6D6` |
| Positive / negative | `#008000` / `#CC0000` |
| Region colours | US `#003366`, Europe `#008080`, India `#FF9933`, Asia `#800080` (`REGION_COLORS`) |
| Line palette (World line charts) | `LINE_BLUE #1F5596`, `LINE_TEAL #0B8F82`, `LINE_ORANGE #C8620A`, `LINE_RUPEE #EA8412`; validated for colour-blind separation |
| Sizes | wide 9.5×4.8, standard 8.5×4.5, compact 8.5×3.5 |
| DPI | 250 (120 with `--preview`) |

Charts drawn outside a generator (e.g. `rbi_sentinel/research/`) copy the same title block, rule, source line and watermark.

---

## 8. RBI Sentinel

Scores the tone of every RBI Monetary Policy Committee document from Oct 2016 on a
hawkish/dovish scale and tracks it against rate decisions.

### Scoring
- **Documents:** MPC Resolution, Governor's Statement, Minutes (press releases only; Monthly
  Bulletin reprints are classified and never scored)
- **Score:** −1 (very dovish) to +1 (very hawkish). Hybrid: **10% RBI-specific lexicon + 90% Claude Opus 5**
  (`LLM_DEFAULT_MODEL = "claude-opus-5"`, `SCORING_MODEL_VERSION = "hybrid_v2"` — bump the version
  if the method changes, so old scores are kept)
- **Sub-dimensions** (each −1 to +1): inflation concern, growth assessment, liquidity stance,
  rate guidance, external (rupee) stance — explained in the dashboard's methodology expander
- **Meeting composite:** Minutes 50% / Resolution 35% / Governor 15% (`score_normalizer._DOC_WEIGHTS`)
- **Policy cycle:** documents are grouped by the decision date they belong to (`rbi_sentinel/db/migrate_policy_cycle.py`)
- **Facts from text (no model):** `rbi_sentinel/cleaners/policy_facts.py` reads the rate decision, stated stance,
  CPI/GDP projections and next meeting date from the Resolution by regex (verified on all 61 cycles).
  These feed the decision strip, the takeaways and the automatic rate record.

### Charts
| File | Chart |
|---|---|
| `01_rbi_stance_meter.png` | gauge for the latest composite |
| `02_rbi_sentiment_trajectory.png` | tone over time with each rate decision in a strip below |
| `03_rbi_resolution_vs_minutes.png` | Resolution vs Minutes, recent cycles |
| `04_rbi_subdimension_radar.png` | sub-dimensions, current vs previous |
| `05_rbi_rate_and_sentiment.png` | repo rate and tone through the policy cycle |
| `assets/rbi_research/07_rbi_tone_vs_10y.png` | Δ Resolution tone vs decision-day 10-year G-sec move |

Chart 06 (meeting timeline) was merged into chart 02 in Sep 2026. Chart 07 is drawn by
`rbi_sentinel/research/tone_vs_10y_chart.py` from price files in `docs/templates/rbi_sentinel/`; it is not redrawn by the pipeline.

Charts are stamped with a fingerprint of the data they were drawn from (`.data_fingerprint`);
`tests/test_rbi_charts_current.py` fails if the database changed since.

### Automation — `.github/workflows/rbi_sentinel.yml`
| Schedule (IST, weekdays) | What happens |
|---|---|
| 10:45, 11:45, 13:15, 14:45 | Runs **only on MPC decision day**, read from the latest Resolution's "next meeting" sentence. Other days the gate stops it in seconds. |
| 18:15 | Always runs: catches Minutes (published 14 days after the decision), off-cycle meetings, and the 10-year close |

Each run: discover new documents on rbi.org.in → extract text → assign cycles → score new
documents → record the rate decision → live log → redraw charts only if data changed →
commit and push only if something changed.

**Claude spend guards** (`pipeline.py`): a document is sent to Claude only if it is new, belongs to an
MPC cycle, and meets a minimum length (Resolution 500 / Governor 1,000 / Minutes 2,000 words).
An automated run scores at most 4 documents; a larger backlog scores nothing and fails the run.
Normal use: 2 calls on decision day, 1 on Minutes day, 0 otherwise (~$0.15 per meeting).

**Failures:** if discovery finds 0 documents or scoring fails, the run ends red and GitHub emails you.

### Live test (from October 2026)
Historical scores could carry hindsight, because every past meeting predates the model's training.
From Oct 2026 `rbi_sentinel/live_log.py` records each Resolution's tone change and the time it
was scored (committed before the 17:00 G-sec close) in `data/rbi_live_log.csv`. The 10-year close
has no sanctioned automatic source, so the workflow opens a GitHub issue assigned to the owner;
the close is added by hand to `data/rbi_live_market.csv`.

### Research findings (Sep 2026)
- The composite tracks the policy cycle but adds nothing beyond the RBI's stated stance for
  predicting rate decisions; no reliable link to Nifty, Bank Nifty, USD/INR, gold or India VIX.
- Change in Resolution tone lines up with the decision-day 10-year G-sec move (~5 bps per typical
  shift, t ≈ 4). Not yet proven free of hindsight — that is what the live test checks.

### Commands
```bash
python generate_rbi_sentinel.py --auto          # what CI runs
python generate_rbi_sentinel.py                 # incremental, local
python generate_rbi_sentinel.py --charts-only   # redraw from the database, no API
python generate_rbi_sentinel.py --dry-run       # fetch only, no writes, no API
python generate_rbi_sentinel.py --full          # rescore EVERYTHING — costs real money, never needed routinely
python -m rbi_sentinel.seed_rates              # rewrite rate history from its list, then redraw charts if needed
```
Logs: `output/logs/rbi_sentinel.log`.
Test pipeline changes on a copy: `RBI_SENTINEL_DB=/path/to/copy.db python …`

---

## 9. Streamlit app (`app.py`)

- **Masthead** (rebuilt 18 Sep 2026 after the owner called the old one "weak and not distinguishing" — the
  descriptor and the byline were styled alike, so nothing told a first-time reader what the site was). Three
  deliberately unalike levels: nameplate **"GLOBAL MACRO & CROSS-ASSET MONITOR"** (Playfair 900, 2.55rem, uppercase),
  a navy strip between hairlines reading "Research & Maintained by *Shreyas Urgunde*" (`.insti-descriptor`,
  `width: fit-content` so the rules hug the text), then the Substack button and a small "About this site &
  resources" link (a grey "Updated every Saturday" line, `.insti-byline`, was removed on 20 Sep 2026).
  The name links to shreyasxi.github.io in the strip's own colour with a rule that appears on hover
  (`a.insti-author`), so a reader can find out who writes it without the link drawing the eye.
  **Every declaration in these rules needs `!important`:** Streamlit styles `h1` and `p` inside its markdown
  container and beats a bare class selector — that is why the old masthead rendered at 44px/700 and the
  descriptor at Streamlit's default 16px, identical to the byline, whatever the CSS asked for. "The Economics
  Hub" appears in the sidebar nameplate, the chart wordmark, the footer and the browser tab.
  Then the tab row: Weekly Markets · World · India · RBI Sentinel, a hairline, then Analysis
  (`.st-key-ehnav-analysis::before`).
- **Page headers** (`_page_header_html`, one per page; the old date/"Last updated" status bars were removed 16 Sep 2026):
  Weekly "The Week in Markets" (Last updated = the weekly folder's date), World "The World Economy" (Data as of =
  snapshot time), India "The Indian Economy" (Edition = month), RBI "The RBI Sentinel" (Latest MPC meeting),
  Analysis "Connecting the Dots" (no date), About "About & Resources".
- **Fonts:** Inter (UI and body text), Playfair Display (masthead, wordmark caps), Merriweather (sidebar
  nameplate), Newsreader (headlines), Dancing Script (the wordmark's "The"), via Google Fonts
- **Weekly routing** (reorganised 17 Sep 2026): explicit lists in `config/weekly_settings.py` (`WEEKLY_SECTIONS`), keyed by
  filename without the numeric prefix, in page order: Equities, Commodities, Rates Inflation & Credit, Currencies,
  Emerging Markets & India, Cross-Asset Signals, Crypto (each also a jump link in the page header, `.tab-jump`); an unlisted chart shows under "Other". Replaced first-match
  keyword routing, which misfiled copper/gold and gold/SPX (Commodities) and real yields (Fixed Income).
  `tests/test_weekly_sections.py` fails when the latest weekly folder and the lists disagree. Odd sections centre the last chart.
- **World page:** reads `world_snapshot.json` from the latest macro folder; strip, calendar and scoreboard are HTML built in
  app.py (`_central_bank_strip_html`, `_calendar_html`, `_scoreboard_html`). `config.world_settings` is reloaded when the file changes.
- **India page:** header "The Indian Economy". Five sections: Growth & Activity; Equity Markets;
  Inflation & Monetary Conditions; External Sector; Fiscal Policy & Public Finances. `page_india()` explicitly
  pairs PMI/IIP, investment/GVA and main CPI/contributions. The retired money-supply/promoter images are filtered.
- **The Week in Headlines (live from 17 Sep 2026, commit 835c3dd):** the weekly workflow runs `generate_news.py`
  after the charts and copies `news.json` into `assets/weekly/<date>/`, so each edition keeps its own headlines and
  they are pruned with it. The Weekly page reads `news.json` from the same folder as its charts; an edition without
  one shows no strip. Locally: `python generate_news.py` writes into the newest `output/weekly/` edition that has
  charts (never a new folder, which would hide the charts). Feeds and filters: `config/news_settings.py`; logic:
  `data/news.py` (feeds read in parallel); tests: `tests/test_news.py` (offline).
  - Content: RSS headlines from BBC, Guardian, CNBC, FT, Bloomberg (World) and Mint, Business Standard, BusinessLine,
    Indian Express (India), last 7 days. Sorted into themes (central banks, inflation, trade, energy, growth, markets,
    public finances), grouped into stories (TF-IDF with synonyms), one story per theme, ranked by outlet count;
    single-outlet stories only under the first three themes. Up to 5 per column; a column under 3 is left out.
    The user rated the theme-based selection highly.
  - Design (rebuilt the same day after the first, card-style version was judged too basic): editorial, no card, on
    the page's ivory background. Headlines in Newsreader (Google Fonts, added to the app's font import), everything
    else Inter. World = lead story over a 2×2 grid; India = narrower column; hairline rules; rank + theme kicker;
    coverage bars ("4 of 5 outlets", other outlets in the tooltip); lock on FT/Bloomberg (`PAYWALLED_PUBLISHERS`);
    method in a "How these are chosen" `<details>` popover (`HEADLINE_METHOD`). Styles live between
    `News strip: The week in headlines` and `end news strip` in the app's CSS; stacks at 1180px and 680px.
  - "Just out" (official releases on World and India) was built and then removed at the user's request: it crowded
    those tabs, and news belongs in one place.
  - Failure rule (agreed with the user): a failed feed is a warning and is skipped; a thin column is dropped; the
    run never fails.
  - Rejected while building: GDELT (429 on the first call), WSJ/Yahoo/Moneycontrol feeds (stale).
  - **Week-long collection (approved by the user and pushed 17 Sep 2026, commit 2636fcc):**
    `headlines.yml` ("Headline Collector") runs `generate_news.py --collect` every 4 hours. Feed depth measured
    that day: Business Standard markets about 6 h, Mint markets 10 h, Bloomberg 15 h, CNBC news 19 h, so the
    twice-daily plan first proposed would have missed stories. Each read adds choosable headlines (theme match, not
    excluded) to `output/headline_pool/pool.json`, deduplicated by link (latest headline kept), deleting anything
    published over 8 days ago (`POOL_KEEP_DAYS`, cap `POOL_MAX_PER_REGION` 3,000). The pool lives only in the
    GitHub Actions cache: restored by key prefix `headline-pool-`, saved under a new key each run, then the
    previous copy is deleted (`gh cache delete`, `actions: write`); GitHub also evicts entries unused for 7 days.
    Never committed. The user insisted it stays temporary (no month-long storage).
    `weekly.yml` restores the pool before its news step; `build_news` ranks pool + a fresh read. No pool: one read,
    as before. news.json gains `reads` {count, first}; the popover footer says "Collected N times since …".
    Size: about 265 bytes a headline; one read gave 162 headlines, 43 KB (12 KB gzipped); a full week is
    estimated at 0.3–0.4 MB uncompressed. Ranking 3,000 headlines per column takes under a second.
  - Ranking since the pool: outlets → days in the news (distinct publication dates, publisher's time zone) →
    theme priority → headline count → recency; `days` is in news.json and the coverage tooltip. The shown
    headline prefers a plain report over explainers/analysis/newsletters (`HEADLINE_EXPLAINERS`) and titles under
    `MIN_HEADLINE_WORDS` (5), among headlines within 0.1 of the story's most typical one. Also added: number
    words and "time" as story stopwords (a BBC Fed headline had joined an FT BoE column via "three"), "Warsh" →
    "fed" synonym (update when the Fed chair changes), and exclusions for closing reports, session previews and
    sector/group stock chatter, which a week's pool would otherwise rank as long-running stories.
- **Pages, not tabs (live since 18 Sep 2026, commit da2d3a7):** built on branch `multipage`, previewed as a second
  Cloud app pinned to that branch, then fast-forward merged into `main`. That preview route needs no configuration,
  because app.py reads no secrets and requirements.txt, both `.db` files and `assets/` are committed; delete the
  preview app after merging, or it keeps serving the charts of the week the branch was cut. Note for next time:
  Streamlit Cloud serves `main` only, so pushing a branch and rebooting the app changes nothing. The app is
  `st.navigation` with callable
  pages at the foot of app.py. Weekly Markets is `default=True`, so it keeps the root URL and links shared
  before the split still work; the others are /world, /india and /rbi-sentinel, and `st.set_page_config` on a
  non-default page titles the browser tab "World · The Economics Hub". The navigation is `position="hidden"`
  and drawn by hand: a `st.container(key="ehnav", horizontal=True)` of `st.page_link`s where the tab bar was,
  because Streamlit's own sidebar navigation would hide behind the collapsed sidebar and its top navigation
  would sit above the masthead. CSS `.st-key-ehnav` copies the old tab bar (uppercase Inter 0.80rem, navy
  underline on the current page): it must zero Streamlit's negative element margin, or the sideways-scrolling
  row clips that underline. Measured against the old bar: identical label positions (82/229/297/352 px) and
  1px of vertical difference. Each tab body became `page_weekly/world/india/rbi()` unchanged; no tab shared a
  variable with another. Only one page's charts now load per visit, instead of all four.
- **Insights:** `get_insight(filename)` strips the `NN_` prefix (`09_vix_trend.png` → `vix_trend`)
- **Chart widths (20 Sep 2026):** `use_container_width` fits a chart to the page and the layout is `wide`, so on a
  1,500px desktop the RBI charts came out 1,339 × 800 and the Weekly snapshot table 882 × 1,456 — the owner and a
  reader both called them out of proportion. `_render_capped(chart, cap)` puts a chart and its insights toggle in a
  `st.container(key=f"{cap}-{slug}")` and the CSS caps that key: `CAP_WIDE` 940px (2:1 time series), `CAP_SQUARE`
  540px (the radar), `CAP_TABLE` 660px (`_render_summary`, the Weekly snapshot). Used by every RBI chart from
  Sentiment Over Time down. The container needs `width: 100%` as well as `max-width` — with auto margins and an
  auto width a Streamlit block shrink-wraps instead of filling the cap — and the image rule needs `!important`,
  because Streamlit measures the container and writes the pixel width into the image's own `style` attribute.
  No phone rule is needed: `width: 100%` is the smaller of the two below the cap. Grid charts (`_render_grid`,
  two per row) were left alone; on a very wide monitor they still stretch.
- **RBI page:** header, stance meter, source documents with per-document scores, methodology
  expander, decision strip (policy rate, sentiment, RBI projections, next meeting), executive
  summary with six takeaways, then charts 02, 03/04, 05, 07
- **Admin panel:** sidebar pipeline controls appear only when `PIPELINE_KEY` is in local
  `.streamlit/secrets.toml`. Never add it to Streamlit Cloud.
- **Streamlit is pinned to 1.50.0.** Newer versions change the page structure the custom CSS targets.
- **Cloud quirk:** after a push, Cloud pulls the files but keeps the running process, so `app.py` and the
  modules it imported keep their old code. `app.py` re-reads, when their files change, `config.insights`,
  `config.resources`, `config.analysis`, `config.world_settings`, `config.weekly_settings`,
  `config.news_settings`, `config.soe_settings`, `config.signals_settings`, the caption code in
  `charts/loader.py` and the RBI brief (`_fresh_config`, `get_insight`, `_chart_title`). Anything else needs
  Manage app → Reboot.
- **Search and chart links:** the search box under the tabs searches every page's captions
  (`_search_index()`); a result, or a link ending `?chart=<slug>` (the key with hyphens), scrolls to
  `#chart-<slug>` on its page.
- **Hero charts:** the India Economic Snapshot table and the RBI stance meter sit in `CAP_HERO` containers
  (600px, left-aligned) beside their text; `CAP_WIDE` 940px, `CAP_SQUARE` 540px and `CAP_TABLE` 660px cap the
  others (below).
- **Footer and page end:** `st.container(key="ehfoot")` after `current.run()`; Streamlit's 10rem bottom padding
  is removed, and a collapsed sidebar's 2px border is zeroed so pages are centred.

---

## 10. CI, secrets, setup

### Workflows
| Workflow | Schedule (UTC) | Command | Commits |
|---|---|---|---|
| `weekly.yml` ("Weekly Markets Generator") | Sat 06:00 | `generate_weekly.py --mode dashboard`, restores the headline pool, then `generate_news.py` (optional: `continue-on-error`, 8 min limit), then `generate_signals.py` (optional, 10 min limit), keeps the last 4 weeks | `assets/weekly/` (charts + `news.json` + `signals.json`), showcase |
| `headlines.yml` ("Headline Collector") | every 4 h at :41 | `generate_news.py --collect` into the headline pool (Actions cache only; previous copy deleted) | nothing |
| `rates.yml` ("Central Bank Rates") | Mon–Fri 06:30 and 21:00 | `generate_macro.py --rates-only` (strip, policy-rate cells, rate cycle chart into the newest `assets/macro/` edition; writes nothing when no rate changed) | `assets/macro/`, `data/pboc_reverse_repo.csv` |
| `macro.yml` ("World Generator") | Sat 10:00 | `generate_macro.py --mode dashboard` (fails on stale/failed sources), copies PNGs + `world_snapshot.json`, keeps the last 4 months | `assets/macro/`, showcase |
| `india.yml` ("India Dashboard Generator") | Sat 08:00 + manual (`skip_fetch` option) | GVA/IIP tests and updates, RBI transmission, NSE updates, CPI tests/update/bridge, generation, RBI briefing, copy/prune; see §0.1; keeps the last 4 months | `india_macro.db`, `rbi_transmission.csv`, NSE stores, CPI/main/contributions, GVA/IIP archives, `assets/india/` and showcase |
| `rbi_sentinel.yml` | weekdays, see §8 | `generate_rbi_sentinel.py --auto`, keeps the last 4 months of charts | `rbi_sentinel.db`, `assets/rbi_sentinel/`, live log |
| `keep_alive.yml` ("Keep Streamlit App Alive") | 00:00, 10:00, 20:00 | `.github/scripts/keep_alive.py` visits the app so it doesn't hibernate | nothing |

GitHub often starts scheduled runs 1–3 hours late. Scheduled workflows in a public repo are
disabled after 60 days without repository activity; re-enable them on the Actions tab.

**Start a workflow by hand with Actions → the workflow → Run workflow → `main`, never with Re-run.** A
re-run reuses the commit of the original run, so its final `git push` is refused once `main` has moved
on. `weekly.yml`, `macro.yml` and `india.yml` push with a plain `git push`, so two of them started together
can collide the same way (on 21 Sep 2026 World collided with India's push, then failed again on Re-run).
`rbi_sentinel.yml` already pulls with `--rebase` and retries three times; copying that into the other three
was offered on 21 Sep 2026 and the owner declined: start runs one at a time with Run workflow instead.

### Secrets
| Name | Where | Used by |
|---|---|---|
| `FRED_API_KEY` | GitHub Actions secrets, Streamlit Cloud secrets, local `.env` | weekly, World, india |
| `ANTHROPIC_API_KEY` | GitHub Actions secrets, local `.env` | RBI Sentinel scoring |
| `PIPELINE_KEY` | local `.streamlit/secrets.toml` only | shows the admin panel |
| `GITHUB_TOKEN` | automatic | workflow commits, RBI issue |

### Local setup
```bash
cd ~/Documents/economics_hub
source .venv/bin/activate        # Python 3.9 locally; CI uses 3.11
pip install -r requirements.txt
streamlit run app.py
for f in tests/test_*.py; do PYTHONPATH=. python "$f" > /dev/null || echo "FAILED: $f"; done
```
The app reads `assets/` first and falls back to `output/` for local previews.

### Streamlit Cloud
share.streamlit.io → repo `shreyasxi/the-economics-hub`, branch `main`, file `app.py`.
Secrets: `FRED_API_KEY` only.

### README showcase
Six charts at fixed names in `assets/readme_showcase/`, refreshed by the workflows: `weekly_summary_table.png`,
`weekly_crude_curve.png` (weekly), `macro_cape.png`, `macro_oecd_cli.png` (macro), `india_fiscal_deficit_gdp.png`,
`india_expenditure_quality.png` (india).

---

## 11. Known issues

1. **World manual cells.** Manufacturing PMIs (US, euro area, UK, Japan, China), Japan CPI, China unemployment and
   China 10-year have no free API and show "awaiting entry" until keyed in (`data/world_manual_entry.py`). (The old Macro Pulse cron bug — `0 8 8-14 * 6`
   running daily on the 8th–14th — was fixed on 15 Sep 2026 by the weekly Saturday schedule.)
2. **RBI fact-extractor tests** (`policy_facts.py`) are deferred to the Oct 2026 MPC cycle.
3. **21 old RBI documents** have no cached page and no cycle; they are logged as skipped every run. Expected.
4. **`meeting_composites`** stores one row per document date; charts group by policy cycle.
5. **EM FX tickers** (`BRL=X` etc.) can be stale at weekends; weekly change uses 30 days of data.
6. **No chart explanation** for the two summary tables, Weekly "Market Snapshot" and "India Economic Snapshot" (by design).
7. **CAG fiscal data** ends Feb 2026 in the workbook; Mar 2026 (provisional) to Jul 2026 and BE 2026-27 are in
   `data/cag_manual_accounts.csv` (BE from Budget at a Glance via PRS; July FD and total spending match CGA press
   reports). GDP 2026-27 is KPMG's rounded ₹393 lakh crore — replace with the exact Budget at a Glance figure.
   Financing rows (Apr–Jul 2026 and BE 2026-27) are in the same file. Next: Aug 2026 accounts including the
   financing page (end-Sep). FPI from NSDL is loaded through Aug 2026.
8. **India source availability:** MoSPI/NSE endpoints can fail or change schema. Failed optional refreshes
   gate the affected chart and remove stale published artifacts; check source status journals and workflow logs.
   The official main CPI bridge covers Jan 2024 onward. Older legacy DB rows are not canonical CPI history;
   do not use FRED/OECD India CPI or silently extend the chart into those rows.
9. **Second y-axes remain on nine older charts** — Weekly 11 (credit spreads), 14 (copper/gold), 22b (EM stress),
   25 (India VIX), 26 (ETH/BTC), 28 (BTC vs M2); India 07 (expenditure quality), 17 (trade); RBI 05. The owner's
   rule for new and redesigned charts is one axis.
10. **`28_btc_global_m2` plots US M2** (FRED M2SL), not global M2; the file name is wrong, the caption is right.
11. **Unused code:** `chart_macro_em_vulnerability`, `chart_bdti_branded_screenshot` and `chart_hormuz_exposure` in
    `generate_macro.py` are never called. Nine `CHART_INSIGHTS` keys have no chart any more (`agflation_pipeline`,
    `india_credit`, `india_repo_rate`, `labour_market`, `macro_em_vulnerability`, `rbi_governor_divergence`,
    `stablecoin_mcap`, `us_yield_trend`, `wage_growth`). Harmless.
12. **Workflow push collisions** — see §10; the owner prefers starting runs one at a time to a workflow change.
13. **Analysis page "why" lines** in `config/analysis.py` are drafts written for the owner to rewrite.
14. **`make_chart.py` moved from the project root into `charts/`** (owner, 21 Sep 2026; its `PROJECT_ROOT` is now
    `Path(__file__).resolve().parents[1]`, so it still finds the house style and writes to `output/custom/`).
    The move was not yet committed on that day, and the README still lists it at the root.

---

## 12. Rules for anyone (or any model) changing this code

1. Never use mock, placeholder or invented data. If a key or source is missing, the run fails.
2. All visual constants come from `EconStyle`; save with `EconStyle.save_chart`.
3. Every chart: top rule, title + subtitle, source line, watermark.
4. A new weekly/World chart needs a generator function, a `dashboard` **and** `newsletter` title,
   a place in `WEEKLY_SECTIONS` (Weekly) or a file name matching an `app.py` section keyword (World, India; §5.3),
   and a `config/insights.py` entry.
5. A new RBI chart: module in `rbi_sentinel/charts/`, call in `pipeline.run_generate_charts()`,
   section in the RBI tab, insight entry, and update the expected set in `tests/test_rbi_charts_current.py`.
6. Keep `# ── EDIT for each Substack issue ──` markers on newsletter titles.
7. No emoji in print/log output or chart text (the existing ℹ️ expander label is fine).
8. Insight text: objective, analyst tone, plain English; no "we" — it is an individual project.
9. `output/` is never committed; `assets/` is what goes live.
10. Don't change `weekly.yml`, `macro.yml` or `india.yml` without explicit instruction.
11. Never add `PIPELINE_KEY` to Streamlit Cloud.
12. Never add model calls to scheduled RBI runs beyond scoring new documents; test RBI changes
    with `RBI_SENTINEL_DB` pointing at a copy, never the real database.
13. Be precise about claims: say what a chart shows and what it doesn't.
14. Ask the owner before any commit, merge, push or workflow run. Structural changes (layout, navigation,
    workflows) go on a branch, with screenshots at desktop and phone widths before merging.
15. Streamlit is pinned to 1.50.0. Custom CSS in `st.markdown` needs `!important` (Streamlit's own `h1`/`p`
    styles win otherwise), and a `$` in page text must go through `_esc()`.
16. `docs/` stays local: never commit or publish it.
17. Don't try to get past CAPTCHAs or bot walls (rbidocs.rbi.org.in, some publishers): use the pages that
    answer normally, or ask the owner.
18. Keep this file current when something it describes changes, and add a line to §13.

---

## 13. History — what changed and why

Dated notes kept for the reasons behind decisions, roughly newest first. Where they differ from §1–§12,
§1–§12 describe the current state. Section numbers in older notes (e.g. "§4", "§7") refer to this file's
earlier layout: pages were §4, the app §7, CI §8.

**Central bank rates the day they are announced; the global rate cycle** (24 Sep 2026, owner's request; not yet
committed on that day). The owner noticed the BoJ's 18 Sep hike missing from the strip: BoJ and PBoC came from BIS,
which runs about a week behind (the Fed was already current through the FOMC statement). Asked for a script to run by
hand on a phone notification, the owner chose an automatic check instead, wanted every decision shown as soon as it
is announced (not when it takes effect), and switched China from the 1-year LPR to the 7-day reverse repo. Built: the
BoJ statement, ECB and BoE rate tables and PBoC notices as sources on top of the daily series (§6 World, central bank
strip), the sourced PBoC ledger, `rates.yml` with `--rates-only`, and the global rate cycle chart replacing "Where
each economy is heading" (the owner picked it from a list of alternatives: real policy rates, 2-year minus policy rate,
term spreads, supply-chain pressure, world trade, r − g, uncertainty indices).

**Analysis page, footer, smaller hero charts** (21 Sep 2026, owner's request; built on branch `feat/analysis-tab`,
**merged to `main` as 3660491 and pushed on 21 Sep 2026** after a second round of owner edits, below). Background: the owner asked for an "executive summary"
section and feared it going stale; the advice (see memory `analysis-page`) was cadence-free, dated views,
threads by theme, and an automated board that stays fresh without them.
- **Nav:** fifth `st.Page(page_analysis, url_path="analysis")` after RBI Sentinel; a hairline separator drawn by
  `.st-key-ehnav-analysis::before` (inside the link box, so the sideways-scrolling row does not clip it).
- **Page (`page_analysis`)**, header "Connecting the Dots" (config/analysis.py `TITLE`, `DEK`; the owner reworded
  the DEK to "the issues I am following across the markets"). No date in the header — the owner removed "Week to";
  the board's week is in its method popover ("The week to Friday …"). Three blocks with editorial Newsreader headers (`.an-head`, no cards):
  1. **Signal or noise** — reads `signals.json` from the newest weekly edition (`_load_signals`). Each series' week
     move ÷ root mean square of its weekly moves over the past 156 weeks; ranked by |multiple|; "Largest rise/fall
     since" = last earlier week at least as large the same way (10 years of history; ICE BofA spreads on FRED have
     only 3 years). Top 8 as rows with a diverging bar (blue #23609E up / orange #C95F18 down, validated against the
     ivory page for CVD + contrast), the rest in a disclosure table; method in a popover. The lede is counts only
     (n of 52 at ≥2×, on the one-decimal figure shown; and a group holding over half the top 8). Series that fail or
     have not traded (last price >4 days before the Friday) are left out and listed; >25% missing fails the run.
     First run (week to Fri 18 Sep 2026): quiet — USD/KRW +2.3% (2.0×) top; dollar broadly up the week of the Fed's
     16 Sep hike (DXY +1.1%, EUR/USD −1.15%, GBP/USD −1.1%); numbers checked against raw Yahoo closes.
  2. **What I'm watching** — `config/analysis.py WATCHING`: theme, why (my draft for the owner to rewrite), charts (a site chart by
     key via `_dashboard_chart`, searched in weekly/macro/india latest editions, linked with `?chart=<slug>`; or a
     saved image in `assets/analysis/` with source/url/date), links (paywall lock, "My essay" tag). Two samples:
     Iran war beyond oil (crude_oil_curve + EIA Brent chart, public domain), AI capex (market_breadth + Epoch AI
     capex-vs-cash-flow, CC BY 4.0 — screenshot cropped of its toolbar). All links verified 21 Sep 2026.
     **Owner's style rule (21 Sep):** no counters or numbering in this page's heads — the "2 threads" and
     "31 posts since 2021" metas, the "01" thread numerals and "Following since March 2026" were all removed, and the
     `since` field with them. Threads after the first are set apart by a rule (`.wt-head.is-later`).
     **Guard:** config/analysis.py is edited by hand, so app.py does not import it at start-up; `_analysis_config()`
     imports it lazily and a slip in it (SyntaxError, NameError) stops only /analysis with "This page is being
     updated" and the file's line number — every other page keeps working, even after a reboot.
     `tests/test_analysis.py` also rejects unknown field names ("paywal"), and its runner reports a KeyError or a
     bad date as a FAIL instead of stopping. The owner's how-to is in project_reminders.md, "Analysis page".
  3. **From the newsletter** — `_substack_posts` (st.cache_data 3 h; a failed read is cleared, not cached) →
     `shelf()` in `data/substack.py`: PINNED slugs in order, led by the newest post marked New for `NEW_FOR_DAYS` (30), so a
     quiet spell never shows as a gap. **Trap:** the archive API returns fewer rows than asked (23 for limit=50), so
     it is paged by `offset=len(rows)` until a page adds nothing — the first count (29) missed two 2021 posts; there
     are 31. Covers go through `substackcdn.com/image/fetch/w_640,...` (one original is 5,760 px / 2.7 MB).
- **weekly.yml step (added 21 Sep 2026 with the owner's explicit approval):** "Rank the week's unusual moves" runs
  `python generate_signals.py` (no arguments: newest folder in output/weekly/, week to the last Friday) after the
  headlines step, `continue-on-error`, 10-minute timeout, `FRED_API_KEY`; "Copy charts to assets/" copies
  `signals.json` beside news.json or logs that the edition has no board. The first board,
  `assets/weekly/2026-09-20/signals.json`, was committed by hand with the owner's approval so the page was not empty
  until Saturday (a re-run gave an identical file apart from the build time). After a merge, reboot the Cloud app
  (app.py changes do not load on a push); config/analysis.py edits and new images need no reboot.
- **Footer** (every page, after `current.run()`, `st.container(key="ehfoot")`, `_footer_html`, links in
  `config/resources.py FOOTER_*`): black strip (#0B0D12), wordmark (Dancing Script "The" + Playfair caps — Dancing
  Script added to the Google Fonts import), Sections / The project / Connect (LinkedIn, GitHub, Instagram
  the.economics.hub, academic site, mailto the address already public on the RBI page), CC BY-NC 4.0 line (the repo
  LICENSE), "not investment advice", Back to top (`#ehtop` above the masthead, `scroll-margin-top: 8rem`). Full
  bleed by cancelling Streamlit's own gutter: `--eh-gutter` 5rem at ≥864px (46rem content + 2×4rem), 1rem below.
  `stMainBlockContainer` padding-bottom 10rem → 0 (that empty band was why pages "ended abruptly").
  **Trap fixed:** the collapsed sidebar keeps its 2px border in the flex row (translated off-screen but 2px wide),
  so every page sat 2px right of centre; `[data-testid="stSidebar"][aria-expanded="false"]` border → 0.
  No contact form, by the owner's choice (21 Sep): the Connect column is enough.
  **The underline is part of the logo** (owner, 21 Sep): `a.ehf-mark::after` draws a 1.5px rule the full width of
  the mark, ~0.6em below the caps baseline, as the chart credit's `WATERMARK_RULE = "under"` does; `.ehf-name` takes
  back its last 0.22em of letter-spacing (`margin-right`) so the rule ends at the B.
- **Sidebar:** the "CC BY-NC 4.0 · Not Investment Advice" line and the two rules above it were removed (21 Sep,
  owner) — the footer carries the licence now. Readers' sidebar ends at the three buttons; the admin-only Pipeline
  Control keeps its own rule. `.sb-rule-thin` went with it.
- **World and India charts without the underline:** they were drawn on 19 Sep, before the underlined wordmark
  (cb95cf8, 20 Sep). No code change is needed — the Saturday runs (india 08:00, macro 10:00 UTC) redraw them, or
  Actions → Run workflow on `main`.
- **Hero charts:** India snapshot table and RBI stance meter (+ its source documents) in `CAP_HERO` containers
  (`max-width: 600px`, left-aligned) and their rows changed from `[1.2, 1]` to `[1, 1]`: ~665 → 600 px wide at 1440.
- **Screenshots:** headless Firefox cannot go below a 500px window; phone views were taken inside a 390px iframe
  (a throwaway script), which lays out exactly as a phone does.

**Weekly — Equities** (added 18 Sep 2026, owner's request): `10a_sector_rotation_12m` sits beside the weekly
`10_sector_rotation`, ranking the same 11 SPDR sector ETFs by trailing-12-month return, so the week's move can be read
against the year's trend (this week Healthcare and Technology led while Energy fell 0.7%; over the year Energy leads at
+48%). Both charts share one `SECTOR_ETFS` dict, so they can never cover different sectors. **These are total returns**,
because `yf.Ticker.history()` adjusts closes for dividends by default — at a 12-month horizon that is not cosmetic:
Utilities read +1.5% adjusted against −1.2% on price alone, which moves it several places up the ranking. The chart,
its source line and its insight all say "total return". Equities now holds 7 charts, so the last one is centred.

**About, wordmark and captions — third pass** (20 Sep 2026, owner's three follow-ups; branch
`feat/long-history-charts`, **merged to `main` as 72e10fc and pushed**):
- **`/about` reworked** after the owner saw the sample. Removed: the standfirst, the "Last reviewed" meta in the
  header, the suggest-and-reviewed footer, the whole "Worth reading" section (kept in `config/resources.py`, not
  rendered — it is meant to come back) and "Updated every Saturday" from the masthead (`.insti-byline` deleted; the
  gap it held is now `.substack-center-container`'s top margin). The chart search box is hidden on this page only
  (`if current.url_path != ABOUT_PAGE.url_path`). "Data I rely on" became **"Data and where to find it"** with a lede
  explaining the `used here` tag: the list now serves researchers as well as crediting sources, so it carries portals
  this site does not touch (ALFRED, IMF, World Bank, ECB, Ken French, Cboe, EIA, SEC EDGAR, Union Budget, data.gov.in,
  PRS, EPWRF, JST Macrohistory, Penn World Table, Maddison, Our World in Data) in four groups. `used` flags were
  corrected against the generators' own `add_source` strings — Damodaran, Shiller, MoSPI, BIS, Eurostat and DGCI&S are
  all used and were marked otherwise. Every URL was checked (FRED/IMF/NSE/RBI refuse a bot but are correct).
  **Body text moved off Newsreader onto Inter** at 1rem/#24282F: the owner has objected to thin body type repeatedly
  and the serif was lighter on the stem than the site's own prose. `Data Architecture` moved out of the sidebar into
  "How it is built" as `resources.ARCHITECTURE` (`.about-arch-*`); the sidebar's `.sb-arch-*` CSS was deleted with it.
- **Chart credit is now a wordmark**, the owner having rejected the caps-only version as not modern: script "The"
  (Dancing Script, +2.5pt) on one baseline with letter-spaced "ECONOMICS HUB". Drawn by `EconStyle.draw_credit`, which
  packs the two parts with `HPacker`/`AnchoredOffsetbox` rather than placing them by hand — the script word's width
  depends on the face, and measuring it would have to happen after layout but before save. Nine treatments were
  rendered at real size first (temporary renders, not kept).
  **Trap found and fixed:** `MASTHEAD_FONTS` began with Cambria and Palatino, which exist on neither this machine nor
  the runner, so the credit resolved to **Georgia locally and DejaVu Serif in Actions** — two different wordmarks on
  one site. Both faces are now committed to `assets/fonts/` (with their OFL licences) and registered on import by
  `_register_bundled_fonts()`. The caps are Playfair Display, the site's own masthead face. Keep a font with **U+2009**
  last in the list: the tracking is built from thin spaces, Matplotlib falls back family-by-family for a missing glyph,
  and Georgia, Lora and Libre Baskerville all render that glyph as tofu when they are the only family named.
  Four places draw the credit — `add_source`, `summary_table.py`, and **two in `generate_india.py`** (the snapshot table
  at ~line 1187 and the fiscal-deficit chart at ~line 2142, both of which had kept the old 10–13pt near-black version
  and would have printed a bare "Economics Hub" once `WATERMARK_TEXT` lost its article). India charts pick this up on
  their next run; the committed PNGs still carry the old credit.
- **Captions** now come from a rebuilt `clean_title()` (`charts/loader.py`): an `_ACRONYMS` map so indicators keep their
  capitals (GDP, BTC, NIFTY, MVRV, MoSPI) and a `_TITLE_OVERRIDES` map for names a filename cannot give — ratios that
  need a slash, and the World page's `macro_` files. Overrides are shortened from the generators' own title dicts, so
  `btc_global_m2` reads "Bitcoin vs US M2": **the chart plots US M2 (M2SL), not global — the filename is wrong.**
  `_SEARCH_ACRONYMS` and `_search_title` in app.py were deleted; search and captions are now the same string.
  **Why the owner saw title case at all:** the caption CSS targeted `[data-testid="caption"]`, which Streamlit renamed
  to `stImageCaption`, so every caption had silently fallen back to Streamlit's 14px near-black serif. The selector is
  fixed and the captions are deliberately **not** upper-cased — capitals only read as acronyms in mixed-case text.
- `.about-grid` is four columns at desktop width (`minmax(250px, 1fr)`) so no group is orphaned on a row of its own.
- **Publishing, two traps.** First: merging to `main` is not enough to change a chart. `output/` is git-ignored and the
  app serves `assets/weekly/`, which only `weekly.yml` writes (regenerate → copy → commit → push). Merge first, then
  dispatch the workflow **on main**, or it regenerates with the old code. On 20 Sep the charts were published by hand
  instead — the same steps the workflow takes, including `generate_news.py` against the local headline pool and
  `prune_assets.py weekly` — so the site could be reviewed before Saturday.
  Second, and the one that cost an hour: **a push does not restart the Cloud app.** Files are pulled, the process is
  not replaced. So chart PNGs update (read from disk at run time) and config modules behind `_fresh_config` update,
  while `app.py` and everything it imports keep running the code they started with. The symptom is new charts under
  old captions and new copy in an old layout. `_chart_title()` now reads `charts.loader` through the same mtime-guarded
  reload, but the running process still had to be rebooted once (Manage app → Reboot) to pick that up.

**Weekly — second pass on the same branch** (20 Sep 2026, owner's five suggestions; branch `feat/long-history-charts`):
- `27_btc_gold_ratio` **rebuilt**: was two years of BTC/gold against a 52-week mean, which the owner called useless.
  Now "Bitcoin Priced in Gold": ounces of gold per bitcoin, weekly (`W-FRI`) since 2015, log scale, parity line, turns
  from `_turning_points(oz, 0.9)`. Bitcoin's price comes from Coin Metrics (Yahoo's BTC-USD only starts Sep 2014); the
  fetch is shared with chart 29 through `btc_cm`. Numbers: 0.27 oz in Jan 2015, parity crossed for good Apr 2017, highs
  14 (Dec 2017), 35 (Oct 2021) and 38 (Jan 2025), lows 2.6 (Dec 2018) and 9.1 (Jan 2023), now 18.3, i.e. 52% below the
  peak. **The point: two peaks four years apart are 9% apart**, and gold is +20% over a year while bitcoin is −31%.
  Start year 2015, not 2010: the full series is a 267,000x rise that flattens everything after it.
- `19b_commodities_vs_equities` gained NBER recession bands (`_recession_bands`, FRED `USREC`, read from the series so a
  future recession draws itself). **Trap:** an `axvspan` widens the axes, so bands drawn before the limits were set
  pulled the x axis back to 1970; the helper must be called last and restores the x limits it found.
- **Chart credit restyled** (`EconStyle.WATERMARK_*`): was 11pt bold serif in near-black, three points larger than the
  source line, so on a page of 40 charts the byline out-shouted the data. Now 7.5pt letter-spaced serif caps in #6B7280
  on the source line's baseline (matplotlib has no tracking, so `_watermark_label()` joins the letters with thin
  spaces). Alternatives were rendered for the owner (temporary, not kept); switching is two constants.
- `_render_grid` now opens one `st.columns` per **row** instead of one per section. Streamlit stacks each column
  independently, so a tall chart used to push everything below it in its column out of line with the next column.
- **New `/about` page** (`page_about`, registered in `st.navigation` but kept out of the four-tab row; reached from a
  centred small-caps link under the Substack button, `.st-key-ehabout`). All copy and both lists live in
  `config/resources.py`; the page only renders them. Sample content only — awaiting the owner's edits.

**Weekly — long-history charts** (19 Sep 2026, owner's request; branch `feat/long-history-charts`). Background
numbers were run first and the owner picked from a list:
- `23d_commodity_cycle` — S&P GSCI deflated by US CPI (CPIAUCSL), monthly averages, since 1984, average = 100, with
  highs and lows marked by `_turning_points` (a log swing of 0.45). `^SPGSCI` is the **spot** index: it kept 84% of
  its Jul 2008 level while GSG (futures total return) kept 48%. A month appears only once its CPI is out.
- `19b_commodities_vs_equities` (Cross-Asset Signals, owner's placement) — GSCI ÷ S&P 500, month-end, Jan 1984 = 100,
  log scale; the note ("lower than in N% of months") is computed. The ratio drifts down structurally (earnings
  compound, commodities track inflation), so the insight says it is context, not timing. Its 2008/2022 highs and 2020
  low came a month before US CPI inflation peaked/bottomed; the 1999 low did not line up (CPI bottomed Mar 1998).
- `23c_commodities_breadth` extended to 2008 (Brent's Yahoo history starts Jul 2007). Gold and oil were **not**
  overlaid (owner agreed): since 2008 breadth has ~0 correlation (−0.10 to +0.06) with the next 3/6/12 months of the
  basket, gold or Brent, and the old insight's "mean-revert from extremes" line was removed. Per-member 200-day
  status with `ffill(limit=5)`: Yahoo's PL=F has 60-day holes in 2007–09, and on those days the share is of the 12
  that traded (never fewer). 18 years of a 13-member daily share is a smear, so the heavy line is a 63-day average and
  the daily reading is drawn faintly; captions have their own bands above 100 and below 0.
- `15_stock_bond_correlation` now from 2002 (TLT's launch), one reading a week on the line, 2021+ shaded; shares of
  days above zero are counted on daily readings: 13% in 2002–20 vs 62% since 2021.
- `10c_india_sector_rotation_12m` — NSE `allIndices` carries `oneYearAgoVal`/`date365dAgo`, so no backfill was needed;
  `fetch_nifty_sector_changes` (renamed from `fetch_nifty_sector_weekly`) returns week and year changes from one
  snapshot shared by both NIFTY charts. **Price return** (NSE sector indices exclude dividends) — the subtitle says
  "not total return". EM & India was reordered so the two NIFTY charts pair like the S&P ones. NSE works from GitHub
  Actions (the 19 Sep weekly run drew `10b`).
- `29_btc_mvrv` — `data/fetchers/coinmetrics_fetcher.py`, Coin Metrics community API (`CapMVRVCur`, `PriceUSD`; free,
  no key; `CapRealUSD`, `NVTAdj`, `SplyAct1yr` are paid — 403). Glassnode's API/CLI needs the ~$999/month plan, so it
  was not used. Starts 2011: Jul–Dec 2010 reads up to 146. **The "MVRV > 3.5 = top" rule broke:** cycle peaks fell
  7.7 (2011) → 5.9 (2013) → 4.7 (2017) → 4.0 (Feb 2021) → 2.8 (Mar 2024); the Nov 2021 and Oct 2025 price tops came
  at 2.85 and 2.29. The chart dates the last reading above 3.5 and labels every high MVRV later more than halved from.
- Sidebar Data Architecture: Weekly row now "Yahoo Finance · NSE · FRED · Coin Metrics" (FRED had been missing).

**Weekly — Cross-Asset Risk & Breadth** (changed 16 Sep 2026): the SPY/TLT ratio was cut. It only ever rose (6.0 to
9.5 over two years) because TLT is driven by long rates, so the ratio climbed whenever yields rose — even during an
equity selloff — which made it a risk gauge that never signalled risk-off, and it duplicated SPHB/SPLV. Replaced by
`15_stock_bond_correlation` (60-day rolling correlation of SPY and TLT daily returns, three years, shaded either side of
zero: below zero bonds hedge equities, above zero they fall together — the 60/40 question, and nothing else on the
dashboard answers it) and `15b_defensives_cyclicals` (XLP+XLU+XLV against XLY+XLK+XLI, both baskets rebased to 100 two
years ago, with a 26-week mean). The section is now correlation, defensives/cyclicals, SPHB/SPLV, RSP/SPY breadth; the
owner also flagged `23_brent_wti_spread` as near-useless (Brent is structurally above WTI; the spread sits in a $2–5
band).

**Weekly — Commodities** (changed 16 Sep 2026): `23_brent_wti_spread` cut for the reason above and replaced by three
charts the owner picked from a list of ten.
- `23_crude_oil_curve` — the WTI futures curve. The ladder is built by walking forward from the current month over
  Yahoo tickers `CL<month-code><yy>.NYM` (month codes `FGHJKMNQUVXZ`), keeping every contract that still returns data
  and stopping at 15. The nearest month is usually already expired (the front contract expires mid-month), so the
  fetcher's "no data" warning is swallowed inside the probe loop and one summary line is logged instead. Today's curve
  and the same contracts a month ago; the band between the curve and a flat line at the front-month price is shaded, so
  the backwardation/contango gap is drawn rather than left for the reader to subtract. The verdict label is anchored
  inside that band in data coordinates, so it follows the band if the curve flips into contango.
- `23b_gold_real_rates` — gold against the 10-year TIPS real yield as a **path**, one step per quarter over ten years,
  split at Jan 2022 and coloured blue (correlation −0.95) and maroon (+0.49). Single pair of axes, so it honours the
  no-dual-axis rule; quarterly rather than monthly because real yields have been range-bound since 2023 while gold
  doubled, which piles monthly points up as horizontal noise on a near-vertical path. Points are labelled by quarter so
  the last one is not misread as a spot price (Q3 2026 averages $4,298 against ~$4,390 spot).
- `23c_commodities_breadth` — share of 13 energy, metal and agricultural futures above their own 200-day average.
  **Gotcha found and fixed here:** `price > rolling(200).mean()` evaluates to `False`, not `NaN`, during the warm-up, so
  comparing first and calling `.dropna()` afterwards published eleven months of a fabricated 0% reading. The average is
  now dropped to its valid index *before* the comparison, and four years of prices are fetched to show three years of
  breadth. (Superseded 19 Sep 2026: now since 2008 with a per-member mask — see below.)

All three are named to match the existing `commo_kws` in app.py (`oil`, `gold`, `commodities`), so they route into the
Commodities section without an app.py change; "Other" is empty again.

**Stale charts on localhost** (fixed 16 Sep 2026): `charts/loader.py` serves the newest dated folder across *both*
`assets/` and `output/`, and `generate_weekly.py` wrote into an existing same-day folder without clearing it. A chart
deleted from the code therefore kept appearing on the dashboard — drifting into the "Other" section once its filename
stopped matching any section's keywords — which is how the owner was still seeing SPY/TLT after it was removed.
`get_output_dir()` now unlinks the folder's PNGs before a run. Local `output/` folders outrank `assets/`, so localhost
shows the newest local run while Streamlit Cloud (no `output/`) shows the newest committed edition.

*Last updated 2026-09-21 by Claude Opus 5 — Sixteenth pass: reorganised for readers without the code: a
"read this first" section (§0), a chart-by-chart index with each chart's function and data (§4), step-by-step
recipes for changing charts, captions, sections and data points and for publishing (§5), current-state notes
for Analysis, About and the footer (§6, §9), known issues added (§11), rules added (§12); corrected four pages
to five, "a push redeploys" to what a push does and does not update, the masthead description, the README
showcase list, and recorded `make_chart.py`'s move to `charts/` with its path fix (§11). The same day: the Analysis page, footer and smaller hero
charts were merged (3660491), the licence line left the sidebar, and the World run's push failures were
traced to re-running an old run while India pushed (§10). Fifteenth pass: the About page reworked to the owner's eight points and its
body type moved onto Inter; Data Architecture moved out of the sidebar; the chart credit rebuilt as a script-and-caps
wordmark with both faces committed to `assets/fonts/` (local and CI had been drawing different credits); chart captions
rebuilt from an acronym and override map after finding Streamlit had renamed the caption testid; branch
`feat/long-history-charts` merged to `main` (§4). Fourteenth pass: four long-history Weekly charts (commodity cycle,
commodities vs equities, NIFTY 12-month rotation, BTC MVRV via Coin Metrics); breadth and stock-bond correlation
extended to 2008 and 2002 (§4). Twelfth pass: masthead rebuilt around three unalike levels
(§7) and the sidebar coverage line rewritten; `local/` moved to `docs/templates/rbi_sentinel/` and its
`.git/info/exclude` entry removed; the Obsidian vault `economics_hub_vault_v2` (9.1 MB) deleted, its seven
notes kept in `docs/vault_archive/` (since removed); a trailing-12-month S&P sector chart added beside the weekly one; a
research write-up for RBI Sentinel was drafted as `RBI_SENTINEL.md`, then deleted at the owner's request in
favour of the website page at shreyasxi.github.io/economics-hub (which the README now links to — do not
restore the file without repointing that link). That website page was rewritten the same day: it had claimed
the Sentinel "captures one of the most consistently mispriced signals in emerging market fixed income" and
that tone "tends to precede actual rate moves", which its own research contradicts, and it still named Claude
Haiku, 30 meetings, seven sub-dimensions and a 0.25/0.75 fusion. Eleventh pass: the four sections became four pages with their own URLs
(§7), built on a branch, previewed as a second Cloud app pinned to that branch, then merged into `main`; Streamlit
Cloud serves `main` only, so pushing a branch and rebooting the live app changes nothing. Tenth pass (17 Sep): The
Week in Headlines is collected through the week — `headlines.yml` runs `generate_news.py --collect` every 4 hours
into a pool held in the GitHub Actions cache (8 days, never committed), `weekly.yml` restores it before ranking, and
selection gained "days in the news", a plain-report-over-explainer preference and exclusions for closing reports and
stock chatter (§7, §8). Ninth pass: Weekly Commodities rebuilt (Brent–WTI out; crude futures curve,
gold-vs-real-rates path and commodity breadth in), and the generator now clears its output folder so deleted charts stop
reappearing under "Other". Eighth pass: EM dollar chart extended to the extreme movers. Seventh pass: OECD CLI redrawn as a ranked chart of all 17 countries; regional ERP redrawn as a strip plot and ratings-vs-markets as a diverging gap chart (owner tired of dumbbells, wanted the chart to do the talking); a World Bank "Long View" section was built and then removed the same day at the owner's request ("they just don't make sense in my project" — annual data on a markets dashboard would confuse readers; do not rebuild it without being asked); Weekly and World standfirsts rewritten; chart-insight expanders restyled (no icon, hairline rule, larger body text) — note that `.main`-scoped CSS has done nothing since the Streamlit 1.50 upgrade, so the chart-card shadow and the top-padding rule are dead and were left alone. Sixth pass: Country Risk section (Damodaran country and regional equity
risk premiums, ratings vs markets). Fifth pass: tab header for Weekly and date bars removed from all tabs;
US summary table retired (macro.yml showcase now copies the CAPE chart); India table renamed "India Economic Snapshot";
claims and excess CAPE yield panels in maroon (`EconStyle.LINE_MAROON`). World tab fourth pass: OECD CLI as small multiples, Sahm chart dropped,
US Equity Valuations section added (Shiller CAPE and excess CAPE yield, Damodaran implied ERP). Third pass (15 Sep): Weekly-weight lines and labels on inflation and EM
charts, labour chart renamed with payrolls badge, Brent in rupees removed. Second pass: inflation and labour charts
redesigned (smooth monotone lines, two-panel labour chart), China chart removed, Emerging Markets section added (EM
yields, dollar vs EM and the rupee), strip/calendar/scoreboard polish. Before that: Macro Pulse rebuilt as the World tab (central bank strip, scoreboard,
regime chart, calendar; overlapping and low-signal charts retired; CPI gap and table colour bugs fixed; weekly schedule);
India tab renamed "The Indian Economy". Earlier the same day: merged instructions.md; folder reorganisation; 4-edition
limit; mock data removed; monthly FPI from DBIE; NIFTY IT moved to India; RBI rate rows normalised.*
