"""Convert text-based RBI article PDFs to the existing validated parser input.

PDFs are not OCR'd or summarised. Unrecognised layouts fail closed, particularly
for transmission tables: we never infer a column from its numeric position.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
import re

import fitz
import pdfplumber

from data.rbi_soe import SoeError
from config.soe_settings import ARTICLE_TITLE


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00ad", "")).strip()


def pdf_to_article(payload: bytes, month: str, source_url: str) -> str:
    if not payload.startswith(b"%PDF-"):
        raise SoeError("not a PDF: RBI may have returned a CAPTCHA page")
    # RBI article filenames carry their publication date, not the data month.
    stamp = re.search(r"ARTICLE(\d{8})", source_url, re.I)
    if not stamp:
        raise SoeError("PDF URL has no identifiable RBI publication date")
    try:
        published = datetime.strptime(stamp.group(1), "%d%m%Y")
    except ValueError as exc:
        raise SoeError("invalid publication date in RBI PDF URL") from exc
    if published.strftime("%Y-%m") != month:
        raise SoeError("PDF publication date does not match the requested edition")
    try:
        return _extract(payload, month, source_url, published)
    except SoeError:
        raise
    except Exception as exc:
        raise SoeError(f"could not extract RBI PDF: {exc}") from exc


def _extract(payload, month, source_url, published):
    paragraphs = []
    tables_html = []
    raw_text = []
    heading_re = re.compile(
        r"^(?:[IVX]+\.\s+.+|Inflation|Aggregate Demand|Aggregate Supply|"
        r"Financial Conditions|References|Annex(?:ure)?.*)$", re.I)
    with fitz.open(stream=payload, filetype="pdf") as doc, pdfplumber.open(BytesIO(payload)) as pdf:
        if not doc.page_count:
            raise SoeError("empty RBI PDF")
        first = doc[0].get_text()
        if ARTICLE_TITLE.casefold() not in _text(first).casefold():
            raise SoeError("PDF is not a State of the Economy article")
        # A filename alone is insufficient: the printed Bulletin month must agree.
        if not re.search(published.strftime("%B") + r"\s+" + published.strftime("%Y"),
                         _text(first), re.I):
            raise SoeError("PDF's printed Bulletin month does not match its URL")
        for page, pp in zip(doc, pdf.pages):
            raw_text.append(page.get_text())
            excluded = []
            for table in pp.find_tables():
                rows = [[_text(c or "") for c in row] for row in table.extract()]
                flat = " ".join(" ".join(r) for r in rows)
                if not (re.search(r"repo\s*rate", flat, re.I) and re.search(r"WALR", flat, re.I)):
                    continue
                excluded.append(table.bbox)
                # Headers may span several rows. Join vertically per column,
                # stopping before the first cycle/data row.
                start = next((i for i, r in enumerate(rows) if r and re.match(
                    r"(?i)^(tightening|easing|[A-Z][a-z]{2,8}[- *]+\d{4})", r[0])), None)
                if start is None:
                    raise SoeError("PDF transmission table has no recognised data rows")
                count = max(map(len, rows[:start]), default=0)
                headers = [" ".join(r[i] for r in rows[:start] if i < len(r)) for i in range(count)]
                # Let the HTML parser validate semantic column names and values.
                body = [["Transmission to Banks' Deposit and Lending Rates"], headers] + rows[start:]
                tables_html.append("<table>" + "".join(
                    "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>"
                    for r in body) + "</table>")
            blocks = page.get_text("dict")["blocks"]
            # RBI's two-column prose reads down the left column, then the right.
            blocks = sorted((b for b in blocks if "lines" in b),
                            key=lambda b: (b["bbox"][0] >= page.rect.width / 2, b["bbox"][1]))
            for block in blocks:
                x0, y0, x1, y1 = block["bbox"]
                if any(x0 >= l-2 and x1 <= r+2 and y0 >= t-2 and y1 <= b+2
                       for l, t, r, b in excluded):
                    continue
                lines = []
                for line in block["lines"]:
                    # Superscript footnote markers are not part of the quotation.
                    line_text = "".join(s["text"] for s in line["spans"] if not s["flags"] & 1)
                    lines.append(_text(line_text))
                text = _text(" ".join(lines))
                if not text or text.casefold() == ARTICLE_TITLE.casefold():
                    continue
                if re.match(r"(?i)^RBI Bulletin\b", text) or text.isdigit() or text == "ARTICLE":
                    continue
                if heading_re.fullmatch(text):
                    paragraphs.append(f'<p class="head">{escape(text)}</p>')
                else:
                    paragraphs.append(f"<p>{escape(text)}</p>")
    if not any(re.search(r">I\.\s*Introduction<", p, re.I) for p in paragraphs):
        raise SoeError("PDF introduction heading not recognised; cannot safely identify its summary")
    raw = _text(" ".join(raw_text))
    if re.search(r"repo\s*rate", raw, re.I) and re.search(r"WAD TDR|WADTDR", raw, re.I) and not tables_html:
        raise SoeError("PDF mentions transmission rates but its table could not be extracted; review required")
    return (f'<meta name="soe-source" content="{escape(source_url, quote=True)}">'
            f'<table><tr><td><b>{ARTICLE_TITLE}</b>'
            f'<p>Date : {published:%b %d, %Y}</p>' + "".join(paragraphs)
            + "</td></tr></table>" + "".join(tables_html))
