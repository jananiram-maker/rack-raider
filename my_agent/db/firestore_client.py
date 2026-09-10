"""
Firestore Database Client with Strict User Isolation.
Real-Time Session State for Items, Outfits, and Wear Logs.
"""

import time
import uuid
from typing import Dict, List, Optional, Any
from ..config import (
    GCP_PROJECT_ID,
    FIRESTORE_USERS_COLLECTION,
    FIRESTORE_ITEMS_SUBCOLLECTION,
    FIRESTORE_OUTFITS_SUBCOLLECTION,
    FIRESTORE_WEAR_LOGS_SUBCOLLECTION
)
from ..auth import validate_user_access

# Try importing real Firestore client
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False


class FirestoreWardrobeClient:
    """
    Manages real-time wardrobe state in Firestore with strict user data isolation.
    """
    def __init__(self, project_id: str = GCP_PROJECT_ID, use_mock: bool = False):
        self.project_id = project_id
        self._db = None
        self._use_mock = use_mock or (not FIRESTORE_AVAILABLE)
        
        # In-memory storage for mock/local development: {user_id: {items: {}, outfits: {}, wear_logs: {}}}
        self._mock_db: Dict[str, Dict[str, Dict[str, Any]]] = {}

        if not self._use_mock:
            try:
                self._db = firestore.Client(project=self.project_id)
            except Exception as e:
                print(f"[Firestore] Live client initialization failed: {e}. Falling back to in-memory store.")
                self._use_mock = True

    def _ensure_user_store(self, user_id: str):
        if user_id not in self._mock_db:
            self._mock_db[user_id] = {
                FIRESTORE_ITEMS_SUBCOLLECTION: {},
                FIRESTORE_OUTFITS_SUBCOLLECTION: {},
                FIRESTORE_WEAR_LOGS_SUBCOLLECTION: {}
            }

    def save_item(self, user_id: str, item_data: Dict[str, Any], auth_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Saves or updates a garment record in the user's isolated Firestore subcollection.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        item_id = item_data.get("item_id") or f"item_{uuid.uuid4().hex[:12]}"
        now = time.time()
        
        record = {
            **item_data,
            "item_id": item_id,
            "user_id": user_id,
            "created_at": item_data.get("created_at", now),
            "updated_at": now,
            "wear_count": item_data.get("wear_count", 0),
            "last_worn_date": item_data.get("last_worn_date", None),
            "status": item_data.get("status", "active")  # active, stored, donated
        }

        if self._use_mock:
            self._ensure_user_store(user_id)
            self._mock_db[user_id][FIRESTORE_ITEMS_SUBCOLLECTION][item_id] = record
        else:
            doc_ref = (
                self._db.collection(FIRESTORE_USERS_COLLECTION)
                .document(user_id)
                .collection(FIRESTORE_ITEMS_SUBCOLLECTION)
                .document(item_id)
            )
            doc_ref.set(record)

        return record

    def get_item(self, user_id: str, item_id: str, auth_user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single item from the user's closet.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        if self._use_mock:
            self._ensure_user_store(user_id)
            return self._mock_db[user_id][FIRESTORE_ITEMS_SUBCOLLECTION].get(item_id)
        
        doc_ref = (
            self._db.collection(FIRESTORE_USERS_COLLECTION)
            .document(user_id)
            .collection(FIRESTORE_ITEMS_SUBCOLLECTION)
            .document(item_id)
        )
        snapshot = doc_ref.get()
        return snapshot.to_dict() if snapshot.exists else None

    def delete_item(self, user_id: str, item_id: str, auth_user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Deletes a garment item from the user's closet.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        if self._use_mock:
            self._ensure_user_store(user_id)
            if item_id in self._mock_db[user_id][FIRESTORE_ITEMS_SUBCOLLECTION]:
                del self._mock_db[user_id][FIRESTORE_ITEMS_SUBCOLLECTION][item_id]
            return {"status": "success", "deleted_item": item_id}

        doc_ref = (
            self._db.collection(FIRESTORE_USERS_COLLECTION)
            .document(user_id)
            .collection(FIRESTORE_ITEMS_SUBCOLLECTION)
            .document(item_id)
        )
        doc_ref.delete()
        return {"status": "success", "deleted_item": item_id}

    def list_items(
        self,
        user_id: str,
        category: Optional[str] = None,
        occasion: Optional[str] = None,
        season: Optional[str] = None,
        status: Optional[str] = "active",
        auth_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Queries all items belonging strictly to the specified user with optional filters.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        if self._use_mock:
            self._ensure_user_store(user_id)
            items = list(self._mock_db[user_id][FIRESTORE_ITEMS_SUBCOLLECTION].values())
            filtered = []
            for item in items:
                if status and item.get("status") != status:
                    continue
                if category and item.get("category") != category:
                    continue
                if occasion and item.get("occasion") != occasion and item.get("occasion") != "Casual / Daily":
                    continue
                if season and item.get("season_tag") and season not in item.get("season_tag") and item.get("season_tag") != "All-Season":
                    continue
                # Ensure gcs_uri is present (normalize from item_gs_uri if needed)
                if not item.get("gcs_uri") and item.get("item_gs_uri"):
                    item["gcs_uri"] = item["item_gs_uri"]
                filtered.append(item)
            return filtered

        query = (
            self._db.collection(FIRESTORE_USERS_COLLECTION)
            .document(user_id)
            .collection(FIRESTORE_ITEMS_SUBCOLLECTION)
        )
        if status:
            query = query.where("status", "==", status)
        if category:
            query = query.where("category", "==", category)
        if occasion:
            query = query.where("occasion", "==", occasion)

        docs = query.stream()
        items = []
        for doc in docs:
            item = doc.to_dict()
            # Normalize gcs_uri from item_gs_uri if present
            if not item.get("gcs_uri") and item.get("item_gs_uri"):
                item["gcs_uri"] = item["item_gs_uri"]
            items.append(item)
        return items

    def increment_wear_count(
        self, 
        user_id: str, 
        item_id: str, 
        worn_date: Optional[str] = None,
        auth_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Increments wear count and updates last_worn_date for an existing item.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        now_str = worn_date or time.strftime("%Y-%m-%d")
        item = self.get_item(user_id, item_id, auth_user_id)
        if not item:
            raise ValueError(f"Garment item '{item_id}' not found for user '{user_id}'.")

        item["wear_count"] = item.get("wear_count", 0) + 1
        item["last_worn_date"] = now_str
        item["updated_at"] = time.time()

        return self.save_item(user_id, item, auth_user_id)

    def log_wear_event(
        self,
        user_id: str,
        item_id: str,
        outfit_id: Optional[str] = None,
        worn_date: Optional[str] = None,
        auth_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records a discrete wear log event for analytics tracking.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        log_id = f"log_{uuid.uuid4().hex[:12]}"
        now_str = worn_date or time.strftime("%Y-%m-%d")
        
        wear_log = {
            "wear_log_id": log_id,
            "user_id": user_id,
            "item_id": item_id,
            "outfit_id": outfit_id,
            "worn_date": now_str,
            "timestamp": time.time()
        }

        if self._use_mock:
            self._ensure_user_store(user_id)
            self._mock_db[user_id][FIRESTORE_WEAR_LOGS_SUBCOLLECTION][log_id] = wear_log
        else:
            (
                self._db.collection(FIRESTORE_USERS_COLLECTION)
                .document(user_id)
                .collection(FIRESTORE_WEAR_LOGS_SUBCOLLECTION)
                .document(log_id)
                .set(wear_log)
            )

        return wear_log

    def save_outfit(
        self,
        user_id: str,
        outfit_data: Dict[str, Any],
        auth_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Saves a synthesized or worn outfit record.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        outfit_id = outfit_data.get("outfit_id") or f"outfit_{uuid.uuid4().hex[:12]}"
        record = {
            **outfit_data,
            "outfit_id": outfit_id,
            "user_id": user_id,
            "created_at": outfit_data.get("created_at", time.time())
        }

        if self._use_mock:
            self._ensure_user_store(user_id)
            self._mock_db[user_id][FIRESTORE_OUTFITS_SUBCOLLECTION][outfit_id] = record
        else:
            (
                self._db.collection(FIRESTORE_USERS_COLLECTION)
                .document(user_id)
                .collection(FIRESTORE_OUTFITS_SUBCOLLECTION)
                .document(outfit_id)
                .set(record)
            )

        return record


# Global singleton instance
_FIRESTORE_CLIENT_INSTANCE: Optional[FirestoreWardrobeClient] = None

def get_firestore_client(force_mock: bool = False) -> FirestoreWardrobeClient:
    global _FIRESTORE_CLIENT_INSTANCE
    if _FIRESTORE_CLIENT_INSTANCE is None:
        _FIRESTORE_CLIENT_INSTANCE = FirestoreWardrobeClient(use_mock=force_mock)
    return _FIRESTORE_CLIENT_INSTANCE
