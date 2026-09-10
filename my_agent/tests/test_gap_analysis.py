import unittest
from my_agent.db.firestore_client import FirestoreWardrobeClient
from my_agent.services.gap_analysis import GapAnalysisService, CompatibilityGraph


class TestPredictiveGapAnalysis(unittest.TestCase):
    def setUp(self):
        self.mock_firestore = FirestoreWardrobeClient(use_mock=True)
        self.gap_service = GapAnalysisService(firestore_client=self.mock_firestore)

    def test_isolated_garment_detection_and_bridge_staple(self):
        """
        Creates a wardrobe with:
        - 1 Formal Top (Black Silk Shirt)
        - 1 Casual Bottom (Ripped Jeans)
        - 1 Dress (Emerald Slip Dress)
        - 1 Athletic Sneaker (Neon Yellow)
        - 1 Heavily worn item (wear_count = 35)
        Tests that isolated garments and Bridge Staples are accurately computed.
        """
        user_id = "user_gap_test"
        
        items = [
            {
                "item_id": "item_top_formal",
                "item_name": "Black Silk Formal Button-Down",
                "category": "Top",
                "formality": "Formal",
                "primary_color": "Black",
                "occasion": "Formal / Black Tie",
                "warmth_rating": 2,
                "wear_count": 2
            },
            {
                "item_id": "item_bottom_casual",
                "item_name": "Ripped Denim Jeans",
                "category": "Bottom",
                "formality": "Casual",
                "primary_color": "Blue",
                "occasion": "Casual / Daily",
                "warmth_rating": 3,
                "wear_count": 35  # Overworn item
            },
            {
                "item_id": "item_dress",
                "item_name": "Emerald Silk Midi Dress",
                "category": "Dress",
                "formality": "Smart Casual",
                "primary_color": "Emerald Green",
                "occasion": "Party / Night Out",
                "warmth_rating": 2,
                "wear_count": 4
            },
            {
                "item_id": "item_shoes_athletic",
                "item_name": "Neon Yellow Running Shoes",
                "category": "Footwear",
                "formality": "Casual",
                "primary_color": "Yellow",
                "occasion": "Athletic / Activewear",
                "warmth_rating": 2,
                "wear_count": 8
            }
        ]

        for item in items:
            self.mock_firestore.save_item(user_id=user_id, item_data=item)

        # Run Gap Analysis with upcoming Formal Dinner schedule at 15°C
        schedule = {"occasion": "Formal / Black Tie", "expected_temp": 15.0}
        report = self.gap_service.analyze_wardrobe(user_id=user_id, target_schedule=schedule)

        self.assertEqual(report["status"], "success")
        self.assertTrue(report["isolated_garments_count"] > 0)
        
        # 1. Versatility Multipliers check
        self.assertIn("versatility_multipliers", report)
        self.assertTrue(len(report["versatility_multipliers"]) > 0)

        # 2. Occasion Bridges check (Formal outerwear gap at 15°C)
        self.assertIn("occasion_bridges", report)
        self.assertTrue(len(report["occasion_bridges"]) > 0)
        bridge_reasons = [b.get("reason", "") for b in report["occasion_bridges"]]
        self.assertTrue(any("Formal" in r or "Outerwear" in r for r in bridge_reasons))

        # 3. Replacement Flags check (Ripped Jeans worn 35 times)
        self.assertIn("replacement_flags", report)
        flagged_ids = [f["item_id"] for f in report["replacement_flags"]]
        self.assertIn("item_bottom_casual", flagged_ids)


if __name__ == "__main__":
    unittest.main()
