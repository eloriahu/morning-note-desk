"""Local public-source morning-note collector and reviewable email generator.

No account connections, message sending, scheduler, or language-model calls.
Imported email bodies are data, never commands or fetch instructions.
"""
from __future__ import annotations

import argparse
import hashlib
import html as escape_html
import io
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, format_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from lxml import etree, html

ROOT = Path(__file__).resolve().parent
SECTIONS = ["Merger Arbitrage", "Fundamental/Pre-Event", "Relative Value", "Other Strategy"]
TRACKING_KEYS = {"gclid", "fbclid", "mc_cid", "mc_eid"}
EVENT_RULES = [
    ("Tender/deadline", r"\b(tender|TOB|last day|deadline|delist|squeeze.out)\b"),
    ("Court/shareholder vote", r"\b(court|scheme|vote|shareholder approval|EGM)\b"),
    ("Regulatory decision", r"\b(antitrust|regulator|clearance|ACCC|CADE|FIRB|CFIUS|aprova\w*)\b"),
    ("Deal terms/process", r"\b(merger|acquisition|takeover|offer|exclusivity|buyout|bid|go.shop)\b"),
    ("Ownership", r"\b(stake|shareholding|shareholder|buys shares|disclosure of interest)\b"),
    ("Results/guidance", r"\b(results|earnings|guidance|EBITDA|dividend)\b"),
    ("Capital raising/IPO", r"\b(IPO|listing|issuance|senior notes|bond|capital raising)\b"),
]
MA_PATTERN = r"\b(merger|acquisition|takeover|tender|TOB|bid|buyout|scheme|antitrust|exclusivity|go.shop|M&A|offer price|acquire)\b|買収|合併|TOB|公開買付|非公開化|aquisi[çc][aã]o|fus[aã]o"


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def node_text(node):
    return clean(" ".join(node.itertext()))


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def safe_url(url):
    p = urlsplit(clean(url))
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("Expected a public HTTP(S) URL without credentials")
    if p.port not in (None, 80, 443):
        raise ValueError("Only normal HTTP(S) ports are supported")
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))


def canonical_url(url):
    p = urlsplit(safe_url(url))
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(sorted(query)), ""))


def public_url(url):
    url = safe_url(url)
    p = urlsplit(url)
    for addr in socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80)):
        if not ipaddress.ip_address(addr[4][0]).is_global:
            raise ValueError("Local and private network addresses are not collection sources")
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    def __init__(self, config):
        self.timeout = config.get("request_timeout_seconds", 15)
        self.interval = config.get("request_interval_seconds", 1.5)
        self.last = {}
        self.cache = {}
        self.opener = urllib.request.build_opener(SafeRedirect())

    def get(self, url):
        url = public_url(url)
        if url in self.cache:
            return self.cache[url]
        host = urlsplit(url).hostname
        for attempt in range(2):
            delay = self.interval - (time.monotonic() - self.last.get(host, 0))
            if delay > 0:
                time.sleep(delay)
            self.last[host] = time.monotonic()
            req = urllib.request.Request(url, headers={
                "User-Agent": "MorningNoteResearch/0.1 (public announcement review)",
                "Accept": "application/rss+xml, application/atom+xml, text/html, application/pdf;q=0.8, */*;q=0.5",
            })
            try:
                with self.opener.open(req, timeout=self.timeout) as response:
                    raw = response.read(8_000_001)
                    if len(raw) > 8_000_000:
                        raise ValueError("Document exceeds the 8 MB collection limit")
                    result = (raw, response.headers.get("Content-Type", ""), response.geturl())
                    self.cache[url] = result
                    return result
            except urllib.error.HTTPError as exc:
                if attempt or exc.code not in (429, 500, 502, 503, 504):
                    raise
                retry = exc.headers.get("Retry-After", "2")
                # Do not retry earlier than a server's requested long backoff.
                if not retry.isdigit() or int(retry) > 8:
                    raise
                time.sleep(max(2, int(retry)))
            except (urllib.error.URLError, TimeoutError):
                if attempt:
                    raise
                time.sleep(2)
        raise RuntimeError("Fetch exhausted")


def parse_date(value, tz="UTC"):
    """Return datetime plus precision; never turn a missing date into 'today'."""
    value = clean(value)
    if not value:
        return None, "missing"
    japanese = re.fullmatch(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(\d{1,2})[:時](\d{2})(?:分)?)?", value)
    if japanese:
        year, month, day, hour, minute = japanese.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                            tzinfo=ZoneInfo(tz)), "time" if hour else "day"
        except ValueError:
            return None, "unparsed"
    precision = "time"
    dt = None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            precision = "day"
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError):
            pass
    if dt is None:
        for fmt, prec in [("%d/%m/%Y %Hh%M", "time"), ("%d/%m/%Y %H:%M", "time"),
                          ("%d/%m/%Y", "day"), ("%d %B %Y", "day"), ("%B %d, %Y", "day"),
                          ("%b %d, %Y", "day"), ("%b. %d, %Y", "day"),
                          ("%Y/%m/%d", "day"), ("%Y.%m.%d", "day"),
                          ("%Y/%m/%d %H:%M:%S", "time")]:
            try:
                dt = datetime.strptime(value, fmt)
                precision = prec
                break
            except ValueError:
                continue
    if dt is None:
        return None, "unparsed"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt, precision


def text_from_html(markup):
    if not clean(markup):
        return ""
    tree = html.fromstring(markup)
    for bad in tree.xpath("//script | //style | //nav | //header | //footer | //noscript"):
        bad.drop_tree()
    return node_text(tree)


def extract_document(raw, kind, url):
    if raw.startswith(b"%PDF") or "application/pdf" in kind:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(p.extract_text() or "" for p in reader.pages[:50])
        return {"title": "", "text": clean(text), "published": "", "date_precision": "missing"}
    tree = html.fromstring(raw)
    title = tree.xpath("//h1[1] | //meta[@property='og:title']/@content")
    title = node_text(title[0]) if title and hasattr(title[0], "itertext") else (title[0] if title else "")
    published = tree.xpath("//meta[@property='article:published_time']/@content | "
                           "//meta[@name='date']/@content | //time/@datetime | "
                           "//span[contains(@class,'documentPublished')]//span[contains(@class,'value')]/text()")
    for bad in tree.xpath("//script | //style | //nav | //header | //footer | //noscript | "
                          "//*[contains(@class,'social-links')] | //form"):
        if bad.getparent() is not None:
            bad.drop_tree()
    main = tree.xpath("//*[@id='parent-fieldname-text'] | //*[@id='content-core'] | //article | //main")
    chosen = next((n for n in main if n.get("id") == "parent-fieldname-text"), None)
    if chosen is None:
        chosen = main[0] if main else tree
    paragraphs = [node_text(p) for p in chosen.xpath(".//p") if len(node_text(p)) >= 35]
    return {"title": clean(title), "text": "\n".join(paragraphs) or node_text(chosen),
            "published": clean(published[0]) if published else ""}


def feed_items(raw, base_url):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    tree = etree.fromstring(raw, parser=parser)
    if etree.QName(tree).localname.lower() not in ("rss", "rdf", "feed"):
        raise ValueError("Source returned a page instead of an RSS/Atom feed")
    result = []
    for item in tree.xpath("//*[local-name()='item' or local-name()='entry']"):
        def field(names):
            for name in names:
                nodes = item.xpath("./*[local-name()=$n]", n=name)
                if nodes:
                    return "".join(nodes[0].itertext()).strip()
            return ""
        links = item.xpath("./*[local-name()='link']")
        link = next((n.get("href") or n.text for n in links
                     if n.get("rel", "alternate") == "alternate"), "")
        if not link:
            continue
        result.append({"title": clean(field(["title"])), "url": urljoin(base_url, link),
                       "text": text_from_html(field(["description", "summary", "content", "encoded"])),
                       "published": field(["pubDate", "published", "date"]),
                       "updated": field(["updated"])})
    return result


def watch_matches(text, watchlist):
    matched = []
    for item in watchlist:
        names = [item["ticker"], item["name"]] + item.get("aliases", [])
        def matches(name):
            name = clean(name)
            if len(name) < 3:
                return False
            if re.search(r'[\u3040-\u30ff\u3400-\u9fff]', name):
                return name.casefold() in text.casefold()
            return re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I) is not None
        if any(matches(n) for n in names):
            matched.append(item)
    return matched


def issuer_jsonp_items(raw, source):
    """Read an official public news widget as data; never execute JavaScript."""
    markup = raw.decode(source.get('encoding', 'utf-8-sig')).strip()
    callback = source['callback']
    wrapped = re.fullmatch(re.escape(callback) + r'\s*\((.*)\)\s*;?', markup, flags=re.S)
    if not wrapped:
        raise ValueError('Official news widget wrapper has changed')
    data = json.loads(wrapped.group(1))
    entries = data.get('item')
    if not isinstance(entries, list):
        raise ValueError('Official news widget has no item list')
    records = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get('title') or not entry.get('link'):
            continue
        records.append({'title': text_from_html(entry['title']), 'url': entry['link'], 'text': '',
                        'published': entry.get(source.get('date_field', 'date'), ''),
                        'language': source.get('language_mapping', {}).get(entry.get(source.get('language_field', '')), source.get('language', 'ja'))})
    return records


def event_label(text):
    return next((name for name, pattern in EVENT_RULES if re.search(pattern, text, re.I)), "Company update")


def within_window(published, precision, start, asof, tz):
    dt, _ = parse_date(published, tz)
    if dt is None:
        return "date_needs_review"
    if precision == "day":
        # A date is an interval, not proof of pre-cutoff availability.
        if dt > asof:
            return "future"
        if dt + timedelta(days=1) <= start:
            return "old"
        return "date_needs_review"
    if dt > asof:
        return "future"
    return "current" if dt >= start else "old"


def classify_record(record, source, watchlist, start, asof, prior):
    text = record["title"] + " " + record.get("text", "")
    matched = watch_matches(text, watchlist)
    tickers = list(dict.fromkeys(source.get("tickers", []) + [m["ticker"] for m in matched]))
    active_tickers = {w["ticker"] for w in watchlist}
    tickers = [t for t in tickers if t in active_tickers]
    label = record.get('event_type') or event_label(text)
    broad = bool(source.get('broad_discovery'))
    if not tickers and not broad:
        return None, "no_watchlist_match"
    topic = clean(source.get("topic", ""))
    topic_discovery_only = False
    if topic:
        expression = MA_PATTERN if topic.lower() in ("m&a", "ma", "mergers") else re.escape(topic)
        if not re.search(expression, text, re.I):
            discovery = record.get('discovery_title', '') + ' ' + record.get('discovery_snippet', '')
            if re.search(expression, discovery, re.I):
                topic_discovery_only = True
            else:
                return None, "topic_not_matched"
    dt, precision = parse_date(record.get("published"), source.get("timezone", "UTC"))
    window = within_window(record.get("published", ""), precision, start, asof, source.get("timezone", "UTC"))
    category = record.get('category') or source.get("category") or (matched[0].get("category") if matched else None) or "Other Strategy"
    if category not in SECTIONS:
        category = "Other Strategy"
    url = canonical_url(record["url"])
    record_id = digest(url)[:20]
    content_hash = digest(clean(record["title"]) + "\n" + clean(record.get("text", "")))
    old = prior.get(record_id)
    status = "changed" if old and old["content_hash"] != content_hash else "unchanged" if old else "new"
    if window == "future":
        return None, window
    if window == "old":
        if status != "changed":
            return None, window
        window = "date_needs_review"
    if status == "unchanged" and old.get("edition_date", asof.date().isoformat()) < asof.date().isoformat():
        return None, "previous_edition_unchanged"
    flags = []
    flags.append("Newly found document or wording; material novelty versus known deal facts still requires review.")
    if broad:
        flags.append('Attention ranking is a provisional event-keyword screen; confirm relevance and identities against the source.')
    if broad and not tickers:
        flags.append('Outside the priority list. Confirm the company, listing and ticker before including it in the stock email.')
    if topic_discovery_only:
        flags.append("Topic match appears only in discovery metadata; verify relevance in the original article.")
    if window == "date_needs_review":
        flags.append("Publication time not established; confirm it was available before the cutoff.")
    language = record.get("language") or source.get("language", "en")
    if not language.lower().startswith("en"):
        flags.append("Original-language source; translation requires review.")
    if not record.get("text"):
        flags.append("Headline only; read the original document before using.")
    if label == "Tender/deadline":
        flags.append("Tender and trading cutoffs require the official timetable and broker confirmation.")
    publisher = broad or source.get("publisher", False) or source.get("issuer_official", False) or source.get("kind") == "brave_search"
    access = record.get("access_status") or ("metadata_only" if publisher else "readable")
    if publisher and access != "readable":
        flags.append("Article not fully available: " + access + ". Discovery lead only; do not infer the full story.")
    if record.get("article_error"):
        flags.append(record["article_error"])
    requires_translation = publisher and not language.lower().startswith("en")
    discovery_only = bool(record.get('discovery_only_tickers'))
    if discovery_only:
        flags.append("Issuer relationship appears only in discovery metadata; confirm it in the source before drafting.")
    if requires_translation:
        flags.append("English summary still needed; source retained in the review queue.")
    previous = old.get("title", "") if old and status == "changed" else ""
    output = dict(record, id=record_id, url=url, tickers=tickers, category=category, event_type=label,
                  source=source["name"], source_id=source["id"], published=dt.isoformat() if dt else None,
                  date_precision=precision, fetched_at=datetime.now(timezone.utc).isoformat(),
                  content_hash=content_hash, change=status, previous_title=previous, flags=flags,
                  eligible=window == "current" and not (publisher and access != "readable") and not requires_translation and not discovery_only and not topic_discovery_only and not (broad and not tickers),
                  access_status=access, language=language, historical=False,
                  collection_role=source.get('collection_role', 'priority'), priority_match=bool(tickers), identity_verified=bool(tickers))
    return output, window


def domain_allowed(url, domains):
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d.lower() or host.endswith('.' + d.lower()) for d in domains)


def expand_publisher_leads(leads, source, watchlist, fetcher, start, asof, report, limit, discovery_log=None):
    """Fetch matched public articles; access failures remain visible review leads."""
    from publisher_extract import extract_publisher_document
    prepared = []
    fetched = 0
    domains = source.get('allowed_domains') or [urlsplit(source['url']).hostname]
    fixed_issuer = source.get('issuer_official') and bool(set(source.get('tickers', [])) & {w['ticker'] for w in watchlist})
    broad = bool(source.get('broad_discovery'))
    audit = {}
    if broad:
        from market_radar import triage
        ranked = []
        for lead in leads:
            matches = watch_matches(lead.get('title', '') + ' ' + lead.get('text', ''), watchlist)
            scored = dict(lead, **triage(lead.get('title', ''), lead.get('text', ''), [w['ticker'] for w in matches]))
            ranked.append(scored)
            _, precision = parse_date(lead.get('published', ''), source.get('timezone', 'UTC'))
            entry = dict(title=lead.get('title', ''), url=lead.get('url', ''), source=source['name'], source_id=source['id'],
                         collection_role='market', published=lead.get('published', ''), date_precision=precision,
                         window_status=within_window(lead.get('published', ''), precision, start, asof, source.get('timezone', 'UTC')),
                         attention_score=scored['attention_score'], attention_reasons=scored['attention_reasons'],
                         priority_matches=[w['ticker'] for w in matches], stage='headline_scanned')
            audit[id(scored)] = entry
            if discovery_log is not None:
                discovery_log.append(entry)
        leads = sorted(ranked, key=lambda item: item['attention_score'], reverse=True)
    for lead in leads:
        log = audit.get(id(lead))
        discovery_text = lead.get('title', '') + ' ' + lead.get('text', '') + ' ' + lead.get('discovery_snippet', '')
        if not broad and not fixed_issuer and not watch_matches(discovery_text, watchlist):
            report['excluded']['discovery_no_name_match'] = report['excluded'].get('discovery_no_name_match', 0) + 1
            continue
        # Official publisher feed dates are usable; search-engine date hints are not.
        dt, precision = parse_date(lead.get('published', ''), source.get('timezone', 'Asia/Tokyo'))
        if dt is not None and within_window(lead['published'], precision, start, asof, source.get('timezone', 'Asia/Tokyo')) in ('old', 'future'):
            report['excluded']['outside_window'] = report['excluded'].get('outside_window', 0) + 1
            if log is not None:
                log['stage'] = 'outside_window'
            continue
        if broad and (not lead['market_relevant'] or lead['attention_score'] < source.get('min_attention_score', 35)):
            report['excluded']['below_attention_threshold'] = report['excluded'].get('below_attention_threshold', 0) + 1
            if log is not None:
                log['stage'] = 'below_attention_threshold'
            continue
        if not domain_allowed(lead.get('url', ''), domains):
            report['errors'].append('Discarded a discovery URL outside the configured publisher domains.')
            if log is not None:
                log['stage'] = 'outside_source_domains'
            continue
        item = dict(lead, access_status='metadata_only', evidence_level='discovery_lead',
                    language=lead.get('language') or source.get('language', 'ja'), date_origin=source.get('kind', 'publisher') if lead.get('published') else 'unknown')
        item['discovery_title'] = lead.get('title', '')
        item['discovery_matches'] = [w['ticker'] for w in watch_matches(discovery_text, watchlist)]
        if log is not None:
            log['stage'] = 'candidate_selected'
        if source.get('article_url_pattern') and not re.search(source['article_url_pattern'], lead['url']):
            item['article_error'] = 'This link is a changing information page, not a verified individual release. Open it and select the specific document before drafting.'
            item['evidence_level'] = 'index_lead'
            item['text'] = ''
            report['access_limited'] = report.get('access_limited', 0) + 1
            prepared.append(item)
            continue
        if fetched >= limit:
            item['article_error'] = 'Article fetch cap reached. Source details have not been checked.'
            prepared.append(item)
            if log is not None:
                log['stage'] = 'article_cap_pending'
            if 'Article fetch cap reached; discovery coverage is partial.' not in report['errors']:
                report['errors'].append('Article fetch cap reached; discovery coverage is partial.')
            continue
        fetched += 1
        try:
            raw, kind, final_url = fetcher.get(lead['url'])
            if not domain_allowed(final_url, domains):
                raise ValueError('Publisher link redirected outside the configured source domains')
            if source.get('issuer_official') and (raw.startswith(b'%PDF') or 'application/pdf' in kind):
                doc = extract_document(raw, kind, final_url)
                doc.update(access_status='readable' if clean(doc.get('text')) else 'metadata_only',
                           evidence_level='official_pdf_text', language=lead.get('language') or source.get('language', ''))
            else:
                doc = extract_publisher_document(raw, kind, final_url)
            item.update(doc)
            item['language'] = doc.get('language') or lead.get('language') or source.get('language', '')
            item['title'] = doc.get('title') or lead['title']
            item['url'] = final_url
            item['published'] = doc.get('published') or lead.get('published', '')
            item['updated'] = doc.get('updated') or lead.get('updated', '')
            item['date_origin'] = 'article' if doc.get('published') else item['date_origin']
            # Keep discovery snippets separate: they are not article evidence.
            item['discovery_snippet'] = lead.get('discovery_snippet') or lead.get('text', '')
            evidence_matches = {w['ticker'] for w in watch_matches(item['title'] + ' ' + item.get('text', ''), watchlist)}
            item['discovery_only_tickers'] = [t for t in item['discovery_matches'] if t not in evidence_matches and t not in source.get('tickers', [])]
            if item.get('access_status') != 'readable':
                report['access_limited'] = report.get('access_limited', 0) + 1
            if log is not None:
                log.update(stage='article_checked', access_status=item.get('access_status'))
        except Exception as exc:
            item.update(text='', access_status='unavailable', article_error=f'Article retrieval failed: {type(exc).__name__}: {exc}')
            report['access_limited'] = report.get('access_limited', 0) + 1
            if log is not None:
                log.update(stage='article_unavailable', access_status='unavailable')
        # Preserve an issuer-name discovery match if the paywall hides the article text.
        item['discovery_matches'] = [w['ticker'] for w in watch_matches(discovery_text, watchlist)]
        prepared.append(item)
    report['articles_attempted'] = fetched
    return prepared


def collect(config, watchlist, inbox, asof, prior, discovery_log=None):
    fetcher = Fetcher(config)
    start = asof - timedelta(hours=config["lookback_hours"])
    sources = list(config["sources"])
    for i, entry in enumerate(inbox):
        sources.append(dict(entry, id=f"inbox-{i+1}", name=entry.get("name", "Public announcement"),
                            kind="document", enabled=True))
    market_first = config.get('discovery_mode') in ('market_first', 'market-first')
    if market_first:
        sources.sort(key=lambda item: item.get('collection_role') != 'market')
    candidates, coverage = [], []
    for source in sources:
        source = dict(source, topic=config.get("topic", ""),
                      broad_discovery=market_first and source.get('collection_role') == 'market')
        report = {"id": source["id"], "name": source["name"], "url": source.get("url", ""),
                  "tickers": source.get("tickers", []), "status": "disabled", "discovered": 0,
                  "matched": 0, "excluded": {}, "errors": [], "coverage_note": source.get('coverage_note', ''),
                  "issuer_official": source.get('issuer_official', False), "scope_market": source.get('scope_market', ''),
                  "collection_role": source.get('collection_role', 'priority')}
        if not source.get("enabled", True):
            report["errors"].append(source.get("disabled_reason", "Not enabled"))
            coverage.append(report)
            continue
        source_watchlist = [w for w in watchlist if w['ticker'].endswith(' ' + source['scope_market'])] if source.get('scope_market') else watchlist
        if source.get('tickers') and (source.get('issuer_official') or source.get('collection_role') == 'priority'):
            source_watchlist = [w for w in source_watchlist if w['ticker'] in source['tickers']]
        if not source_watchlist and not source['broad_discovery']:
            report.update(status='not_applicable', errors=['No selected companies fall within this source scope.'])
            coverage.append(report)
            continue
        report['scope_tickers'] = [w['ticker'] for w in source_watchlist]
        print("Checking " + source["name"] + "...", flush=True)
        try:
            if source['kind'] == 'brave_search':
                from search_discovery import discover
                records, search_report = discover(source, source_watchlist, asof, config['lookback_hours'])
                report.update(search_report)
                report.setdefault('excluded', {})
                report.setdefault('errors', [])
                if report['status'] in ('not_configured', 'disabled', 'failed'):
                    coverage.append(report)
                    continue
                report['discovered'] = len(records)
                records = expand_publisher_leads(records, source, source_watchlist, fetcher, start, asof, report,
                                                  config.get('max_documents_per_source', 12), discovery_log)
            else:
                raw, kind, final_url = fetcher.get(source["url"])
            if source["kind"] == "feed":
                records = feed_items(raw, final_url)
            elif source['kind'] == 'issuer_jsonp':
                records = issuer_jsonp_items(raw, source)
            elif source["kind"] == "document":
                doc = extract_document(raw, kind, final_url)
                records = [dict(doc, url=final_url, title=source.get("title") or doc["title"],
                                published=source.get("published") or doc["published"])]
            elif source["kind"] in ("publisher_index", "issuer_index"):
                tree = html.fromstring(raw, parser=html.HTMLParser(encoding=source.get('encoding', 'utf-8')))
                records, seen = [], set()
                for node in tree.xpath(source.get('item_xpath') or source['link_xpath']):
                    if source.get('item_xpath'):
                        anchors = node.xpath(source['item_link_xpath'])
                        if not anchors:
                            continue
                        anchor = anchors[0]
                    else:
                        anchor = node
                    url = urljoin(final_url, anchor.get('href', ''))
                    if url in seen or not domain_allowed(url, source.get('allowed_domains') or [urlsplit(final_url).hostname]):
                        continue
                    seen.add(url)
                    title_nodes = node.xpath(source['title_xpath']) if source.get('title_xpath') else []
                    title = (clean(title_nodes[0]) if isinstance(title_nodes[0], str) else node_text(title_nodes[0])) if title_nodes else node_text(anchor)
                    if len(title) < 6:
                        continue
                    dates = node.xpath(source['date_xpath']) if source.get('date_xpath') else []
                    published = clean(dates[0]) if dates and isinstance(dates[0], str) else node_text(dates[0]) if dates else ''
                    if source.get('date_format') and published:
                        try:
                            published = datetime.strptime(published, source['date_format']).date().isoformat()
                        except ValueError:
                            pass  # Leave the source wording unparsed and hold it for review.
                    records.append({'title': title, 'url': url, 'text': '', 'published': published})
                report['index_links'] = len(seen)
                if not records:
                    raise ValueError('No announcement/article links found; the page may be restricted or its layout changed')
            elif source["kind"] == "html_index":
                tree = html.fromstring(raw, parser=html.HTMLParser(encoding=source.get('encoding', 'utf-8')))
                records, seen = [], set()
                for anchor in tree.xpath(source["link_xpath"]):
                    url = urljoin(final_url, anchor.get("href", ""))
                    if urlsplit(url).hostname != urlsplit(final_url).hostname or url in seen:
                        continue
                    seen.add(url)
                    if source['broad_discovery']:
                        headline = node_text(anchor)
                        if headline:
                            records.append(dict(title=headline, url=url, text='', published=''))
                        continue
                    # Title screening bounds the crawl. Body-only mentions can be missed.
                    if not source.get("tickers") and not watch_matches(node_text(anchor), watchlist):
                        report["excluded"]["index_title_no_match"] = report["excluded"].get("index_title_no_match", 0) + 1
                        continue
                    if len(records) >= config.get("max_documents_per_source", 12):
                        report["errors"].append("Document cap reached; source coverage is partial.")
                        break
                    try:
                        body, ctype, article_url = fetcher.get(url)
                        doc = extract_document(body, ctype, article_url)
                        records.append(dict(doc, title=doc["title"] or node_text(anchor), url=article_url))
                    except Exception as exc:
                        report["errors"].append(f"{url}: {type(exc).__name__}: {exc}")
                report["index_links"] = len(seen)
                if not seen:
                    raise ValueError("No article links found; the page layout may have changed")
            elif source['kind'] != 'brave_search':
                raise ValueError("Unknown source kind")
            if (source.get('publisher') or source.get('issuer_official') or source['broad_discovery']) and source['kind'] != 'brave_search':
                report['discovered'] = len(records)
                records = expand_publisher_leads(records, source, source_watchlist, fetcher, start, asof, report,
                                                  config.get('max_documents_per_source', 12), discovery_log)
            else:
                report["discovered"] = max(report.get('discovered', 0), len(records))
            for record in records:
                try:
                    # A name matched in the publisher's public headline is still a useful
                    # review lead when the body is unavailable; never treat it as body evidence.
                    record_source = dict(source, tickers=list(dict.fromkeys(source.get('tickers', []) + record.get('discovery_matches', []))))
                    prepared, outcome = classify_record(record, record_source, source_watchlist, start, asof, prior)
                    if prepared:
                        candidates.append(prepared)
                        report["matched"] += 1
                    else:
                        report["excluded"][outcome] = report["excluded"].get(outcome, 0) + 1
                except Exception as exc:
                    report["errors"].append(f"Record rejected: {type(exc).__name__}: {exc}")
            report["status"] = "partial" if report["errors"] or report.get('access_limited') or report.get('unsearched_tickers') or report.get('truncated') else "ok"
        except Exception as exc:
            report["status"] = "failed"
            report["errors"].append(f"{type(exc).__name__}: {exc}")
        coverage.append(report)
    # Identical documents reached through different feeds are one candidate.
    unique, content_seen = {}, {}
    for candidate in candidates:
        signature = digest(clean(candidate["title"]).casefold() + "\n" + clean(candidate.get("text", "")).casefold())
        readable = candidate.get('access_status', 'readable') == 'readable'
        if readable and signature in content_seen:
            original = unique[content_seen[signature]]
            original.setdefault("also_reported_at", []).append(candidate["url"])
            original['tickers'] = list(dict.fromkeys(original['tickers'] + candidate['tickers']))
            original['discovery_matches'] = list(dict.fromkeys(original.get('discovery_matches', []) + candidate.get('discovery_matches', [])))
            continue
        older_duplicate = next((p for key, p in prior.items() if readable and key != candidate["id"]
                                and p.get("content_hash") == candidate["content_hash"]
                                and p.get("edition_date", asof.date().isoformat()) < asof.date().isoformat()), None)
        if older_duplicate:
            continue
        if candidate["id"] not in unique:
            unique[candidate["id"]] = candidate
            if readable:
                content_seen[signature] = candidate["id"]
        else:
            existing = unique[candidate["id"]]
            existing["tickers"] = list(dict.fromkeys(existing["tickers"] + candidate["tickers"]))
    return list(unique.values()), coverage


def brief_bullets(record):
    if record.get("historical"):
        return record.get("bullets", [])
    # The title and excerpt together contain no more than 25 source words.
    # No unsupported generated facts or silent translation are introduced.
    allowance = max(0, 25 - len(record["title"].split()))
    words = clean(record.get("text", "")).split()
    bullets = []
    if allowance and words:
        fragment = " ".join(words[:allowance]) + ("…" if len(words) > allowance else "")
        bullets.append("Source excerpt: “" + fragment + "”")
    else:
        bullets.append("Read the linked announcement for the details.")
    return bullets


def timing_flags(text, asof):
    flags = []
    pattern = r"\bOn (\d{1,2}) ([A-Za-z]{3}) after market close\b"
    for day, month in re.findall(pattern, text, re.I):
        try:
            event_date = datetime.strptime(f"{day} {month} {asof.year}", "%d %b %Y").date()
            if event_date >= asof.date() and asof.hour < 12:
                flags.append("Timing conflict: same-day/future 'after market close' appears in a morning email.")
        except ValueError:
            pass
    return flags


def import_email(path):
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    part = message.get_body(preferencelist=("html",))
    if part is None:
        raise ValueError(f"{path.name}: expected an HTML email")
    asof = parsedate_to_datetime(str(message["Date"])).astimezone(ZoneInfo("Asia/Singapore"))
    tree = html.fromstring(part.get_content())
    stories = []
    for container in tree.xpath("//div[contains(concat(' ',normalize-space(@class),' '),' list-content-container ')]"):
        first = container.xpath("./div[1]")[0]
        header = first.xpath("./table[1]//td[1]/span")
        if len(header) < 2:
            continue
        ticker, company = node_text(header[0]), node_text(header[1])
        headline = first.xpath("./span[1]")
        if not headline:
            continue
        headline = headline[0]
        title = clean(headline.text)
        refs = headline.xpath(".//a")
        source_name = clean(node_text(headline)[len(title):]) or "Sample email"
        section_nodes = container.xpath("preceding::span[normalize-space(.)='Merger Arbitrage' or "
                                        "normalize-space(.)='Fundamental/Pre-Event' or "
                                        "normalize-space(.)='Relative Value' or "
                                        "normalize-space(.)='Other Strategy']")
        category = node_text(section_nodes[-1]) if section_nodes else "Other Strategy"
        bodies = first.xpath("./div[contains(@class,'font-size-10')]")
        bullets = []
        if bodies:
            body = bodies[0]
            for br in body.xpath(".//br"):
                br.tail = " __NOTE_BREAK__ " + (br.tail or "")
            plain = node_text(body)
            bullets = [clean(p).lstrip("* ") for p in plain.split("__NOTE_BREAK__") if clean(p)]
        text = " ".join(bullets)
        flags = ["Historical sample; claims have not been independently verified."] + timing_flags(text, asof)
        if refs:
            flags.append("Sample link uses tracking redirects; original source URL must be supplied for live collection.")
        stories.append({"id": digest(path.name + ticker + title)[:20], "title": title,
                        "company": company, "tickers": [ticker], "category": category,
                        "source": source_name, "source_id": path.name, "url": "", "published": asof.isoformat(),
                        "date_precision": "email_date", "bullets": bullets, "text": text,
                        "event_type": event_label(title + " " + text), "change": "sample",
                        "flags": flags, "eligible": True, "historical": True})
    if not stories:
        raise ValueError(f"{path.name}: no sample stories found; unexpected email layout")
    return {"filename": path.name, "asof": asof.isoformat(), "stories": stories}


def write_watchlist(samples, output):
    names = {}
    for sample in samples:
        for story in sample["stories"]:
            ticker = story["tickers"][0]
            if re.fullmatch(r"[A-Z0-9]+ (AU|HK|JP|SP|NZ|MK|PM)", ticker):
                names[ticker] = {"ticker": ticker, "name": story["company"], "aliases": [], "category": story["category"]}
    aliases = {}
    for ticker, value in names.items():
        value["aliases"] = aliases.get(ticker, [])
    write_json(output, list(names.values()))
    return len(names)


def e(value):
    return escape_html.escape(str(value or ""), quote=True)


def publication_label(record):
    if not record.get('published'):
        return 'publication time unconfirmed'
    if record.get('date_precision') == 'day':
        return record['published'][:10] + ' (date only; time unconfirmed)'
    return record['published']


def export_payload(records, coverage, config, asof):
    """Proposed integration contract, not a known internal publishing platform API schema."""
    tickers = config.get("selected_watchlist", [])
    by_ticker = []
    for company in tickers:
        matched = [r for r in records if company['ticker'] in r['tickers']]
        connected = [c for c in coverage if c['status'] == 'ok'
                     and (not c.get('tickers') or company['ticker'] in c['tickers'])
                     and (not c.get('scope_tickers') or company['ticker'] in c['scope_tickers'])
                     and ('successful_tickers' not in c or company['ticker'] in c['successful_tickers'])]
        if matched:
            status = "candidates_need_review"
            message = f"{len(matched)} relevant candidate(s) found; confirm which facts are new."
        elif connected:
            status = "no_new_items_in_checked_sources"
            message = "No new relevant items found in the connected sources checked. Coverage is partial."
        else:
            status = "coverage_incomplete"
            message = "Collection coverage is insufficient to determine whether there is new information."
        by_ticker.append({"ticker": company['ticker'], "company": company['name'], "status": status,
                          "message": message, "checked_sources": [c['name'] for c in connected],
                          "candidate_ids": [r['id'] for r in matched]})
    return {"schema_version": "morning-note-draft/v1", "integration_status": "proposed contract; internal publishing platform not connected",
            "draft_only": True, "as_of": asof.isoformat(),
            "window_start": (asof - timedelta(hours=config.get('lookback_hours', 24))).isoformat(),
            "topic": config.get('topic') or 'Any material development',
            "watchlist_results": by_ticker, "items": [
                {"id": r['id'], "tickers": r['tickers'], "category": r['category'],
                 "headline": r['title'], "english_summary": None, "source_excerpt": brief_bullets(r),
                 "source_url": r.get('url'), "source_name": r['source'], "published_at": r.get('published'),
                 "document_change": r['change'], "novelty_verified": False,
                 "access_status": r.get('access_status', 'readable'), "language": r.get('language', 'en'),
                 "evidence_level": r.get('evidence_level', 'source_excerpt'),
                 "collection_role": r.get('collection_role', 'priority'),
                 "attention_score": r.get('attention_score'), "attention_reasons": r.get('attention_reasons', []),
                 "identity_verified": r.get('identity_verified', bool(r.get('tickers'))),
                 "proposed_new_facts": [], "known_background": [], "recycled_reporting": [],
                 "review_required": True, "eligible_for_email": r.get('eligible', False)} for r in records],
            "coverage": coverage}


def email_body(records, config, asof, historical=False):
    mode = "HISTORICAL SAMPLE — FOR REVIEW" if historical else "DRAFT — FOR REVIEW"
    hours = config.get('lookback_hours', 24)
    summary = "Reconstructed from the supplied email; not a fresh market update." if historical else f"Candidate new information in the last {hours} hours. Topic: {config.get('topic') or 'material developments'}."
    body = [f'<div style="font-family:Arial,sans-serif;color:#17243a;max-width:780px;margin:auto;padding:28px;background:white">',
            f'<p style="font-size:11px;letter-spacing:1.5px;color:#52677b">{mode}</p>',
            f'<h1 style="font-size:28px;margin:10px 0">{e(config["title"])}</h1>',
            f'<p style="color:#657388;font-size:13px">{e(asof.strftime("%A, %d %B %Y · %H:%M"))} {e(config["timezone"])}</p>',
            f'<p style="font-size:13px">{e(summary)}</p>']
    if not historical:
        body.append('<p style="padding:12px;background:#fff5df;color:#744f13;font-size:12px">Coverage is limited to the source checks shown in the review report. Restricted articles and untranslated leads require review.</p>')
    if not records:
        if config.get('held_count'):
            body.append(f'<p>{config["held_count"]} candidate lead(s) need review before they can be included in this English draft. See the research queue below.</p>')
        elif config.get('collection_failed'):
            body.append('<p>Collection coverage is incomplete. There is insufficient evidence to determine whether there is new information.</p>')
        else:
            body.append(f'<p>No new relevant items found in the connected sources checked over the last {hours} hours. Coverage is partial; see the collection report.</p>')
    else:
        body.append('<h2 style="font-size:16px;border-bottom:2px solid #183b61;padding-bottom:8px">Candidate headlines</h2><ul>')
        for r in records:
            body.append(f'<li style="font-size:13px;margin:6px 0"><a style="color:#173e68" href="#story-{e(r["id"])}">{e(" / ".join(r["tickers"]))} · {e(r["title"])}</a></li>')
        body.append('</ul>')
    for section in SECTIONS:
        group = [r for r in records if r["category"] == section]
        if not group:
            continue
        body.append(f'<h2 style="font-size:17px;color:#183b61;border-bottom:2px solid #dce5ee;padding:18px 0 8px">{e(section)}</h2>')
        for record in group:
            body.append(f'<div id="story-{e(record["id"])}" style="margin:22px 0"><p style="font-size:12px;font-weight:bold;color:#476884">{e(" / ".join(record["tickers"]))} {e(record.get("company", ""))}</p>')
            body.append(f'<h3 style="font-size:15px;margin:8px 0">{e(record["title"])}</h3><ul style="padding-left:19px;font-size:14px;line-height:1.65">')
            for bullet in brief_bullets(record):
                body.append(f'<li>{e(bullet)}</li>')
            body.append('</ul>')
            if record.get("url"):
                body.append(f'<p style="font-size:11px;color:#64748b"><a style="color:#245b8b" href="{e(safe_url(record["url"]))}">{e(record["source"])}</a> · published {e(record.get("published") or "time unconfirmed")}</p>')
            else:
                body.append(f'<p style="font-size:11px;color:#64748b">Source label in sample: {e(record["source"])} · original link not resolved</p>')
            body.append('</div>')
    body.append('</div>')
    return "\n".join(body)


def plain_email(records, config, asof, historical=False):
    lines = [config["title"], asof.isoformat(), "HISTORICAL SAMPLE — NOT CURRENT" if historical else "DRAFT — FOR REVIEW", ""]
    if not historical:
        lines.extend(["Limited pilot coverage; see the review report before using this draft.", ""])
    if not records:
        lines.append(f"{config['held_count']} candidate lead(s) need review before inclusion in this English draft." if config.get('held_count')
                     else "Collection coverage is incomplete; new-information status is undetermined." if config.get('collection_failed')
                     else "No new relevant items found in the connected sources checked. Coverage is partial.")
    for section in SECTIONS:
        group = [r for r in records if r["category"] == section]
        if not group:
            continue
        lines.extend([section.upper(), ""])
        for r in group:
            lines.extend([" / ".join(r["tickers"]) + " — " + r["title"], *["* " + b for b in brief_bullets(r)],
                          "Source: " + r["source"], r.get("url", ""), ""])
    return "\n".join(lines)


def render(records, coverage, config, asof, out, historical=False):
    from coverage_view import render_watchlist_overview
    from radar_view import render_market_radar
    out.mkdir(parents=True, exist_ok=True)
    config = dict(config)
    active = [c for c in coverage if c['status'] not in ('disabled', 'not_applicable')]
    config['collection_failed'] = not historical and not any(c['status'] == 'ok' for c in active)
    ranked = sorted(records, key=lambda r: (-r.get('attention_score', 0), r.get("change") != "changed", r.get("event_type") == "Company update", r.get("tickers", [])))
    eligible = [r for r in ranked if r.get("eligible")]
    selected = eligible[:config.get("max_stories", 25)]
    held = [r for r in ranked if not r.get("eligible")] + eligible[len(selected):]
    config['held_count'] = len(held)
    body = email_body(selected, config, asof, historical)
    plain = plain_email(selected, config, asof, historical)
    msg = EmailMessage(policy=policy.SMTP)
    msg["Subject"] = ("[HISTORICAL SAMPLE] " if historical else "[DRAFT] ") + config["title"] + " — " + asof.strftime("%d %b %Y")
    msg["Date"] = format_datetime(asof)
    msg["X-Unsent"] = "1"
    msg.set_content(plain)
    msg.add_alternative(body, subtype="html")
    (out / "morning-note.eml").write_bytes(msg.as_bytes())
    (out / "email.html").write_text('<!doctype html><html><head><meta charset="utf-8"><title>Draft morning note</title></head><body>' + body + '</body></html>', encoding="utf-8")
    (out / "morning-note.txt").write_text(plain, encoding="utf-8")
    discovery_log = config.get('discovery_log', [])
    write_json(out / "evidence.json", {"asof": asof.isoformat(), "historical": historical, "candidates": records, "coverage": coverage,
                                      "discovery_mode": config.get('discovery_mode', 'targeted'), "headline_audit": discovery_log})
    write_json(out / 'headline-audit.json', {"asof": asof.isoformat(), "headlines": discovery_log,
                                          "note": "All discovered market headlines, including low-ranked and out-of-window items; rankings are provisional."})
    payload = export_payload(records, coverage, config, asof)
    write_json(out / "draft-payload.json", payload)
    review = []
    for c in coverage:
        counts = f'{c.get("discovered", 0)} headlines scanned · {c["articles_attempted"]} articles checked' if 'articles_attempted' in c else f'{c.get("discovered", 0)} source records checked'
        review.append(f'<div class="source"><strong>{e(c["name"])}</strong><span class="pill {e(c["status"])}">{e(c["status"])}</span><p>{c.get("matched", 0)} matches · {counts}</p>')
        for error in c.get("errors", []):
            review.append(f'<p class="warning">{e(error)}</p>')
        if c.get('access_limited'):
            review.append(f'<p class="warning">{int(c["access_limited"])} article(s) could not be fully read.</p>')
        if c.get('coverage_note'):
            review.append(f'<p>{e(c["coverage_note"])}</p>')
        if c.get('message'):
            review.append(f'<p class="warning">{e(c["message"])}</p>')
        review.append('</div>')
    checks = []
    for r in records:
        for flag in r.get("flags", []):
            checks.append(f'<li><b>{e(" / ".join(r["tickers"]))}</b>: {e(flag)}</li>')
    if held:
        checks.append(f'<li>{len(held)} candidate(s) require date, access or English-summary review, or exceed the story limit. See the research queue.</li>')
    if not checks:
        checks.append('<li>Confirm relevance, wording, dates and all quantities against the linked source.</li>')
    styles = (ROOT / "review.css").read_text(encoding="utf-8")
    script = (ROOT / "review.js").read_text(encoding="utf-8")
    notes = "".join(f'<li>{e(n)}</li>' for n in config.get("coverage_notes", []))
    ticker_checks = ''.join(f'<li><b>{e(t["ticker"])} · {e(t["company"])}</b><br>{e(t["message"])}</li>' for t in payload['watchlist_results'])
    mode = "Historical sample" if historical else "Public-source draft"
    watchlist = config.get('selected_watchlist', [])
    overview = render_watchlist_overview(watchlist, records, coverage) if watchlist and not historical else ''
    tracking_banner = f'<div class="tracking-banner"><strong>{len(watchlist)} companies tracked</strong><span>{len(selected)} stories in this draft · {len(held)} leads need review</span><a href="#watchlist-overview">View every company and its coverage ↓</a></div>' if overview else ''
    radar = ''
    if not historical and config.get('discovery_mode') in ('market_first', 'market-first'):
        radar = render_market_radar(records, coverage, discovery_log, len(watchlist))
        headline_count = sum(c.get('discovered', 0) for c in coverage if c.get('collection_role') == 'market')
        tracking_banner = f'<div class="tracking-banner"><strong>{headline_count} market headlines scanned</strong><span>{len(watchlist)} priority names for deeper checks · {len(held)} leads need review</span><a href="#market-radar">View the market radar ↓</a></div>'
    queue = []
    if held:
        queue.append('<section class="research-queue"><h2>Research queue</h2><p>These source leads are not in the email. Restricted articles remain leads only. Check the original before drafting an English update.</p>')
        for r in held:
            lead_title = r.get('discovery_title') or r['title']
            linked_title = f'<a href="{e(safe_url(r["url"]))}" target="_blank" rel="noopener noreferrer">{e(lead_title)}</a>' if r.get('url') else e(lead_title)
            queue.append(f'<article class="lead-card"><p class="small">{e(" / ".join(r["tickers"]))} · {e(r.get("access_status", "review"))} · {e(r.get("language", ""))}</p><h3>{linked_title}</h3><p class="small">{e(r["source"])} · {e(publication_label(r))}</p><ul>')
            queue.extend(f'<li>{e(flag)}</li>' for flag in r.get('flags', []) if 'Newly found' not in flag)
            queue.append('</ul></article>')
        queue.append('</section>')
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Morning Note · Review</title><style>{styles}</style></head><body>
<header class="bar"><div><span class="brand">MORNING NOTE</span><span class="mode">{mode}</span></div><div class="actions"><button onclick="copyEmail()">Copy email</button><button class="primary" onclick="downloadEmail()">Download edited .eml</button></div></header>
{tracking_banner}
{radar}
<main class="layout"><section class="left"><div class="intro"><h1>Your morning draft</h1><p>Click the email to edit. Changes stay in this page until you download the edited email.</p><p id="feedback" role="status"></p></div><div id="email" contenteditable="true" spellcheck="true">{body}</div>{''.join(queue)}</section>
<aside><h2>Review desk</h2><div class="stats"><div><b>{len(selected)}</b><span>in draft</span></div><div><b>{len(held)}</b><span>held for review</span></div></div><h3>Before you use it</h3><ul class="checks">{''.join(checks)}</ul><h3>Collection status</h3>{''.join(review) or '<p>Local email import only. No public sources fetched for this sample.</p>'}<details><summary>Ticker-by-ticker results</summary><ul class="checks">{ticker_checks}</ul></details><details open><summary>Coverage limits</summary><ul class="checks">{notes}</ul></details><p class="small">Cutoff: {e(asof.isoformat())}<br>Window: {config.get('lookback_hours', 24)} hours<br>Change labels compare documents, not contractual deal terms.</p><p><a href="evidence.json">Evidence and collection log</a></p><a href="draft-payload.json">Structured draft export</a></aside></main>
{overview}
<script type="application/json" id="draft-meta">{json.dumps({"subject": str(msg['Subject']), "date": str(msg['Date'])}).replace('<', chr(92)+'u003c')}</script><script>{script}</script></body></html>'''
    (out / "review.html").write_text(page, encoding="utf-8")
    return {"selected": len(selected), "held": len(held), "review": str(out / "review.html")}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Collect configured public sources and create a draft")
    run.add_argument("--config", type=Path, default=ROOT / "config.json")
    run.add_argument("--as-of", help="ISO 8601 timestamp including UTC offset; default is now")
    run.add_argument("--dry-run", action="store_true", help="Write preview but leave the document history unchanged")
    run.add_argument("--open", action="store_true")
    run.add_argument("--hours", type=int, choices=(12, 24, 48, 72, 96), help="News window; longer windows cover weekends/holidays")
    run.add_argument("--ticker", action="append", help="Limit to a watchlist ticker; repeat for multiple tickers")
    run.add_argument("--topic", help="Optional topic, e.g. M&A; matched against available source text")
    run.add_argument("--mode", choices=('market-first', 'targeted'), help="Scan market sources broadly, or limit collection to selected priority names")
    run.add_argument("--with-search", action="store_true", help="Opt in to the configured Brave API connector; requires an existing BRAVE_SEARCH_API_KEY and may consume your provider quota")
    imp = sub.add_parser("import-examples", help="Import local example emails without fetching their links")
    imp.add_argument("files", nargs="+", type=Path)
    imp.add_argument("--write-watchlist", action="store_true", help="Create a starter watchlist only if one does not exist")
    args = parser.parse_args()
    if args.command == "import-examples":
        samples = [import_email(p) for p in args.files]
        config = read_json(ROOT / "config.json")
        for sample in samples:
            asof = datetime.fromisoformat(sample["asof"])
            render(sample["stories"], [], config, asof, ROOT / "output" / ("sample-" + asof.strftime("%Y-%m-%d")), True)
        write_json(ROOT / "output" / "sample-analysis.json", samples)
        if args.write_watchlist:
            target = ROOT / "watchlist.json"
            if target.exists():
                raise ValueError("watchlist.json already exists; it was not overwritten")
            print(f"Created a {write_watchlist(samples, target)}-company starter watchlist.")
        print(json.dumps({"samples": len(samples), "stories": sum(len(s['stories']) for s in samples)}, indent=2))
        return
    config_path = args.config.resolve()
    config = read_json(config_path)
    if not config:
        raise ValueError("Configuration file is missing")
    if args.hours:
        config['lookback_hours'] = args.hours
    if args.topic is not None:
        config['topic'] = args.topic
    if args.mode:
        config['discovery_mode'] = args.mode.replace('-', '_')
    if args.with_search:
        for source in config['sources']:
            if source['kind'] == 'brave_search':
                source['enabled'] = True
    asof = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(ZoneInfo(config["timezone"]))
    if asof.tzinfo is None:
        raise ValueError("--as-of must include an explicit UTC offset")
    asof = asof.astimezone(ZoneInfo(config["timezone"]))
    watchlist = read_json(config_path.parent / config["watchlist_file"])
    if not isinstance(watchlist, list):
        raise ValueError("watchlist.json must contain a list of priority companies")
    if not watchlist and config.get('discovery_mode') not in ('market_first', 'market-first'):
        raise ValueError("A non-empty watchlist.json is required")
    if args.ticker:
        requested = {t.upper() for t in args.ticker}
        missing = requested - {w['ticker'] for w in watchlist}
        if missing:
            raise ValueError('Ticker(s) not in watchlist: ' + ', '.join(sorted(missing)))
        watchlist = [w for w in watchlist if w['ticker'] in requested]
    config['selected_watchlist'] = watchlist
    inbox = read_json(config_path.parent / config["inbox_file"], [])
    state_path = config_path.parent / "state" / "documents.json"
    prior = read_json(state_path, {})
    discovery_log = []
    records, coverage = collect(config, watchlist, inbox, asof, prior, discovery_log)
    config['discovery_log'] = discovery_log
    # Revision folders avoid overwriting edits from earlier runs.
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out = config_path.parent / "output" / ("dry-run-" + run_id if args.dry_run else run_id)
    result = render(records, coverage, config, asof, out)
    if not args.dry_run:
        for r in records:
            prior[r["id"]] = {k: r[k] for k in ("content_hash", "title", "published", "url", "fetched_at")}
            prior[r["id"]]["edition_date"] = asof.date().isoformat()
        write_json(state_path, prior)
    write_json(out / "run.json", dict(result, coverage=coverage, dry_run=args.dry_run, asof=asof.isoformat()))
    print(json.dumps(result, indent=2))
    if args.open:
        webbrowser.open((out / "review.html").as_uri())
    active = [c for c in coverage if c["status"] not in ("disabled", "not_applicable")]
    if not any(c['status'] in ('ok', 'partial') for c in active):
        print("Collection failed for every enabled source. The preview is an error report, not a complete morning note.")
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(f"Cannot generate the draft: {exc}", file=sys.stderr)
        raise SystemExit(1)
