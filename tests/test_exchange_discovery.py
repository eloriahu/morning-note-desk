import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT if (ROOT / 'morning_note.py').exists() else ROOT / 'collector'))
from exchange_discovery import asx_items, nzx_items, tdnet_items, hkex_items, collect_exchange
from morning_note import expand_publisher_leads, classify_record, resolve_lookback_hours


class ExchangeDiscoveryTests(unittest.TestCase):
    def test_monday_default_and_explicit_override(self):
        monday = datetime.fromisoformat('2026-09-28T08:22:51+08:00')
        config = dict(lookback_hours=24, monday_lookback_hours=72)
        self.assertEqual(resolve_lookback_hours(monday, config), 72)
        self.assertEqual(resolve_lookback_hours(monday, config, 24), 24)
        self.assertEqual(resolve_lookback_hours(monday.replace(day=29), config), 24)

    def test_asx_timestamp_and_clean_title(self):
        raw = b'<table><tr><td>CWY</td><td>28/09/2026 <span>8:24 am</span></td><td></td><td><a href="displayAnnouncement.do?idsId=123">Scheme update<br/>3 pages</a></td></tr></table>'
        row = asx_items(raw, 'https://www.asx.com.au/')[0]
        self.assertEqual(row['published'], '2026-09-28T08:24:00+10:00')
        self.assertEqual(row['title'], 'CWY AU Scheme update')

    def test_nzx_daylight_saving_transition(self):
        raw = b'<table><tr class="announcement"><td class="code">SKT</td><td class="title"><a href="announcement/1">Scheme update</a></td><td class="date"><span>28/09/2026 08:00 NZDT</span></td></tr></table>'
        row = nzx_items(raw, 'https://announcements.nzx.com/')[0]
        self.assertEqual(row['published'], '2026-09-28T08:00:00+13:00')

    def test_tdnet_japanese_and_same_day_pagination(self):
        raw = '''<table id="main-list-table"><tr><td class="kjTime">16:00</td><td class="kjCode">65940</td><td class="kjName">ニデック</td><td class="kjTitle"><a href="1.pdf">公開買付け</a></td></tr></table><a onclick="pager('I_list_002_20260925.html')"></a>'''.encode()
        rows, pages = tdnet_items(raw, 'https://www.release.tdnet.info/inbs/I_list_001_20260925.html', '20260925')
        self.assertIn('ニデック', rows[0]['title'])
        self.assertEqual(rows[0]['exchange_tickers'], ['6594 JP'])
        self.assertEqual(pages, ['https://www.release.tdnet.info/inbs/I_list_002_20260925.html'])

    def test_hkex_multiple_securities_and_total(self):
        row = dict(STOCK_CODE='03187<br/>09187', STOCK_NAME='Company', TITLE='Scheme',
                   FILE_LINK='/filing.pdf', DATE_TIME='27/09/2026 18:25')
        rows, total = hkex_items(json.dumps(dict(result=json.dumps([row]), recordCnt=400)), 'https://www1.hkexnews.hk/')
        self.assertEqual(rows[0]['exchange_tickers'], ['3187 HK', '9187 HK'])
        self.assertEqual(total, 400)

    def test_changed_layout_is_not_empty_success(self):
        for parser in (asx_items, nzx_items):
            with self.assertRaises(ValueError):
                parser(b'<html>Access denied</html>', 'https://example.com/')

    def test_tdnet_verified_empty_weekend(self):
        rows, pages = tdnet_items('<html>2026年09月26日に開示された情報はありません。</html>'.encode(), 'https://www.release.tdnet.info/inbs/I_list_001_20260926.html', '20260926')
        self.assertEqual((rows, pages), ([], []))

    def test_metadata_only_and_cutoff_enforced(self):
        asof = datetime.fromisoformat('2026-09-28T08:22:51+08:00')
        start = asof - timedelta(hours=72)
        source = dict(id='test', name='Test exchange', url='https://example.com/',
                      allowed_domains=['example.com'], broad_discovery=True, retain_all_leads=True,
                      discovery_only=True, kind='exchange_index', language='en', timezone='Asia/Singapore')
        leads = [dict(title='ABC AU Administrative notice', text='', url='https://example.com/a', published='2026-09-25T10:00:00+08:00'),
                 dict(title='ABC AU Future bid', text='', url='https://example.com/b', published='2026-09-28T10:00:00+08:00')]
        report = dict(excluded={}, errors=[])
        audit = []
        # A dummy fetcher proves that metadata discovery never fetches a document.
        rows = expand_publisher_leads(leads, source, [], object(), start, asof, report, 12, audit)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['access_status'], 'metadata_only')
        candidate, _ = classify_record(rows[0], source, [], start, asof, {})
        self.assertFalse(candidate['eligible'])
        self.assertEqual({x['stage'] for x in audit}, {'outside_window', 'document_review_pending'})

    def test_unavailable_tdnet_dates_are_reported(self):
        class Offline:
            def get(self, url):
                raise OSError('unavailable')
        report = dict(errors=[])
        source = dict(exchange_adapter='tdnet', url='https://www.release.tdnet.info/inbs/')
        with self.assertRaises(ValueError):
            collect_exchange(source, Offline(), datetime.fromisoformat('2026-09-25T08:00:00+08:00'), datetime.fromisoformat('2026-09-28T08:00:00+08:00'), report)
        self.assertEqual(len(report['day_coverage']), 4)
        self.assertTrue(all(not d['complete'] for d in report['day_coverage']))


if __name__ == '__main__':
    unittest.main()
