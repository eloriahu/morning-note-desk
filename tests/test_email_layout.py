import copy
import importlib.util
from pathlib import Path
import unittest

from lxml import html


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "email_layout.py"
SPEC = importlib.util.spec_from_file_location("email_layout", SCRIPT)
layout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(layout)


def sample_pack():
    return {"title": "Internal edition title", "as_of": "2026-09-25T08:00:00+08:00", "coverage": ["Private coverage audit"],
            "top_stories": ["sample/a"], "stories": [
                {"id": "sample/a", "company": "Example company", "tickers": ["TEST JP"], "category": "Merger Arbitrage",
                 "composition_status": "ready", "headline": "Synthetic example headline",
                 "bullets": [{"text": "Synthetic example statement.", "source_urls": ["https://example.com/one"]}],
                 "sources": [{"url": "https://example.com/one", "name": "Example source"}]},
                {"id": "held", "company": "Held company", "tickers": [], "category": "Other Strategy", "composition_status": "hold", "headline": "Held headline"},
            ]}


class EmailLayoutTests(unittest.TestCase):
    def test_top_pick_is_index_link_and_remains_in_real_detail_category(self):
        pack = sample_pack()
        groups = layout.ordered_groups(pack)
        self.assertEqual([label for label, _ in groups], list(layout.SECTIONS))
        self.assertEqual([story["id"] for story in groups[0][1]], ["sample/a"])
        doc = html.fromstring(layout.email_body(pack))
        index = doc.xpath('//table[@class="mn-index"]')[0]
        links = index.xpath('.//a')
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].get("href"), links[1].get("href"))
        self.assertEqual(len(doc.xpath('//div[@class="mn-story"]')), 1)
        self.assertEqual(doc.xpath('//table[@class="mn-category"]/tr/td')[0].text, "Merger Arbitrage")
        self.assertIn("NEWS SUMMARY", doc.text_content())
        self.assertNotIn("Held headline", doc.text_content())

    def test_dense_house_structure_uses_inline_style_and_ticker_first(self):
        doc = html.fromstring(layout.email_body(sample_pack()))
        self.assertFalse(doc.xpath('//h1 | //h2 | //h3 | //ul | //li'))
        story = doc.xpath('//div[@class="mn-story"]')[0]
        self.assertLess(story.text_content().index("TEST JP"), story.text_content().index("EXAMPLE COMPANY"))
        self.assertIn("* Synthetic example statement.", story.text_content())
        self.assertTrue(doc.xpath('//*[@style and contains(@style,"font-size:10pt")]'))
        self.assertTrue(doc.xpath('//*[@style and contains(@style,"#0A2348")]'))
        self.assertTrue(doc.xpath('//a[@href="#mn-top"]'))

    def test_app_audit_content_is_not_exported(self):
        pack = sample_pack()
        for output in (layout.email_body(pack), layout.email_text(pack)):
            self.assertNotIn("AI-generated", output)
            self.assertNotIn("Private coverage audit", output)
            self.assertNotIn(pack["as_of"], output)
            self.assertNotIn("Held headline", output)

    def test_single_shared_source_lives_next_to_headline_without_bullet_repetition(self):
        pack = sample_pack()
        pack["stories"][0]["bullets"].append({"text": "Second synthetic statement.", "source_urls": ["https://example.com/one"]})
        doc = html.fromstring(layout.email_body(pack))
        story = doc.xpath('//div[@class="mn-story"]')[0]
        self.assertEqual(len(story.xpath('.//a[@href="https://example.com/one"]')), 1)
        source = story.xpath('.//a')[0]
        self.assertEqual(source.text, "Example source")
        self.assertEqual(source.getparent().getparent().tag, "p")

    def test_different_bullet_sources_retain_discreet_direct_numbered_citations(self):
        pack = sample_pack()
        story = pack["stories"][0]
        story["sources"].append({"url": "https://example.com/two", "name": "Second source"})
        story["bullets"].append({"text": "Second synthetic statement.", "source_urls": ["https://example.com/two"]})
        doc = html.fromstring(layout.email_body(pack))
        rendered = doc.xpath('//div[@class="mn-story"]')[0]
        self.assertEqual(len(rendered.xpath('.//a')), 4)
        self.assertEqual(rendered.xpath('.//p[last()]/span/a')[0].get("href"), "https://example.com/two")
        self.assertEqual(rendered.xpath('.//p[last()]/span/a')[0].text, "[2]")

    def test_escaped_data_and_stable_safe_anchors(self):
        pack = sample_pack()
        payload = '<img src=x onerror="alert(1)">'
        pack["stories"][0].update(id=payload, company=payload, headline=payload)
        pack["top_stories"] = [payload]
        pack["stories"][0]["bullets"][0]["text"] = payload
        pack["stories"][0]["sources"][0]["name"] = payload
        branding = {"title": payload, "subtitle": payload, "region": payload, "logo_data_url": "data:image/svg+xml,<svg onload=alert(1)>",
                    "footer": {"include_in_draft": True, "heading": payload, "intro": payload, "groups": [{"label": payload, "lines": [payload]}], "disclaimer_text": payload}}
        first = layout.email_body(pack, branding)
        second = layout.email_body(copy.deepcopy(pack), branding)
        self.assertEqual(first, second)
        doc = html.fromstring(first)
        self.assertFalse(doc.xpath('//img | //script | //*[@onerror]'))
        ids = set(doc.xpath('//@id'))
        for anchor in doc.xpath('//a[starts-with(@href,"#")]/@href'):
            self.assertIn(anchor[1:], ids)

    def test_no_brand_or_contacts_are_assumed_and_optional_branding_is_applied(self):
        default = layout.email_body(sample_pack())
        self.assertNotIn("Example Brand", default)
        self.assertNotIn("mailto:", default)
        branded = html.fromstring(layout.email_body(sample_pack(), {"title": "Team note", "contact_email": "desk@example.com",
                    "footer": {"include_in_draft": True, "intro": "Contact our team", "contact_email": "desk@example.com", "groups": [{"label": "Region", "lines": ["Example contact"]}], "disclaimer_text": "Example footer", "disclaimer_url": "https://example.com/disclaimer"}}))
        self.assertIn("Team note", branded.text_content())
        self.assertEqual(len(branded.xpath('//a[@href="mailto:desk@example.com"]')), 2)
        self.assertIn("Example footer", branded.text_content())
        self.assertIn("Example contact", branded.text_content())
        self.assertEqual(len(branded.xpath('//a[@href="https://example.com/disclaimer"]')), 1)

    def test_footer_must_be_explicitly_enabled(self):
        branding = {"footer": {"include_in_draft": False, "intro": "Do not export this footer"}}
        self.assertNotIn("Do not export", layout.email_body(sample_pack(), branding))
        self.assertNotIn("Do not export", layout.email_text(sample_pack(), branding))

    def test_plain_text_has_index_then_details_and_all_citation_urls(self):
        output = layout.email_text(sample_pack())
        self.assertLess(output.index("Top Stories"), output.index("NEWS SUMMARY"))
        self.assertEqual(output.count("Synthetic example headline"), 3)
        self.assertEqual(output.count("* Synthetic example statement."), 1)
        self.assertIn("https://example.com/one", output)


if __name__ == "__main__":
    unittest.main()
