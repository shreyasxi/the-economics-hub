"""
About page: the words and the lists, kept apart from the layout.

Everything on /about is edited here. Adding a source is one line in SOURCES;
changing how a page is built is one line in ARCHITECTURE. Nothing else has to
change.

The prose below is a draft, written to show the shape of the page — replace it
with your own. Keep the notes to one line each: the page reads as a list of
recommendations, and a paragraph per entry turns it into an essay nobody
finishes.

Fields
    name    what it is called
    url     where it lives
    note    one line on what it is good for
    used    True if this site draws on it, which marks it "used here"
    paywall True if most of it sits behind a subscription
"""

# ── The opening. Two or three paragraphs, first person. ────────────────────
INTRO = [
    "This site began as my own reading of markets, kept in one place so I "
    "would stop rebuilding the same charts every week. It now runs on its own: "
    "the charts are drawn from live data on a schedule, and nothing on them "
    "is typed in by hand except the handful of Indian series that no API "
    "publishes.",

    "It is deliberately incomplete. I add what I find myself wanting to look "
    "at, drop what I stop reading, and would rather show one chart that "
    "settles a question than five that gesture at it. If something here is "
    "wrong, or if there is a series you think belongs on it, tell me — "
    "recommendations are genuinely welcome.",
]

# ── How it is built. ───────────────────────────────────────────────────────
# Longer than a caption, shorter than documentation: enough that a reader can
# judge how much to trust a chart without opening the repository.
BUILD_NOTES = [
    "Nothing here is drawn by hand. Each page is a Python job that fetches "
    "its own data, draws its charts and publishes them; the site itself only "
    "displays what the latest run produced.",

    "The jobs run on a schedule rather than on demand, so a chart is as fresh "
    "as the line under it says it is. Every chart carries its source and the "
    "date it was drawn.",

    "Where a figure cannot be fetched, the chart is left out rather than "
    "filled in. There is no placeholder data anywhere on this site: a missing "
    "source fails the run loudly instead of publishing a plausible number.",

    "Revisions are respected. Series that get restated — Indian fiscal "
    "accounts, payrolls, the national accounts — are re-read in full on each "
    "run rather than appended to, so an old chart never disagrees with a new "
    "one.",

    "Indian data is the hard part. Several series exist only as monthly PDFs "
    "or as a portal that resists scraping, so those are parsed on a best "
    "effort basis and checked against the published document before they go up.",

    "The code is open: the pipelines, the chart styles and these lists are all "
    "in one repository, and the charts are drawn with Matplotlib on a house "
    "style rather than with a charting service.",
]

# ── What each page is built from, and when it refreshes. ───────────────────
# Moved here from the sidebar. The schedules are the crons in
# .github/workflows; the sources are the fetchers each generator calls. Keep
# both in step with those files when either moves.
ARCHITECTURE = [
    ("Weekly Markets", "Saturdays", "Yahoo Finance · NSE · FRED · Coin Metrics"),
    ("World",          "Saturdays", "FRED · OECD · BIS · Damodaran · Shiller"),
    ("India",          "Saturdays", "RBI Bulletin & DBIE · MoSPI · CGA · NSDL"),
    ("RBI Sentinel",   "Weekdays",  "RBI policy documents, scored by Claude"),
    ("Headlines",      "4-hourly",  "Nine publishers’ news feeds"),
]

# ── Data, grouped. ─────────────────────────────────────────────────────────
# Two jobs at once: credit what these charts are built from (used=True), and
# point a researcher at the portals worth knowing whether or not this site
# touches them. Keep both kinds in the same list — a reader looking for data
# does not care which of them I happened to use.
SOURCES: list[tuple[str, list[dict]]] = [
    ("Global macro & policy", [
        dict(name="FRED, St. Louis Fed", url="https://fred.stlouisfed.org/",
             note="The fastest route to almost any US series, and where most charts here start.",
             used=True),
        dict(name="ALFRED, vintage FRED", url="https://alfred.stlouisfed.org/",
             note="The same series as first published, before revision — the honest way to test a forecast.",
             used=False),
        dict(name="OECD Data Explorer", url="https://data-explorer.oecd.org/",
             note="One comparable growth signal across countries, which is rarer than it sounds.",
             used=True),
        dict(name="BIS statistics", url="https://data.bis.org/",
             note="Policy rates, cross-border credit and the dollar funding picture, free and well documented.",
             used=True),
        dict(name="IMF Data", url="https://data.imf.org/",
             note="Balance of payments, reserves and the WEO vintages, for anything comparative.",
             used=False),
        dict(name="World Bank Open Data", url="https://data.worldbank.org/",
             note="The default for development and long-run country indicators.",
             used=False),
        dict(name="Eurostat", url="https://ec.europa.eu/eurostat/data/database",
             note="European data at source, with an API that behaves.",
             used=True),
        dict(name="ECB Data Portal", url="https://data.ecb.europa.eu/",
             note="Euro-area rates, balance sheet and bank lending surveys.",
             used=False),
        dict(name="NBER business cycle dating", url="https://www.nber.org/research/business-cycle-dating",
             note="The recession dates every shaded chart on this site uses.",
             used=True),
    ]),
    ("Markets, valuation & prices", [
        dict(name="Yahoo Finance", url="https://finance.yahoo.com/",
             note="Long daily histories for indices, futures and FX, free and good enough for charts.",
             used=True),
        dict(name="Damodaran Online, NYU Stern", url="https://pages.stern.nyu.edu/~adamodar/",
             note="Equity risk premiums, country risk and cost of capital, updated yearly and free.",
             used=True),
        dict(name="Shiller data, Yale", url="https://shillerdata.com/",
             note="US equity prices, earnings and CAPE monthly back to 1881.",
             used=True),
        dict(name="Ken French Data Library", url="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
             note="Factor and portfolio returns — the starting point for most asset pricing work.",
             used=False),
        dict(name="Coin Metrics community data", url="https://coinmetrics.io/community-network-data/",
             note="On-chain bitcoin measures, including several Glassnode now charges for.",
             used=True),
        dict(name="Cboe historical data", url="https://www.cboe.com/tradable_products/vix/vix_historical_data/",
             note="VIX and its term structure from the exchange rather than second-hand.",
             used=False),
        dict(name="US Energy Information Administration", url="https://www.eia.gov/",
             note="Production, stocks and the petroleum balance behind every oil price argument.",
             used=False),
        dict(name="SEC EDGAR full-text search", url="https://www.sec.gov/edgar/search/",
             note="Every US filing, searchable by phrase — underused outside equity research.",
             used=False),
    ]),
    ("India", [
        dict(name="RBI Database on the Indian Economy", url="https://data.rbi.org.in/DBIE/",
             note="The primary source for Indian monetary and banking data; awkward to scrape, worth it.",
             used=True),
        dict(name="Controller General of Accounts", url="https://cga.nic.in/MonthlyReport.aspx",
             note="Monthly union accounts: receipts, spending and how the deficit is financed.",
             used=True),
        dict(name="MoSPI", url="https://www.mospi.gov.in/",
             note="CPI, IIP and the national accounts, at source rather than through a wire report.",
             used=True),
        dict(name="NSDL FPI flows", url="https://www.fpi.nsdl.co.in/web/Reports/ReportItem.aspx?ReportId=31",
             note="What foreign investors actually bought and sold, by sector, fortnightly.",
             used=True),
        dict(name="NSE India", url="https://www.nseindia.com/",
             note="Index levels and sector returns, after Yahoo stopped carrying the NIFTY sector indices.",
             used=True),
        dict(name="Union Budget documents", url="https://www.indiabudget.gov.in/",
             note="Receipts, expenditure and the fiscal arithmetic as tabled, including past years.",
             used=False),
        dict(name="Trade statistics, DGCI&S", url="https://tradestat.commerce.gov.in/",
             note="India's merchandise trade by commodity and partner country.",
             used=True),
        dict(name="data.gov.in", url="https://www.data.gov.in/",
             note="The open data platform: uneven, but it holds series published nowhere else.",
             used=False),
        dict(name="PRS Legislative Research", url="https://prsindia.org/",
             note="Bills, budgets and committee reports explained without a position.",
             used=False),
        dict(name="EPWRF India Time Series", url="https://epwrfits.in/",
             note="The deepest curated Indian series collection; institutional subscription.",
             used=False, paywall=True),
    ]),
    ("Long-run & research datasets", [
        dict(name="Jordà-Schularick-Taylor Macrohistory", url="https://www.macrohistory.net/database/",
             note="Rates, credit and asset prices for 18 countries since 1870, in one file.",
             used=False),
        dict(name="Penn World Table", url="https://www.rug.nl/ggdc/productivity/pwt/",
             note="Comparable output, capital and productivity across countries and decades.",
             used=False),
        dict(name="Maddison Project", url="https://www.rug.nl/ggdc/historicaldevelopment/maddison/",
             note="GDP per capita back to 1 AD, for when the argument is about centuries.",
             used=False),
        dict(name="Our World in Data", url="https://ourworldindata.org/",
             note="Cleaned, sourced and downloadable — often faster than the original portal.",
             used=False),
    ]),
]

# ── People and publications worth following. ───────────────────────────────
# Not shown on the page at the moment; kept here so the section can come back
# by rendering it again.
READING = [
    dict(name="FT Alphaville", url="https://www.ft.com/alphaville",
         note="Sceptical, numerate and quick on anything that smells like a bubble.", paywall=True),
    dict(name="Lyn Alden", url="https://www.lynalden.com/",
         note="Long-form on liquidity, fiscal dominance and bitcoin, with the workings shown.", paywall=False),
    dict(name="Javier Blas, Bloomberg Opinion", url="https://www.bloomberg.com/opinion/authors/AS1nnPeIDGo/javier-blas",
         note="Commodities reported from the trade itself rather than from the price screen.", paywall=True),
    dict(name="Money Stuff, Matt Levine", url="https://www.bloomberg.com/account/newsletters/money-stuff",
         note="How finance actually works, on the days when that is funnier than it should be.", paywall=False),
    dict(name="The RBI's own bulletins", url="https://www.rbi.org.in/Scripts/BS_ViewBulletin.aspx",
         note="The State of the Economy article is the closest thing to the RBI thinking aloud.", paywall=False),
]
