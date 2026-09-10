import unittest
import os
from my_agent import config
from my_agent.auth import (
    create_dev_session,
    authenticate_user,
    validate_user_access,
    UserSession
)


class TestConfigAndAuth(unittest.TestCase):
    def test_global_config_values(self):
        """Validates that global settings are accessible and configurable."""
        self.assertIsNotNone(config.DEFAULT_GEMINI_MODEL)
        self.assertIsNotNone(config.GCS_BUCKET_NAME)
        self.assertIsNotNone(config.BIGQUERY_DATASET)
        self.assertIsNotNone(config.BIGQUERY_TABLE_ITEMS)
        self.assertIsNotNone(config.BIGQUERY_TABLE_OUTFITS)
        self.assertIsNotNone(config.BIGQUERY_TABLE_OUTFIT_ITEMS)
        self.assertEqual(config.SIMILARITY_THRESHOLD, 0.88)

        # Test table id formatting
        table_id = config.get_bq_table_id("Items", project_id="test-proj", dataset="test_ds")
        self.assertEqual(table_id, "test-proj.test_ds.Items")

    def test_user_authentication_and_isolation(self):
        """Validates user session creation and cross-user data isolation enforcement."""
        session_a = authenticate_user("user_alice")
        session_b = authenticate_user("user_bob")

        self.assertEqual(session_a.user_id, "user_alice")
        self.assertEqual(session_b.user_id, "user_bob")

        # Accessing own data should succeed
        self.assertTrue(validate_user_access("user_alice", "user_alice"))
        self.assertTrue(validate_user_access("user_bob", "user_bob"))

        # Cross-user access MUST raise PermissionError
        with self.assertRaises(PermissionError):
            validate_user_access("user_alice", "user_bob")

        with self.assertRaises(PermissionError):
            validate_user_access("user_bob", "user_alice")


if __name__ == "__main__":
    unittest.main()
