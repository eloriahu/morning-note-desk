"""Optional, bounded Brave discovery. Search metadata is never article evidence.

Provider documentation checked 2026-09-24:
https://api-dashboard.search.brave.com/api-reference/web/search/get
https://api-dashboard.search.brave.com/documentation/resources/search-operators

``fetcher`` injection accepts (urllib.request.Request, timeout=<seconds>) and
returns a decoded JSON dict. It replaces only the provider request, not the
explicit enabled/environment-key gates. No publisher pages are fetched here.
"""
from __future__ import annotations

import html
import ipaddress
import json
import math
import os
import re
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
MAX_RESPONSE_BYTES = 2_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The subscription header must never follow a provider redirect.
        return None


def _request_json(request: Request, timeout: float) -> dict:
    if request.full_url.split("?", 1)[0] != BRAVE_ENDPOINT:
        raise ValueError("Unexpected provider endpoint")
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("Provider response exceeds size limit")
    return json.loads(content.decode("utf-8"))


def _domain(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Domains must be hostnames")
    value = value.lower().strip().rstrip(".")
    if (len(value) > 253 or "." not in value or
            not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", value) or
            any(part.startswith("-") or part.endswith("-") or len(part) > 63
                for part in value.split(".")) or
            not re.fullmatch(r"[a-z]{2,63}", value.rsplit(".", 1)[-1])):
        raise ValueError("Domains must be public DNS hostnames")
    if value.endswith((".localhost", ".local", ".internal", ".test", ".invalid")):
        raise ValueError("Domains must be public DNS hostnames")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError("IP addresses are not publisher domains")


def _domains(values) -> list[str]:
    if not isinstance(values, list) or not values or len(values) > 12:
        raise ValueError("Provide between one and twelve allowed publisher domains")
    return list(dict.fromkeys(_domain(item) for item in values))


def allowed_url(url: str, domains: list[str]) -> str:
    """Return a normalized allowed public HTTP(S) URL, otherwise an empty string.

    This is hostname validation only. The caller must apply its own public-IP,
    redirect and access-policy checks before fetching a discovered article.
    """
    if not isinstance(url, str) or len(url) > 4096 or re.search(r"[\x00-\x20\\]", url):
        return ""
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or parts.username is not None or
                parts.password is not None or not parts.hostname):
            return ""
        host = _domain(parts.hostname)
        if parts.port not in {None, 443 if parts.scheme == "https" else 80}:
            return ""
        if not any(host == domain or host.endswith("." + domain) for domain in domains):
            return ""
        # Fragments cannot distinguish articles and are not sent to the server.
        return urlunsplit((parts.scheme, host, parts.path or "/", parts.query, ""))
    except (ValueError, UnicodeError):
        return ""


def _clean(value, limit: int) -> str:
    if not isinstance(value, (str, int, float)):
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", str(value))).split())[:limit]


def _terms(company: dict) -> list[str]:
    raw = company.get("search_terms")
    if not isinstance(raw, list) or not raw:
        aliases = company.get("aliases", [])
        raw = [company.get("name", "")] + (aliases if isinstance(aliases, list) else [])
    terms = []
    for item in raw:
        # Alias strings are quoted as data; quotes/backslashes cannot add operators.
        term = _clean(item, 100).replace('"', " ").replace("\\", " ")
        term = " ".join(term.split())
        if term and term.casefold() not in {other.casefold() for other in terms}:
            terms.append(term)
        if len(terms) == 4:
            break
    return terms


def build_query(company: dict, domains: list[str]) -> str:
    """One bounded issuer query, including configured related-party aliases."""
    sites = "(" + " OR ".join("site:" + domain for domain in _domains(domains)) + ")"
    terms = _terms(company)
    while terms:
        names = "(" + " OR ".join('"' + term + '"' for term in terms) + ")"
        query = names + " AND " + sites
        if len(query) <= 600 and len(query.split()) <= 75:
            return query
        terms.pop()
    raise ValueError("Issuer needs usable search terms within provider query limits")


def _number(value, default, minimum, maximum, integer=False):
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError
        return max(minimum, min(maximum, int(number) if integer else number))
    except (ValueError, TypeError, OverflowError):
        return default


def discover(source: dict, watchlist: list, asof: datetime, hours: int,
             fetcher=None) -> tuple[list, dict]:
    """Collect leads only when explicitly enabled and an environment key exists.

    Defaults: six requests, ten results/request, one query/issuer, no retries or
    pagination. A custom freshness range is only a discovery hint; verified
    source publication timestamps must determine final email eligibility.
    """
    targets = []
    selected = source.get("tickers", [])
    for company in watchlist:
        ticker = company.get("ticker")
        if ticker and (not selected or ticker in selected) and ticker not in [c["ticker"] for c in targets]:
            targets.append(company)
    report = {
        "id": source.get("id", "brave-search"),
        "name": source.get("name", "Brave publisher discovery"),
        "provider": "brave", "status": "disabled",
        "tickers": [company["ticker"] for company in targets],
        "queried_tickers": [], "successful_tickers": [], "failed_tickers": [],
        "unsearched_tickers": [company["ticker"] for company in targets],
        "queries": [], "errors": [], "rejected_urls": 0,
        "discovered": 0, "truncated": False,
        "coverage_note": "Search index coverage is partial. Snippets and search dates are unverified leads; publisher text and publication time still need checking.",
    }
    if source.get("enabled") is not True:
        report["message"] = "Optional search is disabled."
        return [], report
    token = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if not token:
        report.update(status="not_configured", message="BRAVE_SEARCH_API_KEY is not configured in the local environment.")
        return [], report
    try:
        domains = _domains(source.get("allowed_domains"))
        if asof.tzinfo is None or asof.utcoffset() is None or not 0 < hours <= 744:
            raise ValueError("Use a timezone-aware cutoff and a lookback of 1-744 hours")
        freshness = f"{(asof - timedelta(hours=hours)).date().isoformat()}to{asof.date().isoformat()}"
    except (ValueError, TypeError, AttributeError):
        report.update(status="failed", message="Invalid domains, cutoff or lookback in search configuration.")
        return [], report
    max_queries = _number(source.get("max_queries"), 6, 1, 60, integer=True)
    count = _number(source.get("count"), 10, 1, 20, integer=True)
    timeout = _number(source.get("request_timeout_seconds"), 15, 1, 30)
    interval = _number(source.get("request_interval_seconds"), 1.5, 1, 30)
    report.update(max_queries=max_queries, count=count, freshness=freshness, allowed_domains=domains)
    records = {}
    request_json = fetcher or _request_json
    for company in targets[:max_queries]:
        ticker = company["ticker"]
        try:
            query = build_query(company, domains)
        except ValueError:
            report["errors"].append({"ticker": ticker, "error": "No usable issuer query; check search_terms."})
            report["failed_tickers"].append(ticker)
            continue
        if report["queries"]:
            time.sleep(interval)
        query_report = {"ticker": ticker, "query": query, "status": "failed"}
        report["queries"].append(query_report)
        report["queried_tickers"].append(ticker)
        params = {"q": query, "count": count, "freshness": freshness,
                  "country": source.get("country", "JP"),
                  "search_lang": source.get("search_lang", "jp"),
                  "spellcheck": "false", "text_decorations": "false", "result_filter": "web"}
        try:
            request = Request(BRAVE_ENDPOINT + "?" + urlencode(params),
                              headers={"Accept": "application/json", "X-Subscription-Token": token,
                                       "User-Agent": "MorningNote/1.0"})
            result = request_json(request, timeout=timeout)
            if not isinstance(result, dict) or result.get("error") or result.get("type") == "ErrorResponse":
                raise ValueError("Invalid provider response")
            if "web" not in result and not (result.get("type") == "search" and isinstance(result.get("query"), dict)):
                raise ValueError("Missing provider search response")
            web = result.get("web") or {}
            if not isinstance(web, dict) or not isinstance(web.get("results", []), list):
                raise ValueError("Invalid provider result list")
            results = web.get("results", [])
            query_report.update(status="ok", returned=len(results), accepted=0)
            provider_query = result.get("query") or {}
            if len(results) >= count or (isinstance(provider_query, dict) and provider_query.get("more_results_available")):
                query_report["result_cap_reached"] = True
                report["truncated"] = True
            for item in results[:count]:
                if not isinstance(item, dict):
                    continue
                url = allowed_url(item.get("url", ""), domains)
                if not url:
                    report["rejected_urls"] += 1
                    continue
                query_report["accepted"] += 1
                if url in records:
                    if ticker not in records[url]["discovered_for"]:
                        records[url]["discovered_for"].append(ticker)
                    continue
                records[url] = {
                    "title": _clean(item.get("title", ""), 500), "url": url,
                    "text": "", "published": "",
                    "discovery_snippet": _clean(item.get("description", ""), 600),
                    "discovery_date_hint": _clean(item.get("page_age") or item.get("age") or item.get("published"), 120),
                    "discovered_for": [ticker], "evidence_level": "search_lead",
                    "access_status": "metadata_only", "publisher_domain": urlsplit(url).hostname,
                }
            report["successful_tickers"].append(ticker)
        except Exception as exc:
            # Never persist exception text, request objects or response bodies:
            # third-party failures can contain credentials or request headers.
            error = f"Provider returned HTTP {exc.code}." if isinstance(exc, HTTPError) else "Provider request failed or returned invalid data."
            query_report["error"] = error
            report["errors"].append({"ticker": ticker, "error": error})
            report["failed_tickers"].append(ticker)
            if isinstance(exc, HTTPError) and exc.code in {401, 403, 429}:
                break
    report["unsearched_tickers"] = [company["ticker"] for company in targets
                                     if company["ticker"] not in report["queried_tickers"]]
    report["truncated"] = report["truncated"] or bool(report["unsearched_tickers"])
    report["discovered"] = len(records)
    if report["errors"] and not report["successful_tickers"]:
        report["status"] = "failed"
    elif report["errors"] or report["truncated"]:
        report["status"] = "partial"
    else:
        report["status"] = "ok"
    return list(records.values()), report
