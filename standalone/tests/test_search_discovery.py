import json
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import search_discovery as search


class SearchDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.asof = datetime.fromisoformat("2025-01-10T07:00:00+09:00")
        self.source = {"id": "jp-search", "enabled": True,
                       "allowed_domains": ["nikkei.com", "diamond.jp"]}
        self.watch = [{"ticker": "0001 JP", "name": "Example Company",
                       "aliases": ["サンプル会社", "Related Buyer"]}]
        self.calls = []
        self.env = patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "FAKE-UNIT-TEST-TOKEN"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sleeper = patch.object(search.time, "sleep")
        self.sleeper.start()
        self.addCleanup(self.sleeper.stop)

    def fetch(self, request, timeout):
        self.calls.append((request, timeout))
        return {"web": {"results": [{
            "url": "https://www.nikkei.com/article/abc#details",
            "title": "Example Company update", "description": "<b>Unverified</b> search excerpt",
            "age": "1 hour ago", "page_age": "2025-01-10T06:00:00+09:00",
        }]}}

    def discover(self, **kwargs):
        return search.discover(kwargs.pop("source", self.source),
                               kwargs.pop("watchlist", self.watch),
                               kwargs.pop("asof", self.asof),
                               kwargs.pop("hours", 24),
                               fetcher=kwargs.pop("fetcher", self.fetch))

    def test_requires_literal_enabled_before_reading_key(self):
        for enabled in (False, None, "true", 1):
            with self.subTest(enabled=enabled), patch.object(search.os.environ, "get", side_effect=AssertionError("Must not read key")):
                records, report = self.discover(source=dict(self.source, enabled=enabled))
                self.assertEqual((records, report["status"]), ([], "disabled"))
        self.assertEqual(self.calls, [])

    def test_missing_key_is_not_configured_without_network(self):
        with patch.dict(os.environ, {}, clear=True):
            records, report = self.discover()
        self.assertEqual((records, report["status"]), ([], "not_configured"))
        self.assertEqual(report["unsearched_tickers"], ["0001 JP"])
        self.assertEqual(self.calls, [])

    def test_query_uses_issuer_japanese_and_related_aliases_and_domain_or(self):
        query = search.build_query(self.watch[0], self.source["allowed_domains"])
        for part in ('"Example Company"', '"サンプル会社"', '"Related Buyer"', "site:nikkei.com OR site:diamond.jp"):
            self.assertIn(part, query)

    def test_search_terms_override_general_aliases_and_are_bounded(self):
        company = dict(self.watch[0], search_terms=["Specific Japanese", "特定名称", "Buyer", "Fourth", "Fifth"])
        query = search.build_query(company, self.source["allowed_domains"])
        self.assertNotIn("Example Company", query)
        self.assertNotIn("Fifth", query)
        self.assertIn('"特定名称"', query)
        self.assertLessEqual(len(query), 600)

    def test_historical_cutoff_uses_explicit_dates_no_relative_freshness(self):
        records, report = self.discover()
        request, timeout = self.calls[0]
        params = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(params["freshness"], ["2025-01-09to2025-01-10"])
        self.assertEqual(params["count"], ["10"])
        self.assertEqual(timeout, 15)
        self.assertTrue(request.full_url.startswith(search.BRAVE_ENDPOINT + "?"))
        self.assertEqual(request.get_header("X-subscription-token"), "FAKE-UNIT-TEST-TOKEN")
        self.assertNotIn("FAKE-UNIT-TEST-TOKEN", request.full_url)
        self.assertNotIn("FAKE-UNIT-TEST-TOKEN", json.dumps((records, report)))

    def test_search_age_and_snippet_never_become_article_evidence(self):
        records, report = self.discover()
        record = records[0]
        self.assertEqual(record["published"], "")
        self.assertEqual(record["text"], "")
        self.assertEqual(record["discovery_date_hint"], "2025-01-10T06:00:00+09:00")
        self.assertEqual(record["discovery_snippet"], "Unverified search excerpt")
        self.assertEqual(record["evidence_level"], "search_lead")
        self.assertEqual(record["access_status"], "metadata_only")
        self.assertEqual(record["url"], "https://www.nikkei.com/article/abc")
        self.assertEqual(report["successful_tickers"], ["0001 JP"])

    def test_url_validation_blocks_spoofs_credentials_ports_and_local_urls(self):
        invalid = ["https://nikkei.com.evil.org/a", "https://evilnikkei.com/a",
                   "https://nikkei.com@evil.org/a", "https://user@nikkei.com/a",
                   "https://nikkei.com:8080/a", "file:///nikkei.com/a", "https://127.0.0.1/a",
                   "http://localhost/a", "https://nikkei.com\\@evil.org/a", "https://nikkei.com/\na"]
        for url in invalid:
            with self.subTest(url=url):
                self.assertEqual(search.allowed_url(url, ["nikkei.com"]), "")
        self.assertEqual(search.allowed_url("https://asia.nikkei.com/a", ["nikkei.com"]), "https://asia.nikkei.com/a")

    def test_default_request_cap_reports_unsearched_issuers(self):
        watch = [dict(self.watch[0], ticker=f"{i} JP") for i in range(8)]
        records, report = self.discover(watchlist=watch)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["unsearched_tickers"], ["6 JP", "7 JP"])
        self.assertEqual(report["successful_tickers"], [f"{i} JP" for i in range(6)])
        self.assertEqual(records[0]["discovered_for"], [f"{i} JP" for i in range(6)])

    def test_response_domain_filter_and_result_cap(self):
        def fetch(request, timeout):
            return {"query": {"more_results_available": True}, "web": {"results": [
                {"title": "Spoof", "url": "https://nikkei.com.evil.org/a"},
                {"title": "Allowed", "url": "https://nikkei.com/a"},
                {"title": "Beyond cap", "url": "https://diamond.jp/a"}]}}
        records, report = self.discover(source=dict(self.source, count=2), fetcher=fetch)
        self.assertEqual(len(records), 1)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["rejected_urls"], 1)

    def test_auth_failure_stops_without_leaking_provider_error(self):
        def fail(request, timeout):
            self.calls.append(request)
            raise HTTPError(request.full_url, 401, "FAKE-UNIT-TEST-TOKEN", {}, None)
        records, report = self.discover(watchlist=self.watch + [{"ticker": "1234 JP", "name": "Another"}], fetcher=fail)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["unsearched_tickers"], ["1234 JP"])
        self.assertNotIn("FAKE-UNIT-TEST-TOKEN", json.dumps(report))
        self.assertIn("HTTP 401", report["errors"][0]["error"])

    def test_partial_failure_keeps_successful_query_coverage(self):
        def fetch(request, timeout):
            if self.calls:
                raise RuntimeError("FAKE-UNIT-TEST-TOKEN")
            return self.fetch(request, timeout)
        records, report = self.discover(watchlist=self.watch + [{"ticker": "1234 JP", "name": "Another"}], fetcher=fetch)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["successful_tickers"], ["0001 JP"])
        self.assertEqual(report["failed_tickers"], ["1234 JP"])
        self.assertNotIn("FAKE-UNIT-TEST-TOKEN", json.dumps(report))
        self.assertEqual(len(records), 1)

    def test_invalid_config_and_naive_cutoff_do_not_request(self):
        for domains in ([], ["https://nikkei.com"], ["localhost"], ["127.0.0.1"], ["nikkei.com OR site:evil.org"]):
            with self.subTest(domains=domains):
                _, report = self.discover(source=dict(self.source, allowed_domains=domains))
                self.assertEqual(report["status"], "failed")
        _, report = self.discover(asof=datetime(2025, 1, 10))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(self.calls, [])

    def test_no_results_is_explicit_successful_query_not_unsearched(self):
        records, report = self.discover(fetcher=lambda request, timeout: {"web": {"results": []}})
        self.assertEqual(records, [])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["unsearched_tickers"], [])
        self.assertEqual(report["successful_tickers"], ["0001 JP"])

    def test_malformed_provider_response_is_not_counted_as_coverage(self):
        for response in ({}, [], {"web": {"results": "bad"}}, {"type": "ErrorResponse"}):
            with self.subTest(response=response):
                records, report = self.discover(fetcher=lambda request, timeout: response)
                self.assertEqual(records, [])
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["successful_tickers"], [])

    def test_redirection_is_disabled_and_alternate_provider_endpoint_rejected(self):
        request = Request(search.BRAVE_ENDPOINT)
        self.assertIsNone(search._NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://other.org/"))
        with self.assertRaises(ValueError):
            search._request_json(Request("https://other.org/"), 1)


if __name__ == "__main__":
    unittest.main()
