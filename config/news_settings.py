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

# Collected through the week, not read once on Saturday: some feeds hold only
# hours of stories (Business Standard markets about 6 h, Mint markets 10 h,
# Bloomberg 15 h; measured 17 Sep 2026). The Headline Collector workflow reads
# every feed every 4 hours into a pool kept in GitHub's Actions cache, never
# in the repository, and the weekly run ranks the whole pool. Only headlines
# that could be chosen are kept: a theme matches and no exclusion does.
POOL_KEEP_DAYS = 8          # older headlines are deleted on every read: the week plus a day's margin
POOL_MAX_PER_REGION = 3000  # a safety cap, newest kept; a normal week is under 1,000 per column

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
    # Daily market reports: every outlet runs one, so they look widely covered,
    # and across a week's collection they would also look like the story that
    # stayed in the news longest.
    r"\bearly trade\b", r"\bat midday\b", r"\bmorning (?:gains|losses|trade)\b", r"\bopening bell\b",
    r"\bmarket today\b", r"\bpaise\b", r"\b\d[\d,]* (?:pts|points)\b", r"\b(?:positive|negative) terrain\b",
    r"\bsnaps? \d+-day\b", r"\bbuzzing stocks\b", r"\bstocks? for (?:today|tomorrow|\w+ \d{1,2})\b",
    r"\bfutures (?:rise|fall|gain|decline|climb|slip|drop|edge|trade|jump|surge|slide|dip|inch|sink)s?\b",
    r"\bprices? today\b",
    r"\b(?:gold|silver|petrol|diesel) (?:rate|price)s? (?:in india )?(?:today|on \w+ \d{1,2})\b", r"\btoday'?s (?:gold|silver) rate\b",
    r"\bturns \d{2,3}\b",
    # Closing reports and previews of the next session. Checked on 10-17 Sep 2026
    # headlines: these caught only such reports, no macro news.
    r"\bbarometers?\b", r"\bquick wrap\b", r"\bmarket (?:prediction|highlights)\b", r"\bcues to watch\b",
    r"\b(?:sensex|nifty) today\b", r"\bmixed trend\b", r"\bmarkets? (?:steady|flat|subdued|range-?bound)\b",
    r"\b(?:sensex|nifty)(?:,? (?:and )?(?:sensex|nifty))?(?: 50)? (?:holds?|stays?|ends?|closes?|settles?|opens?|trades?|finishes?)\b",
    r"\b(?:ends?|closes?|settles?|finishes?|opens?) (?:above|below|near|around|at) [\d,.]{3,}",
    r"\b(?:ends?|closes?|settles?|finishes?|trades?|opens?) (?:almost |nearly )?(?:flat|sideways|mixed|higher|lower|in the (?:red|green))\b",
    r"\b(?:rupee|inr) (?:settles?|ends?|closes?|opens?) (?:almost |nearly |marginally )?(?:flat|higher|lower|up|down|at|near|\d)",
    r"\bwall street (?:climbs|rises|gains|rallies|falls|slips|drops|dips|sinks|ends|closes|opens|edges)\b",
    r"\b(?:gold|silver)(?:,? (?:and )?silver)? (?:prices?|rates?) (?:rise|fall|gain|drop|dip|edge|climb|slip|decline)s?\b",
    # A company group's or a sector's shares moving is stock chatter, not the week's market news.
    r"\b(?:group|sector|sectoral|psu|defen[cs]e|pharma|metal|auto|realty|railway|sugar|cement|fmcg|smallcap|midcap) (?:stocks|shares)\b",
    r"\bstocks? (?:on fire|in focus)\b",
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
    (r"\b(?:kevin )?warsh\b", "fed"),                      # the Fed chair: update when the chair changes
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
    # Counting words match unrelated stories: BBC's "US interest rates raised for first time in
    # three years" joined the FT's "The BoE's three balance sheet problem" (17 Sep 2026).
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "second", "third", "time",
}
# Headlines that count as coverage of a story but are shown for it only when no
# plain report of the news is as typical of the story: explainers, analysis and
# newsletters. A headline of fewer than MIN_HEADLINE_WORDS words ("AI debt vs
# Treasuries") is too short to say what happened, and is shown last of all.
# A week's collection holds more of these: they follow an event for days.
HEADLINE_EXPLAINERS = [
    r"^(?:why|how|what|who|here's|here are)\b", r"^(?:analysis|explainer|opinion|comment|firstft|the big read)\b",
    r"\bexplained\b", r"\btakeaways\b", r"\bwhat (?:it|this|that) means\b", r"\bwhat to (?:know|expect|watch)\b",
]
MIN_HEADLINE_WORDS = 5

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
    "Stories rank by how many of the outlets read carried them (the bars beside each one show that count), "
    "then by how many days they stayed in the news.",
    "Headlines are the publishers’ own and link to the original. A lock marks outlets that may require "
    "a subscription.",
]
