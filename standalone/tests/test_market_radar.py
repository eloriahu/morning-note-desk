import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_radar import triage


class MarketRadarTests(unittest.TestCase):
    def test_unknown_company_deal_does_not_need_watchlist_match(self):
        result = triage("NewCo agrees to acquire Horizon for $3 billion")
        self.assertGreaterEqual(result["attention_score"], 80)
        self.assertEqual(result["category"], "Merger Arbitrage")
        self.assertTrue(result["market_relevant"])
        self.assertEqual(set(result), {"attention_score", "attention_reasons", "event_type", "category", "market_relevant"})

    def test_priority_boring_item_does_not_outrank_unknown_deal(self):
        boring = triage("Acme company opens a new branch", priority_matches=["DEMO"])
        deal = triage("NewCo launches tender offer for Horizon")
        self.assertLess(boring["attention_score"], deal["attention_score"])
        self.assertEqual(boring["event_type"], "General business")

    def test_priority_match_is_small_bounded_boost(self):
        title = "Acme announces financial results"
        normal = triage(title)
        boosted = triage(title, priority_matches=["A", "B", "C"])
        self.assertEqual(boosted["attention_score"] - normal["attention_score"], 8)
        self.assertIn("Priority-name match", boosted["attention_reasons"][-1])

    def test_priority_name_alone_does_not_create_event_evidence(self):
        result = triage("Acme hosts a charity picnic", priority_matches=["A"])
        self.assertFalse(result["market_relevant"])
        self.assertEqual(result["attention_score"], 8)

    def test_japanese_tender_without_known_name(self):
        result = triage("未登録企業が公開買い付けを発表、非公開化へ")
        self.assertEqual(result["event_type"], "Tender/deadline")
        self.assertGreaterEqual(result["attention_score"], 90)

    def test_full_width_tob_normalised(self):
        self.assertEqual(triage("新会社のＴＯＢ価格引き上げ")["event_type"], "Tender/deadline")
        self.assertEqual(triage("新会社がＩＰＯへ")["event_type"], "Capital raising/IPO")
        self.assertEqual(triage("国内Ｍ＆Ａ増加へ")["event_type"], "Deal terms/process")

    def test_chinese_simplified_and_traditional(self):
        for title in ["甲公司收购乙公司控股权", "甲公司收購乙公司控股權"]:
            with self.subTest(title=title):
                self.assertEqual(triage(title)["event_type"], "Deal terms/process")

    def test_portuguese_merger(self):
        self.assertEqual(triage("Companhia anuncia fusão com rival")["event_type"], "Deal terms/process")

    def test_buyback_multilingual(self):
        for title in ["Acme announces share buyback programme", "会社が自社株買いを発表", "公司宣布回購股份"]:
            with self.subTest(title=title):
                self.assertEqual(triage(title)["event_type"], "Buyback/capital return")

    def test_earnings_guidance_multilingual(self):
        for title in ["Acme cuts guidance after weak quarter", "今期業績予想を下方修正", "公司發布盈利預警"]:
            with self.subTest(title=title):
                self.assertEqual(triage(title)["event_type"], "Results/guidance")

    def test_activism_and_stake(self):
        for title in ["Activist investor demands board changes at NewCo", "Fund takes a 12 percent stake in NewCo", "物言う株主が会社に株主提案"]:
            with self.subTest(title=title):
                self.assertEqual(triage(title)["event_type"], "Ownership/activism")

    def test_restructuring_capital_and_regulatory(self):
        cases = {
            "Company proposes spin-off of its business": "Restructuring/spin-off",
            "NewCo plans rights issue": "Capital raising/IPO",
            "Competition regulator clears transaction": "Regulatory decision",
            "FDA approves NewCo drug": "Regulatory decision",
        }
        for title, kind in cases.items():
            with self.subTest(title=title):
                self.assertEqual(triage(title)["event_type"], kind)

    def test_macro_classified_but_not_ranked_as_corporate_event(self):
        result = triage("Central bank holds interest rates as inflation slows")
        self.assertEqual(result["event_type"], "Macro/markets")
        self.assertTrue(result["market_relevant"])
        self.assertLess(result["attention_score"], 40)

    def test_general_unrelated_headline(self):
        result = triage("City opens a park for children")
        self.assertEqual(result["attention_score"], 0)
        self.assertFalse(result["market_relevant"])

    def test_shopping_offer_is_not_takeover(self):
        for title in ["Weekend offer: buy one get one free", "Retailer offers discounts for shoppers"]:
            with self.subTest(title=title):
                self.assertLess(triage(title)["attention_score"], 40)

    def test_sports_bid_and_tournament_results_not_event(self):
        for title in ["Team launches bid to win the world cup", "Latest cricket results", "Runner wins race in final bid"]:
            with self.subTest(title=title):
                self.assertFalse(triage(title)["market_relevant"])

    def test_public_tender_contract_is_not_tender_offer(self):
        self.assertLess(triage("City opens tender for a new bridge")["attention_score"], 40)

    def test_noncorporate_acquisition_senses(self):
        for title in ["New study explores language acquisition", "Black-hole merger observed in distant space", "Students acquire new skills", "Museum acquires portrait for its collection"]:
            with self.subTest(title=title):
                self.assertLess(triage(title)["attention_score"], 40)

    def test_real_takeover_of_sports_club_still_kept(self):
        self.assertGreaterEqual(triage("Investor launches takeover offer for football club")["attention_score"], 80)

    def test_article_text_signal_explains_lower_confidence(self):
        title_result = triage("Acme announces share buyback")
        body_result = triage("Acme investor update", "The company announces share buyback.")
        self.assertEqual(title_result["attention_score"] - body_result["attention_score"], 8)
        self.assertIn("article text", body_result["attention_reasons"][0])

    def test_multiple_signals_and_score_cap(self):
        result = triage("Tender offer and merger agreement receive antitrust clearance", priority_matches=["A"])
        self.assertLessEqual(result["attention_score"], 100)
        self.assertGreaterEqual(len(result["attention_reasons"]), 3)
        self.assertEqual(result, triage("Tender offer and merger agreement receive antitrust clearance", priority_matches=["A"]))

    def test_empty_inputs(self):
        self.assertEqual(triage(None, None)["attention_score"], 0)


if __name__ == "__main__":
    unittest.main()
