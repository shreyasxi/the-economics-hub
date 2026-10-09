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

from data.processors.rbi_soe import SoeError
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


def _html_table(rows):
    return "<table>" + "".join(
        "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>"
        for row in rows) + "</table>"


def _numbered_table(page):
    """Use RBI's printed column numbers and grid boundaries, not PDF text order."""
    words = page.extract_words()
    starts = [w for w in words if w["text"] == "(1)"]
    for first in starts:
        numbered = sorted([w for w in words if abs(w["top"]-first["top"]) < 2
                           and re.fullmatch(r"\(\d+\)", w["text"])], key=lambda w: w["x0"])
        if [w["text"] for w in numbered] not in [
                [f"({i})" for i in range(1, 9)], [f"({i})" for i in range(1, 10)]]:
            continue
        top = first["top"]
        period = [w for w in words if w["text"].lower() == "period" and top-100 < w["top"] < top]
        if not period:
            continue
        header_top = min(w["top"] for w in period) - 2
        centers = [(w["x0"] + w["x1"])/2 for w in numbered]
        boundaries = [0.0]
        for left, right in zip(centers, centers[1:]):
            edges = [e["x0"] for e in page.edges if e["orientation"] == "v"
                     and left < e["x0"] < right and header_top <= e["top"] < top]
            if not edges:
                raise SoeError("PDF transmission column boundary is missing")
            boundaries.append(sorted(edges)[len(edges)//2])
        boundaries.append(float(page.width))
        headers = [_text(page.crop((l, header_top, r, top-1)).extract_text() or "")
                   for l, r in zip(boundaries, boundaries[1:])]
        if not any(re.search(r"repo\s*rate", h, re.I) for h in headers):
            continue
        # Stop at the first notes/source line below the numbered header.
        notes = [w["top"] for w in words if w["top"] > top+10
                 and (w["text"] in {"#:", "Note:", "Source:", "WALR:"})]
        if not notes:
            raise SoeError("PDF transmission table has no identifiable end")
        bottom = min(notes)
        lines = []
        for w in sorted((w for w in words if top+8 < w["top"] < bottom),
                        key=lambda w: (w["top"], w["x0"])):
            if not lines or abs(w["top"]-lines[-1][0]) > 2:
                lines.append((w["top"], []))
            lines[-1][1].append(w)
        rows = [["Transmission to Banks' Deposit and Lending Rates"], headers]
        for _, line in lines:
            cells = ["" for _ in numbered]
            for w in sorted(line, key=lambda w: w["x0"]):
                center = (w["x0"] + w["x1"])/2
                col = next(i for i, (l, r) in enumerate(zip(boundaries, boundaries[1:])) if l <= center < r)
                cells[col] = (cells[col] + " " + w["text"]).strip()
            if any(cells[1:]):
                rows.append(cells)
            elif re.match(r"(?i)^(tightening|easing)", cells[0]):
                rows.append(cells)
            elif re.search(r"\d{4}.*to.*\d{4}", cells[0]) and len(rows) > 2:
                rows[-1][0] += " " + cells[0]
        return _html_table(rows)
    return None


def _transmission_tables(page):
    numbered = _numbered_table(page)
    if numbered:
        return [numbered]
    result = []
    for table in page.find_tables():
        rows = [[_text(c or "") for c in row] for row in table.extract()]
        flat = " ".join(" ".join(r) for r in rows)
        if not (re.search(r"repo\s*rate", flat, re.I) and re.search(r"WALR", flat, re.I)):
            continue
        start = next((i for i, r in enumerate(rows) if r and re.match(
            r"(?i)^(tightening|easing|[A-Z][a-z]{2,8}[- *]+\d{4})", r[0])), None)
        if start is None:
            raise SoeError("PDF transmission table has no recognised data rows")
        count = max(map(len, rows[:start]), default=0)
        headers = [" ".join(r[i] for r in rows[:start] if i < len(r)) for i in range(count)]
        result.append(_html_table([["Transmission to Banks' Deposit and Lending Rates"], headers] + rows[start:]))
    return result


def _prose(doc):
    """Reassemble body-size lines into paragraphs across columns and pages.

    RBI exports some paragraphs as one PDF block per line. Indentation marks a
    new paragraph; a column or page break does not. Smaller chart/footnote text
    is excluded, as are chart/table captions and running headers.
    """
    from collections import Counter
    sizes = Counter()
    for block in doc[0].get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if 9 <= span["size"] <= 14:
                    sizes[round(span["size"])] += len(span["text"])
    if not sizes:
        raise SoeError("PDF has no readable body text")
    body_size = sizes.most_common(1)[0][0]
    paragraphs, pending = [], []
    def flush():
        if pending:
            text = ""
            for part in pending:
                text += ("" if not text or text.endswith("-") else " ") + part
            paragraphs.append(f"<p>{escape(text)}</p>")
            pending.clear()
    for page in doc:
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                full_text = _text("".join(s["text"] for s in line["spans"]))
                is_heading = re.fullmatch(r"(?:[IVX]+\.\s*)?(?:Introduction|Conclusion)|Annex(?:ure)?|References", full_text, re.I)
                spans = [s for s in line["spans"] if abs(s["size"]-body_size) < 0.6 or is_heading
                         or (s["flags"] & 1 and s["text"].strip() in {"st", "nd", "rd", "th"})]
                if not spans:
                    continue
                text = _text("".join(s["text"] for s in spans))
                if not text or text.rstrip("*").casefold() == ARTICLE_TITLE.casefold():
                    continue
                if re.match(r"(?i)^(RBI Bulletin|ARTICLE$|(?:Annex )?(?:Chart|Table)\s+[A-Z0-9])", text):
                    continue
                lines.append((line["bbox"], text, spans))
        # Left/right columns are determined by the line's left edge.
        lines.sort(key=lambda item: (item[0][0] >= page.rect.width/2, item[0][1]))
        bases = {}
        for bbox, _, _ in lines:
            col = bbox[0] >= page.rect.width/2
            bases[col] = min(bases.get(col, bbox[0]), bbox[0])
        for bbox, text, spans in lines:
            heading = (re.fullmatch(r"(?:[IVX]+\.\s*)?(?:Introduction|Conclusion)|Annex(?:ure)?|References", text, re.I)
                       or (len(text.split()) < 14 and all("Bold" in s["font"] for s in spans)))
            if heading:
                flush()
                paragraphs.append(f'<p class="head">{escape(text)}</p>')
                if re.fullmatch(r"Annex(?:ure)?|References", text, re.I):
                    return paragraphs
            else:
                col = bbox[0] >= page.rect.width/2
                if bbox[0] - bases[col] > 10 and pending:
                    flush()
                pending.append(text)
    flush()
    return paragraphs


def _extract(payload, month, source_url, published):
    tables_html, raw_text = [], []
    with fitz.open(stream=payload, filetype="pdf") as doc, pdfplumber.open(BytesIO(payload)) as pdf:
        if not doc.page_count:
            raise SoeError("empty RBI PDF")
        first = doc[0].get_text()
        if ARTICLE_TITLE.casefold() not in _text(first).casefold():
            raise SoeError("PDF is not a State of the Economy article")
        if not re.search(published.strftime("%B") + r"\s+" + published.strftime("%Y"), _text(first), re.I):
            raise SoeError("PDF's printed Bulletin month does not match its URL")
        paragraphs = _prose(doc)
        for page, pp in zip(doc, pdf.pages):
            text = page.get_text()
            raw_text.append(text)
            if re.search(r"repo\s*rate", text, re.I) and re.search(r"WADTDR", text, re.I):
                tables_html.extend(_transmission_tables(pp))
    if not any(re.search(r">(?:I\.\s*)?Introduction<", p, re.I) for p in paragraphs):
        raise SoeError("PDF introduction heading not recognised; cannot safely identify its summary")
    raw = _text(" ".join(raw_text))
    if re.search(r"repo\s*rate", raw, re.I) and re.search(r"WAD TDR|WADTDR", raw, re.I) and not tables_html:
        raise SoeError("PDF mentions transmission rates but its table could not be extracted; review required")
    return (f'<meta name="soe-source" content="{escape(source_url, quote=True)}">'
            f'<table><tr><td><b>{ARTICLE_TITLE}</b>'
            f'<p>Date : {published:%b %d, %Y}</p>' + "".join(paragraphs)
            + "".join(tables_html) + "</td></tr></table>")
