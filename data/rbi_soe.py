"""
RBI Bulletin — State of the Economy: fetching and reading the article.

Two things come out of each edition (see config/soe_settings.py for why):
the opening summary and concluding assessment, shown at the top of the India
tab, and Table IV.3, the pass-through of policy rate changes to bank deposit
and lending rates.

Everything here either returns RBI's own words and figures or raises. Nothing is
summarised, rounded up or filled in: an edition that cannot be read is reported
as missing, and the dashboard then shows no briefing rather than stale text.

Layout notes, from reading every kind of edition between Jan 2021 and Aug 2026:
  - the article sits in the table whose header cell reads "State of the Economy";
  - its paragraphs are plain <p>; section headings are <p class="head">, and
    footnotes <p class="footnote">;
  - section headings vary ("II. Global Setting" and "II. Global Section" are the
    same section), so Conclusion is matched on the word, not the numeral;
  - charts and the high-frequency tables III.1-III.5 are images, and are ignored.
    The four real HTML tables include the transmission table this module reads.

The pure parsers (everything below "PARSERS") take HTML text and are covered by
tests/test_soe.py against saved editions; only the fetchers touch the network.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config.soe_settings import (
    ARTICLE_TITLE, ARTICLE_URL, BULLETIN_URL, CACHE_DIR, CONCLUSION_MAX_PARAGRAPHS,
    CHANGES_MAX, CHANGES_MIN_WORDS, CHART_REFERENCE, CYCLE_LABEL_ROW, CYCLE_ROW, FIRST_EDITION, MAX_ATTEMPTS, MAX_PLAUSIBLE_BPS, MONTHLY_ROW,
    PAUSE_SECONDS, PERIOD_ROW, REQUEST_TIMEOUT, SUMMARY_MAX_WORDS, SUMMARY_MIN_WORDS,
    TOPIC_SECTIONS, TRANSMISSION_CAPTION, TRANSMISSION_COLUMNS, TRANSMISSION_OPTIONAL,
    USER_AGENT,
)

log = logging.getLogger(__name__)

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


class SoeError(Exception):
    """The article could not be found, read or trusted."""


@dataclass(frozen=True)
class Edition:
    """One month's article: where it is and when RBI published it."""
    month: str          # "2026-08", the Bulletin's month
    article_id: str
    url: str

    def as_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════
# FETCHING
# ═══════════════════════════════════════════

def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


def _request(session: requests.Session, method: str, url: str, **kwargs) -> str:
    """One page, with retries. Anything but a page of HTML is an error, not an empty string."""
    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            resp.raise_for_status()
            text = resp.text
            if "text/html" not in resp.headers.get("Content-Type", "") or len(text) < 5000:
                raise SoeError(f"{url} did not return the Bulletin page "
                               f"({resp.headers.get('Content-Type')}, {len(text)} bytes)")
            return text
        except (requests.RequestException, SoeError) as exc:
            last = exc
            log.warning("RBI Bulletin fetch failed (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, exc)
            if attempt < MAX_ATTEMPTS:
                time.sleep(PAUSE_SECONDS * attempt)
    raise SoeError(f"could not read {url}: {last}")


def _hidden_fields(page: str) -> dict[str, str]:
    """The ASP.NET state the Bulletin page needs back when asking for another month."""
    fields = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        m = re.search(rf'id="{name}"\s+value="([^"]*)"', page)
        if m:
            fields[name] = m.group(1)
    if "__VIEWSTATE" not in fields:
        raise SoeError("the Bulletin page no longer carries __VIEWSTATE; the archive form has changed")
    return fields


def find_latest(session: requests.Session) -> Edition:
    """The newest published article, from the Bulletin's contents page."""
    page = _request(session, "GET", BULLETIN_URL)
    edition = _edition_from_contents(page)
    if edition is None:
        raise SoeError("the latest Bulletin contents page has no State of the Economy link")
    return edition


def find_month(session: requests.Session, month: str) -> Edition | None:
    """
    The article for one month ("2026-08"), through the Bulletin page's month archive.

    Returns None when that month's Bulletin carries no such article, which is a
    fact about the archive (it starts in November 2020), not a failure.
    """
    _check_month(month)
    year, mon = month.split("-")
    page = _request(session, "GET", BULLETIN_URL)
    data = {
        **_hidden_fields(page),
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "hdnYear": year,
        "hdnMonth": str(int(mon)),
        "ddlSubSection": "0",
    }
    archive = _request(session, "POST", BULLETIN_URL, data=data)
    return _edition_from_contents(archive, month=month)


def fetch_article(session: requests.Session, edition: Edition, *, use_cache: bool = True) -> str:
    """The article's HTML, from the cache when it is already there (editions never change)."""
    cached = CACHE_DIR / f"{edition.month}.html"
    if use_cache and cached.exists():
        return cached.read_text(encoding="utf-8")
    page = _request(session, "GET", edition.url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(page, encoding="utf-8")
    return page


def _check_month(month: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise SoeError(f"month must look like 2026-08, not {month!r}")
    if month < FIRST_EDITION:
        raise SoeError(f"State of the Economy starts in {FIRST_EDITION}; {month} is before it")


# ═══════════════════════════════════════════
# PARSERS — HTML in, RBI's own words and figures out
# ═══════════════════════════════════════════

def _soup(page: str) -> BeautifulSoup:
    return BeautifulSoup(page, "lxml")


def _edition_from_contents(page: str, month: str | None = None) -> Edition | None:
    """Find the State of the Economy link on a Bulletin contents page."""
    soup = _soup(page)
    for link in soup.find_all("a", href=True):
        if link.get_text(" ", strip=True).lower() != ARTICLE_TITLE.lower():
            continue
        m = re.search(r"Id=(\d+)", link["href"])
        if not m:
            continue
        article_id = m.group(1)
        return Edition(
            month=month or _bulletin_month(page),
            article_id=article_id,
            url=ARTICLE_URL.format(article_id=article_id),
        )
    return None


def _bulletin_month(page: str) -> str:
    """"Reserve Bank of India Bulletin - August 2026" -> "2026-08"."""
    m = re.search(r"Bulletin\s*[-–]\s*([A-Z][a-z]+)\s+(\d{4})", page)
    if not m or m.group(1) not in MONTHS:
        raise SoeError("could not read which month this Bulletin is")
    return f"{m.group(2)}-{MONTHS.index(m.group(1)) + 1:02d}"


def _article_table(page: str):
    """The table holding the article, found by its header cell."""
    soup = _soup(page)
    head = soup.find(lambda t: t.name == "b" and t.get_text(strip=True) == ARTICLE_TITLE)
    table = head.find_parent("table") if head else None
    if table is None:
        raise SoeError("this page is not a State of the Economy article")
    return table


def published_date(page: str) -> date:
    """The date RBI printed on the article ("Date : Aug 25, 2026")."""
    text = _article_table(page).get_text(" ", strip=True)
    m = re.search(r"Date\s*:\s*([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})", text)
    if not m:
        raise SoeError("the article carries no publication date")
    return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date()


def _paragraphs(table) -> list:
    """Body paragraphs and section headings, in the order they appear."""
    return [p for p in table.find_all("p")
            if "footnote" not in (p.get("class") or [])]


def _clean(node) -> str:
    """A paragraph as plain words: footnote markers and stray spaces removed."""
    for sup in node.find_all("sup"):
        sup.decompose()
    text = node.get_text(" ", strip=True)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)      # the markup leaves gaps before punctuation
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_summary(page: str) -> str:
    """
    The article's opening summary: RBI's own account of the month, verbatim.

    It is the first body paragraph, before the Introduction heading. A paragraph
    of an implausible length means the layout has changed, and that raises rather
    than putting the wrong text on the dashboard.
    """
    for para in _paragraphs(_article_table(page)):
        if para.get("class"):
            # The summary sits above the first heading (Introduction, or II.).
            # Reaching one first means the paragraph before it was not the
            # summary, and the next paragraph belongs to a section — quoting it
            # would put a section's opening line on the page as the month's
            # summary, so this stops instead.
            raise SoeError(f"the article reaches the heading {_clean(para)!r} before any "
                           "opening summary; the article's layout has changed")
        text = _clean(para)
        words = len(text.split())
        if words < 20:                               # the date line and other scraps
            continue
        if not (SUMMARY_MIN_WORDS <= words <= SUMMARY_MAX_WORDS):
            raise SoeError(f"the opening paragraph is {words} words, outside the expected "
                           f"{SUMMARY_MIN_WORDS}-{SUMMARY_MAX_WORDS}; the article's layout has changed")
        return text
    raise SoeError("the article has no opening summary")


def parse_conclusion(page: str) -> list[str]:
    """
    The concluding section, verbatim. Empty when an edition has none, which a
    few older editions do not.
    """
    out: list[str] = []
    seen_heading = False
    for para in _paragraphs(_article_table(page)):
        heading = bool(para.get("class"))
        text = _clean(para)
        if heading:
            if seen_heading:                          # the next section (Annex, References)
                break
            seen_heading = re.match(r"(?i)^[IVX]+\.?\s*conclu", text) is not None
            continue
        if seen_heading and len(text.split()) >= 20:
            out.append(text)
            if len(out) == CONCLUSION_MAX_PARAGRAPHS:
                break
    return out


def summary_sentences(summary: str) -> list[str]:
    """
    The summary as sentences, without cutting figures in half.

    "4.45 per cent" and "US$ 44.2 billion" carry full stops that a naive split
    turns into sentence breaks, which is how an early version of this parser
    reported CPI as "from 4."
    """
    guarded = re.sub(r"(\d)\.(\d)", "\\1\x00\\2", summary)
    guarded = re.sub(r"\b(US|Rs|No|Dr|Mr|vs|Prof)\.", "\\1\x00", guarded)
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(])", guarded)
    return [p.replace("\x00", ".").strip() for p in parts if p.strip()]


def parse_topics(page: str) -> dict[str, str]:
    """
    Each section's opening verdict: {topic: RBI's first sentence under that heading}.

    Sections are used rather than the summary because they carry the month's
    figures in RBI's own sentence ("inflation increased marginally to 4.45 per
    cent (y-o-y) in July 2026 from 4.38 per cent in June"), and because the
    summary is already shown in full above. Only the chart pointers RBI writes
    for its own readers are removed; nothing else in the sentence is touched.
    """
    topics: dict[str, str] = {}
    heading: str | None = None
    for para in _paragraphs(_article_table(page)):
        text = _clean(para)
        if para.get("class"):
            heading = text
            continue
        if heading is None:
            continue
        label = next((name for name, pattern in TOPIC_SECTIONS if re.search(pattern, heading)), None)
        if label is None or label in topics:
            continue
        sentence = re.sub(CHART_REFERENCE, "", summary_sentences(text)[0]).strip()
        if len(sentence.split()) >= CHANGES_MIN_WORDS:
            topics[label] = sentence
    return topics


def compare_editions(page: str, month: str, previous_page: str, previous_month: str) -> list[dict]:
    """
    What RBI said about each topic this month, beside what it said last month.

    Only topics both editions cover are returned, in the order of SUMMARY_TOPICS,
    and both sides are quoted verbatim. Nothing here decides whether a topic got
    better or worse: the two sentences say that, in RBI's words.
    """
    now, before = parse_topics(page), parse_topics(previous_page)
    changes = []
    for label, _ in TOPIC_SECTIONS:
        if label in now and label in before and now[label] != before[label]:
            changes.append({
                "topic": label,
                "now": now[label],
                "now_month": month,
                "before": before[label],
                "before_month": previous_month,
            })
    return changes[:CHANGES_MAX]


def parse_briefing(page: str, edition: Edition) -> dict:
    """Everything the India tab shows from one edition."""
    published = published_date(page)
    if edition.month != f"{published:%Y-%m}":
        raise SoeError(f"the {edition.month} article is dated {published}; "
                       "the archive and the article disagree")
    return {
        "month": edition.month,
        "published": published.isoformat(),
        "url": edition.url,
        "summary": parse_summary(page),
        "conclusion": parse_conclusion(page),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


# ── Table IV.3: transmission to deposit and lending rates ──────────────────

def _table_rows(table) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(td) for td in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


def _find_transmission_table(page: str):
    """
    The transmission table itself, not the page table that contains it.

    The whole article sits inside one big <table>, and its text matches any
    caption pattern, so only tables holding no further table are considered.
    """
    for table in _soup(page).find_all("table"):
        if table.find("table") is not None:
            continue
        text = table.get_text(" ", strip=True)
        if re.search(TRANSMISSION_CAPTION, text, re.I) and re.search(r"repo\s*rate", text, re.I):
            return table
    return None


def _column_order(rows: list[list[str]]) -> list[str]:
    """
    Match the table's header cells to the eight columns RBI prints.

    The header is spread over two or three rows and the wording drifts between
    editions, so cells are matched by pattern. If the columns come back in a
    different order, or any is missing, this raises: the alternative is reading
    the deposit figure as a lending figure.
    """
    found: list[str] = []
    for row in rows:
        for cell in row:
            for field, pattern in TRANSMISSION_COLUMNS:
                if re.search(pattern, cell, re.I) and field not in found:
                    found.append(field)
    expected = [field for field, _ in TRANSMISSION_COLUMNS]
    # Trailing optional columns (the "overall interest rate effect", added during
    # 2025) may be absent; everything else must be present and in RBI's order.
    while expected and expected[-1] in TRANSMISSION_OPTIONAL and expected[-1] not in found:
        expected = expected[:-1]
    if found != expected:
        missing = [f for f in expected if f not in found]
        raise SoeError("the transmission table's columns have changed "
                       f"(read {found}, expected {expected}, missing {missing})")
    return expected


def _to_bps(cell: str) -> int | None:
    """One table cell as basis points; blank and dashes mean RBI printed nothing."""
    text = cell.replace("−", "-").replace("–", "-").replace(",", "").strip()
    text = re.sub(r"^\((-?[\d.]+)\)$", r"-\1", text)     # a bracketed figure is negative
    if text in {"", "-", "--", "..", "n.a."}:
        return None
    try:
        value = float(text)
    except ValueError:
        raise SoeError(f"the transmission table holds {cell!r} where a number belongs")
    if abs(value) > MAX_PLAUSIBLE_BPS:
        raise SoeError(f"{value} basis points is not a plausible rate change; "
                       "the table's units have changed")
    return int(round(value))


def _month_key(text: str) -> str:
    """"Jun 2026", "June 2026", "Jun-2026" or "Jun* 2025" -> "2026-06"."""
    text = re.sub(r"[*^#†]", "", text)        # footnote marks sit inside the month cell
    m = re.match(r"(?i)^([A-Za-z]+)[-\s]+(\d{4})$", text.strip())
    if not m:
        raise SoeError(f"could not read {text!r} as a month")
    name = m.group(1).title()
    for i, full in enumerate(MONTHS, start=1):
        if full.startswith(name):
            return f"{m.group(2)}-{i:02d}"
    raise SoeError(f"could not read {text!r} as a month")


def parse_transmission(page: str) -> dict | None:
    """
    Table IV.3 as figures: one entry per cycle (tightening, easing) and per month.

    Returns None when the edition has no such table, which happens in months when
    RBI reports transmission in the text alone. A table that is there but cannot
    be read raises instead, so a layout change is never mistaken for an absence.
    """
    table = _find_transmission_table(page)
    if table is None:
        return None

    rows = _table_rows(table)
    order = _column_order(rows)
    cycles: list[dict] = []
    monthly: list[dict] = []

    # Some editions put the cycle's name on its own row and the dates on the
    # next one, so the name in hand carries forward to the row that follows it.
    named_cycle: str | None = None

    for row in rows:
        label = row[0].strip()
        numbers = [v for v in row[1:] if v != ""]

        if not numbers:
            name = re.match(CYCLE_LABEL_ROW, label)
            if name:
                named_cycle = name.group(1).lower()
            continue

        # Only rows this parser recognises are read. Headers and note rows can
        # hold as many cells as the table has columns, and converting one would
        # turn a column name into a rate change.
        cycle = re.match(CYCLE_ROW, label)
        period = re.match(PERIOD_ROW, label)
        month = re.match(MONTHLY_ROW, label)
        if not (cycle or period or month):
            continue
        if len(numbers) != len(order):
            raise SoeError(f"the transmission row {label!r} has {len(numbers)} figures "
                           f"for {len(order)} columns; the table's layout has changed")
        figures = dict(zip(order, (_to_bps(v) for v in numbers)))

        if cycle or period:
            cycle_type = cycle.group(1).lower() if cycle else named_cycle
            if cycle_type is None:
                raise SoeError(f"the transmission row {label!r} does not say which cycle it belongs to")
            start, end = (cycle.group(2), cycle.group(3)) if cycle else (period.group(1), period.group(2))
            cycles.append({
                "cycle_type": cycle_type,
                "cycle_start": _month_key(start),
                "cycle_end": _month_key(end),
                **figures,
            })
        else:
            monthly.append({"month": _month_key(label), **figures})

    if not cycles:
        raise SoeError("the transmission table has no cycle row; its layout has changed")

    caption = rows[0][0] if rows and rows[0] else ""
    return {"cycles": cycles, "monthly": monthly, "table": caption}


# ═══════════════════════════════════════════
# ONE EDITION, END TO END
# ═══════════════════════════════════════════

def read_edition(session: requests.Session, month: str | None = None,
                 *, use_cache: bool = True) -> tuple[Edition, dict, dict | None]:
    """
    Fetch one edition (the latest when no month is given) and read both parts.

    Returns (edition, briefing, transmission); transmission is None when that
    edition has no table.
    """
    if month is None:
        edition = find_latest(session)
    else:
        edition = find_month(session, month)
        if edition is None:
            raise SoeError(f"the {month} Bulletin has no State of the Economy article")
    page = fetch_article(session, edition, use_cache=use_cache)
    return edition, parse_briefing(page, edition), parse_transmission(page)
