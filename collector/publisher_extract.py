"""Conservative, offline extraction of publicly readable publisher articles.

The returned text is evidence, never an instruction. This module does not fetch
links, run scripts, sign in, or recover text from restricted article bodies.
"""

from __future__ import annotations

import codecs
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from lxml import etree, html


_ARTICLE_TYPES = {"article", "newsarticle", "report", "reportagenewsarticle", "analysisnewsarticle", "businessarticle"}
_WALL = re.compile(r"(?:^|[\s_-])(?:paywall|pay-wall|subscription-wall|subscriber-only|subscribers-only|premium-content|premiumcontent|login-wall|loginwall|registration-wall|regwall|member-only|members-only)(?:$|[\s_-])", re.I)
_WALL_TEXT = re.compile(r"この記事は(?:有料|会員限定)記事|有料会員限定記事|続きを(?:読む|お読みいただく)には(?:会員登録|ログイン)|(?:subscribe|sign in|log in) to (?:continue reading|read (?:the )?(?:full|rest of the) article)", re.I)
_NOISE = re.compile(r"(?:^|[\s_-])(?:ad|ads|advert|advertisement|adslot|social|share|related|recommend|breadcrumb|navigation|newsletter|cookie|toolbar|byline|author|caption|paywall)(?:$|[\s_-])", re.I)
_LOGIN_TITLE = re.compile(r"^(?:ログイン|会員ログイン|サインイン|sign[ -]?in|log[ -]?in|account login)(?:\s|$|[|｜:：-])", re.I)
_JAPANESE_DATE = re.compile(r"(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日(?:\s*[（(][^）)]*[）)])?(?:\s*(?P<hour>\d{1,2})(?::|時)(?P<minute>\d{1,2})(?:分)?(?::(?P<second>\d{1,2}))?)?")


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _node_text(node) -> str:
    return _clean(" ".join(node.itertext()))


def _decode(raw: bytes, kind: str) -> str:
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig", errors="replace")
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16", errors="replace")
    header = re.search(r"charset\s*=\s*[\"']?([^\s;\"'>]+)", kind, re.I)
    declaration = re.search(br"charset\s*=\s*[\"']?([^\s;\"'>/]+)", raw[:8192], re.I)
    encodings = [header.group(1)] if header else []
    if declaration:
        encodings.append(declaration.group(1).decode("ascii", errors="ignore"))
    encodings.extend(["utf-8", "cp932", "euc-jp"])
    for encoding in dict.fromkeys(encodings):
        try:
            # CP932 also decodes the common publisher variant of Shift-JIS.
            if encoding.lower().replace("-", "_") in {"shift_jis", "sjis"}:
                encoding = "cp932"
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _meta(tree, *keys) -> str:
    for key in keys:
        values = tree.xpath("//meta[translate(@property,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')=$key or translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')=$key]/@content", key=key.lower())
        if values and _clean(values[0]):
            return _clean(values[0])
    return ""


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _article_data(tree, url) -> list[dict]:
    articles = []
    for script in tree.xpath("//script[contains(translate(@type,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ld+json')]"):
        try:
            data = json.loads(script.text or "")
        except (ValueError, TypeError, RecursionError):
            continue
        for node in _walk_json(data):
            types = node.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if any(str(t).rstrip("/").rsplit("/", 1)[-1].lower() in _ARTICLE_TYPES for t in types):
                articles.append(node)
    def same_url(article):
        for key in ("url", "@id", "mainEntityOfPage"):
            candidate = article.get(key, "")
            if isinstance(candidate, dict):
                candidate = candidate.get("@id", "")
            if isinstance(candidate, str) and candidate.split("#")[0].rstrip("/") == url.split("#")[0].rstrip("/"):
                return True
        return False
    articles.sort(key=same_url, reverse=True)
    return articles


def _is_false(value) -> bool:
    return value is False or (isinstance(value, str) and value.strip().lower() == "false")


def _restricted(tree, article) -> bool:
    # Do not consume an articleBody before examining all its access metadata.
    if any(_is_false(node.get("isAccessibleForFree")) for node in _walk_json(article)):
        return True
    if tree.xpath("//*[@itemprop='isAccessibleForFree' and (translate(@content,'FALSE','false')='false' or translate(@value,'FALSE','false')='false')]"):
        return True
    for node in tree.iter():
        if not isinstance(node.tag, str) or node.tag in {"script", "style", "link", "meta"}:
            continue
        # A navigation link inviting sign-in is not evidence of an article wall.
        if node.tag == "a":
            continue
        label = " ".join((node.get("class", ""), node.get("id", ""))).replace("__", "-")
        if _WALL.search(label):
            return True
        for key in ("data-paywall", "data-is-premium", "data-subscriber-only"):
            if node.get(key, "").strip().lower() in {"true", "1", "yes", "locked"}:
                return True
        if node.get("data-access", "").strip().lower() in {"paid", "premium", "subscriber", "restricted"}:
            return True
        if _is_false(node.get("data-is-free")):
            return True
        if node.tag in {"p", "aside", "section", "div"}:
            text = _node_text(node)
            if len(text) <= 500 and _WALL_TEXT.search(text):
                return True
    return False


def _date(value) -> tuple[str, str]:
    value = _clean(value)
    if not value:
        return "", "missing"
    japanese = _JAPANESE_DATE.search(value)
    if japanese:
        parts = japanese.groupdict()
        try:
            day = datetime(int(parts["year"]), int(parts["month"]), int(parts["day"]))
            if parts["hour"] is None:
                return day.date().isoformat(), "day"
            day = day.replace(hour=int(parts["hour"]), minute=int(parts["minute"]), second=int(parts["second"] or 0), tzinfo=timezone(timedelta(hours=9)))
            return day.isoformat(), "time"
        except ValueError:
            return value, "unparsed"
    numeric = re.fullmatch(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?(?:\s*(JST))?", value, re.I)
    if numeric:
        year, month, day, hour, minute, second, jst = numeric.groups()
        try:
            dt = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0))
            if hour is None:
                return dt.date().isoformat(), "day"
            if jst:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
            return dt.isoformat(), "time"
        except ValueError:
            return value, "unparsed"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (dt.date().isoformat(), "day") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else (dt.isoformat(), "time")
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).isoformat(), "time"
    except (ValueError, TypeError, IndexError, OverflowError):
        return value, "unparsed"


def _dates(tree, article) -> tuple[str, str, str]:
    published = article.get("datePublished") or _meta(tree, "article:published_time", "datepublished", "pubdate", "publishdate", "publication_date", "date")
    updated = article.get("dateModified") or _meta(tree, "article:modified_time", "datemodified", "last-modified")
    if not published:
        nodes = tree.xpath("//*[@itemprop='datePublished'] | //article//time | //main//time | //*[contains(@class,'publish-date') or contains(@class,'published-date') or contains(@class,'article-date') or contains(@class,'documentPublished')]")
        for node in nodes:
            label = " ".join((node.get("itemprop", ""), node.get("class", ""), node.get("id", ""), _node_text(node)))
            if re.search(r"modified|updated|更新", label, re.I):
                if not updated:
                    updated = node.get("datetime") or node.get("content") or _node_text(node)
                continue
            candidate = node.get("datetime") or node.get("content") or _node_text(node)
            normalized, precision = _date(candidate)
            if precision in {"day", "time"}:
                published = normalized
                break
    if not updated:
        nodes = tree.xpath("//*[@itemprop='dateModified'] | //time[contains(@class,'updated') or contains(@class,'modified')]")
        if nodes:
            updated = nodes[0].get("datetime") or nodes[0].get("content") or _node_text(nodes[0])
    publication, precision = _date(published)
    modification, _ = _date(updated)
    return publication, modification, precision


def _prune(tree):
    for node in list(tree.iter()):
        if not isinstance(node.tag, str):
            if node.getparent() is not None:
                node.getparent().remove(node)
            continue
        label = " ".join((node.get("id", ""), node.get("class", "")))
        hidden = node.get("hidden") is not None or node.get("aria-hidden", "").lower() == "true" or re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", node.get("style", ""), re.I)
        if node.tag in {"script", "style", "nav", "header", "footer", "form", "noscript", "iframe", "button", "aside", "template", "svg"} or hidden or _NOISE.search(label) or node.get("role") in {"navigation", "button", "banner"}:
            if node.getparent() is not None:
                node.drop_tree()


def _meaningful(text) -> bool:
    return len(text) >= 45 or len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", text)) >= 18


def _body(tree, article, url="") -> tuple[str, str]:
    _prune(tree)
    # These are verified, rendered article containers on these publishers only.
    # Select after pruning so hidden containers and children cannot be recovered.
    host = (urlsplit(url).hostname or "").lower()
    body_class = {
        "news.rthk.hk": "itemFullText",
        "focustaiwan.tw": "paragraph",
        "www.focustaiwan.tw": "paragraph",
    }.get(host)
    publisher_roots = tree.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), $token)]", token=f" {body_class} ") if body_class else []
    roots = publisher_roots + tree.xpath("//*[@itemprop='articleBody'] | //*[contains(concat(' ', normalize-space(@class), ' '),' article-body ') or contains(concat(' ', normalize-space(@class), ' '),' articleBody ') or @id='article-body' or @id='articleBody']")
    roots += tree.xpath("//article")
    if article or tree.xpath("//h1"):
        roots += tree.xpath("//main | //*[@role='main']")
    for root in roots:
        paragraphs = []
        for node in root.xpath(".//p | .//h2 | .//h3 | .//li"):
            value = _node_text(node)
            if not value or value == _clean(article.get("headline")):
                continue
            # Skip link collections, including related-story lists.
            link_text = sum(len(_node_text(link)) for link in node.xpath(".//a"))
            if link_text > len(value) * 0.75:
                continue
            if value not in paragraphs:
                paragraphs.append(value)
        text = "\n".join(paragraphs)
        if not text and (root in publisher_roots or root.get("itemprop") == "articleBody" or root.get("id") in {"article-body", "articleBody"}):
            text = _node_text(root)
        if _meaningful(text):
            return text, "public_article_body"
    # This fallback is only reached after access checks, and never for a body
    # marked isAccessibleForFree=false or a page containing a recognized wall.
    body = article.get("articleBody")
    if isinstance(body, str) and body.strip():
        fragment = html.fragment_fromstring(body, create_parent="div")
        _prune(fragment)
        text = _node_text(fragment)
        if _meaningful(text):
            return text, "public_structured_article_body"
    return "", "metadata_only"


def extract_publisher_document(raw: bytes, kind: str, url: str) -> dict:
    """Extract public article evidence while retaining publication uncertainty.

    Date-only publication remains YYYY-MM-DD. An update timestamp is never used
    as publication. A restricted result contains public title/description only.
    """
    result = {"title": "", "text": "", "published": "", "updated": "", "date_precision": "missing", "access_status": "unavailable", "evidence_level": "unavailable", "language": ""}
    if not raw or raw.startswith(b"%PDF") or (kind and not any(t in kind.lower() for t in ("html", "xml", "text/plain", "octet-stream"))):
        return result
    try:
        markup = _decode(raw, kind)
        tree = html.fromstring(markup, parser=html.HTMLParser(no_network=True, recover=True))
    except (ValueError, etree.ParserError, UnicodeError):
        return result
    articles = _article_data(tree, url)
    article = articles[0] if articles else {}
    h1 = tree.xpath("//h1[1]")
    titles = tree.xpath("//title/text()")
    title = _clean(article.get("headline")) or (_node_text(h1[0]) if h1 else "") or _meta(tree, "og:title", "twitter:title") or (_clean(titles[0]) if titles else "")
    language = tree.get("lang") or tree.get("xml:lang") or article.get("inLanguage") or _meta(tree, "language", "content-language")
    if isinstance(language, dict):
        language = language.get("alternateName") or language.get("name") or ""
    description = _meta(tree, "description", "og:description", "twitter:description")
    published, updated, precision = _dates(tree, article)
    result.update(title=title, language=_clean(language), published=published, updated=updated, date_precision=precision)
    if _restricted(tree, article):
        result.update(text=description, access_status="restricted", evidence_level="public_metadata_only")
        return result
    # A login/registration destination is not an article, even if it carries
    # descriptive metadata or a main element containing instructional prose.
    path = urlsplit(url).path.lower()
    login_form = tree.xpath("//form//input[@type='password']")
    if _LOGIN_TITLE.search(title) or (login_form and re.search(r"/(?:login|signin|sign-in|auth)(?:/|$)", path)):
        return result
    text, evidence = _body(tree, article, url)
    if text:
        result.update(text=text, access_status="readable", evidence_level=evidence)
    elif title or description:
        result.update(text=description, access_status="metadata_only", evidence_level="public_metadata_only")
    if not result["language"] and re.search(r"[\u3040-\u30ff]", title + result["text"]):
        result["language"] = "ja"
    return result
