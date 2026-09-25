import sys
import unittest
from pathlib import Path

from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from radar_view import render_market_radar


class RadarViewTests(unittest.TestCase):
    def render(self, records=(), coverage=(), log=(), priority_count=32):
        return html.fromstring(render_market_radar(records, coverage, log, priority_count))

    @staticmethod
    def candidate(**updates):
        record = {"id": "new", "title": "New Company receives takeover proposal", "source": "Publisher",
                  "url": "https://example.jp/story", "tickers": [], "collection_role": "market",
                  "attention_score": 60, "attention_reasons": ["Takeover signal"], "eligible": False,
                  "language": "en", "published": "2026-09-24T10:00:00+09:00", "date_precision": "minute",
                  "access_status": "readable"}
        record.update(updates)
        return record

    def test_outside_name_is_visible_with_no_ticker_invented(self):
        doc = self.render([self.candidate()])
        text = doc.text_content()
        self.assertIn("New Company receives takeover proposal", text)
        self.assertIn("Outside priority list — company/ticker review needed", text)
        self.assertIn("1 market candidates", text)
        self.assertIn("1 outside the priority list", text)
        self.assertEqual(doc.xpath('//article/@data-priority-match'), ["false"])
        self.assertNotIn("Draft candidate", text)

    def test_priority_count_is_not_a_filter_or_candidate_limit(self):
        records = [self.candidate(id=str(i), title=f"New issuer {i}") for i in range(40)]
        doc = self.render(records, priority_count=1)
        self.assertEqual(len(doc.xpath('//article')), 40)
        self.assertIn("1 priority companies receive extra checks", doc.text_content())
        self.assertIn("40 outside the priority list", doc.text_content())

    def test_ranked_market_candidates_separate_from_extra_priority_results(self):
        doc = self.render([
            self.candidate(id="low", attention_score=12, tickers=["1000 JP"], eligible=True),
            self.candidate(id="high", attention_score=95),
            self.candidate(id="priority-only", attention_score=100, collection_role="priority"),
        ])
        self.assertEqual(doc.xpath('//article/@data-candidate-id'), ["high", "low"])
        self.assertIn("Priority-list match: 1000 JP", doc.text_content())
        self.assertIn("Draft candidate — review required", doc.text_content())
        self.assertIn("provisional rules", doc.text_content())
        self.assertNotIn("priority-only", html.tostring(doc, encoding="unicode"))

    def test_restricted_undated_original_language_stays_explicit(self):
        doc = self.render([self.candidate(title="新会社の買収", language="ja", access_status="restricted",
                                         published="2026-09-24", date_precision="day", flags=["Confirm event details."])])
        text = doc.text_content()
        self.assertIn("Restricted article — public headline or metadata only", text)
        self.assertIn("Original language: Japanese — English summary needed", text)
        self.assertIn("date only; time unconfirmed", text)
        self.assertIn("Confirm event details", text)

    def test_failed_sources_never_imply_scan_complete_or_no_news(self):
        doc = self.render(coverage=[{"name": "Publisher", "collection_role": "market", "status": "failed",
                                     "errors": ["Timed out"], "discovered": 0}])
        text = doc.text_content()
        self.assertIn("Scan failed", text)
        self.assertIn("Coverage is incomplete", text)
        self.assertIn("Timed out", text)
        self.assertNotIn("Scan finished", text)

    def test_market_and_priority_source_counts_are_separate(self):
        doc = self.render(coverage=[
            {"name": "Market", "collection_role": "market", "status": "partial", "discovered": 25, "articles_attempted": 4},
            {"name": "Company IR", "collection_role": "priority", "status": "ok", "discovered": 900, "articles_attempted": 7},
        ])
        self.assertIn("25 headline items returned", doc.text_content())
        self.assertIn("4 article checks attempted", doc.text_content())
        self.assertIn("Market", doc.xpath('//table[@id="radar-market-sources"]')[0].text_content())
        self.assertNotIn("Company IR", doc.xpath('//table[@id="radar-market-sources"]')[0].text_content())
        self.assertIn("Company IR", doc.xpath('//table[@id="radar-priority-sources"]')[0].text_content())

    def test_audit_preserves_all_entries_without_making_old_news_current(self):
        log = [{"title": f"Headline {i}", "source": "Publisher", "stage": "old", "published": "2020-01-01",
                "date_precision": "day", "reason": "Outside chosen window"} for i in range(501)]
        log.append({"title": "Extra company lead", "collection_role": "priority"})
        doc = self.render(log=log)
        self.assertEqual(len(doc.xpath('//table[@id="radar-audit-table"]/tbody/tr')), 501)
        text = doc.text_content()
        self.assertIn("501 logged market items", text)
        self.assertIn("Headline 500", text)
        self.assertIn("Outside time window", text)
        self.assertNotIn("Extra company lead", text)

    def test_untrusted_text_and_unsafe_links_are_not_active_markup(self):
        bad = '<img src=x onerror="alert(1)">'
        doc = self.render([
            self.candidate(id=bad, title=bad, source=bad, url="javascript:alert(1)", attention_reasons=[bad], flags=[bad]),
            self.candidate(id="second", url="https://user:pass@example.jp/story"),
        ], coverage=[{"name": bad, "url": "file:///private", "errors": [bad]}],
                          log=[{"title": bad, "reason": bad, "stage": bad, "url": "data:text/html,bad"}])
        self.assertFalse(doc.xpath('//img | //script | //a'))
        self.assertIn(bad, doc.text_content())

    def test_safe_source_link_preserves_query_and_external_link_protection(self):
        url = 'https://example.jp/story?x="&y=1'
        doc = self.render([self.candidate(url=url)])
        link = doc.xpath('//article//a')[0]
        self.assertEqual(link.get("href"), url)
        self.assertEqual(link.get("rel"), "noopener noreferrer")
        self.assertEqual(link.text, "Read public source")

    def test_missing_or_nonfinite_score_and_counts_do_not_break_display(self):
        doc = self.render([self.candidate(attention_score=float("nan")), self.candidate(id="none", attention_score=None)],
                          coverage=[{"status": "ok", "discovered": "invalid", "articles_attempted": -1}],
                          priority_count=0)
        self.assertIn("Attention score: 0", doc.text_content())
        self.assertIn("0 headline items returned", doc.text_content())
        self.assertIn("0 article checks attempted", doc.text_content())


if __name__ == "__main__":
    unittest.main()
