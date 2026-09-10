import unittest
from my_agent.db.firestore_client import FirestoreWardrobeClient
from my_agent.services.circular_commerce import CircularCommerceService


class TestCircularCommerce(unittest.TestCase):
    def setUp(self):
        self.firestore = FirestoreWardrobeClient(use_mock=True)
        self.circular_service = CircularCommerceService(firestore_client=self.firestore)

    def test_circular_domain_logic_evaluation(self):
        """
        Creates items triggering each of the 3 circular commerce rules:
        1. "Style It Differently": In-season (Summer), unworn for 45 days, has >= 2 pairings (with neutrals)
        2. "Move to Storage": Out-of-season (Winter heavy coat), worn in past active season
        3. "Consider Donating": In-season (Summer), unworn for 200 days, 0 or 1 pairings
        """
        user_id = "user_circular_test"

        items = [
            # Item 1: Style It Differently candidate
            {
                "item_id": "item_summer_linen_shirt",
                "item_name": "Sky Blue Linen Shirt",
                "category": "Top",
                "season_tag": "Summer",
                "formality": "Smart Casual",
                "primary_color": "Blue",
                "wear_count": 3,
                "last_worn_date": "2026-07-01",  # Unworn for > 30 days
            },
            # Compatible pieces to provide >= 2 pairings
            {
                "item_id": "item_beige_chinos",
                "item_name": "Beige Cotton Chinos",
                "category": "Bottom",
                "season_tag": "Summer",
                "formality": "Smart Casual",
                "primary_color": "Beige",
                "wear_count": 10,
                "last_worn_date": "2026-08-25"
            },
            {
                "item_id": "item_white_shorts",
                "item_name": "White Linen Shorts",
                "category": "Bottom",
                "season_tag": "Summer",
                "formality": "Casual",
                "primary_color": "White",
                "wear_count": 5,
                "last_worn_date": "2026-08-20"
            },
            {
                "item_id": "item_loafers",
                "item_name": "Brown Leather Loafers",
                "category": "Footwear",
                "season_tag": "Summer",
                "formality": "Smart Casual",
                "primary_color": "Brown",
                "wear_count": 12,
                "last_worn_date": "2026-08-28"
            },
            # Item 2: Move to Storage candidate (Winter coat during Summer evaluation)
            {
                "item_id": "item_heavy_parka",
                "item_name": "Heavy Down Winter Parka",
                "category": "Outerwear",
                "season_tag": "Winter",
                "formality": "Casual",
                "primary_color": "Black",
                "wear_count": 15,
                "last_worn_date": "2026-01-15"
            },
            # Item 3: Consider Donating candidate (Unworn for > 180 days, no matching bottom)
            {
                "item_id": "item_obscure_polka_top",
                "item_name": "Neon Purple Polka Dot Top",
                "category": "Top",
                "season_tag": "Summer",
                "formality": "Formal",
                "primary_color": "Purple",
                "wear_count": 0,
                "last_worn_date": "2025-05-01"  # > 180 days
            }
        ]

        for item in items:
            self.firestore.save_item(user_id=user_id, item_data=item)

        # Run evaluation with active season = "Summer"
        report = self.circular_service.evaluate_closet(
            user_id=user_id,
            current_season="Summer",
            days_unworn_threshold=30
        )

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["active_season"], "Summer")

        # 1. Check "Style It Differently"
        style_ids = [i["item_id"] for i in report["style_it_differently"]]
        self.assertIn("item_summer_linen_shirt", style_ids)

        # 2. Check "Move to Storage"
        storage_ids = [i["item_id"] for i in report["move_to_storage"]]
        self.assertIn("item_heavy_parka", storage_ids)

        # 3. Check "Consider Donating"
        donate_ids = [i["item_id"] for i in report["consider_donating"]]
        self.assertIn("item_obscure_polka_top", donate_ids)


if __name__ == "__main__":
    unittest.main()
