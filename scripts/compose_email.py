"""Compose a reviewable morning email from a Codex-authored research pack.

Standard library only. No network, credentials, model calls or email sending.
Validation checks structure and source metadata; it cannot establish factual truth.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime
from html import escape
import ipaddress
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit

_layout_spec = importlib.util.spec_from_file_location('morning_note_email_layout', Path(__file__).with_name('email_layout.py'))
layout = importlib.util.module_from_spec(_layout_spec)
_layout_spec.loader.exec_module(layout)


SECTIONS = ("Merger Arbitrage", "Fundamental/Pre-Event", "Relative Value", "Other Strategy")


def text(value):
    return str(value if value is not None else "")


def esc(value):
    return escape(text(value), quote=True)


def timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("A full ISO timestamp with timezone is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp timezone is required")
    return parsed


def safe_url(value):
    """Allow public-looking HTTP(S) references, never executable or local links.

    This does not perform DNS/network checks or verify ownership of a hostname.
    """
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 33 or ord(c) == 127 for c in value):
        return False
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        if (parts.scheme not in ("http", "https") or not host or parts.username or parts.password
                or parts.port not in (None, 80, 443) or "\\" in value):
            return False
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def _strings(value):
    return [text(item) for item in value] if isinstance(value, list) else ([text(value)] if value else [])


def validate_pack(pack):
    """Return a copy with composition_status/reasons on every input story."""
    if not isinstance(pack, dict):
        raise ValueError("Research pack must be a JSON object")
    result = deepcopy(pack)
    as_of = timestamp(result.get("as_of"))
    start = timestamp(result.get("window_start"))
    if start > as_of:
        raise ValueError("window_start must not be after as_of")
    stories = result.get("stories", [])
    if not isinstance(stories, list) or not all(isinstance(story, dict) for story in stories):
        raise ValueError("stories must be a list of story objects")
    ids = [text(story.get("id")) for story in stories]
    for story in stories:
        reasons = []
        if not isinstance(story.get("id"), str) or not story["id"].strip():
            reasons.append("Story ID is missing.")
        elif ids.count(story["id"]) > 1:
            reasons.append("Story ID is duplicated.")
        if not isinstance(story.get("company"), str) or not story["company"].strip():
            reasons.append("Company identity needs review.")
        if not isinstance(story.get("headline"), str) or not story["headline"].strip():
            reasons.append("English headline is missing.")
        if story.get("review_status") != "ready":
            reasons.append("Research review status is not ready.")
        if story.get("novelty") not in ("new", "changed"):
            reasons.append("New information or a changed event has not been established.")
        if story.get("category") not in SECTIONS:
            reasons.append("A supported morning-note category is required.")
        sources = story.get("sources", [])
        if not isinstance(sources, list) or not all(isinstance(source, dict) for source in sources):
            sources = []
            reasons.append("Sources must be a list of source objects.")
        source_by_url = {}
        for source in sources:
            url = source.get("url")
            if not safe_url(url):
                reasons.append("A source URL is invalid or is not a public HTTP(S) reference.")
                continue
            if url in source_by_url:
                reasons.append("A source URL is duplicated; consolidate its metadata.")
            source_by_url[url] = source
        bullets = story.get("bullets", [])
        if not isinstance(bullets, list) or not bullets:
            bullets = []
            reasons.append("At least one sourced English bullet is required.")
        for number, bullet in enumerate(bullets, 1):
            if not isinstance(bullet, dict) or not isinstance(bullet.get("text"), str) or not bullet["text"].strip():
                reasons.append(f"Bullet {number} has no text.")
                continue
            urls = bullet.get("source_urls")
            if not isinstance(urls, list) or not urls:
                reasons.append(f"Bullet {number} needs at least one source citation.")
                continue
            for url in urls:
                if not safe_url(url):
                    reasons.append(f"Bullet {number} has an invalid or forbidden citation URL.")
                    continue
                source = source_by_url.get(url)
                if source is None:
                    reasons.append(f"Bullet {number} cites a source absent from the story's source list.")
                    continue
                if source.get("access") != "readable":
                    reasons.append(f"Bullet {number} cites an unreadable or restricted source.")
                if source.get("date_precision") != "time":
                    reasons.append(f"Bullet {number} source publication time is unconfirmed.")
                try:
                    published = timestamp(source.get("published_at"))
                    if not start <= published <= as_of:
                        reasons.append(f"Bullet {number} source is outside the selected time window.")
                except (ValueError, TypeError):
                    reasons.append(f"Bullet {number} source needs an ISO publication timestamp with timezone.")
        story["composition_reasons"] = list(dict.fromkeys(reasons))
        story["composition_status"] = "hold" if reasons else "ready"
    result["composition"] = {
        "ready_count": sum(story["composition_status"] == "ready" for story in stories),
        "held_count": sum(story["composition_status"] == "hold" for story in stories),
        "validation_scope": "Structural checks only. Codex research and an editor must verify identity, factual support, novelty, relevance and English wording.",
    }
    return result


def _ordered_groups(pack):
    return layout.ordered_groups(pack)


def email_body(pack, branding=None):
    return layout.email_body(pack, branding)


def email_text(pack, branding=None):
    return layout.email_text(pack, branding)


def load_branding(style_path):
    """Read local template data and its attached logo; never fetch remote assets."""
    if not style_path:
        return {}, None
    style_path = Path(style_path).resolve()
    data = json.loads(style_path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('House style must be a JSON object')
    branding = {key: data[key] for key in ('title', 'region', 'subtitle', 'contact_email', 'footer') if key in data}
    attachment = None
    if data.get('logo_path'):
        logo = (style_path.parent / data['logo_path']).resolve()
        if not logo.is_relative_to(style_path.parent):
            raise ValueError('House logo must be inside the house-style directory')
        payload = logo.read_bytes()
        if len(payload) > 2_000_000:
            raise ValueError('House logo exceeds 2 MB')
        subtype = ('png' if payload.startswith(b'\x89PNG\r\n\x1a\n') else
                   'jpeg' if payload.startswith(b'\xff\xd8\xff') else
                   'gif' if payload.startswith((b'GIF87a', b'GIF89a')) else None)
        if not subtype:
            raise ValueError('House logo must be a PNG, JPEG or GIF')
        encoded = base64.b64encode(payload).decode('ascii')
        branding['logo_data_url'] = f'data:image/{subtype};base64,{encoded}'
        branding['logo_width'] = max(1, min(int(data.get('logo_width', 314)), 1200))
        attachment = {'payload': payload, 'subtype': subtype, 'base64': encoded,
                      'cid': 'morning-note-house-logo', 'data_url': branding['logo_data_url']}
    return branding, attachment


def find_house_style(input_path):
    """Prefer a style beside the research pack, then its enclosing project."""
    for directory in (Path(input_path).resolve().parent, *Path(input_path).resolve().parents, Path.cwd()):
        for candidate in (directory / 'house-style.json', directory / 'morning-note' / 'house-style.json'):
            if candidate.is_file():
                return candidate
    return None


STYLE = """body{margin:0;background:#eff3f7;color:#183049;font:15px/1.65 Arial,sans-serif}main{max-width:960px;margin:24px auto;padding:0 20px}h1{font-size:27px;line-height:1.3}h2{font-size:20px;border-bottom:1px solid #d8e1eb;padding-bottom:7px;margin-top:27px}h3{font-size:16px}a{color:#165f99}li{margin:8px 0}.toolbar,.notice,.held,.email{background:white;border:1px solid #d6e0eb;border-radius:8px;padding:22px;margin:18px 0}.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.toolbar label{width:100%}.toolbar input{width:100%;padding:8px;box-sizing:border-box}button{background:#173d65;color:white;border:0;border-radius:5px;padding:11px 16px;cursor:pointer}.edition,.citations{font-size:12px;color:#566b80}.draft-label{padding:10px 14px;background:#f6f0df}.held{background:#fffaf0}.held article{border-top:1px solid #e2d8bc}.email{outline-color:#5c86ae}#feedback{color:#216148}.status{font-size:13px}@media print{.toolbar,.notice,.held,.priority-audit{display:none}body{background:white}.email{border:0;padding:0}}"""


SCRIPT = r"""(() => {
  const editor = document.getElementById('email');
  const feedback = document.getElementById('feedback');
  const subject = document.getElementById('subject');
  const houseLogo = __LOGO_CONFIG__;
  function cleaned() {
    const copy = editor.cloneNode(true);
    copy.querySelectorAll('script,style,iframe,object,embed,form,meta,link,input,button,svg,math,video,audio').forEach(n => n.remove());
    copy.querySelectorAll('*').forEach(n => {
      if (n.tagName === 'IMG' && (!houseLogo || n.getAttribute('src') !== houseLogo.data_url)) { n.remove(); return; }
      if (n.hasAttribute('style')) {
        const allowed = new Set(['font-family','font-size','font-weight','font-style','color','background','background-color','text-align','line-height','margin','margin-top','margin-bottom','margin-left','margin-right','padding','padding-top','padding-bottom','padding-left','padding-right','border','border-top','border-bottom','border-left','border-right','border-collapse','vertical-align','width','min-width','max-width','height','display','text-decoration','white-space']);
        for (const property of Array.from(n.style)) {
          const value = n.style.getPropertyValue(property);
          if (!allowed.has(property) || /url|expression|javascript|@import|[<>\\]/i.test(value)) n.style.removeProperty(property);
        }
      }
      for (const a of Array.from(n.attributes)) {
        if (!['href','colspan','rowspan','style','id','name','width','height','align','valign','cellpadding','cellspacing','border','role','alt','title'].includes(a.name) && !(n.tagName === 'IMG' && a.name === 'src')) n.removeAttribute(a.name);
      }
      if (n.hasAttribute('href')) {
        const href = n.getAttribute('href');
        if (!/^#[A-Za-z0-9_-]+$/.test(href) && !/^mailto:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(href)) {
          try { const u = new URL(href); if (!['https:','http:'].includes(u.protocol) || u.username || u.password) n.removeAttribute('href'); }
          catch (_) { n.removeAttribute('href'); }
        }
      }
    });
    return {html: '<!doctype html><html><head><meta charset="utf-8"></head><body style="font-family:Arial,sans-serif;font-size:10pt;color:#000000;background-color:#ffffff">' + copy.innerHTML + '</body></html>', plain: editor.innerText};
  }
  function base64(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = ''; for (const b of bytes) binary += String.fromCharCode(b);
    return btoa(binary);
  }
  function wrapped(value) { return base64(value).match(/.{1,76}/g).join('\r\n'); }
  function download(name, type, value) {
    const url = URL.createObjectURL(new Blob([value], {type}));
    const a = document.createElement('a'); a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  document.getElementById('copy').addEventListener('click', async () => {
    const content = cleaned();
    try {
      if (navigator.clipboard && window.ClipboardItem) await navigator.clipboard.write([new ClipboardItem({'text/html': new Blob([content.html], {type:'text/html'}), 'text/plain': new Blob([content.plain], {type:'text/plain'})})]);
      else if (navigator.clipboard) await navigator.clipboard.writeText(content.plain);
      else throw new Error('Clipboard unavailable');
      feedback.textContent = 'Edited email copied.';
    } catch (_) {
      const range = document.createRange(); range.selectNodeContents(editor);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      feedback.textContent = 'Email selected. Press Ctrl+C to copy.';
    }
  });
  document.getElementById('download').addEventListener('click', () => {
    const content = cleaned();
    const boundary = 'morning-note-' + Date.now().toString(36);
    const name = subject.value.replace(/[\r\n]/g,' ').trim() || 'Morning Note';
    const headers = ['Subject: =?UTF-8?B?' + base64(name) + '?=', 'X-Unsent: 1', 'MIME-Version: 1.0', 'Content-Type: multipart/alternative; boundary="' + boundary + '"'];
    const part = (delimiter, type, value) => ['--' + delimiter, 'Content-Type: ' + type + '; charset=utf-8', 'Content-Transfer-Encoding: base64', '', wrapped(value)].join('\r\n');
    let htmlPart;
    if (houseLogo && content.html.includes(houseLogo.data_url)) {
      const related = boundary + '-related';
      const html = content.html.split(houseLogo.data_url).join('cid:' + houseLogo.cid);
      const imagePart = ['--' + related, 'Content-Type: image/' + houseLogo.subtype, 'Content-Transfer-Encoding: base64', 'Content-ID: <' + houseLogo.cid + '>', 'Content-Disposition: inline; filename="header-logo.' + houseLogo.subtype + '"', '', houseLogo.base64.match(/.{1,76}/g).join('\r\n')].join('\r\n');
      htmlPart = '--' + boundary + '\r\nContent-Type: multipart/related; boundary="' + related + '"\r\n\r\n' + part(related, 'text/html', html) + '\r\n' + imagePart + '\r\n--' + related + '--\r\n';
    } else htmlPart = part(boundary, 'text/html', content.html);
    const eml = headers.join('\r\n') + '\r\n\r\n' + part(boundary, 'text/plain', content.plain || ' ') + '\r\n' + htmlPart + '\r\n--' + boundary + '--\r\n';
    download('morning-note-edited.eml', 'message/rfc822', eml);
    feedback.textContent = 'Edited draft downloaded. Nothing has been sent.';
  });
})();"""


def calendar_review(pack):
    """Display calendar screening separately; it never bypasses the news gates."""
    events = pack.get('upcoming_events', [])
    if not isinstance(events, list) or not events:
        return ''
    rows = []
    for event in events:
        if not isinstance(event, dict):
            continue
        label = event.get('label') or event.get('company') or 'Event awaiting identification'
        url = event.get('source_url')
        source = ('<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(event.get('source_name') or 'Source') + '</a>') if safe_url(url) else 'Source missing'
        rows.append('<tr><td>' + esc(event.get('event_date') or 'Date unconfirmed') + '<br>' + esc(event.get('timezone')) + '</td><td>' + esc(label) + '<br>' + esc(event.get('event_type')) + '</td><td>' + esc(event.get('time_status') or 'Unconfirmed') + ' / ' + esc(event.get('status') or 'Status unchecked') + '</td><td>' + source + '<br>Checked: ' + esc(event.get('checked_at') or 'Not recorded') + '</td></tr>')
    if not rows:
        return ''
    return '<section class="notice"><h2>Upcoming catalysts — editor only</h2><p>Calendar reminders are separate from new developments. Verify the source and current event status before using a date in the email.</p><table style="width:100%;text-align:left;font-size:13px"><thead><tr><th>Date / timezone</th><th>Event</th><th>Timing / status</th><th>Evidence</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></section>'


def review_page(pack, body, subject, attachment=None):
    held = [story for story in pack.get("stories", []) if story["composition_status"] == "hold"]
    output = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
              f'<title>{esc(subject)} — review</title><style>{STYLE}</style></head><body><main>',
              '<section class="notice"><h1>Review your morning email</h1><p>Codex researched and drafted this pack. '
              'The composer checked citation links, source access, timestamps and required fields. '
              'An editor must still check factual support, company identity, novelty and English wording.</p>',
              f'<p class="status">{pack["composition"]["ready_count"]} draft stories · {len(held)} held for research/review. No email has been sent.</p>',
              f'<p class="status">Research window: {esc(pack["window_start"])} to {esc(pack["as_of"])}. AI-generated draft; review before sending.</p></section>',
              '<div class="toolbar"><label>Subject<input id="subject" type="text" value="' + esc(subject) + '"></label>',
              '<button id="copy" type="button">Copy edited email</button><button id="download" type="button">Download edited email draft</button>',
              '<span id="feedback" role="status"></span></div><p>Edit the email below before copying or downloading it. Edits stay in this page until you copy or download.</p>',
              '<section id="email" class="email" contenteditable="true" aria-label="Editable email draft">' + body + '</section>',
              '<section class="held"><h2>Held items</h2><p>These items are excluded from the email until the research pack is corrected and composed again.</p>']
    if not held:
        output.append('<p>No held items.</p>')
    for story in held:
        output.append('<article><h3>' + esc(story.get("headline") or story.get("id") or "Untitled item") + '</h3><ul>')
        output.extend('<li>' + esc(reason) + '</li>' for reason in story["composition_reasons"])
        output.extend('<li>Research note: ' + esc(note) + '</li>' for note in _strings(story.get("review_notes")))
        output.append('</ul>')
        for source in story.get("sources", []) if isinstance(story.get("sources"), list) else []:
            if isinstance(source, dict) and safe_url(source.get("url")):
                output.append('<p><a href="' + esc(source["url"]) + '" target="_blank" rel="noopener noreferrer">' + esc(source.get("name") or "Read source") + '</a></p>')
        output.append('</article>')
    output.append('</section>')
    if pack.get('coverage'):
        output.append('<section class="notice"><h2>Coverage notes — editor only</h2><ul>' + ''.join('<li>' + esc(note) + '</li>' for note in _strings(pack['coverage'])) + '</ul></section>')
    output.append(calendar_review(pack))
    if pack.get("priority_checks"):
        output.append('<details class="priority-audit"><summary>Priority company checks</summary><pre>' + esc(json.dumps(pack["priority_checks"], indent=2, ensure_ascii=False)) + '</pre></details>')
    logo_config = {key: attachment[key] for key in ('subtype', 'base64', 'cid', 'data_url')} if attachment else None
    script = SCRIPT.replace('__LOGO_CONFIG__', json.dumps(logo_config).replace('<', '\\u003c'))
    output.append('</main><script>' + script + '</script></body></html>')
    return "".join(output)


def compose(pack, output_dir, style_path=None):
    validated = validate_pack(pack)
    branding, attachment = load_branding(style_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    subject = " ".join(text(validated.get("title") or "Asia-Pacific Morning Note").splitlines()).strip()
    body = email_body(validated, branding)
    html_email = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>' + esc(subject) + '</title></head><body style="margin:8px;font-family:Arial,sans-serif;font-size:10pt;color:#000000;background-color:#ffffff">' + body + '</body></html>'
    plain = email_text(validated, branding)
    eml = EmailMessage(policy=policy.SMTP)
    eml["Subject"] = subject
    eml["Date"] = format_datetime(timestamp(validated["as_of"]))
    eml["X-Unsent"] = "1"
    eml.set_content(plain)
    mime_html = html_email.replace(attachment['data_url'], 'cid:' + attachment['cid']) if attachment else html_email
    eml.add_alternative(mime_html, subtype="html")
    if attachment:
        eml.get_payload()[-1].add_related(attachment['payload'], maintype='image', subtype=attachment['subtype'],
                                        cid='<' + attachment['cid'] + '>', disposition='inline',
                                        filename='header-logo.' + attachment['subtype'])
    files = {"email.html": html_email, "morning-note.txt": plain,
             "review.html": review_page(validated, body, subject, attachment),
             "research.json": json.dumps(validated, indent=2, ensure_ascii=False) + "\n"}
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8")
    (output / "morning-note.eml").write_bytes(eml.as_bytes())
    return {"output": str(output.resolve()), **validated["composition"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Codex-authored research JSON")
    parser.add_argument("--output", required=True, type=Path, help="Local output directory")
    parser.add_argument("--style", type=Path, help="Optional local house-style JSON; otherwise discover the enclosing project's style")
    args = parser.parse_args(argv)
    try:
        pack = json.loads(args.input.read_text(encoding="utf-8-sig"))
        result = compose(pack, args.output, args.style or find_house_style(args.input))
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, f"Unable to compose draft: {error}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
