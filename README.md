# The Economics Hub — Weekly Dashboard System

An automated Python pipeline that generates key macroeconomic charts and tables; tracking Global Equities, Forex, Sovereign Bonds, Commodities, and Indian Market nuances for [The Economics Hub](https://economicshub.substack.com/) Substack newsletter.

---

## 🚀 Quick Start

```bash
# 1. Clone/download this project
# 2. Install dependencies
pip install -r requirements.txt

# 3. Get your free FRED API key
#    → https://fred.stlouisfed.org/docs/api/api_key.html
#    → Edit config/settings.py and paste your key

# 4. Generate dashboard with mock data (test first!)
python generate_weekly.py --mock

# 5. Generate with live data
python generate_weekly.py
```

Output appears in `output/weekly/YYYY-MM-DD/`.

---

## 📁 Project Structure

```
economics_hub/
│
├── generate_weekly.py          ← MAIN SCRIPT: run this every week
├── requirements.txt
│
├── config/
│   └── settings.py             ← All indicator definitions & API keys
│
├── style/
│   └── economics_hub_style.py  ← Visual identity (colours, fonts, layouts)
│
├── data/
│   ├── mock_data.py            ← Mock data for testing
│   ├── cache/                  ← Cached API responses
│   └── fetchers/
│       ├── yfinance_fetcher.py ← Equities, FX, commodities
│       └── fred_fetcher.py     ← US yields, credit spreads, macro
│
├── charts/
│   ├── templates/              ← Reusable chart components
│   │   ├── weekly_bar.py       ← Horizontal bar (weekly % changes)
│   │   ├── trend_line.py       ← 12-month trend with area fill
│   │   ├── yield_curve.py      ← Yield curve overlay comparison
│   │   └── summary_table.py    ← Compact data table
│   ├── generators/             ← Category-specific chart generators
│   └── bank/                   ← Chart bank (all saved outputs)
│       └── 2026/
│
├── output/
│   ├── weekly/                 ← Generated dashboards by date
│   │   └── 2026-02-07/
│   │       ├── 00_summary_table.png
│   │       ├── 01_equities_weekly.png
│   │       ├── 02_equities_trend.png
│   │       ├── ...
│   │       └── newsletter.md
│   └── templates/
│
└── notebooks/                  ← Exploration & data checks
```

---

## 📊 What Gets Generated Each Week

| # | Chart | Type | Description |
|---|-------|------|-------------|
| 00 | Market Snapshot | Summary Table | All indicators with level, 1W change, YTD |
| 01 | Global Equities | Weekly Bar | S&P 500, FTSE 100, Euro Stoxx 50, Nifty 50, Nikkei, Shanghai |
| 02 | Equities Trend | Line (indexed) | 12-month trailing, normalised to 100 |
| 03 | Foreign Exchange | Weekly Bar | DXY, EUR/USD, GBP/USD, USD/INR, USD/JPY, USD/CHF |
| 04 | FX Trend | Line (indexed) | 12-month trailing, normalised to 100 |
| 05 | Bond Yields | Weekly Bar | US 2Y/10Y/30Y, German 10Y, UK Gilt, India 10Y |
| 06 | Yield Curve | Curve overlay | Current vs 4 weeks vs 52 weeks ago |
| 06b | Yields Trend | Multi-line | 10Y yields: US, UK, Germany, India |
| 07 | Commodities | Weekly Bar | Brent, WTI, Gold, Silver, Copper, Natural Gas |
| 08 | Commodities Trend | Line (indexed) | 12-month trailing, normalised to 100 |

---

## 🎨 Visual Design System

The style library (`style/economics_hub_style.py`) ensures every chart has:

- **Poppins** font family (modern, professional)
- **Consistent colour palette**: Navy (US), Teal (Europe), Amber (India), Purple (Asia)
- **Green/Red** for positive/negative changes
- **FT-style layout**: no top/right spines, horizontal gridlines only, clean titles
- **Automatic watermark** and source attribution
- **200 DPI** output for Substack

### Colour Palette

| Role | Hex | Use |
|------|-----|-----|
| US | `#16365C` | S&P 500, DXY, US yields |
| Europe | `#0E918C` | FTSE, Euro Stoxx, EUR, GBP |
| India | `#E8913A` | Nifty, INR, India 10Y |
| Asia | `#7C3AED` | Nikkei, Shanghai, JPY |
| Positive | `#059669` | Green bars (gains) |
| Negative | `#DC2626` | Red bars (losses) |

---

## 🔧 Adding New Indicators

1. Add the indicator definition in `config/settings.py` → `INDICATORS` dict
2. Add it to the relevant section in `DASHBOARD_SECTIONS`
3. The chart templates will pick it up automatically

---

## 📝 Weekly Workflow

1. **Friday evening**: Run `python generate_weekly.py`
2. **Review**: Open `output/weekly/YYYY-MM-DD/` and check charts
3. **Write**: Open `newsletter.md`, fill in one-liners and The Signal
4. **Publish**: Upload charts to Substack, paste text, publish

Estimated time after setup: **60-90 minutes per week**.

---

## 🗺️ Roadmap

- [ ] Wire up live data fetchers (replace mock data)
- [ ] Add credit spreads (FRED: IG & HY)
- [ ] Add breakeven inflation expectations
- [ ] Add India-specific monthly supplement
- [ ] Build Streamlit interactive version
- [ ] Automated chart bank archiving
- [ ] GitHub Actions for scheduled generation

---

*Built for The Economics Hub by Shreyas.*