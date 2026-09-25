"""Market discovery is not restricted to the optional priority-company list."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import morning_note as note


class MarketCollectionTests(unittest.TestCase):
    def setUp(self):
        self.asof = datetime.fromisoformat('2026-09-24T09:00:00+09:00')
        self.source = dict(id='market', name='Broad public news', kind='feed', collection_role='market',
                           url='https://example.jp/feed', publisher=True, language='en', timezone='Asia/Tokyo',
                           scope_market='JP', allowed_domains=['example.jp'], enabled=True)
        self.watch = [dict(ticker='1234 JP', name='PriorityCo', aliases=[])]
        self.config = dict(sources=[self.source], lookback_hours=24, max_documents_per_source=2,
                           discovery_mode='market_first', title='Morning note', timezone='Asia/Tokyo',
                           selected_watchlist=self.watch)

    @staticmethod
    def feed(*headlines):
        items = ''.join(f'<item><title>{title}</title><link>https://example.jp/{index}</link>'
                        '<pubDate>Thu, 24 Sep 2026 08:00:00 +0900</pubDate></item>'
                        for index, title in enumerate(headlines))
        return f'<rss><channel>{items}</channel></rss>'.encode()

    @staticmethod
    def article(title):
        data = json.dumps(dict(datePublished='2026-09-24T08:00:00+09:00', headline=title,
                               **{'@type': 'NewsArticle'}))
        return ('<html lang="en"><script type="application/ld+json">' + data + '</script><article><h1>'
                + title + '</h1><p>The transaction is subject to shareholder approval and regulatory clearance.'
                ' Further details are available in the official announcement.</p></article></html>').encode()

    def collect(self, pages, watch=None, config=None):
        fake = Mock()
        fake.get.side_effect = lambda url: (pages[url], 'text/html', url)
        audit = []
        with patch.object(note, 'Fetcher', return_value=fake):
            records, coverage = note.collect(config or self.config, self.watch if watch is None else watch,
                                             [], self.asof, {}, audit)
        return records, coverage, audit, fake

    def test_unknown_issuer_retained_without_inventing_identity(self):
        title = 'UnknownCo announces tender offer for Horizon'
        records, coverage, audit, _ = self.collect({self.source['url']: self.feed(title),
                                                    'https://example.jp/0': self.article(title)})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['tickers'], [])
        self.assertFalse(records[0]['identity_verified'])
        self.assertFalse(records[0]['eligible'])
        self.assertEqual(records[0]['collection_role'], 'market')
        self.assertGreater(records[0]['attention_score'], 80)
        self.assertEqual(audit[0]['stage'], 'article_checked')
        self.assertEqual(coverage[0]['collection_role'], 'market')

    def test_empty_priority_list_still_discovers_market(self):
        title = 'NewCo announces merger with Horizon'
        records, coverage, _, _ = self.collect({self.source['url']: self.feed(title),
                                               'https://example.jp/0': self.article(title)}, watch=[])
        self.assertEqual(len(records), 1)
        self.assertNotEqual(coverage[0]['status'], 'not_applicable')

    def test_all_headlines_are_audited_even_low_ranked(self):
        deal = 'UnknownCo announces tender offer for Horizon'
        records, _, audit, fake = self.collect({self.source['url']: self.feed('City opens a park', deal),
                                               'https://example.jp/1': self.article(deal)})
        self.assertEqual(len(records), 1)
        self.assertEqual(len(audit), 2)
        self.assertEqual(audit[0]['title'], 'City opens a park')
        self.assertEqual(audit[0]['stage'], 'below_attention_threshold')
        self.assertEqual(fake.get.call_count, 2)

    def test_priority_sources_only_run_for_selected_companies_and_market_runs_first(self):
        excluded = dict(self.source, id='other', publisher=False, issuer_official=True,
                        collection_role='priority', tickers=['9999 JP'], url='https://example.jp/other')
        included = dict(excluded, id='selected', tickers=['1234 JP'], url='https://example.jp/selected')
        config = dict(self.config, sources=[excluded, included, self.source])
        _, coverage, _, fake = self.collect({self.source['url']: self.feed(), included['url']: self.feed()}, config=config)
        self.assertEqual(fake.get.call_args_list[0].args[0], self.source['url'])
        self.assertEqual([c for c in coverage if c['id'] == 'other'][0]['status'], 'not_applicable')
        self.assertEqual(fake.get.call_count, 2)

    def test_targeted_default_stays_backward_compatible(self):
        config = dict(self.config)
        del config['discovery_mode']
        records, _, audit, fake = self.collect({self.source['url']: self.feed('UnknownCo announces merger')}, config=config)
        self.assertEqual(records, [])
        self.assertEqual(audit, [])
        self.assertEqual(fake.get.call_count, 1)

    def test_html_index_collects_unknown_names_and_retains_nonfinancial_audit(self):
        source = dict(self.source, kind='html_index', publisher=False, link_xpath='//a[@href]')
        title = 'NewCo announces merger with Horizon'
        index = ('<a href="/0">' + title + '</a><a href="/1">City opens a park</a>').encode()
        records, _, audit, fake = self.collect({source['url']: index, 'https://example.jp/0': self.article(title)},
                                               config=dict(self.config, sources=[source]), watch=[])
        self.assertEqual(len(records), 1)
        self.assertEqual(len(audit), 2)
        self.assertEqual(fake.get.call_count, 2)

    def test_render_exports_audit_and_outside_list_candidates(self):
        title = 'UnknownCo announces tender offer for Horizon'
        records, coverage, audit, _ = self.collect({self.source['url']: self.feed(title, 'City opens park'),
                                                    'https://example.jp/0': self.article(title)})
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            note.render(records, coverage, dict(self.config, discovery_log=audit), self.asof, out)
            saved = json.loads((out / 'headline-audit.json').read_text(encoding='utf-8'))
            self.assertEqual(len(saved['headlines']), 2)
            payload = json.loads((out / 'draft-payload.json').read_text(encoding='utf-8'))
            self.assertEqual(payload['items'][0]['tickers'], [])
            self.assertEqual(payload['items'][0]['collection_role'], 'market')
            self.assertGreater(payload['items'][0]['attention_score'], 80)
            review = (out / 'review.html').read_text(encoding='utf-8')
            self.assertIn('2 market headlines scanned', review)
            self.assertIn('market-radar', review)
            self.assertNotIn(title, (out / 'email.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
