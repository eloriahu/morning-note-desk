"""Run the exported review JavaScript in Node with a small, inert DOM mock.

These are syntax/MIME tests, not browser or interactive UI verification. No page
is opened, navigated or fetched. Node is optional; tests skip if it is absent.
"""
import base64
from email import policy
from email.parser import BytesParser
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("edited_export_composer", SCRIPTS / "compose_email.py")
composer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(composer)
NODE = shutil.which("node")

HARNESS = r"""
const data = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const handlers = {};
let downloadedBlob, clicked = false;
const escape = value => String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
class Element {
  constructor(spec) {
    this.tagName = spec.tag.toUpperCase();
    this.attrs = {...(spec.attrs || {})};
    this.children = (spec.children || []).map(child => typeof child === 'string' ? child : new Element(child));
    this.removed = false;
    const declarations = new Map((this.attrs.style || '').split(';').filter(Boolean).map(pair => {
      const i = pair.indexOf(':'); return [pair.slice(0,i).trim(),pair.slice(i+1).trim()];
    }));
    this.style = {
      [Symbol.iterator]: function*() { yield* declarations.keys(); },
      getPropertyValue: key => declarations.get(key) || '',
      removeProperty: key => { declarations.delete(key); this.attrs.style = [...declarations].map(([k,v]) => k+':'+v).join(';'); }
    };
  }
  get attributes() { return Object.keys(this.attrs).map(name => ({name})); }
  hasAttribute(name) { return Object.hasOwn(this.attrs,name); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  removeAttribute(name) { delete this.attrs[name]; }
  remove() { this.removed = true; }
  querySelectorAll(selector) {
    const names = selector.split(',');
    const found = [];
    const visit = node => { for (const child of node.children) {
      if (typeof child === 'string' || child.removed) continue;
      if (selector === '*' || names.includes(child.tagName.toLowerCase())) found.push(child);
      visit(child);
    }};
    visit(this); return found;
  }
  get innerHTML() { return this.children.map(child => typeof child === 'string' ? escape(child) : child.serialize()).join(''); }
  serialize() {
    if (this.removed) return '';
    const attrs = Object.entries(this.attrs).map(([k,v]) => ' '+k+'="'+escape(v)+'"').join('');
    const tag = this.tagName.toLowerCase();
    return '<'+tag+attrs+'>'+(tag === 'img' ? '' : this.innerHTML+'</'+tag+'>');
  }
}
const feedback = {textContent:''};
const editor = {innerText:data.plain, cloneNode:() => new Element({tag:'section',children:data.elements})};
global.document = {
  getElementById: id => id === 'email' ? editor : id === 'feedback' ? feedback : id === 'subject' ? {value:data.subject} : {addEventListener:(event,handler) => {handlers[id] = handler;}},
  createElement: () => ({click:() => {clicked = true;}})
};
URL.createObjectURL = blob => {downloadedBlob = blob; return 'blob:mocked-local-download';};
URL.revokeObjectURL = () => {};
global.setTimeout = () => 0;
eval(data.script);
handlers.download();
(async () => {
  if (!downloadedBlob || !clicked) throw new Error('Download handler did not create and click the local artifact');
  process.stdout.write(JSON.stringify({eml:await downloadedBlob.text(), type:downloadedBlob.type, feedback:feedback.textContent}));
})().catch(error => {process.stderr.write(String(error));process.exitCode=1;});
"""


@unittest.skipUnless(NODE, "Node runtime not installed; JavaScript export tests skipped")
class EditedExportTests(unittest.TestCase):
    @staticmethod
    def generated_script(attachment=None):
        pack = {"stories": [], "as_of": "2026-09-25T08:00:00+08:00", "window_start": "2026-09-24T08:00:00+08:00",
                "composition": {"ready_count": 0, "held_count": 0}}
        review = composer.review_page(pack, '<div id="mn-top">Edited fixture</div>', "Fixture subject", attachment)
        return re.findall(r"<script>(.*?)</script>", review, flags=re.S)[-1]

    def execute_download(self, attachment=None):
        elements = [
            {"tag": "div", "attrs": {"id": "mn-top", "style": "font-family:Arial;font-size:10pt;color:#0A2348", "onclick": "bad()"}, "children": ["Edited fixture"]},
            {"tag": "a", "attrs": {"href": "#mn-top", "style": "font-size:8pt;color:#124084"}, "children": ["Back to Top"]},
            {"tag": "p", "attrs": {"style": "font-size:10pt;background-image:url(https://example.com/tracker)"}, "children": ["* Edited English / 日本語 fixture."]},
            {"tag": "a", "attrs": {"href": "javascript:alert(1)"}, "children": ["Unsafe pasted link"]},
            {"tag": "script", "children": ["Untrusted pasted script"]},
            {"tag": "img", "attrs": {"src": "https://example.com/unapproved.png"}},
        ]
        if attachment:
            elements.insert(0, {"tag": "img", "attrs": {"src": attachment["data_url"], "width": "314", "style": "display:block;width:314px"}})
        data = {"script": self.generated_script(attachment), "elements": elements,
                "plain": "Edited fixture\n* Edited English / 日本語 fixture.",
                "subject": "Edited subject\r\nBcc: injected@example.com"}
        run = subprocess.run([NODE, "-e", HARNESS], input=json.dumps(data, ensure_ascii=False), text=True,
                             encoding="utf-8", capture_output=True, timeout=20, check=True)
        result = json.loads(run.stdout)
        self.assertEqual(result["type"], "message/rfc822")
        self.assertIn("Nothing has been sent", result["feedback"])
        message = BytesParser(policy=policy.default).parsebytes(result["eml"].encode("utf-8"))
        self.assertEqual(message["X-Unsent"], "1")
        self.assertEqual(str(message["Subject"]), "Edited subject  Bcc: injected@example.com")
        for header in ("From", "To", "Cc", "Bcc", "Sender"):
            self.assertIsNone(message[header])
        self.assertEqual(message.get_body(preferencelist=("plain",)).get_content(), data["plain"])
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn('href="#mn-top"', html)
        self.assertIn('id="mn-top"', html)
        self.assertIn("font-size:10pt", html)
        self.assertIn("#0A2348", html)
        self.assertIn("日本語", html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("background-image", html)
        self.assertNotIn("unapproved.png", html)
        self.assertNotIn("Untrusted pasted script", html)
        return message, html

    def test_generated_script_syntax_and_unbranded_edited_download(self):
        script = self.generated_script()
        subprocess.run([NODE, "--check"], input=script, text=True, encoding="utf-8", capture_output=True, timeout=20, check=True)
        message, _ = self.execute_download()
        self.assertEqual(message.get_content_type(), "multipart/alternative")
        self.assertFalse([part for part in message.walk() if part.get_content_maintype() == "image"])

    def test_branded_edited_download_keeps_logo_as_related_cid_attachment(self):
        payload = b"\x89PNG\r\n\x1a\nsynthetic-logo-fixture"
        encoded = base64.b64encode(payload).decode("ascii")
        attachment = {"subtype": "png", "base64": encoded, "cid": "morning-note-house-logo", "data_url": "data:image/png;base64," + encoded}
        message, html = self.execute_download(attachment)
        related = [part for part in message.walk() if part.get_content_type() == "multipart/related"]
        self.assertEqual(len(related), 1)
        images = [part for part in related[0].walk() if part.get_content_maintype() == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["Content-ID"], "<morning-note-house-logo>")
        self.assertEqual(images[0].get_content_disposition(), "inline")
        self.assertEqual(images[0].get_payload(decode=True), payload)
        self.assertIn('src="cid:morning-note-house-logo"', html)
        self.assertNotIn("data:image", html)


if __name__ == "__main__":
    unittest.main()
