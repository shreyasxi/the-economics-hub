"""
The Week in Headlines (Weekly Markets tab): which feeds are read, how headlines
are sorted into themes, and what is dropped.

generate_news.py reads this file and writes news.json into the weekly edition
folder. Nothing here is written or summarised by the pipeline: every headline
on the page is the publisher's own, linked to the original.

A feed that fails is skipped with a warning; a column left with too little is
dropped from the page. News never blocks the charts.
"""

# ─────────────────────────────────────────────
# THE WEEK IN HEADLINES
# ─────────────────────────────────────────────

HEADLINE_WINDOW_DAYS = 7
HEADLINES_PER_REGION = 5
MIN_HEADLINES = 3           # fewer than this after filtering: the column is left out
MAX_PER_PUBLISHER = 2       # beyond this, another outlet's headline for the story is used if it has one

# (publisher, feed URL). When several outlets carry the same story, the
# headline shown comes from the publisher listed first, so free-to-read outlets
# lead. WSJ, Yahoo Finance and Moneycontrol were left out: their feeds serve
# items months or years old (checked Sep 2026).
HEADLINE_FEEDS: dict[str, list[tuple[str, str]]] = {
    "world": [
        ("BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/business/economics/rss"),
        ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
        ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("Financial Times", "https://www.ft.com/global-economy?format=rss"),
        ("Financial Times", "https://www.ft.com/markets?format=rss"),
        ("Bloomberg", "https://feeds.bloomberg.com/economics/news.rss"),
        ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
    ],
    "india": [
        ("Mint", "https://www.livemint.com/rss/economy"),
        ("Mint", "https://www.livemint.com/rss/markets"),
        ("Business Standard", "https://www.business-standard.com/rss/economy-102.rss"),
        ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
        ("BusinessLine", "https://www.thehindubusinessline.com/economy/feeder/default.rss"),
        ("BusinessLine", "https://www.thehindubusinessline.com/markets/feeder/default.rss"),
        ("The Indian Express", "https://indianexpress.com/section/business/economy/feed/"),
    ],
}

# Themes, in priority order. A headline belongs to the first theme it matches
# ("Fed hike lifts the dollar" is Central banks, not Markets) and is ignored if
# it matches none. Each column shows at most one story per theme, the one the
# most outlets covered, so a single event cannot fill a column.
HEADLINE_THEMES: list[tuple[str, list[str]]] = [
    ("Central banks", [
        r"\bfed\b", r"\bfederal reserve\b", r"\bfomc\b", r"\bwarsh\b", r"\becb\b", r"\blagarde\b",
        r"\bbank of england\b", r"\bboe\b", r"\bbank of japan\b", r"\bboj\b", r"\brbi\b",
        r"\breserve bank\b", r"\bmpc\b", r"\bpboc\b", r"\bcentral banks?\b", r"\binterest[- ]rates?\b",
        r"\brate (?:hikes?|cuts?|rises?|decision)\b", r"\brepo rate\b", r"\bmonetary policy\b",
    ]),
    ("Inflation", [
        r"\binflation\b", r"\bcpi\b", r"\bwpi\b", r"\bconsumer prices\b", r"\bprice index\b", r"\bfood prices?\b",
    ]),
    ("Trade & tariffs", [
        r"\btariffs?\b", r"\btrade (?:war|deal|pact|talks|deficit|surplus|data)\b", r"\bexports?\b",
        r"\bimports?\b", r"\bsanctions?\b", r"\bwto\b", r"\bfta\b", r"\bfree trade\b",
    ]),
    ("Energy & commodities", [
        r"(?<!cooking )(?<!edible )(?<!palm )\boil\b", r"\bcrude\b", r"\bbrent\b", r"\bopec\b", r"\bnatural gas\b", r"\bgold\b",
        r"\bsilver\b", r"\bcopper\b", r"\bcommodit(?:y|ies)\b",
    ]),
    ("Growth & jobs", [
        r"\bgdp\b", r"\beconomic growth\b", r"\brecession\b", r"\bjobs\b", r"\bpayrolls\b",
        r"\bunemployment\b", r"\bwages?\b", r"\bpmi\b", r"\bmanufacturing\b", r"\bindustrial (?:output|production)\b",
        r"\biip\b", r"\bgrowth (?:forecast|outlook)\b", r"\beconomy\b",
    ]),
    ("Markets", [
        r"\bstocks\b", r"\bequities\b", r"\bsensex\b", r"\bnifty\b", r"\bs&p 500\b", r"\bdow\b",
        r"\bnasdaq\b", r"\bftse\b", r"\bnikkei\b", r"\bbonds?\b", r"\byields?\b", r"\btreasur(?:y|ies)\b",
        r"\bgilts?\b", r"\bdollar\b", r"\brupee\b", r"\byen\b", r"\byuan\b", r"\bcurrenc(?:y|ies)\b",
        r"\bfpis?\b", r"\bfiis?\b",
    ]),
    ("Public finances", [
        r"\bbudget\b", r"\bfiscal\b", r"\bdeficit\b", r"\bpublic debt\b", r"\bborrowing\b", r"\btax\b",
        r"\bgst\b", r"\bgovernment spending\b",
    ]),
]

# Under the other themes a story needs at least two outlets: one outlet's
# company news ("... commences trial production of copper cathodes") otherwise
# fills the lower slots. A column may then show fewer than HEADLINES_PER_REGION.
ONE_OUTLET_THEMES = {"Central banks", "Inflation", "Trade & tariffs"}

# Dropped whatever their theme: live blogs, stock tips, single-company market
# chatter and explainers that are not the week's news.
HEADLINE_EXCLUDE = [
    r"^live\b", r"\blive(?: updates?| blog| coverage)?:", r"\blive updates?\b", r"\bmarket live\b",
    r"\bpodcast\b", r"\bquiz\b", r"\bvideo\b",
    r"\bipo\b", r"\bgmp\b", r"share price", r"shares? (?:jump|rise|fall|surge|slump|zoom|rally|gain|drop)",
    r"stocks? to (?:buy|watch|beat)", r"\b(?:dividend|multibagger|penny|safe) stocks\b", r"\bbuy or sell\b",
    r"target price", r"\bq[1-4] results?\b",
    r"^how to\b", r"^what is\b", r"personal finance", r"credit card", r"\bmortgage rates? today\b",
    r"\bin charts\b", r"\bsubmit a question\b", r"\btracker: see\b",
    r"\bas it happened\b", r"\bbusiness live\b", r"^watch:", r"markets wrap$",
    r"\|\s*editorial$", r"(?-i:\| [A-Z][\w'’.-]+(?: [A-Z][\w'’.-]+)+$)",   # Guardian opinion columns end "| Author Name"
    r"\?$",                                                              # questions are explainers, not the news
    # Daily market reports: every outlet runs one, so they look widely covered.
    r"\bearly trade\b", r"\bat midday\b", r"\bmorning (?:gains|losses|trade)\b", r"\bopening bell\b",
    r"\bmarket today\b", r"\bpaise\b", r"\b\d[\d,]* (?:pts|points)\b", r"\b(?:positive|negative) terrain\b",
    r"\bsnaps? \d+-day\b", r"\bbuzzing stocks\b", r"\bstocks? for (?:today|tomorrow|\w+ \d{1,2})\b",
    r"\bfutures (?:rise|fall|gain|decline|climb|slip|drop|edge|trade)s?\b", r"\bprices? today\b",
    r"\b(?:gold|silver|petrol|diesel) (?:rate|price)s? (?:in india )?(?:today|on \w+ \d{1,2})\b", r"\btoday'?s (?:gold|silver) rate\b",
    r"\bturns \d{2,3}\b",
]

# The India column is for India's own news. Indian outlets rarely say "India"
# in a domestic headline ("Retail inflation rises to 4.82%"), so a story is
# dropped only when it names a foreign actor and none of its headlines has an
# India angle: the Fed hike itself belongs under World, "Fed hike: what it
# means for FII flows" stays.
HEADLINE_LOCAL: dict[str, dict[str, list[str]]] = {
    "india": {
        "local": [
            r"\bindia", r"\brbi\b", r"\breserve bank\b", r"\bmpc\b", r"\bsensex\b", r"\bnifty\b",
            r"\brupee\b", r"\bgst\b", r"\bsebi\b", r"\bfpis?\b", r"\bfiis?\b", r"\bcrore\b", r"\blakh\b",
            r"\bdelhi\b", r"\bmumbai\b", r"\bsitharaman\b", r"\bmalhotra\b", r"\bmodi\b", r"\bmospi\b",
        ],
        "foreign": [
            r"\bfed\b", r"\bfederal reserve\b", r"\bwarsh\b", r"\bu\.?s\.?\b", r"\bamerica", r"\btrump\b",
            r"\bwall street\b", r"\bchina\b", r"\bchinese\b", r"\bjapan", r"\bkospi\b", r"\btaiwan\b",
            r"\beurope", r"\beu\b", r"\buk\b", r"\bbritain\b", r"\bboe\b", r"\becb\b", r"\bboj\b", r"\bopec\b",
        ],
    },
}

# Matching headlines about the same story. Outlets word one event differently
# ("Fed defies Trump with first rate rise" / "Federal Reserve raises fed funds
# rate"), so common variants are rewritten to one word first, in this order.
STORY_SYNONYMS: list[tuple[str, str]] = [
    (r"\bfederal reserve\b|\bfomc\b|\bus central bank\b", "fed"),
    (r"\bbank of england\b", "boe"),
    (r"\bbank of japan\b", "boj"),
    (r"\beuropean central bank\b", "ecb"),
    (r"\breserve bank of india\b", "rbi"),
    (r"\binterest[- ]rates?\b", "rate"),
    (r"\brates?[- ]rises?\b", "rate hike"),
    (r"\b(?:raise[sd]?|raising|hike[sd]?|hiking)\b", "hike"),
    (r"\b(?:cuts?|cutting)\b", "cut"),
    (r"\b(?:holds?|held|keeps?|kept|pause[sd]?)\b", "hold"),
    (r"\b(?:crude|brent|wti)\b", "oil"),
    (r"\b(?:cpi|consumer prices)\b", "inflation"),
    (r"\b(?:treasuries|treasury yields?|bond yields?|yields)\b", "yield"),
    (r"\bbritain\b|\bbritish\b|\bu\.k\.", "uk"),
]
STORY_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by", "with", "from",
    "as", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that", "after",
    "amid", "over", "into", "up", "down", "new", "says", "say", "said", "will", "could",
    "may", "might", "can", "than", "more", "most", "first", "since", "year", "years",
    "week", "what", "why", "how", "who", "not", "no", "but", "about", "ahead", "us",
    "india", "indian", "global", "world", "market", "markets", "set", "here", "plus",
}
# A headline joins a story (within its theme) when its similarity to the story
# so far, TF-IDF cosine against the story's centroid, reaches this. Checked on
# the week of 10-17 Sep 2026: 0.25 split the Fed hike's coverage, 0.3 split
# more; 0.2 kept it together without merging unrelated stories.
STORY_SIMILARITY = 0.2

# These sites refuse the pipeline's own user agent, so requests to them
# identify as a desktop browser.
BROWSER_UA_HOSTS = {"www.business-standard.com"}

# Marked with a lock on the page. Hard paywalls only: Mint and Business
# Standard lock some stories, not most.
PAYWALLED_PUBLISHERS = {"Financial Times", "Bloomberg"}

# "How these are chosen" on the page, one line each; {themes} is filled from
# HEADLINE_THEMES. The outlets actually read that week are listed after these.
HEADLINE_METHOD = [
    "Chosen automatically from the week’s RSS headlines. Each theme ({themes}) offers its most "
    "widely covered story.",
    "Stories rank by how many of the outlets read carried them; the bars beside each one show that count.",
    "Headlines are the publishers’ own and link to the original. A lock marks outlets that may require "
    "a subscription.",
]
