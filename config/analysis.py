"""
Analysis page: the words, the threads and the pinned essays, kept apart from the layout.

Everything written by hand on /analysis is edited here. Adding a link to a
thread is one entry in its "links"; saving a chart to a thread is one file in
assets/analysis/ and one entry in its "charts"; starting a new thread is one
dict in WATCHING. Nothing else has to change.

Not here: the "Signal or noise" board at the top of the page. It is computed
each week by generate_signals.py from the series in config/signals_settings.py.

DRAFT: each thread's "why" is a placeholder written for the owner to replace in
their own words. Every link and chart below is real and was checked on
21 Sep 2026.

How to change a chart, a link or a thread, step by step, and how to check this
file before publishing it: the owner's local notes, docs/project_reminders.md,
under "Analysis page". The short version: edit, run
python tests/test_analysis.py, look at the page locally, then push.

Fields — a thread
    theme    the thread's title
    why      a sentence or two: why it matters, and what would change your mind
    charts   each one of
               {"dashboard": "<chart name>", "note": "..."}
                   one of this site's own charts, by its file name without the
                   number (crude_oil_curve); always the latest edition
               {"image": "analysis/<file>", "title": "...", "source": "...",
                "url": "...", "date": "YYYY-MM-DD", "note": "..."}
                   a chart you saved, a screenshot included, kept in assets/analysis/
    links    each {"title", "source", "url", "date": "YYYY-MM-DD", "note"}
             plus "paywall": True when it is behind a subscription and
             "mine": True for your own writing
"""

TITLE = "Connecting the Dots"
DEK = ("Which of the week's moves were unusual for their own market, the issues I am following "
       "across the markets, and longer essays from the newsletter.")

# ── The essay shelf ────────────────────────────────────────────────────────
SUBSTACK_URL = "https://economicshub.substack.com"

# Your best pieces, by the last part of their Substack address
# (economicshub.substack.com/p/<this>), in the order they should appear.
PINNED = [
    "iran-war-is-more-than-just-oil",
    "will-the-ai-boom-actually-hollow",
    "commodities-dominate-the-supreme",
    "the-takaichi-trade-indias-statistical",
]

# A new post leads the shelf, marked New, for this many days. After that it
# drops back among the pinned ones (or out, if it is not pinned), so a quiet
# spell never shows as a gap on the page.
NEW_FOR_DAYS = 30

# ── What I'm watching ──────────────────────────────────────────────────────
WATCHING = [
    {
        "theme": "The Iran war, beyond oil",
        "why": ("Before the war about a fifth of the world's oil passed through the Strait of Hormuz. "
                "The oil price is the headline; the slower effects run through diesel, fertiliser, "
                "LNG and shipping, and through how long Gulf output takes to recover once the strait "
                "fully reopens."),
        "charts": [
            {
                "dashboard": "crude_oil_curve",
                "note": ("A curve that falls steeply from the front month means oil is scarce now; "
                         "it flattens as supply returns."),
            },
            {
                "image": "analysis/eia_brent_2q26.png",
                "title": "Brent crude, daily front-month futures, April 2025 to June 2026",
                "source": "U.S. EIA, Today in Energy (data: Bloomberg L.P.)",
                "url": "https://www.eia.gov/todayinenergy/detail.php?id=67865",
                "date": "2026-07-15",
                "note": ("Brent peaked at $118 on 29 April and fell to $72 by 26 June as ceasefire "
                         "talks advanced."),
            },
        ],
        "links": [
            {
                "title": "IEA cuts oil supply forecast as Iran war delays Middle East recovery",
                "source": "CNBC",
                "url": "https://www.cnbc.com/2026/09/11/iran-war-oil-diesel-iea-hormuz.html",
                "date": "2026-09-11",
                "note": "The IEA's September report: shrinking inventories and strained refineries.",
            },
            {
                "title": "For the Oil Market, the Strait of Hormuz Isn't Closed",
                "source": "Bloomberg Opinion · Javier Blas",
                "url": "https://www.bloomberg.com/opinion/articles/2026-08-13/for-the-oil-market-the-strait-of-hormuz-isn-t-closed",
                "date": "2026-08-13",
                "paywall": True,
                "note": "Why the oil price is lower than a closed strait would suggest.",
            },
            {
                "title": "Fertilizer trade impacted by Strait of Hormuz conflict",
                "source": "WTO Data Blog",
                "url": "https://www.wto.org/english/blogs_e/data_blog_e/blog_dta_10jul26_451_e.htm",
                "date": "2026-07-10",
                "note": "Urea and phosphate trade disrupted; parts of Africa and Asia most exposed.",
            },
            {
                "title": "Javier Blas on Lessons from Closing Hormuz (So Far)",
                "source": "Columbia CGEP · podcast",
                "url": "https://www.energypolicy.columbia.edu/javier-blas-on-lessons-from-closing-hormuz-so-far/",
                "date": "2026-08-04",
                "note": "A conversation on what the closure has taught energy markets.",
            },
            {
                "title": "Iran War is More Than Just Oil",
                "source": "Substack",
                "url": "https://economicshub.substack.com/p/iran-war-is-more-than-just-oil",
                "date": "2026-03-10",
                "mine": True,
                "note": ("The second-order shocks across agriculture, LNG, petrochemicals, "
                         "semiconductors and shipping."),
            },
        ],
    },
    {
        "theme": "AI capex, growth and circular financing",
        "why": ("Data-centre spending has become one of the largest sources of US growth, and more of it "
                "is now paid for with debt and with deals in which suppliers invest in their own "
                "customers. Watching whether cash flow keeps up with capex, and what the bond market "
                "charges for the gap."),
        "charts": [
            {
                "dashboard": "market_breadth",
                "note": ("Equal-weight against cap-weight S&P 500: a falling line means the market's "
                         "gains are narrowing to its largest companies."),
            },
            {
                "image": "analysis/epoch_capex_vs_ocf.png",
                "title": "Hyperscaler cash capex against operating cash flow",
                "source": "Epoch AI (CC BY 4.0)",
                "url": "https://epoch.ai/data-insights/hyperscaler-capex-vs-cash-flow",
                "date": "2026-06-16",
                "note": ("Microsoft, Amazon, Alphabet, Meta and Oracle combined: capex on trend to "
                         "overtake operating cash flow in the third quarter of 2026."),
            },
            {
                "image": "analysis/AI_related_debt.png",
                "title": "AI-related debt issuance across global credit markets, 2026 year to date",
                "source": "Morgan Stanley Research · client note",
                "url": "https://finance.yahoo.com/markets/stocks/articles/morgan-stanley-forecasts-ai-debt-135325015.html",
                "date": "2026-08-19",
                "note": ("$445bn issued by 19 August against $72bn a year earlier, $132bn of it US "
                         "investment-grade bonds from the hyperscalers; July and August stayed busy even as "
                         "spreads widened. The note itself is for Morgan Stanley clients: the source link is "
                         "Quartz's June report on the same tracker."),
            },
            {
                "image": "analysis/iea-data-centre-electricity-2025.png",
                "title": "How much of global electricity is used for data centers?",
                "source": "Our World in Data (CC BY) · data: IEA, Key Questions on Energy and AI",
                "url": "https://ourworldindata.org/how-much-energy-do-data-centers-and-artificial-intelligence-use",
                "date": "2026-07-20",
                "note": ("485 TWh in 2025, 1.5% of the world's electricity. The IEA's base case nearly "
                         "doubles it to 945 TWh by 2030, and AI-focused data centres account for most of the "
                         "rise, from 155 to 465 TWh."),
            },
        ],
        "links": [
            {
                "title": "How much is AI contributing to US economic growth?",
                "source": "ING THINK",
                "url": "https://think.ing.com/opinions/how-much-is-ai-contributing-to-us-economic-growth/",
                "date": "2026-08-20",
                "note": "ING's estimate: AI technology and data centres are a third of US growth in 2026.",
            },
            {
                "title": "Nvidia's $750 Billion in Deals Reignite Circular AI Fears",
                "source": "Bloomberg",
                "url": "https://www.bloomberg.com/news/articles/2026-07-27/nvidia-s-750-billion-deals-revive-fear-of-ai-circular-financing",
                "date": "2026-07-27",
                "paywall": True,
                "note": "The supplier-invests-in-customer deals, and why they worry investors.",
            },
            {
                "title": "How AI Debt Is Reshaping Credit Markets",
                "source": "Goldman Sachs Exchanges · podcast",
                "url": "https://www.goldmansachs.com/insights/goldman-sachs-exchanges/how-ai-debt-is-reshaping-the-credit-market",
                "date": "2026-08-05",
                "note": "What the borrowing behind the buildout is doing to bond yields and private credit.",
            },
            {
                "title": "Should we worry about AI's circular deals?",
                "source": "Noahpinion · Noah Smith",
                "url": "https://www.noahpinion.blog/p/should-we-worry-about-ais-circular",
                "date": "2025-10-22",
                "note": "What the circular deals do, and do not, imply.",
            },
            {
                "title": "Will the AI Boom Actually Hollow Out Its Own Customers?",
                "source": "Substack",
                "url": "https://economicshub.substack.com/p/will-the-ai-boom-actually-hollow",
                "date": "2026-03-01",
                "mine": True,
                "note": "The viral Citrini Research memo, summarised, with counter-perspectives.",
            },
        ],
    },
]
