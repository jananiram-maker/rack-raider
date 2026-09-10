import unittest
from my_agent.services.vector_search import (
    VectorSearchService,
    compute_cosine_similarity
)
from my_agent.services.ingestion_service import IngestionService
from my_agent.db.firestore_client import FirestoreWardrobeClient
from my_agent.db.bigquery_client import BigQueryWardrobeClient
from my_agent.db.sync_service import SyncService


class TestIngestionAndDeDuplication(unittest.TestCase):
    def setUp(self):
        self.mock_firestore = FirestoreWardrobeClient(use_mock=True)
        self.mock_bigquery = BigQueryWardrobeClient(use_mock=True)
        self.sync_service = SyncService(
            firestore_client=self.mock_firestore,
            bigquery_client=self.mock_bigquery,
            run_worker_thread=False
        )
        self.vector_service = VectorSearchService()
        self.ingestion_service = IngestionService(
            firestore_client=self.mock_firestore,
            sync_service=self.sync_service,
            vector_service=self.vector_service
        )

    def test_cosine_similarity_math(self):
        """Validates exact vector cosine similarity calculation."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        vec3 = [0.0, 1.0, 0.0]
        vec4 = [0.7071, 0.7071, 0.0]

        self.assertAlmostEqual(compute_cosine_similarity(vec1, vec2), 1.0, places=4)
        self.assertAlmostEqual(compute_cosine_similarity(vec1, vec3), 0.0, places=4)
        self.assertAlmostEqual(compute_cosine_similarity(vec1, vec4), 0.7071, places=3)

    def test_outfit_decomposition_with_dress(self):
        """Validates multimodal decomposition recognizing Dress as a standalone category."""
        result = self.ingestion_service.decompose_outfit_image("gs://wardrobe_sfs/user01/photos/emerald_dress.jpg")
        self.assertIsNotNone(result)
        self.assertTrue(len(result.garments) >= 1)

        categories = [g.category for g in result.garments]
        self.assertIn("Dress", categories)

    def test_ingestion_new_item_creation_and_deduplication(self):
        """
        Validates that:
        1. Ingesting an outfit for the first time creates new items in Firestore with wear_count = 1.
        2. Ingesting the same outfit again triggers >0.88 cosine similarity and increments wear_count to 2.
        """
        user_id = "test_user_001"
        image_uri = "gs://wardrobe_sfs/user001/photos/daily_outfit.jpg"

        # Pass 1: Initial Ingestion
        res1 = self.ingestion_service.process_outfit_image_and_deduplicate(
            user_id=user_id,
            image_uri=image_uri,
            worn_date="2026-09-01"
        )

        self.assertEqual(res1["status"], "success")
        self.assertTrue(res1["total_garments_processed"] > 0)
        
        # Verify all items in pass 1 were created as new items
        for g in res1["garments"]:
            self.assertEqual(g["action"], "NEW_ITEM_CREATED")
            self.assertEqual(g["wear_count"], 1)

        # Check items in Firestore
        items_after_pass1 = self.mock_firestore.list_items(user_id=user_id)
        self.assertEqual(len(items_after_pass1), res1["total_garments_processed"])

        # Pass 2: Re-ingest the same outfit photo
        res2 = self.ingestion_service.process_outfit_image_and_deduplicate(
            user_id=user_id,
            image_uri=image_uri,
            worn_date="2026-09-02"
        )

        self.assertEqual(res2["status"], "success")
        
        # Verify that all identical garments were de-duplicated and wear counts incremented
        for g in res2["garments"]:
            self.assertEqual(g["action"], "INCREMENT_WEAR")
            self.assertEqual(g["wear_count"], 2)
            self.assertTrue(g["similarity_score"] >= 0.88)

        # Check that no duplicate items were created in Firestore
        items_after_pass2 = self.mock_firestore.list_items(user_id=user_id)
        self.assertEqual(len(items_after_pass2), len(items_after_pass1))


if __name__ == "__main__":
    unittest.main()
