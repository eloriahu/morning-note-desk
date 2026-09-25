"""Compact table-based morning-note presentation, independent of the review UI.

Input is a composition-validated research pack. No sample identities, branding,
contact details or research facts are bundled in this presentation module.
"""
from __future__ import annotations

import base64
import hashlib
from html import escape
import re
from urllib.parse import quote, urlsplit


SECTIONS = ("Merger Arbitrage", "Fundamental/Pre-Event", "Relative Value", "Other Strategy")
FONT = "font-family:Arial,sans-serif;font-size:10pt;color:#000000;"
SMALL = "font-family:Arial,sans-serif;font-size:8pt;"
NAVY = "#0A2348"
BLUE = "#124084"
GREY = "#CBCBCB"
TABLE = 'role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;"'


def _text(value):
    return str(value if value is not None else "")


def _esc(value):
    return escape(_text(value), quote=True)


def _list(value):
    return [str(item) for item in value if isinstance(item, (str, int))] if isinstance(value, list) else []


def _url(value):
    if not isinstance(value, str) or any(ord(char) < 33 or ord(char) == 127 for char in value) or "\\" in value:
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password or parts.port not in (None, 80, 443):
            return ""
    except ValueError:
        return ""
    return value


def _logo(value):
    if not isinstance(value, str):
        return ""
    match = re.fullmatch(r"data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/]+={0,2})", value)
    if not match:
        return ""
    try:
        data = base64.b64decode(match[2], validate=True)
    except ValueError:
        return ""
    valid = {"png": data.startswith(b"\x89PNG\r\n\x1a\n"), "jpeg": data.startswith(b"\xff\xd8\xff"),
             "gif": data.startswith((b"GIF87a", b"GIF89a")),
             "webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP"}
    return value if valid[match[1]] else ""


def _email(value):
    if not isinstance(value, str) or not re.fullmatch(r"[^\s<>\"'@]+@[^\s<>\"'@]+\.[^\s<>\"'@]+", value):
        return ""
    return 'mailto:' + quote(value, safe="@.+-_")


def _anchor(story):
    identity = _text(story.get("id") or story.get("headline") or story.get("company"))
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", identity).strip("-")[:45] or "item"
    return "mn-story-" + slug + "-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]


def _primary(story):
    tickers = _list(story.get("tickers"))
    return tickers[0] if tickers else _text(story.get("company")).upper()


def ordered_groups(pack):
    """Keep top picks in their real sections; the contents page promotes them."""
    ready = [story for story in pack.get("stories", []) if story.get("composition_status") == "ready"]
    return [(category, [story for story in ready if story.get("category") == category]) for category in SECTIONS]


def _top_stories(pack, groups):
    by_id = {story.get("id"): story for _, stories in groups for story in stories}
    requested = pack.get("top_stories", [])
    ids = list(dict.fromkeys(item for item in requested if isinstance(item, str)))[:2] if isinstance(requested, list) else []
    return [by_id[item] for item in ids if item in by_id]


def _source_map(story):
    available = {source.get("url"): source for source in story.get("sources", [])
                 if isinstance(source, dict) and _url(source.get("url"))}
    urls = []
    for bullet in story.get("bullets", []):
        for url in _list(bullet.get("source_urls")):
            if url in available and url not in urls:
                urls.append(url)
    return [(url, available[url]) for url in urls]


def _index_section(label, stories):
    if not stories:
        return ""
    rows = [f'<tr><td colspan="3" style="{FONT}color:{BLUE};font-weight:bold;padding-top:10pt;padding-bottom:2pt;">{_esc(label)}</td></tr>']
    for story in stories:
        rows.append(f'<tr><td valign="top" width="98" style="{FONT}width:98px;padding:0;">{_esc(_primary(story))}</td>'
                    '<td width="20" style="width:20px;"></td>'
                    f'<td valign="top" style="{FONT}padding:0;"><a href="#{_anchor(story)}" style="{FONT}text-decoration:none;">{_esc(story.get("headline"))}</a></td></tr>')
    return "".join(rows)


def _story_html(story):
    tickers = _list(story.get("tickers"))
    company = _text(story.get("company")).upper()
    output = [f'<div id="{_anchor(story)}" class="mn-story" style="padding-top:10pt;padding-bottom:8pt;">',
              f'<table {TABLE}><tr><td style="{FONT}">']
    if tickers:
        output.append(f'<span style="{FONT}color:{NAVY};font-weight:bold;">{_esc(" / ".join(tickers))}</span>'
                      f'<span style="{FONT}">&nbsp;&nbsp;&nbsp;&nbsp;{_esc(company)}</span>')
    else:
        output.append(f'<span style="{FONT}color:{NAVY};font-weight:bold;">{_esc(company)}</span>')
    output.append('</td></tr></table>')
    sources = _source_map(story)
    numbers = {url: index for index, (url, _) in enumerate(sources, 1)}
    bullet_sets = {tuple(sorted(set(_list(bullet.get("source_urls"))))) for bullet in story.get("bullets", [])}
    numbered = len(bullet_sets) > 1 and len(sources) > 1
    source_links = []
    for url, source in sources:
        name = source.get("name") or urlsplit(url).hostname
        label = f'[{numbers[url]}] {name}' if numbered else name
        source_links.append(f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer" style="{SMALL}color:{BLUE};text-decoration:none;font-weight:normal;">{_esc(label)}</a>')
    output.append(f'<p style="{FONT}margin:5pt 0 2pt 0;line-height:1.15;"><strong>{_esc(story.get("headline"))}</strong>')
    if source_links:
        output.append('&nbsp;&nbsp;&nbsp;<span style="' + SMALL + '">' + '&nbsp; / &nbsp;'.join(source_links) + '</span>')
    output.append('</p>')
    for bullet in story.get("bullets", []):
        output.append(f'<p style="{FONT}margin:0 0 2pt 0;line-height:1.25;text-align:justify;">* {_esc(bullet.get("text"))}')
        if numbered:
            refs = [f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer" style="{SMALL}color:{BLUE};text-decoration:none;">[{numbers[url]}]</a>'
                    for url in dict.fromkeys(_list(bullet.get("source_urls"))) if url in numbers]
            output.append(' <span style="' + SMALL + '">' + ' '.join(refs) + '</span>')
        output.append('</p>')
    output.append('</div>')
    return "".join(output)


def _footer(branding):
    footer = branding.get("footer")
    if not isinstance(footer, dict) or footer.get("include_in_draft") is not True:
        return ""
    output = [f'<table {TABLE}><tr><td style="{FONT}color:{NAVY};font-weight:bold;border-bottom:2px solid {GREY};padding-top:14pt;">{_esc(footer.get("heading") or "CONTACT")}</td>'
              f'<td align="right" style="border-bottom:2px solid {GREY};padding-top:14pt;"><a href="#mn-top" style="{SMALL}color:{BLUE};text-decoration:none;">Back to Top</a></td></tr></table>']
    if footer.get("intro"):
        output.append(f'<p style="{SMALL}color:#000000;margin:7pt 0;">{_esc(footer["intro"])}')
        if _email(footer.get("contact_email")):
            output.append(f' <a href="{_esc(_email(footer["contact_email"]))}" style="color:{BLUE};text-decoration:none;">{_esc(footer["contact_email"])}</a>')
        output.append('</p>')
    elif _email(footer.get("contact_email")):
        output.append(f'<p style="{SMALL}margin:7pt 0;"><a href="{_esc(_email(footer["contact_email"]))}" style="color:{BLUE};text-decoration:none;">{_esc(footer["contact_email"])}</a></p>')
    groups = [group for group in footer.get("groups", []) if isinstance(group, dict)] if isinstance(footer.get("groups"), list) else []
    if groups:
        output.append(f'<table {TABLE}><tr>')
        for group in groups:
            output.append(f'<td valign="top" style="{SMALL}color:#000000;padding:4pt 14pt 4pt 0;"><strong>{_esc(group.get("label"))}</strong>')
            for line in _list(group.get("lines")):
                output.append('<br>' + _esc(line))
            output.append('</td>')
        output.append('</tr></table>')
    if footer.get("disclaimer_text") or _url(footer.get("disclaimer_url")):
        output.append(f'<p style="{SMALL}color:#595959;margin:10pt 0 0;">{_esc(footer.get("disclaimer_text"))}')
        if _url(footer.get("disclaimer_url")):
            url = footer["disclaimer_url"]
            output.append(f' <a href="{_esc(url)}" target="_blank" rel="noopener noreferrer" style="color:{BLUE};text-decoration:none;">{_esc(url)}</a>')
        output.append('</p>')
    return "".join(output)


def email_body(pack, branding=None):
    branding = branding if isinstance(branding, dict) else {}
    title = branding.get("title") or "Morning Note Asia-Pacific"
    region = branding.get("region") or "ASIA-PACIFIC"
    subtitle = branding.get("subtitle") or "Daily pre-market summary of material developments"
    groups = ordered_groups(pack)
    output = [f'<div id="mn-top" style="{FONT}background:#ffffff;">']
    logo = _logo(branding.get("logo_data_url"))
    if logo:
        try:
            width = max(1, min(1000, int(branding.get("logo_width", 314))))
        except (ValueError, TypeError):
            width = 314
        output.append(f'<img src="{_esc(logo)}" width="{width}" alt="{_esc(title)}" style="display:block;border:0;width:{width}px;max-width:100%;height:auto;">')
    output.extend([
        f'<table {TABLE}><tr><td colspan="2" style="height:3px;line-height:3px;font-size:0;background:#BFBFBF;">&nbsp;</td></tr>',
        f'<tr><td align="left" valign="top" style="{SMALL}color:#595959;padding-top:3pt;">{_esc(title)}</td>',
        f'<td align="right" valign="top" style="{SMALL}color:#595959;padding-top:3pt;">{_esc(subtitle)}</td></tr>',
    ])
    email = branding.get("contact_email")
    href = _email(email)
    if href:
        output.append(f'<tr><td></td><td align="right" style="{SMALL}"><a href="{_esc(href)}" style="{SMALL}color:{BLUE};text-decoration:none;">{_esc(email)}</a></td></tr>')
    output.append('</table>')
    output.append(f'<table {TABLE} class="mn-index"><tr><td colspan="3" style="{FONT}color:{NAVY};font-weight:bold;border-bottom:2px solid {GREY};padding-top:18pt;">{_esc(region)}</td></tr>')
    output.append(_index_section("Top Stories", _top_stories(pack, groups)))
    for category, stories in groups:
        output.append(_index_section(category, stories))
    output.append('</table>')
    output.append(f'<table {TABLE}><tr><td style="{FONT}color:{NAVY};font-weight:bold;border-bottom:3px solid {GREY};padding-top:28pt;">NEWS SUMMARY</td></tr></table>')
    if not any(stories for _, stories in groups):
        output.append(f'<p style="{FONT}margin:10pt 0;">No items included in this edition.</p>')
    for category, stories in groups:
        if not stories:
            continue
        output.append(f'<table {TABLE} class="mn-category"><tr><td style="{FONT}color:{BLUE};font-weight:bold;padding-top:12pt;">{_esc(category)}</td>'
                      f'<td align="right" style="padding-top:12pt;"><a href="#mn-top" style="{SMALL}color:{BLUE};text-decoration:none;">Back to Top</a></td></tr></table>')
        output.extend(_story_html(story) for story in stories)
    output.append(_footer(branding))
    output.append('</div>')
    return "".join(output)


def email_text(pack, branding=None):
    branding = branding if isinstance(branding, dict) else {}
    groups = ordered_groups(pack)
    lines = [_text(branding.get("title") or "Morning Note Asia-Pacific"),
             _text(branding.get("subtitle") or "Daily pre-market summary of material developments")]
    if _email(branding.get("contact_email")):
        lines.append(branding["contact_email"])
    lines.extend(["", _text(branding.get("region") or "ASIA-PACIFIC"), ""])
    index_groups = [("Top Stories", _top_stories(pack, groups))] + groups
    for label, stories in index_groups:
        if stories:
            lines.append(label)
            lines.extend(f'{_primary(story)}  {story.get("headline", "")}' for story in stories)
            lines.append("")
    lines.extend(["NEWS SUMMARY", ""])
    if not any(stories for _, stories in groups):
        lines.append("No items included in this edition.")
    for label, stories in groups:
        if not stories:
            continue
        lines.extend([label, ""])
        for story in stories:
            tickers = " / ".join(_list(story.get("tickers")))
            lines.append((tickers + "  " if tickers else "") + _text(story.get("company")).upper())
            lines.append(_text(story.get("headline")))
            for bullet in story.get("bullets", []):
                lines.append("* " + _text(bullet.get("text")))
                for url in dict.fromkeys(_list(bullet.get("source_urls"))):
                    if _url(url):
                        lines.append("  " + url)
            lines.append("")
    footer = branding.get("footer")
    if isinstance(footer, dict) and footer.get("include_in_draft") is True:
        lines.extend([_text(footer.get("heading") or "CONTACT"), _text(footer.get("intro"))])
        if _email(footer.get("contact_email")):
            lines.append(footer["contact_email"])
        for group in footer.get("groups", []) if isinstance(footer.get("groups"), list) else []:
            if isinstance(group, dict):
                lines.extend([_text(group.get("label")), *_list(group.get("lines"))])
        if footer.get("disclaimer_text"):
            lines.append(_text(footer["disclaimer_text"]))
        if _url(footer.get("disclaimer_url")):
            lines.append(footer["disclaimer_url"])
    return "\n".join(lines).rstrip() + "\n"
