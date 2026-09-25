"""Offline checks of publisher discovery, eligibility, and exported coverage."""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import morning_note as note


class PublisherIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.asof = datetime.fromisoformat("2026-09-24T09:00:00+09:00")
        self.start = self.asof - timedelta(hours=24)
        self.watch = [{"ticker": "1234 JP", "name": "Example Corp", "aliases": ["例示会社"]}]
        self.source = {"id": "public-news", "name": "Example public news", "kind": "feed",
                       "url": "https://example.jp/feed", "publisher": True, "enabled": True,
                       "scope_market": "JP", "language": "en", "timezone": "Asia/Tokyo",
                       "allowed_domains": ["example.jp"], "tickers": [],
                       "coverage_note": "Only the latest public headlines are scanned."}
        self.config = {"sources": [self.source], "lookback_hours": 24,
                       "max_documents_per_source": 12, "max_stories": 25,
                       "selected_watchlist": self.watch, "title": "Example morning note",
                       "timezone": "Asia/Tokyo", "topic": ""}

    @staticmethod
    def rss(items):
        body = "".join('<item><title>' + title + '</title><link>https://example.jp/' + slug + '</link>'
                       + ('<pubDate>' + published + '</pubDate>' if published else '') + '</item>'
                       for title, slug, published in items)
        return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>' + body + '</channel></rss>').encode("utf-8")

    @staticmethod
    def article(title, *, published="2026-09-24T08:00:00+09:00", language="en", restricted=False):
        structured = {"@type": "NewsArticle", "headline": title, "isAccessibleForFree": not restricted}
        if published:
            structured["datePublished"] = published
        text = "The company increased the offer price and extended the acceptance period."
        if language == "ja":
            text = "例示会社は公開買付け価格の変更と買付け期間の延長を発表しました。"
        if restricted:
            structured["articleBody"] = "PRIVATE BODY must never become a source excerpt or an email draft."
        return ('<html lang="' + language + '"><meta name="description" content="Public article teaser">'
                '<script type="application/ld+json">' + json.dumps(structured, ensure_ascii=False) + '</script>'
                '<article><h1>' + title + '</h1><p>' + text + '</p></article></html>').encode("utf-8")

    def collect(self, pages, config=None, watch=None):
        fake = Mock()
        def get(url):
            value = pages[url]
            if isinstance(value, Exception):
                raise value
            return value, "text/html; charset=utf-8", url
        fake.get.side_effect = get
        with patch.object(note, "Fetcher", return_value=fake):
            records, coverage = note.collect(config or self.config, watch or self.watch, [], self.asof, {})
        return records, coverage, fake

    def test_restricted_japanese_and_undated_leads_stay_out_of_email(self):
        pages = {self.source["url"]: self.rss([
            ("Example Corp restricted offer", "restricted", "Thu, 24 Sep 2026 08:00:00 +0900"),
            ("例示会社が買付け条件を変更", "japanese", "Thu, 24 Sep 2026 08:00:00 +0900"),
            ("Example Corp undated transaction", "undated", ""),
            ("Example Corp readable release", "readable", "Thu, 24 Sep 2026 08:00:00 +0900")]),
            "https://example.jp/restricted": self.article("Subscriber offer story", restricted=True),
            "https://example.jp/japanese": self.article("例示会社が買付け条件を変更", language="ja"),
            "https://example.jp/undated": self.article("Example Corp undated transaction", published=""),
            "https://example.jp/readable": self.article("Example Corp readable release")}
        records, coverage, _ = self.collect(pages)
        self.assertEqual(len(records), 4)
        by_url = {record["url"]: record for record in records}
        self.assertTrue(by_url["https://example.jp/readable"]["eligible"])
        for slug in ("restricted", "japanese", "undated"):
            self.assertFalse(by_url["https://example.jp/" + slug]["eligible"])
        self.assertEqual(by_url["https://example.jp/restricted"]["tickers"], ["1234 JP"])
        self.assertEqual(by_url["https://example.jp/restricted"]["text"], "Public article teaser")
        self.assertIsNone(by_url["https://example.jp/undated"]["published"])
        self.assertEqual(coverage[0]["status"], "partial")
        with tempfile.TemporaryDirectory() as directory:
            result = note.render(records, coverage, self.config, self.asof, Path(directory))
            self.assertEqual((result["selected"], result["held"]), (1, 3))
            email = (Path(directory) / "email.html").read_text(encoding="utf-8")
            review = (Path(directory) / "review.html").read_text(encoding="utf-8")
            payload = json.loads((Path(directory) / "draft-payload.json").read_text(encoding="utf-8"))
            self.assertIn("Example Corp readable release", email)
            self.assertNotIn("Subscriber offer story", email)
            self.assertNotIn("Example Corp undated transaction", email)
            self.assertNotIn("例示会社が買付け条件を変更", email)
            self.assertIn("Example Corp restricted offer", review)
            self.assertNotIn("PRIVATE BODY", review)
            self.assertEqual(sum(item["eligible_for_email"] for item in payload["items"]), 1)

    def test_publisher_without_access_confirmation_is_held(self):
        record = {"title": "Example Corp offer", "text": "A source excerpt without verified access status.",
                  "url": "https://example.jp/unknown-access", "published": "2026-09-24T08:00:00+09:00", "language": "en"}
        prepared, _ = note.classify_record(record, self.source, self.watch, self.start, self.asof, {})
        self.assertFalse(prepared["eligible"])
        self.assertNotEqual(prepared.get("access_status"), "readable")

    def test_atom_updated_is_not_promoted_to_publication(self):
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Example Corp updated offer</title><link href="https://example.jp/update-only"/>
        <updated>2026-09-24T08:00:00+09:00</updated></entry></feed>'''
        pages = {self.source["url"]: atom,
                 "https://example.jp/update-only": self.article("Example Corp updated offer", published="")}
        records, _, _ = self.collect(pages)
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["published"])
        self.assertFalse(records[0]["eligible"])
        self.assertEqual(records[0].get("updated"), "2026-09-24T08:00:00+09:00")

    def test_feed_publication_can_support_readable_article_without_own_date(self):
        pages = {self.source["url"]: self.rss([("Example Corp feed dated", "feed-dated", "Thu, 24 Sep 2026 08:00:00 +0900")]),
                 "https://example.jp/feed-dated": self.article("Example Corp feed dated", published="")}
        records, _, _ = self.collect(pages)
        self.assertEqual(records[0]["published"], "2026-09-24T08:00:00+09:00")
        self.assertEqual(records[0]["date_origin"], "feed")
        self.assertTrue(records[0]["eligible"])

    def test_utf8_index_title_and_japanese_date_are_preserved(self):
        source = dict(self.source, kind="publisher_index", encoding="utf-8", language="ja",
                      item_xpath="//article", item_link_xpath=".//a", date_xpath=".//time/text()")
        config = dict(self.config, sources=[source])
        index = '<html><article><a href="/indexed">例示会社が公開買付け条件を変更</a><time>2026年9月24日 08時00分</time></article></html>'.encode("utf-8")
        pages = {source["url"]: index, "https://example.jp/indexed": self.article("例示会社が公開買付け条件を変更", published="", language="ja")}
        records, coverage, _ = self.collect(pages, config=config)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["published"], "2026-09-24T08:00:00+09:00")
        self.assertFalse(records[0]["eligible"])
        self.assertEqual(coverage[0]["articles_attempted"], 1)

    def test_failed_article_is_a_review_lead_and_incomplete_coverage(self):
        pages = {self.source["url"]: self.rss([("Example Corp failed fetch", "failed", "Thu, 24 Sep 2026 08:00:00 +0900")]),
                 "https://example.jp/failed": PermissionError("Public source access denied")}
        records, coverage, _ = self.collect(pages)
        self.assertEqual(records[0]["access_status"], "unavailable")
        self.assertFalse(records[0]["eligible"])
        self.assertEqual(records[0]["text"], "")
        self.assertEqual(coverage[0]["access_limited"], 1)
        self.assertEqual(coverage[0]["status"], "partial")
        payload = note.export_payload(records, coverage, self.config, self.asof)
        self.assertEqual(payload["watchlist_results"][0]["status"], "candidates_need_review")
        self.assertEqual(payload["watchlist_results"][0]["checked_sources"], [])

    def test_unmatched_ticker_outside_source_scope_is_not_reported_checked(self):
        watch = self.watch + [{"ticker": "OTHER AU", "name": "Other Corp", "aliases": []}]
        config = dict(self.config, selected_watchlist=watch)
        records, coverage, fake = self.collect({self.source["url"]: self.rss([])}, config=config, watch=watch)
        payload = note.export_payload(records, coverage, config, self.asof)
        by_ticker = {item["ticker"]: item for item in payload["watchlist_results"]}
        self.assertEqual(by_ticker["1234 JP"]["status"], "no_new_items_in_checked_sources")
        self.assertEqual(by_ticker["OTHER AU"]["status"], "coverage_incomplete")
        self.assertEqual(fake.get.call_count, 1)

    def test_search_result_cap_remains_partial_after_article_processing(self):
        source = dict(self.source, kind="brave_search")
        config = dict(self.config, sources=[source])
        report = {"status": "partial", "truncated": True, "errors": [], "excluded": {},
                  "successful_tickers": ["1234 JP"], "unsearched_tickers": []}
        with patch("search_discovery.discover", return_value=([], report)):
            records, coverage, fake = self.collect({}, config=config)
        self.assertEqual(coverage[0]["status"], "partial")
        self.assertEqual(fake.get.call_count, 0)
        payload = note.export_payload(records, coverage, config, self.asof)
        self.assertEqual(payload["watchlist_results"][0]["status"], "coverage_incomplete")

    def test_day_only_timestamp_stays_held_and_source_coverage_note_survives(self):
        pages = {self.source["url"]: self.rss([("Example Corp day only", "day-only", "2026-09-24")]),
                 "https://example.jp/day-only": self.article("Example Corp day only", published="2026-09-24")}
        records, coverage, _ = self.collect(pages)
        self.assertFalse(records[0]["eligible"])
        self.assertEqual(records[0]["date_precision"], "day")
        self.assertEqual(coverage[0].get("coverage_note"), self.source["coverage_note"])

    def test_generic_paywall_metadata_does_not_merge_distinct_issuer_leads(self):
        watch = self.watch + [{"ticker": "5678 JP", "name": "Second Corp", "aliases": []}]
        pages = {self.source["url"]: self.rss([
            ("Example Corp offer update", "first-locked", "Thu, 24 Sep 2026 08:00:00 +0900"),
            ("Second Corp offer update", "second-locked", "Thu, 24 Sep 2026 08:00:00 +0900")]),
            "https://example.jp/first-locked": self.article("Subscriber article", restricted=True),
            "https://example.jp/second-locked": self.article("Subscriber article", restricted=True)}
        records, coverage, _ = self.collect(pages, watch=watch)
        self.assertEqual(len(records), 2)
        self.assertEqual({ticker for record in records for ticker in record["tickers"]}, {"1234 JP", "5678 JP"})
        payload = note.export_payload(records, coverage, dict(self.config, selected_watchlist=watch), self.asof)
        self.assertTrue(all(item["status"] == "candidates_need_review" for item in payload["watchlist_results"]))

    def test_topic_only_in_discovery_is_retained_as_held_lead(self):
        pages = {self.source["url"]: self.rss([("Example Corp takeover update", "topic-locked", "Thu, 24 Sep 2026 08:00:00 +0900")]),
                 "https://example.jp/topic-locked": self.article("Subscriber article", restricted=True)}
        records, _, _ = self.collect(pages, config=dict(self.config, topic="M&A"))
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["eligible"])
        self.assertTrue(any("topic" in flag.lower() for flag in records[0]["flags"]))

    def test_partial_only_empty_collection_does_not_claim_no_news(self):
        coverage = [{"id": "partial", "name": "Incomplete public scan", "status": "partial",
                     "errors": ["Article cap reached"], "tickers": [], "scope_tickers": ["1234 JP"]}]
        with tempfile.TemporaryDirectory() as directory:
            note.render([], coverage, self.config, self.asof, Path(directory))
            draft = (Path(directory) / "morning-note.txt").read_text(encoding="utf-8")
            self.assertNotIn("No new relevant items found", draft)
            self.assertRegex(draft.lower(), r"insufficient|incomplete|undetermined")


if __name__ == "__main__":
    unittest.main()
