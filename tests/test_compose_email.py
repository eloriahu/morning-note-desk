import copy
import base64
from email import policy
from email.parser import BytesParser
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compose_email.py"
SPEC = importlib.util.spec_from_file_location("compose_email", SCRIPT)
composer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(composer)


def example_pack():
    # Synthetic fixture, not a statement about a real company or news event.
    return {"title": "Synthetic test morning note", "as_of": "2026-09-24T08:00:00+08:00",
            "window_start": "2026-09-23T08:00:00+08:00", "coverage": ["Synthetic fixture only."],
            "stories": [{"id": "test-1", "company": "Example Company", "tickers": [],
                         "category": "Merger Arbitrage", "headline": "Synthetic event for renderer testing",
                         "bullets": [{"text": "Synthetic sourced statement.", "source_urls": ["https://example.com/source"]}],
                         "sources": [{"url": "https://example.com/source", "name": "Example source",
                                      "published_at": "2026-09-24T06:00:00+08:00", "access": "readable", "date_precision": "time"}],
                         "novelty": "new", "review_status": "ready", "review_notes": []}]}


class ComposerTests(unittest.TestCase):
    def test_ready_sourced_story_becomes_unsent_eml_without_recipients(self):
        with tempfile.TemporaryDirectory() as temp:
            result = composer.compose(example_pack(), temp)
            self.assertEqual(result["ready_count"], 1)
            message = BytesParser(policy=policy.default).parsebytes((Path(temp) / "morning-note.eml").read_bytes())
            self.assertEqual(message["X-Unsent"], "1")
            self.assertEqual(message["Subject"], "Synthetic test morning note")
            for header in ("From", "To", "Cc", "Bcc", "Sender"):
                self.assertIsNone(message[header])
            self.assertIn("Synthetic sourced statement", message.get_body(preferencelist=("plain",)).get_content())
            self.assertEqual({p.name for p in Path(temp).iterdir()}, {"email.html", "morning-note.txt", "morning-note.eml", "review.html", "research.json"})

    def test_background_and_unconfirmed_novelty_are_held_even_if_source_is_fresh(self):
        for novelty in ("background", "unconfirmed"):
            pack = example_pack()
            pack["stories"][0]["novelty"] = novelty
            validated = composer.validate_pack(pack)
            self.assertEqual(validated["composition"]["ready_count"], 0)
            self.assertNotIn("Synthetic sourced statement", composer.email_body(validated))
            self.assertIn("not been established", " ".join(validated["stories"][0]["composition_reasons"]))

    def test_uncited_bullet_and_nonexistent_citation_are_held(self):
        for urls in ([], ["https://example.com/missing"]):
            pack = example_pack()
            pack["stories"][0]["bullets"][0]["source_urls"] = urls
            self.assertEqual(composer.validate_pack(pack)["composition"]["held_count"], 1)

    def test_restricted_old_future_day_only_and_naive_dates_are_held(self):
        changes = [{"access": "restricted"}, {"published_at": "2026-09-20T06:00:00+08:00"},
                   {"published_at": "2026-09-25T06:00:00+08:00"}, {"date_precision": "day"},
                   {"published_at": "2026-09-24T06:00:00"}]
        for change in changes:
            pack = example_pack()
            pack["stories"][0]["sources"][0].update(change)
            self.assertEqual(composer.validate_pack(pack)["composition"]["held_count"], 1, change)

    def test_every_citation_must_pass_and_unknown_company_is_held(self):
        pack = example_pack()
        source = copy.deepcopy(pack["stories"][0]["sources"][0])
        source.update(url="https://example.com/restricted", access="restricted")
        pack["stories"][0]["sources"].append(source)
        pack["stories"][0]["bullets"][0]["source_urls"].append(source["url"])
        self.assertEqual(composer.validate_pack(pack)["composition"]["held_count"], 1)
        pack = example_pack()
        pack["stories"][0]["company"] = ""
        self.assertIn("Company identity", " ".join(composer.validate_pack(pack)["stories"][0]["composition_reasons"]))

    def test_untrusted_fields_escape_and_forbidden_urls_are_held(self):
        pack = example_pack()
        payload = '<img src=x onerror="alert(1)">'
        pack["title"] = payload
        pack["stories"][0]["headline"] = payload
        pack["stories"][0]["bullets"][0]["text"] = payload
        validated = composer.validate_pack(pack)
        body = composer.email_body(validated)
        self.assertNotIn("<img", body)
        self.assertIn("&lt;img", body)
        for url in ("javascript:alert(1)", "file:///private", "https://user:pass@example.com", "http://127.0.0.1/a", "https://localhost/a"):
            bad = example_pack()
            bad["stories"][0]["sources"][0]["url"] = url
            bad["stories"][0]["bullets"][0]["source_urls"] = [url]
            self.assertEqual(composer.validate_pack(bad)["composition"]["held_count"], 1, url)

    def test_held_reasons_persist_and_held_bullets_are_excluded_from_email(self):
        pack = example_pack()
        pack["stories"][0]["review_status"] = "hold"
        with tempfile.TemporaryDirectory() as temp:
            composer.compose(pack, temp)
            saved = json.loads((Path(temp) / "research.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["stories"][0]["composition_status"], "hold")
            self.assertTrue(saved["stories"][0]["composition_reasons"])
            self.assertNotIn("Synthetic sourced statement", (Path(temp) / "email.html").read_text(encoding="utf-8"))
            self.assertIn("Research review status is not ready", (Path(temp) / "review.html").read_text(encoding="utf-8"))

    def test_invalid_window_raises_without_producing_draft(self):
        pack = example_pack()
        pack["window_start"] = "2026-09-25T08:00:00+08:00"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                composer.compose(pack, temp)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_top_stories_stay_in_their_strategy_detail_section(self):
        pack = example_pack()
        original = pack["stories"][0]
        pack["stories"] = [dict(copy.deepcopy(original), id=f"story-{i}", headline=f"Unique headline {i}") for i in range(3)]
        pack["top_stories"] = ["story-0", "story-1", "story-2"]
        groups = composer._ordered_groups(composer.validate_pack(pack))
        self.assertEqual(groups[0][0], 'Merger Arbitrage')
        self.assertEqual(len(groups[0][1]), 3)
        self.assertEqual(sum(len(items) for _, items in groups), 3)

    def test_review_diagnostics_and_calendar_never_enter_distribution_email(self):
        pack = example_pack()
        pack['upcoming_events'] = [{'label': 'Synthetic meeting reminder', 'event_date': '2026-09-25',
                                    'source_url': 'https://example.com/meeting', 'source_name': 'Issuer',
                                    'time_status': 'provisional', 'status': 'scheduled'}]
        with tempfile.TemporaryDirectory() as temp:
            composer.compose(pack, temp)
            email = (Path(temp) / 'email.html').read_text(encoding='utf-8')
            review = (Path(temp) / 'review.html').read_text(encoding='utf-8')
            for label in ('Synthetic fixture only.', 'Synthetic meeting reminder', 'AI-generated draft', pack['as_of']):
                self.assertNotIn(label, email)
                self.assertIn(label, review)

    def test_local_logo_is_self_contained_in_html_and_inline_cid_in_mime(self):
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3iUAAAAASUVORK5CYII=')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'logo.png').write_bytes(png)
            style = root / 'house-style.json'
            style.write_text(json.dumps({'title': 'Supplied house title', 'logo_path': 'logo.png', 'logo_width': 314}), encoding='utf-8')
            output = root / 'draft'
            composer.compose(example_pack(), output, style)
            message = BytesParser(policy=policy.default).parsebytes((output / 'morning-note.eml').read_bytes())
            html = message.get_body(preferencelist=('html',)).get_content()
            self.assertIn('cid:morning-note-house-logo', html)
            self.assertNotIn('data:image', html)
            image_parts = [part for part in message.walk() if part.get_content_maintype() == 'image']
            self.assertEqual(len(image_parts), 1)
            self.assertEqual(image_parts[0].get_payload(decode=True), png)
            self.assertEqual(image_parts[0]['Content-ID'], '<morning-note-house-logo>')
            preview = (output / 'email.html').read_text(encoding='utf-8')
            self.assertIn('data:image/png;base64,', preview)
            self.assertIn('Supplied house title', preview)

    def test_house_style_rejects_logo_outside_its_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            style = root / 'house-style.json'
            style.write_text(json.dumps({'logo_path': '../outside.png'}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'inside'):
                composer.load_branding(style)

    def test_review_has_no_external_assets_and_edited_eml_controls(self):
        pack = composer.validate_pack(example_pack())
        review = composer.review_page(pack, composer.email_body(pack), pack["title"])
        self.assertIn('contenteditable="true"', review)
        self.assertIn('id="copy"', review)
        self.assertIn('id="download"', review)
        self.assertNotIn('<script src=', review)
        self.assertNotIn('<link ', review)
        self.assertIn('X-Unsent: 1', review)


if __name__ == "__main__":
    unittest.main()
