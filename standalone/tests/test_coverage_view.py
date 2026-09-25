import sys
import unittest
from pathlib import Path

from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coverage_view import render_watchlist_overview


class CoverageViewTests(unittest.TestCase):
    watchlist = [{"ticker": "1001 JP", "name": "Company One"},
                 {"ticker": "1002 JP", "name": "Company Two"},
                 {"ticker": "ABC AU", "name": "Company Three"}]

    def render(self, records=(), coverage=(), watchlist=None):
        return html.fromstring(render_watchlist_overview(
            self.watchlist if watchlist is None else watchlist, records, coverage))

    @staticmethod
    def row(doc, ticker):
        return doc.xpath('//tr[@data-ticker=$ticker]', ticker=ticker)[0].text_content()

    def test_all_companies_visible_even_with_only_one_story(self):
        doc = self.render([{"tickers": ["1001 JP"], "eligible": True}])
        self.assertEqual(len(doc.xpath('//tbody/tr')), 3)
        self.assertIn("3 companies tracked", doc.text_content())
        self.assertIn("1 with draft-ready candidates", doc.text_content())
        self.assertIn("1 draft-ready candidate", self.row(doc, "1001 JP"))
        self.assertIn("No sources checked", self.row(doc, "1002 JP"))

    def test_general_publisher_is_not_an_official_company_connection(self):
        doc = self.render(coverage=[{"status": "ok", "scope_tickers": ["1001 JP", "1002 JP"],
                                   "name": "Publisher", "url": "https://example.jp/news"}])
        self.assertIn("Needs a direct source", self.row(doc, "1001 JP"))
        self.assertIn("No matching items in limited general news", self.row(doc, "1001 JP"))
        self.assertIn("No sources checked", self.row(doc, "ABC AU"))
        self.assertIn("0 with an official company source connected", doc.text_content())

    def test_official_requires_explicit_marker_and_ticker(self):
        coverage = [{"status": "ok", "tickers": ["1001 JP"], "issuer_official": True},
                    {"status": "ok", "tickers": ["1002 JP"]},
                    {"status": "ok", "issuer_official": True, "scope_tickers": ["ABC AU"]}]
        doc = self.render(coverage=coverage)
        self.assertIn("Connected (1)", self.row(doc, "1001 JP"))
        self.assertIn("Needs a direct source", self.row(doc, "1002 JP"))
        self.assertIn("Needs a direct source", self.row(doc, "ABC AU"))
        self.assertIn("1 with an official company source connected", doc.text_content())

    def test_failed_disabled_and_partial_direct_sources_are_explicit(self):
        doc = self.render(coverage=[
            {"status": "failed", "issuer_official": True, "tickers": ["1001 JP"]},
            {"status": "disabled", "issuer_official": True, "tickers": ["1002 JP"]},
            {"status": "partial", "issuer_official": True, "tickers": ["ABC AU"]}])
        self.assertIn("Direct source failed", self.row(doc, "1001 JP"))
        self.assertIn("Direct source disabled", self.row(doc, "1002 JP"))
        self.assertIn("Connected (1)", self.row(doc, "ABC AU"))
        self.assertIn("1 (1 partial)", self.row(doc, "ABC AU"))

    def test_scope_and_search_success_filter_checked_source_count(self):
        doc = self.render(coverage=[
            {"status": "ok", "scope_tickers": []},
            {"status": "ok", "scope_market": "AU"},
            {"status": "partial", "scope_tickers": ["1001 JP", "1002 JP"],
             "successful_tickers": ["1001 JP"]}])
        rows = {node.attrib["data-ticker"]: node for node in doc.xpath('//tbody/tr')}
        self.assertEqual(rows["1001 JP"].xpath('./td')[3].text, "1 (1 partial)")
        self.assertEqual(rows["1002 JP"].xpath('./td')[3].text, "0")
        self.assertEqual(rows["ABC AU"].xpath('./td')[3].text, "1")
        self.assertIn("No sources checked", self.row(doc, "1002 JP"))

    def test_review_and_ready_counts_are_by_company(self):
        doc = self.render(records=[
            {"tickers": ["1001 JP", "1002 JP"], "eligible": True},
            {"tickers": ["1001 JP"], "eligible": True},
            {"tickers": ["1001 JP"], "eligible": False},
            {"tickers": ["ABC AU"]}])
        self.assertIn("2 with draft-ready candidates", doc.text_content())
        self.assertIn("2 with leads to review", doc.text_content())
        self.assertIn("2 draft-ready candidates; 1 lead to review", self.row(doc, "1001 JP"))
        self.assertIn("1 lead to review", self.row(doc, "ABC AU"))

    def test_links_and_source_company_text_are_safe(self):
        doc = self.render(watchlist=[{"ticker": 'A" JP', "name": '<script>alert(1)</script>'}],
                          coverage=[
                              {"status": "ok", "name": '<img src=x onerror=alert(1)>',
                               "url": 'https://example.jp/?x="&y=1'},
                              {"status": "failed", "url": "javascript:alert(1)"},
                              {"status": "disabled", "url": "file:///C:/private.txt"},
                              {"status": "ok", "url": "https://user:password@example.jp/"},
                              {"status": "ok", "url": "https://example.jp:broken/"}])
        self.assertEqual(len(doc.xpath('//a')), 1)
        self.assertFalse(doc.xpath('//script | //img'))
        self.assertEqual(doc.xpath('//a')[0].get('href'), 'https://example.jp/?x="&y=1')
        self.assertEqual(doc.xpath('//a')[0].get('rel'), 'noopener noreferrer')
        self.assertIn('<script>alert(1)</script>', doc.text_content())

    def test_one_company_and_empty_watchlists_are_clear(self):
        self.assertIn("1 company tracked", self.render(watchlist=self.watchlist[:1]).text_content())
        empty = self.render(watchlist=[])
        self.assertIn("0 companies tracked", empty.text_content())
        self.assertIn("No companies are configured", empty.text_content())
        self.assertFalse(empty.xpath('//tbody/tr'))


if __name__ == "__main__":
    unittest.main()
