import unittest
from my_agent.db.firestore_client import FirestoreWardrobeClient
from my_agent.db.bigquery_client import BigQueryWardrobeClient
from my_agent.db.sync_service import SyncService


class TestDualDatabaseArchitecture(unittest.TestCase):
    def setUp(self):
        self.firestore = FirestoreWardrobeClient(use_mock=True)
        self.bigquery = BigQueryWardrobeClient(use_mock=True)
        self.sync_service = SyncService(
            firestore_client=self.firestore,
            bigquery_client=self.bigquery,
            run_worker_thread=False
        )

    def test_firestore_user_isolation(self):
        """Validates that user A cannot see user B's closet items in Firestore."""
        item_a = {"item_id": "item_a_01", "item_name": "Alice's Jacket", "category": "Outerwear"}
        item_b = {"item_id": "item_b_01", "item_name": "Bob's Shoes", "category": "Footwear"}

        self.firestore.save_item("alice", item_a)
        self.firestore.save_item("bob", item_b)

        alice_items = self.firestore.list_items("alice")
        bob_items = self.firestore.list_items("bob")

        self.assertEqual(len(alice_items), 1)
        self.assertEqual(alice_items[0]["item_id"], "item_a_01")

        self.assertEqual(len(bob_items), 1)
        self.assertEqual(bob_items[0]["item_id"], "item_b_01")

    def test_bigquery_tables_and_sync_queue(self):
        """Validates BigQuery 3-table insertion and async sync queue."""
        user_id = "user_bq_test"
        
        # 1. Sync Item
        item_data = {
            "item_id": "item_tshirt_01",
            "user_id": user_id,
            "category": "Top",
            "occasion": "Casual / Daily",
            "material": "Cotton",
            "season_tag": "Summer",
            "wear_frequency_expectation": "Weekly"
        }
        self.sync_service.queue_item_sync(item_data)

        # 2. Sync Outfit + Junction
        outfit_data = {
            "outfit_id": "outfit_01",
            "user_id": user_id,
            "worn_date": "2026-09-01",
            "occasion": "Casual / Daily",
            "weather_summary": "Sunny 22C"
        }
        self.sync_service.queue_outfit_sync(outfit_data, item_ids=["item_tshirt_01", "item_jeans_01"])

        # Manually process queue in test
        while not self.sync_service._queue.empty():
            evt = self.sync_service._queue.get()
            self.sync_service._dispatch_event(evt)
            self.sync_service._queue.task_done()

        # Check BigQuery mock tables
        self.assertEqual(len(self.bigquery._mock_tables["Items"]), 1)
        self.assertEqual(len(self.bigquery._mock_tables["Outfits"]), 1)
        self.assertEqual(len(self.bigquery._mock_tables["Outfit_Items"]), 2)

    def test_bigquery_analytics_helpers(self):
        """Validates item wear frequency, co-occurrence matrix, and seasonal underutilization queries."""
        user_id = "analytics_user"

        # Populate Items
        items = [
            {"item_id": "top_01", "user_id": user_id, "category": "Top", "occasion": "Casual / Daily", "season_tag": "Summer", "wear_frequency_expectation": "Weekly"},
            {"item_id": "bottom_01", "user_id": user_id, "category": "Bottom", "occasion": "Casual / Daily", "season_tag": "Summer", "wear_frequency_expectation": "Weekly"},
            {"item_id": "top_winter_01", "user_id": user_id, "category": "Top", "occasion": "Casual / Daily", "season_tag": "Winter", "wear_frequency_expectation": "Seasonal"},
            {"item_id": "summer_unworn_01", "user_id": user_id, "category": "Top", "occasion": "Casual / Daily", "season_tag": "Summer", "wear_frequency_expectation": "Weekly"}
        ]
        self.bigquery.insert_items(items)

        # Populate Outfits & Outfit_Items (worn 3 times together)
        for i in range(3):
            outfit_id = f"outfit_wear_{i}"
            self.bigquery.insert_outfits([{
                "outfit_id": outfit_id, "user_id": user_id, "worn_date": f"2026-08-0{i+1}", "occasion": "Casual / Daily", "weather_summary": "Warm"
            }])
            self.bigquery.insert_outfit_items([
                {"outfit_id": outfit_id, "item_id": "top_01"},
                {"outfit_id": outfit_id, "item_id": "bottom_01"}
            ])

        # 1. Wear Frequency Query
        freq_results = self.bigquery.query_item_wear_frequency(user_id=user_id)
        top_worn = next(x for x in freq_results if x["item_id"] == "top_01")
        self.assertEqual(top_worn["total_wears"], 3)

        # 2. Co-occurrence Matrix Query
        co_results = self.bigquery.query_cooccurrence_matrix(user_id=user_id)
        self.assertEqual(len(co_results), 1)
        self.assertEqual(co_results[0]["cooccurrence_count"], 3)

        # 3. Seasonal Underutilized Flags Query (Summer active, summer_unworn_01 has 0 wears)
        flagged = self.bigquery.query_underutilized_seasonal_flags(user_id=user_id, current_season="Summer")
        flagged_ids = [f["item_id"] for f in flagged]
        self.assertIn("summer_unworn_01", flagged_ids)


if __name__ == "__main__":
    unittest.main()
