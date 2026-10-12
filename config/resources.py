"""
Research & About page and site footer: the words and the lists, kept apart from the layout.

Reference copy on /research is edited here. METHODS describes the published
pages; SOURCES holds the research directory. Keep methods in step with the
processors, source contracts and workflow schedules.

INTRO is the owner's own writing, deliberately informal and personal. Do not
smooth it into house style, and do not rewrite it without being asked.

Keep the source notes to one line each: the page reads as a list of
recommendations, and a paragraph per entry turns it into an essay nobody
finishes.

Fields
    name    what it is called
    url     where it lives
    note    one line on what it is good for
    used    True if this site draws on it, which marks it "used here"
    paywall True if most of it sits behind a subscription
"""

# ── The opening. The owner's own words — keep the informal voice. ──────────
INTRO = [
    "This project grew out of my own curiosity and a somewhat idiosyncratic "
    "way of reading financial markets. Rather than claiming to have found the "
    "“best” way of making sense of them (something I doubt we ever really "
    "will — kudos to the fun of lifelong learning!), I wanted to standardise "
    "my own process and bring the different pieces of information I routinely "
    "follow into one place. This will, hopefully, make the day-to-day task of "
    "keeping up with markets a little more structured and convenient. I use "
    "the project myself to track developments across markets, and having built "
    "it from scratch has naturally made me rather particular about its data, "
    "presentation, and reliability. At its core, it is a practical attempt to "
    "turn a process that was previously quite fragmented into something more "
    "systematic to follow.",

    "Of course, these are ultimately just data points, and I would not pretend "
    "that a collection of charts can do the harder part of interpreting the "
    "market for you. The explanations are there to provide some context and, "
    "hopefully, make the relevant developments easier to spot. But the real "
    "value comes from connecting those dots. Working out which movements "
    "matter, which are merely noise, and whether they point towards any "
    "broader or leading theme. The project can hopefully help with that "
    "process, but the connecting of the dots is still very much a human job.",

    "If something here looks wrong, or there is a series you think belongs on "
    "it, please tell me. I genuinely welcome the recommendations and am always "
    "looking for ways to make the project better (&amp; useful!!).",
]

# ── Methods for the published pages (Portfolio Lab is intentionally omitted). ──
METHODS_INTRO = (
    "Each page combines published data with calculations made for Monetaria. "
    "The notes below explain the inputs, the transformations and the timing; "
    "individual charts and their insights provide the more specific definitions."
)
METHODS = [
    dict(name="Weekly Markets", cadence="Saturday edition", points=[
        ("Sources", "Yahoo Finance supplies market prices and investable proxies; NSE supplies Indian index observations, FRED rates and credit series, and Coin Metrics selected Bitcoin history and network measures."),
        ("Method", "Charts use the returns, ratios, rolling averages, correlations and breadth measures stated in their captions. The performance matrix uses dividend-adjusted fund returns where available and direct Bitcoin price returns; a fund proxy is not the underlying spot market. Weekly commentary combines stored market signals and macro observations using defined rules."),
        ("Timing &amp; interpretation", "The main edition is scheduled for Saturday at 11:30 IST. News feeds are collected every four hours and ranked into weekly themes; headlines retain the publisher’s wording and link to the original article. Price-return charts and total-return comparisons should be read according to their own labels."),
    ]),
    dict(name="World", cadence="Weekly + selected refreshes", points=[
        ("Sources", "FRED, OECD, BIS and official central-bank feeds provide macro and policy series. Valuation panels use Shiller and Damodaran; specialist indicators draw on the Chicago Fed, New York Fed and ECB. Historical investment comparisons use the Global Macro Database."),
        ("Method", "Growth, inflation, valuation and financial-condition panels retain the frequency and definition of their source. Global inflation uses published OECD monthly year-on-year rates, with classification transitions recorded. Government yields combine official national observations with OECD monthly backfill; historical percentile ranks use one observation per month."),
        ("Timing &amp; interpretation", "The main edition is scheduled for Saturday at 15:30 IST, with weekday policy-rate checks and a Monday yield refresh. A refresh does not create a new economic observation: national publication lags, mixed yield frequencies and source joins still matter. Yield percentiles describe each country’s own history, not credit quality."),
    ]),
    dict(name="India", cadence="Weekly + daily monetary data", points=[
        ("Sources", "RBI Bulletin, DBIE and official releases cover monetary, banking and external data; MoSPI supplies prices, activity and labour statistics; CGA fiscal accounts; NSDL foreign portfolio flows; NSE equity indices and valuations. RBI survey releases supply household expectations and confidence."),
        ("Method", "Collectors validate the series concept, units, base year and reporting period before a chart uses it. Published growth rates are preferred where required; incompatible statistical bases and survey definitions are not spliced. CPI item price changes are distinct from weighted inflation contributions. Fiscal totals are interpreted in their financial-year context."),
        ("Timing &amp; interpretation", "The main edition is scheduled for Saturday at 13:30 IST; monetary conditions have a separate daily refresh at 20:40 IST. Some inputs still require a separate collector or a verified manual update, including CPI item and external-sector stores. Their observation dates can therefore lag the edition date. Failed source checks can leave the affected panel unavailable."),
    ]),
    dict(name="RBI Sentinel &amp; Sentiment Archive", cadence="Policy documents as released", points=[
        ("Sources", "The RBI’s MPC Resolution, Governor’s Statement and Minutes are grouped by the policy decision date. Repo decisions, stated stance and voting information are extracted from the saved policy text; document links let readers check the original release."),
        ("Method", "The tone scale runs from −1 (dovish) to +1 (hawkish). Each document combines a 10% RBI-specific lexicon score with 90% language-model analysis. The meeting score weights Minutes 50%, Resolution 35% and Governor’s Statement 15%, renormalising over documents available at the time. Tone is separate from the stated policy stance and rate decision."),
        ("Timing &amp; interpretation", "Decision-day checks and a weekday evening check look for newly released documents. When Minutes arrive, the stored meeting score and summary can change. The archive reads that saved analysis and does not preserve every prior revision. Historical meetings were analysed retrospectively, so the history is not a record of forecasts made at the time."),
    ]),
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
        dict(name="Chicago Fed NFCI", url="https://www.chicagofed.org/research/data/nfci/current-data",
             note="Weekly US financial conditions and the published contributions behind the index.",
             used=True),
        dict(name="New York Fed GSCPI", url="https://www.newyorkfed.org/research/policy/gscpi",
             note="Monthly global supply-chain pressure, from the official historical workbook.",
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
             note="Euro-area rates, balance sheet and systemic stress; supplies the CISS series used here.",
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
        dict(name="Controller General of Accounts", url="https://cga.nic.in/index.aspx#account-section",
             note="Monthly union accounts: receipts, spending and how the deficit is financed.",
             used=True),
        dict(name="MoSPI", url="https://www.mospi.gov.in/",
             note="CPI, IIP and the national accounts, at source rather than through a wire report.",
             used=True),
        dict(name="e-Sankhyiki Portal (MoSPI)", url="https://esankhyiki.mospi.gov.in/",
             note="MoSPI's portal for official Indian statistics and downloadable datasets.",
             used=True),
        dict(name="NSDL FPI flows", url="https://www.fpi.nsdl.co.in/web/Reports/Yearwise.aspx?RptType=6",
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
        dict(name="Global Macro Database", url="https://www.globalmacrodata.com/index.html",
             note="Historical macroeconomic data across countries, used here for investment comparisons.",
             used=True),
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

# ── The footer, on every page. ─────────────────────────────────────────────
# The black strip under the last chart of every page. A link that starts with
# "/" is a page of this site and opens in the same tab; mailto: opens the
# reader's email; anything else opens in a new tab. Readers get in touch
# through the Connect column; the site has no contact form, by choice.
FOOTER_TAGLINE = "Global macro and cross-asset monitor, researched and maintained by Shreyas Urgunde."
FOOTER_SUBSCRIBE = "https://economicshub.substack.com/"
FOOTER_COLUMNS = [
    ("Sections", [
        ("Weekly Markets", "/"),
        ("World", "/world"),
        ("India", "/india"),
        ("RBI Sentinel", "/rbi-sentinel"),
        ("Portfolio Lab", "/portfolio-lab"),
        ("Research & About", "/research"),
    ]),
    ("The project", [
        ("Methods & sources", "/research#research-methods"),
        ("System architecture", "https://shreyasxi.github.io/economics-hub/"),
        ("Newsletter archive", "https://economicshub.substack.com/archive"),
        ("Source code", "https://github.com/shreyasxi/the-economics-hub"),
    ]),
    ("Connect", [
        ("LinkedIn", "https://www.linkedin.com/in/shreyasurgunde"),
        ("GitHub", "https://github.com/shreyasxi"),
        ("Instagram", "https://www.instagram.com/the.economics.hub/"),
        ("Academic website", "https://shreyasxi.github.io/"),
        ("Email me", "mailto:shreyasurgunde20@gmail.com"),
    ]),
]
# The repository's LICENSE: Creative Commons Attribution-NonCommercial 4.0.
FOOTER_LICENCE = ("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/")
FOOTER_LEGAL = ("The data remain with the sources credited on each chart. "
                "For information and research, not investment advice.")
