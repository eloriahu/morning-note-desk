"""Official issuer announcements remain attributable without a name in the title."""
import sys
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import morning_note as note


class IssuerSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            'id': 'example-ir', 'name': 'Example official announcements', 'kind': 'issuer_index',
            'url': 'https://example.com/ir', 'allowed_domains': ['example.com'],
            'item_xpath': '//li', 'item_link_xpath': './a', 'title_xpath': './a/span',
            'date_xpath': './time/text()', 'issuer_official': True, 'tickers': ['1234 JP'],
            'language': 'en', 'timezone': 'Asia/Tokyo', 'enabled': True,
        }
        self.watch = [{'ticker': '1234 JP', 'name': 'Example Company', 'aliases': []}]
        self.config = {'sources': [self.source], 'lookback_hours': 24}
        self.asof = datetime.fromisoformat('2026-09-24T15:00:00+09:00')

    def collect(self, publication, *, pdf=False, watch=None):
        index = ('<html><li><time>' + publication + '</time><a href="/release"><span>Revised offer terms</span></a></li></html>').encode()
        article = b'<html lang="en"><article><h1>Revised offer terms</h1><p>The directors announced revised offer terms and a later acceptance deadline following the board meeting.</p></article></html>'
        fake = Mock()
        fake.get.side_effect = [(index, 'text/html', self.source['url']),
                                (b'%PDFfixture' if pdf else article, 'application/pdf' if pdf else 'text/html', 'https://example.com/release')]
        with patch.object(note, 'Fetcher', return_value=fake):
            records, coverage = note.collect(self.config, self.watch if watch is None else watch, [], self.asof, {})
        return records, coverage, fake

    def test_fixed_issuer_dated_announcement_needs_no_company_name_in_title(self):
        records, coverage, _ = self.collect('2026-09-24T08:30:00+09:00')
        self.assertEqual(records[0]['title'], 'Revised offer terms')
        self.assertEqual(records[0]['tickers'], ['1234 JP'])
        self.assertTrue(records[0]['eligible'])
        self.assertTrue(coverage[0]['issuer_official'])
        self.assertEqual(coverage[0]['articles_attempted'], 1)

    def test_english_date_only_stays_visible_but_held(self):
        records, _, _ = self.collect('Sep 24, 2026')
        self.assertEqual(records[0]['date_precision'], 'day')
        self.assertFalse(records[0]['eligible'])
        self.assertEqual(records[0]['published'], '2026-09-24T00:00:00+09:00')

    def test_official_pdf_uses_index_date_and_verified_issuer(self):
        with patch.object(note, 'extract_document', return_value={'title': '', 'text': 'Official offer document text.', 'published': ''}) as reader:
            records, _, _ = self.collect('2026/09/24', pdf=True)
        reader.assert_called_once()
        self.assertEqual(records[0]['evidence_level'], 'official_pdf_text')
        self.assertEqual(records[0]['title'], 'Revised offer terms')
        self.assertFalse(records[0]['eligible'])

    def test_issuer_not_selected_is_skipped_without_network(self):
        records, coverage, fetcher = self.collect('Sep 24, 2026', watch=[{'ticker': 'OTHER AU', 'name': 'Other Company'}])
        self.assertEqual(records, [])
        self.assertEqual(coverage[0]['status'], 'not_applicable')
        fetcher.get.assert_not_called()

    def test_unknown_date_is_not_replaced_by_today(self):
        records, _, _ = self.collect('September issue')
        self.assertIsNone(records[0]['published'])
        self.assertFalse(records[0]['eligible'])

    def test_public_widget_uses_displayed_day_not_internal_timestamp(self):
        source = dict(self.source, callback='public_news', date_field='format_date',
                      language='ja', language_field='sub_type', language_mapping={'english': 'en'})
        data = {'item': [{'title': 'Offer update', 'link': 'https://example.com/release',
                         'date': '2026/09/24 12:05:17', 'format_date': '2026年09月24日', 'sub_type': 'english'}]}
        raw = ('public_news(' + json.dumps(data) + ');').encode()
        records = note.issuer_jsonp_items(raw, source)
        self.assertEqual(records[0]['published'], '2026年09月24日')
        self.assertEqual(records[0]['language'], 'en')
        self.assertEqual(note.parse_date(records[0]['published'], 'Asia/Tokyo')[1], 'day')

    def test_widget_never_executes_javascript_or_accepts_extra_statements(self):
        source = dict(self.source, callback='public_news')
        for raw in [b'public_news({"item":[]}); doSomething();', b'other_callback({"item":[]});',
                    b'public_news({item: process.exit()});']:
            with self.assertRaises(ValueError):
                note.issuer_jsonp_items(raw, source)

    def test_english_pdf_language_survives_mixed_language_source(self):
        source = dict(self.source, kind='issuer_jsonp', callback='public_news', language='ja',
                      date_field='format_date', language_field='sub_type', language_mapping={'english': 'en'})
        payload = {'item': [{'title': 'Revised offer terms', 'link': 'https://example.com/release.pdf',
                            'format_date': '2026年09月24日', 'sub_type': 'english'}]}
        fake = Mock()
        fake.get.side_effect = [(('public_news(' + json.dumps(payload) + ');').encode(), 'text/javascript', source['url']),
                                (b'%PDFfixture', 'application/pdf', 'https://example.com/release.pdf')]
        with patch.object(note, 'Fetcher', return_value=fake), patch.object(note, 'extract_document', return_value={'title': '', 'text': 'Official English offer document.', 'published': ''}):
            records, _ = note.collect(dict(self.config, sources=[source]), self.watch, [], self.asof, {})
        self.assertEqual(records[0]['language'], 'en')
        self.assertFalse(any('translation' in flag.lower() or 'English summary' in flag for flag in records[0]['flags']))
        self.assertFalse(records[0]['eligible'])  # Date-only remains unresolved.

    def test_changing_landing_page_is_held_without_reading_it_as_article(self):
        self.source['article_url_pattern'] = r'\.pdf$'
        records, coverage, fetcher = self.collect('2026-09-24T08:30:00+09:00')
        self.assertFalse(records[0]['eligible'])
        self.assertEqual(records[0]['text'], '')
        self.assertEqual(coverage[0]['status'], 'partial')
        self.assertEqual(fetcher.get.call_count, 1)


if __name__ == '__main__':
    unittest.main()
