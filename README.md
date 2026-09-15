# Automated Macro Dashboard & RBI Sentiment Tracker

An automated Python pipeline tracking Global Equities, Forex, Sovereign Bonds, Commodities, and Indian Markets — published via [The Economics Hub on Substack](https://economicshub.substack.com/).

<p align="center">
  <a href="https://weekly-macro-dashboard.streamlit.app/">
    <img src="https://img.shields.io/badge/Launch%20Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Launch Dashboard">
  </a>
</p>

---

## Sample Charts

| **Market Snapshot** | **Macro Pulse** |
|:---:|:---:|
| <img src="assets/readme_showcase/weekly_summary_table.png" width="100%"> | <img src="assets/readme_showcase/macro_table.png" width="100%"> |
| **Sectoral Rotations** | **Fiscal Deficit** |
| <img src="assets/readme_showcase/weekly_sector_rotation.png" width="100%"> | <img src="assets/readme_showcase/india_fiscal_deficit_gdp.png" width="100%"> |
| **Expenditure Quality** | **US Housing Market** |
| <img src="assets/readme_showcase/india_expenditure_quality.png" width="100%"> | <img src="assets/readme_showcase/macro_housing.png" width="100%"> |

*Charts update automatically after each pipeline run — images always reflect the latest data.*

---

## Reproducibility Guide

### Prerequisites

Python 3.9+ and a free FRED API key from [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html).

### Installation

```bash
git clone https://github.com/shreyasxi/the-economics-hub.git
cd the-economics-hub
pip install -r requirements.txt
```

### API Key Configuration

**Windows (PowerShell — permanent):**
```powershell
[System.Environment]::SetEnvironmentVariable("FRED_API_KEY", "your_key_here", "User")
# Restart terminal to take effect
```

**macOS / Linux:**
```bash
echo 'export FRED_API_KEY="your_key_here"' >> ~/.bashrc
source ~/.bashrc
```

---

## Project Structure

```
economics_hub/
├── app.py                       # Streamlit 4-tab dashboard
├── generate_weekly.py           # Weekly global dashboard (~32 charts, every Saturday via CI)
├── generate_macro.py            # Monthly macro pulse (9–11 charts, via CI)
├── generate_india.py            # India macro dashboard (14 charts, Saturdays via CI + manual)
├── generate_rbi_sentinel.py     # RBI MPC sentiment pipeline (automated via CI)
├── make_chart.py                # CLI tool for ad-hoc charts from any CSV
│
├── charts/
│   ├── style.py                 # EconStyle — all visual constants and chart methods
│   ├── loader.py                # Finds the latest published charts for the dashboard
│   └── templates/               # Reusable chart template classes
├── config/
│   ├── settings.py              # Weekly indicators (Yahoo Finance + FRED tickers)
│   ├── macro_settings.py        # Monthly macro indicators (FRED + manual data)
│   └── insights.py              # Chart explanations shown under each chart
├── data/
│   ├── fetchers/                # yfinance, FRED and India data fetchers
│   ├── india_manual_entry.py    # CLI for monthly India figures (PMI, GST, CPI, IIP)
│   ├── india_macro.db           # India SQLite database
│   ├── cag_monthly_accounts.xlsx # India CAG fiscal data
│   └── rbi_sentinel.db          # RBI MPC documents, scores and rate decisions
├── rbi_sentinel/                # RBI Sentinel package (fetch, score, charts)
│   ├── research/                # Research charts drawn outside the pipeline
│   └── seed_rates.py            # Repo-rate history corrections
├── tests/
├── assets/                      # Git-tracked PNGs served by Streamlit Cloud
│   ├── weekly/YYYY-MM-DD/       # Newest 4 editions kept (monthly folders too)
│   ├── macro/YYYY-MM/
│   ├── india/YYYY-MM/
│   ├── rbi_sentinel/YYYY-MM/
│   ├── rbi_research/
│   ├── brand/                   # Logo
│   └── readme_showcase/         # Static-named flagship charts (always current)
├── output/                      # Local generation output (git-ignored)
└── .github/                     # GitHub Actions workflows and helper scripts
```

---

## Usage

### 1. Weekly Global Dashboard
Generates ~32 charts (Equities, Commodities, Yields, FX, Cross-Asset, Crypto) — runs automatically every Saturday via GitHub Actions.
```bash
python generate_weekly.py
```

### 2. Macro Pulse
Generates 9–11 monthly macro charts — runs automatically on the 2nd Saturday via GitHub Actions.
```bash
python generate_macro.py
```

### 3. India Macro Dashboard
Generates 14 India-specific charts (FPI, NIFTY IT, GST, Fiscal, Credit, Trade) — runs every Saturday via GitHub Actions. Monthly figures without an API (PMI, GST, CPI, IIP) are entered with the manual-entry CLI.
```bash
python -m data.india_manual_entry status
python generate_india.py
```

### 4. Reserve Bank of India Policy Related Charts
Scores the tone of RBI Monetary Policy Committee documents and charts it against rate decisions — runs automatically via GitHub Actions (needs an `ANTHROPIC_API_KEY`).
```bash
python generate_rbi_sentinel.py
```

### 5. Ad-Hoc Chart Tool
Quickly generate a styled chart from any CSV without modifying the codebase.
```bash
python make_chart.py
```

---

## Data Sources

| Source | Type | Access | Used by |
|--------|------|--------|---------|
| Yahoo Finance | Equities, FX, commodities, ETFs, VIX, NIFTY IT | Free, no key | `generate_weekly.py`, `generate_india.py` |
| FRED | US yields, CPI, PCE, unemployment, M2, NFCI, credit spreads | Free API key | `generate_weekly.py`, `generate_macro.py` |
| RBI DBIE workbook | India credit, M3, FPI flows, forex reserves, trade | Free, refreshed monthly | `generate_india.py` |
| Manual entry + CAG workbook | India PMI, GST, CPI, IIP, FPI (NSDL); CAG fiscal accounts | Hand-entered monthly | `generate_india.py` |
| rbi.org.in | RBI MPC documents (HTML, cached locally) | Free | `generate_rbi_sentinel.py` |

---

## License

Licensed under **CC BY-NC 4.0** — free for personal and research use with credit to **The Economics Hub**.  
See the [LICENSE](LICENSE) file for details.
