# The Economics Hub — Weekly Dashboard System

An automated Python pipeline that generates key macroeconomic charts and tables; tracking Global Equities, Forex, Sovereign Bonds, Commodities, and Indian Market nuances for [The Economics Hub](https://economicshub.substack.com/) Substack newsletter.


## 📁 Project Structure

```
economics_hub/
├── config/
│   ├── settings.py              # Weekly indicators (Yahoo Finance + FRED tickers)
│   └── macro_settings.py        # Monthly macro indicators (FRED + manual data)
├── data/
│   ├── fetchers/
│   │   ├── yf_fetcher.py        # Yahoo Finance data fetcher
│   │   └── fred_fetcher.py      # FRED API data fetcher
│   └── india_manual.csv         # India metrics (manual monthly CSV)
├── charts/templates/
│   ├── trend_line.py            # TrendLineChart — line charts with end labels
│   ├── weekly_bar.py            # WeeklyBarChart — horizontal green/red bars
│   ├── yield_curve.py           # YieldCurveChart — multi-date yield curves
│   └── summary_table.py         # SummaryTable — market snapshot table
├── style/
│   └── economics_hub_style.py   # EconStyle — visual theme (fonts, colours, layout)
├── output/                      # Generated charts (not tracked by git)
│   ├── weekly/YYYY-MM-DD/
│   ├── macro/YYYY-MM/
│   └── india/YYYY-MM/
│   └── custom
├── generate_weekly.py           # Weekly dashboard
├── generate_macro.py            # Monthly macro dashboard
├── generate_india.py            # India macro dashboard
├── make_chart.py                # CLI tool for ad-hoc charts from any CSV
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 🔧 Reproducibility Guide

### Prerequisites

Python 3.9+ and a free FRED API key from [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html).

### Installation

```bash
git clone https://github.com/shreyasxi/economics-hub.git
cd the-economics-hub
pip install -r requirements.txt
```

### API Key Configuration

Set your FRED API key as an environment variable. Do **not** hardcode it in source files.

**Windows (PowerShell — permanent):**
```powershell
[System.Environment]::SetEnvironmentVariable("FRED_API_KEY", "your_key_here", "User")
# Restart terminal for it to take effect
```

**macOS / Linux:**
```bash
echo 'export FRED_API_KEY="your_key_here"' >> ~/.bashrc
source ~/.bashrc
```

Verify it works:
```bash
python -c "import os; print(os.environ.get('FRED_API_KEY', 'NOT SET'))"
```

## 📊 Usage

### 1. Weekly Global Dashboard
Generates the standard 12-chart pack (Equities, FX, Yields, Commodities) automatically fetching live data.
```bash
python generate_weekly.py
```

### 2. Weekly Macro Dashboard
Generates the charts that are generally released on a monthly basis. Some India specific indicators might require manual entires.
```bash
python generate_macro.py
```

### 3. India Macro Monitor
Generates the India-specific deep dive (FPI, GST, Credit). **Note:** Ensure ```data/india_manual.csv``` is updated with the latest monthly figures before running.
```bash
python generate_india.py
```
### 4. Ad-Hoc Chart Tool (CLI)
Quickly generate a styled chart from any CSV file without modifying the codebase.
```bash
python make_chart.py
```


---


##  Adding New Indicators

1. Add the indicator definition in `config/settings.py` → `INDICATORS` dict
2. Add it to the relevant section in `DASHBOARD_SECTIONS`
3. The chart templates will pick it up automatically

---

## Visual Style

All charts follow a consistent institutional theme defined in `style/economics_hub_style.py`:

**Layout:** White background, black title (18pt bold, top-left), thin horizontal rule below title, source citation bottom-left, "The Economics Hub" watermark bottom-right in bold serif (Cambria → Georgia → Palatino → Times New Roman).

**Colour Palette:**

| Key | Hex | Usage |
|-----|-----|-------|
| US | `#003366` | S&P 500, DXY, US yields, navy series |
| EU | `#008080` | Euro Stoxx, EUR/USD, teal series |
| UK | `#2ca02c` | FTSE, GBP, green series |
| India | `#FF9933` | Nifty, INR, saffron series |
| Japan | `#CC0066` | Nikkei, JPY, magenta series |
| Gold | `#B8860B` | Gold price |
| Silver | `#708090` | Silver price |
| Copper | `#B87333` | Copper price |
| Energy | `#CC0000` | Brent crude |
| Positive | `#065F46` | Green (gains, inflows) |
| Negative | `#991B1B` | Red (losses, outflows) |

**Chart features:** Anti-aliased lines with subtle shadow for depth, end-labels on trend lines with white stroke background, reference lines (e.g., VIX at 20, Fed target at 2%, PMI at 50).

---

## Chart Templates

All templates inherit from `EconStyle` and share the same visual language. They can be used independently for custom charts.

### TrendLineChart

```python
from charts.templates.trend_line import TrendLineChart

trend = TrendLineChart()
trend.add_series("S&P 500", dates, values, color_key="us")
trend.add_series("FTSE 100", dates, values, color_key="uk")
trend.add_reference_line(4500, label="2023 High", color="#999")
trend.render(title="Equity Markets", subtitle="12-Month Trend",
             source="Yahoo Finance", ylabel="Index", normalize=True)
trend.save("output/my_chart.png")
```

### WeeklyBarChart

```python
from charts.templates.weekly_bar import WeeklyBarChart

chart = WeeklyBarChart(
    names=["S&P 500", "FTSE", "Nifty"],
    values=[1.5, -0.8, 2.1],
    change_type="pct"
)
chart.render(title="Equities", subtitle="Weekly Change", source="Yahoo Finance")
chart.save("output/equities_bar.png")
```

### YieldCurveChart

```python
from charts.templates.yield_curve import YieldCurveChart

yc = YieldCurveChart()
yc.add_curve("Current", tenors, yields, style="current")
yc.add_curve("4 Weeks Ago", tenors, yields_4w, style="4w_ago")
yc.add_curve("52 Weeks Ago", tenors, yields_52w, style="52w_ago")
yc.render(title="US Treasury Yield Curve", subtitle="...", source="FRED")
yc.save("output/yield_curve.png")
```

---

## Data Sources

| Source | Type | Access | Used by |
|--------|------|--------|---------|
| Yahoo Finance | Equities, FX, commodities, crypto, VIX, sector ETFs | Free, no key needed | `generate_weekly.py` |
| FRED | US yields, CPI, PCE, unemployment, claims, M2, NFCI, credit spreads | Free API key | `generate_weekly.py`, `generate_macro.py` |
| Manual CSV | India PMI, GST, bank credit, unemployment, FPI flows | Hand-entered monthly | `generate_india.py` |
| Manual dict | India indicators in macro table | Hand-entered in `macro_settings.py` | `generate_macro.py` |

---

## 📄 License

**Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**

This project is licensed for **personal and research use only**.

**You are free to:**
* **Share:** Copy and redistribute the material.
* **Adapt:** Remix, transform, and build upon the material.

**Under the following terms:**
* **Attribution:** You must give appropriate credit to **The Economics Hub**.
* **NonCommercial:** You may **not** use this material for commercial purposes (e.g., selling these charts, using the pipeline for a paid client deliverable).
---

**The Economics Hub** — Data-driven macro analysis for finance professionals.


