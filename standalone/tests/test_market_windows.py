import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT if (ROOT / 'morning_note.py').exists() else ROOT / 'collector'))
from market_windows import DEFAULT_CLOSES, build_windows, record_window
from morning_note import classify_record, expand_publisher_leads


class MarketWindowTests(unittest.TestCase):
    # Normal-session fixtures; holidays are supplied separately through overrides.
    SGT_CLOSES = {'JP': '14:30:00', 'KR': '14:30:00', 'AU': '14:15:00',
                  'HK': '16:10:00', 'CH': '15:00:00', 'TT': '13:30:00',
                  'NZ': '12:00:30', 'SP': '17:16:00', 'IN': '18:00:00',
                  'MK': '17:00:00', 'IJ': '17:15:00', 'TB': '17:40:00',
                  'PM': '15:15:00', 'VN': '16:00:00'}

    def windows(self, when='2026-09-28T16:00:00+08:00', **extra):
        asof = datetime.fromisoformat(when)
        config = dict(timing_mode='market_close', timezone='Asia/Singapore', **extra)
        windows, start = build_windows(config, asof)
        return asof, windows, start

    def test_all_markets_and_every_day_use_strict_1410_sgt(self):
        for date in ('2026-09-28', '2026-09-29', '2026-10-03', '2026-10-04'):
            asof, windows, start = self.windows(date + 'T16:00:00+08:00')
            self.assertEqual(set(windows), set(DEFAULT_CLOSES) | {'GLOBAL'})
            self.assertEqual(start.isoformat(), date + 'T14:10:00+08:00')
            for market, window in windows.items():
                with self.subTest(date=date, market=market):
                    self.assertEqual(window['window_start'], date + 'T14:10:00+08:00')
                    self.assertFalse(window['start_inclusive'])
                    self.assertEqual(window['status'], 'active')
                    self.assertEqual(window['as_of'], asof.isoformat())

    def test_monday_morning_and_weekend_use_friday_close(self):
        for when in ['2026-09-28T08:00:00+08:00', '2026-09-27T08:00:00+08:00']:
            _, windows, _ = self.windows(when)
            for market, clock in self.SGT_CLOSES.items():
                clock = '13:00:30' if market == 'NZ' else clock
                with self.subTest(when=when, market=market):
                    self.assertEqual(windows[market]['window_start'], f'2026-09-25T{clock}+08:00')

    def test_before_at_and_after_afternoon_start(self):
        cutoff = datetime.fromisoformat('2026-09-29T14:10:00+08:00')
        for seconds, status in [(-1, 'pending_start'), (0, 'pending_start'), (1, 'active')]:
            asof, windows, start = self.windows((cutoff + timedelta(seconds=seconds)).isoformat())
            self.assertLessEqual(start, asof)
            self.assertTrue(all(w['status'] == status for w in windows.values()))
            self.assertTrue(all(not w['start_inclusive'] for w in windows.values()))

    def test_fixed_au_sgt_cutoff_and_new_zealand_dst(self):
        _, before, _ = self.windows('2026-09-25T16:00:00+08:00', timing_edition='morning')
        _, after, _ = self.windows('2026-10-05T16:00:00+08:00', timing_edition='morning')
        self.assertIn('T13:00:30', before['NZ']['window_start'])
        self.assertIn('T12:00:30', after['NZ']['window_start'])
        self.assertIn('T14:15:', after['AU']['window_start'])

    def test_holidays_and_short_sessions_do_not_shift_afternoon_floor(self):
        _, windows, _ = self.windows(market_close_rules={'JP': {'sessions': {'2026-09-28': None}},
                                                        'HK': {'sessions': {'2026-09-28': '12:10'}}})
        for market in ('JP', 'HK'):
            self.assertEqual(windows[market]['status'], 'active')
            self.assertEqual(windows[market]['window_start'], '2026-09-28T14:10:00+08:00')
        _, morning, _ = self.windows('2026-09-29T05:00:00+08:00',
            market_close_rules={'JP': {'sessions': {'2026-09-28': None}},
                                'HK': {'sessions': {'2026-09-28': '12:10'}}})
        self.assertEqual(morning['JP']['session_date'], '2026-09-25')
        self.assertEqual(morning['HK']['window_start'], '2026-09-28T12:10:00+08:00')

    def test_morning_holiday_keeps_latest_completed_session(self):
        _, windows, _ = self.windows('2026-09-28T05:00:00+08:00',
            market_close_rules={'JP': {'sessions': {'2026-09-25': None}}})
        self.assertEqual(windows['JP']['session_date'], '2026-09-24')

    def test_afternoon_before_any_close_has_empty_global_window(self):
        asof, windows, start = self.windows('2026-09-28T12:00:00+08:00')
        self.assertEqual(start, asof)
        self.assertTrue(all(w['status'] == 'pending_start' for w in windows.values()))

    def test_edition_override_and_configurable_afternoon_boundary(self):
        _, windows, _ = self.windows(timing_edition='morning')
        self.assertEqual(windows['HK']['session_date'], '2026-09-25')
        _, windows, _ = self.windows('2026-09-28T13:00:00+08:00', afternoon_start='14:00')
        self.assertEqual(windows['HK']['session_date'], '2026-09-25')
        with self.assertRaises(ValueError):
            self.windows(timing_edition='unknown')

    def test_all_market_collector_boundaries_and_timezone_conversion(self):
        asof, windows, start = self.windows()
        for market in (*DEFAULT_CLOSES, 'GLOBAL'):
            watch = [dict(ticker=f'TEST {market}', name='Example Company', aliases=[])]
            source = dict(id='test', name='Test', timezone='UTC', language='en', market_windows=windows)
            for published, accepted in [('2026-09-25T21:56:00+08:00', False),
                                        ('2026-09-28T14:09:59+08:00', False),
                                        ('2026-09-28T14:10:00+08:00', False),
                                        ('2026-09-28T06:10:00+00:00', False),
                                        ('2026-09-28T06:10:01+00:00', True),
                                        ('2026-09-28T15:10:01+09:00', True),
                                        ('2026-09-28T16:00:00+08:00', True),
                                        ('2026-09-28T16:00:01+08:00', False)]:
                with self.subTest(market=market, published=published):
                    row = dict(title='Example Company update', text='Synthetic fact', url='https://example.com/a', published=published)
                    candidate, _ = classify_record(row, source, watch, start, asof, {})
                    self.assertEqual(bool(candidate and candidate['eligible']), accepted)

    def test_singapore_date_is_used_even_after_new_zealand_midnight(self):
        _, windows, _ = self.windows('2026-09-28T23:00:00+08:00')
        self.assertEqual(windows['NZ']['window_start'], '2026-09-28T14:10:00+08:00')
        _, utc, _ = self.windows('2026-09-28T08:00:00+00:00')
        self.assertEqual(utc['HK']['window_start'], '2026-09-28T14:10:00+08:00')

    def test_explicit_rolling_hours_preserved(self):
        asof = datetime.fromisoformat('2026-09-28T16:00:00+08:00')
        windows, start = build_windows(dict(timing_mode='rolling_hours', lookback_hours=24), asof)
        self.assertEqual(windows, {})
        self.assertEqual(start, asof - timedelta(hours=24))

    def test_market_follows_security_not_publisher_timezone(self):
        _, windows, start = self.windows()
        applied, markets, resolved = record_window(dict(exchange_tickers=['TEST AU']), dict(scope_market='JP', market_windows=windows), start)
        self.assertEqual((markets, resolved), (['AU'], True))
        self.assertEqual(applied.isoformat(), '2026-09-28T14:10:00+08:00')

    def test_country_aliases_and_full_bloomberg_tickers(self):
        _, windows, start = self.windows('2026-09-28T18:30:00+08:00')
        for alias, market in [('ID', 'IJ'), ('TH', 'TB'), ('PH', 'PM'), ('TW', 'TT'), ('CN', 'CH'), ('SG', 'SP'), ('MY', 'MK')]:
            with self.subTest(alias=alias):
                applied, markets, resolved = record_window(dict(tickers=[f'TEST {alias} Equity']), dict(market_windows=windows), start)
                self.assertEqual((markets, resolved), ([market], True))
                self.assertEqual(applied.isoformat(), windows[market]['window_start'])

    def test_publisher_country_cannot_resolve_unknown_company_market(self):
        _, windows, start = self.windows()
        source = dict(scope_market='JP', publisher=True, market_windows=windows)
        self.assertEqual(record_window({}, source, start), (start, [], False))
        applied, markets, resolved = record_window({}, dict(source, kind='exchange_index'), start)
        self.assertEqual((markets, resolved), (['JP'], True))
        self.assertEqual(applied.isoformat(), windows['JP']['window_start'])

    def test_additional_requested_markets_can_supply_their_own_rule(self):
        _, windows, start = self.windows(market_close_rules={'CUSTOM': {'timezone': 'Asia/Singapore', 'close': '15:45'}})
        applied, markets, resolved = record_window(dict(market='CUSTOM'), dict(market_windows=windows), start)
        self.assertEqual((markets, resolved), (['CUSTOM'], True))
        self.assertEqual(applied.isoformat(), '2026-09-28T14:10:00+08:00')

    def test_collector_rejects_preclose_and_future_news(self):
        asof, windows, start = self.windows()
        watch = [dict(ticker='TEST JP', name='Example Company', aliases=[])]
        source = dict(id='test', name='Test', scope_market='JP', timezone='Asia/Tokyo', language='en', market_windows=windows)
        for clock, accepted in [('14:09:59', False), ('14:10:00', False), ('14:10:01', True), ('15:30:00', True), ('16:00:01', False)]:
            row = dict(title='Example Company update', text='Synthetic fact', url='https://example.com/a', published=f'2026-09-28T{clock}+08:00')
            candidate, _ = classify_record(row, source, watch, start, asof, {})
            self.assertEqual(bool(candidate), accepted)
            if candidate:
                self.assertEqual(candidate['applied_window_start'], windows['JP']['window_start'])

    def test_audit_retains_preclose_headlines_without_selecting_them(self):
        asof, windows, start = self.windows()
        source = dict(id='test', name='Test', url='https://example.com/', scope_market='JP',
                      timezone='Asia/Tokyo', language='en', kind='exchange_index', broad_discovery=True,
                      discovery_only=True, retain_all_leads=True, market_windows=windows)
        leads = [dict(title='TEST JP Synthetic event', text='', url='https://example.com/'+clock,
                      published=f'2026-09-28T{clock}:00+08:00') for clock in ['14:00', '14:10', '15:00']]
        audit = []
        selected = expand_publisher_leads(leads, source, [], object(), start, asof, dict(excluded={}, errors=[]), 12, audit)
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(audit), 3)
        self.assertEqual({x['stage'] for x in audit}, {'outside_window', 'document_review_pending'})


if __name__ == '__main__':
    unittest.main()
