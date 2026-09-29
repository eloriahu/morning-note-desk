"""Synthetic chronology regressions: a fresh recap must not revive old news."""
import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from test_compose_email import composer, example_pack


def afternoon_pack(original='2026-09-29T14:20:00+08:00', market='HK'):
    pack = example_pack()
    as_of = datetime.fromisoformat('2026-09-29T16:00:00+08:00')
    windows, start = composer.windows.build_windows({'timing_mode': 'market_close'}, as_of)
    pack.update(as_of=as_of.isoformat(), window_start=start.isoformat(),
                timing_mode='market_close', market_windows=windows)
    story = pack['stories'][0]
    story['market'] = market
    story['sources'][0]['published_at'] = original
    return pack


def add_report(story, published='2026-09-29T15:00:00+08:00', cite=True, **metadata):
    source = dict(copy.deepcopy(story['sources'][0]), url='https://example.com/later-report',
                  name='Synthetic media report', published_at=published, **metadata)
    story['sources'].append(source)
    if cite:
        story['bullets'][0]['source_urls'].append(source['url'])
    return source


class OriginalTimingTests(unittest.TestCase):
    def held(self, pack, reason):
        result = composer.validate_pack(pack)
        self.assertEqual(result['composition']['ready_count'], 0)
        self.assertIn(reason, ' '.join(result['stories'][0]['composition_reasons']))
        self.assertNotIn('Synthetic sourced statement', composer.email_body(result))
        return result

    def test_later_media_cannot_revive_an_older_original_in_any_market(self):
        for market in afternoon_pack()['market_windows']:
            for original in ('2026-09-28T22:00:00+08:00', '2026-09-29T14:09:00+08:00',
                             '2026-09-29T14:10:00+08:00', '2026-09-29T06:10:00+00:00'):
                with self.subTest(market=market, original=original):
                    pack = afternoon_pack(original, market)
                    story = pack['stories'][0]
                    report = add_report(story)
                    # Even citing only the fresh media article cannot bypass the origin gate.
                    story['bullets'][0]['source_urls'] = [report['url']]
                    self.held(pack, 'Original disclosure is outside')

    def test_a_later_exchange_announcement_cannot_hide_an_earlier_report(self):
        pack = afternoon_pack('2026-09-29T15:10:00+08:00')
        add_report(pack['stories'][0], '2026-09-29T13:55:00+08:00', cite=False)
        self.held(pack, 'An earlier report of the same development')

    def test_missing_or_unverified_origin_stays_held_in_legacy_packs_too(self):
        for value in (None, {}, {'status': 'unconfirmed'}, 'invalid'):
            pack = example_pack()
            pack['stories'][0]['origin'] = value
            self.held(pack, 'Original disclosure')

    def test_original_requires_readable_exact_time_and_recorded_verification(self):
        for change in ({'access': 'restricted'}, {'date_precision': 'day'},
                       {'published_at': '2026-09-29'}, {'published_at': '2026-09-29T14:20:00'}):
            pack = afternoon_pack()
            pack['stories'][0]['sources'][0].update(change)
            self.held(pack, 'Original source')
        for field in ('development', 'timestamp_evidence', 'verification_notes'):
            pack = afternoon_pack()
            pack['stories'][0]['origin'].pop(field)
            self.held(pack, field)

    def test_invalid_or_uncited_original_is_held(self):
        for url in ('https://example.com/missing', 'javascript:alert(1)', ['invalid']):
            pack = afternoon_pack()
            pack['stories'][0]['origin']['source_url'] = url
            self.held(pack, 'Original source URL')
        pack = afternoon_pack()
        story = pack['stories'][0]
        report = add_report(story)
        story['bullets'][0]['source_urls'] = [report['url']]
        self.held(pack, 'original disclosure must be cited')

    def test_known_recap_chronology_must_be_resolved_even_when_uncited(self):
        for change in ({'date_precision': 'day'}, {'published_at': 'unknown'}, {'relationship': 'unknown'}):
            pack = afternoon_pack()
            report = add_report(pack['stories'][0], cite=False)
            report.update(change)
            self.assertEqual(composer.validate_pack(pack)['composition']['ready_count'], 0)

    def test_in_window_original_and_later_reports_are_one_eligible_story(self):
        pack = afternoon_pack('2026-09-29T06:10:01+00:00')
        add_report(pack['stories'][0])
        result = composer.validate_pack(pack)
        self.assertEqual(result['composition']['ready_count'], 1)
        self.assertEqual(result['stories'][0]['original_published_at_sgt'], '2026-09-29T14:10:01+08:00')

    def test_material_new_terms_can_use_a_new_origin_with_old_background(self):
        pack = afternoon_pack()
        story = pack['stories'][0]
        story['novelty'] = 'changed'
        story['origin']['development'] = 'The offer price was increased for the first time today.'
        add_report(story, '2026-09-20T10:00:00+08:00', cite=False, relationship='background',
                   context_notes='Original offer terms only; this document did not disclose today\'s price increase.')
        self.assertEqual(composer.validate_pack(pack)['composition']['ready_count'], 1)
        story['sources'][-1].pop('context_notes')
        self.held(pack, 'Background sources need context_notes')

    def test_original_after_cutoff_is_held_and_exact_cutoff_is_allowed(self):
        self.held(afternoon_pack('2026-09-29T16:00:01+08:00'), 'Original disclosure is outside')
        self.assertEqual(composer.validate_pack(afternoon_pack('2026-09-29T16:00:00+08:00'))['composition']['ready_count'], 1)

    def test_original_time_evidence_and_decision_are_saved_and_editor_only(self):
        pack = afternoon_pack()
        story = pack['stories'][0]
        story['origin']['verification_notes'] = '<script>chronology audit</script>'
        with tempfile.TemporaryDirectory() as temp:
            composer.compose(pack, temp)
            output = Path(temp)
            saved = json.loads((output / 'research.json').read_text(encoding='utf-8'))['stories'][0]
            review = (output / 'review.html').read_text(encoding='utf-8')
            email = (output / 'email.html').read_text(encoding='utf-8')
            self.assertEqual(saved['original_published_at_sgt'], '2026-09-29T14:20:00+08:00')
            self.assertFalse(saved['applied_start_inclusive'])
            self.assertIn('Original disclosure audit', review)
            self.assertIn(saved['original_published_at_sgt'], review)
            self.assertIn('&lt;script&gt;chronology audit&lt;/script&gt;', review)
            self.assertNotIn('<script>chronology audit</script>', review)
            self.assertNotIn('Original disclosure audit', email)
            self.assertNotIn('chronology audit', email)


if __name__ == '__main__':
    unittest.main()
