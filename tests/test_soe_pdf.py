"""Offline tests for PDF-only discovery, HTML priority and PDF safeguards."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fitz
from data.processors import rbi_soe as soe
from data.processors.rbi_soe_pdf import pdf_to_article

URL = 'https://rbidocs.rbi.org.in/rdocs/Bulletin/PDFs/1ARTICLE25092026ABC.PDF'
EDITION = soe.Edition('2026-09', '123', 'https://rbi.org.in/scripts/BS_ViewBulletin.aspx?Id=123', URL)
SUMMARY = ('The global economy continues to face uncertainty as trade policies evolve. '
           'Domestic activity remains resilient, supported by consumption and investment. '
           'Inflation has moderated while monetary conditions have eased. '
           'Exports and imports reflect changing global demand. '
           'Financial markets remain sensitive to developments in the global economy and the outlook for growth.')


def make_pdf(month='September 2026', table=False):
    doc = fitz.open()
    page = doc.new_page(width=620, height=800)
    page.insert_text((40, 35), 'State of the Economy')
    page.insert_textbox(fitz.Rect(40, 60, 295, 200), SUMMARY, fontsize=10)
    page.insert_text((40, 220), 'I. Introduction')
    page.insert_text((40, 250), 'Activity remained resilient during the month.')
    page.insert_text((330, 60), 'V. Conclusion')
    page.insert_textbox(fitz.Rect(330, 80, 590, 200), SUMMARY, fontsize=10)
    page.insert_text((40, 775), 'RBI Bulletin ' + month)
    if table:
        page.insert_text((40, 300), 'Repo Rate and WADTDR transmission table')
    payload = doc.tobytes()
    doc.close()
    return payload


def make_table_pdf():
    doc = fitz.open(stream=make_pdf(), filetype='pdf')
    page = doc.new_page(width=1100, height=800)
    xs = [30, 270, 360, 450, 540, 630, 720, 810, 900, 990]
    rows = [
        ['Period', 'Repo Rate', 'WADTDR Fresh', 'WADTDR Outstanding', 'EBLR', 'MCLR', 'WALR Fresh', 'Interest Rate Effect', 'WALR Outstanding'],
        ['Easing Cycle Feb 2025 to Jul 2026', '-125', '-65', '-52', '-125', '-50', '-80', '-79', '-91'],
        ['Jul 2026', '0', '-2', '-1', '0', '0', '-3', '-2', '-2'],
    ]
    for y in [100, 155, 210, 265]:
        page.draw_line((xs[0], y), (xs[-1], y))
    for x in xs:
        page.draw_line((x, 100), (x, 265))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            page.insert_textbox(fitz.Rect(xs[c]+4, 105+r*55, xs[c+1]-4, 150+r*55), text, fontsize=9)
    payload = doc.tobytes()
    doc.close()
    return payload


class PdfFallbackTests(unittest.TestCase):
    def test_pdf_only_row_with_plain_title(self):
        page = f'<h1>Reserve Bank of India Bulletin - September 2026</h1><table><tr><td>State of the Economy</td><td></td><td><a href="{URL}"><img alt="PDF"></a></td></tr></table>'
        e = soe._edition_from_contents(page)
        self.assertEqual(e.month, '2026-09')
        self.assertEqual(e.url, URL)

    def test_both_links_prefer_html(self):
        page = f'<table><tr><td><a href="BS_ViewBulletin.aspx?Id=123">State of the Economy</a></td><td><a href="{URL}">PDF</a></td></tr></table>'
        e = soe._edition_from_contents(page, '2026-09')
        self.assertEqual(e.article_id, '123')
        self.assertEqual(e.pdf_url, URL)
        self.assertIn('Id=123', e.url)

    def test_good_html_does_not_fetch_pdf(self):
        page = Path('tests/fixtures/soe/2026-08.html').read_text()
        e = soe.Edition('2026-08', '1', 'https://rbi.org.in/?Id=1', URL)
        with tempfile.TemporaryDirectory() as tmp, patch.object(soe, 'CACHE_DIR', Path(tmp)), patch.object(soe, '_request', return_value=page), patch.object(soe, '_request_pdf') as pdf:
            self.assertEqual(soe.fetch_article(Mock(), e), page)
            pdf.assert_not_called()

    def test_html_failure_falls_back_and_credits_pdf(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(soe, 'CACHE_DIR', Path(tmp)), patch.object(soe, '_request', side_effect=soe.SoeError('blocked')), patch.object(soe, '_request_pdf', return_value=make_pdf()):
            page = soe.fetch_article(Mock(), EDITION)
            briefing = soe.parse_briefing(page, EDITION)
            self.assertEqual(briefing['url'], URL)
            self.assertEqual(briefing['summary'], SUMMARY)
            self.assertEqual(briefing['conclusion'], [SUMMARY])
            self.assertTrue((Path(tmp)/'2026-09.pdf').exists())
            self.assertFalse((Path(tmp)/'2026-09.html').exists())

    def test_captcha_is_not_cached_or_retried(self):
        session = Mock()
        session.get.return_value.content = b'<html>CAPTCHA</html>'
        with self.assertRaisesRegex(soe.SoeError, 'non-PDF'):
            soe._request_pdf(session, URL)
        self.assertEqual(session.get.call_count, 1)

    def test_wrong_printed_month_rejected(self):
        with self.assertRaisesRegex(soe.SoeError, 'printed Bulletin month'):
            pdf_to_article(make_pdf('August 2026'), '2026-09', URL)

    def test_unreadable_transmission_is_not_silently_absent(self):
        with self.assertRaisesRegex(soe.SoeError, 'table could not be extracted'):
            pdf_to_article(make_pdf(table=True), '2026-09', URL)

    def test_pdf_transmission_keeps_column_identity_and_signs(self):
        page = pdf_to_article(make_table_pdf(), '2026-09', URL)
        transmission = soe.parse_transmission(page)
        self.assertEqual(transmission['cycles'][0]['wadtdr_fresh_bps'], -65)
        self.assertEqual(transmission['cycles'][0]['walr_fresh_bps'], -80)
        self.assertEqual(transmission['cycles'][0]['cycle_end'], '2026-07')
        self.assertEqual(transmission['monthly'][0]['repo_bps'], 0)

    def test_real_september_pdf_summary_conclusion_and_columns(self):
        source = 'https://rbidocs.rbi.org.in/rdocs/Bulletin/PDFs/1ARTICLE25092026551C90FB61784218909A840A2A4F1E39.PDF'
        payload = Path('tests/fixtures/soe/2026-09.pdf').read_bytes()
        page = pdf_to_article(payload, '2026-09', source)
        brief = soe.parse_briefing(page, soe.Edition('2026-09', '', source))
        self.assertTrue(brief['summary'].startswith('With geopolitical tensions re-escalating'))
        self.assertTrue(brief['summary'].endswith('foreign exchange reserves reached an all time high.'))
        self.assertEqual(len(brief['summary'].split()), 125)
        self.assertEqual(len(brief['conclusion']), 1)
        self.assertTrue(brief['conclusion'][0].endswith('Overall, the economy performed strongly despite external headwinds.'))
        self.assertIn('System liquidity remained in surplus', brief['conclusion'][0])
        self.assertNotIn('Chart', brief['conclusion'][0])
        self.assertNotIn('Source:', brief['conclusion'][0])
        topics = soe.parse_topics(page)
        self.assertEqual(len(topics), 5)
        self.assertIn('4.8 per cent', topics['Inflation'])
        self.assertNotIn('Chart', topics['Inflation'])
        table = soe.parse_transmission(page)
        easing = table['cycles'][-1]
        self.assertEqual(easing['walr_outstanding_bps'], -90)  # last printed column
        self.assertEqual(easing['overall_bps'], -75)          # interest-rate effect
        self.assertEqual(easing['walr_fresh_bps'], -81)
        self.assertEqual(easing['wadtdr_fresh_bps'], -72)
        self.assertEqual(table['monthly'][-1]['repo_bps'], 0)
        self.assertEqual(table['monthly'][-1]['wadtdr_fresh_bps'], -9)

    def test_latest_month_needs_no_archive_post(self):
        page = f'<h1>Bulletin - September 2026</h1><table><tr><td>State of the Economy</td><td><a href="{URL}">PDF</a></td></tr></table>'
        with patch.object(soe, '_request', return_value=page) as request:
            self.assertEqual(soe.find_month(Mock(), '2026-09').url, URL)
            self.assertEqual(request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
