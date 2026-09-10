import json
from typing import List, Optional, Dict, Any
from ..config import GCS_BUCKET_NAME
from ..db.firestore_client import get_firestore_client
from ..auth import validate_user_access

# Try importing storage
try:
    from google.cloud import storage
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False


def fetch_wardrobe_inventory(
    categories: list[str], 
    occasion: Optional[str] = None, 
    min_warmth: int = 1, 
    max_warmth: int = 5,
    user_id: str = "user0001",
    auth_user_id: Optional[str] = None,
    bucket_name: str = GCS_BUCKET_NAME
) -> dict:
    """
    Fetches candidate clothing items filtering by category, occasion, and warmth level.
    Queries user's live isolated Firestore inventory first, falling back to GCS if needed.
    
    Args:
        categories: List of categories to fetch, e.g. ["Top", "Bottom", "Dress", "Footwear", "Outerwear"]
        occasion: Target occasion e.g. "Work / Professional", "Casual / Daily"
        min_warmth: Minimum warmth rating (1-5)
        max_warmth: Maximum warmth rating (1-5)
        user_id: The target user's isolated wardrobe identifier
    """
    if auth_user_id:
        validate_user_access(auth_user_id, user_id)

    # 1. Primary Source: Live Isolated Firestore Database
    firestore = get_firestore_client()
    firestore_items = firestore.list_items(user_id=user_id, status="active", auth_user_id=auth_user_id)

    if firestore_items:
        items = []
        for item in firestore_items:
            cat = item.get("category")
            if cat not in categories:
                continue
            warmth = item.get("warmth_rating", 3)
            if not (min_warmth <= warmth <= max_warmth):
                continue
            if occasion and item.get("occasion") != occasion and item.get("occasion") != "Casual / Daily":
                continue
            items.append(item)
        return {"status": "success", "count": len(items), "source": "firestore", "filtered_items": items}

    # 2. Secondary Fallback Source: GCS Bucket
    items = []
    if STORAGE_AVAILABLE:
        try:
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            index_blob = bucket.blob("wardrobe_index.json")
            
            if index_blob.exists():
                inventory = json.loads(index_blob.download_as_text())
                for item in inventory:
                    if item.get("category") not in categories:
                        continue
                    warmth = item.get("warmth_rating", 3)
                    if not (min_warmth <= warmth <= max_warmth):
                        continue
                    if occasion and item.get("occasion") != occasion and item.get("occasion") != "Casual / Daily":
                        continue
                    items.append(item)
            else:
                blobs = client.list_blobs(bucket_name)
                for blob in blobs:
                    if not blob.metadata:
                        continue
                    cat = blob.metadata.get("category", "").replace('"', '')
                    if cat in categories:
                        items.append({
                            "gcs_uri": f"gs://{bucket_name}/{blob.name}",
                            "item_name": blob.metadata.get("item_name", "").replace('"', ''),
                            "category": cat,
                            "primary_color": blob.metadata.get("primary_color", "").replace('"', ''),
                            "formality": blob.metadata.get("formality", "").replace('"', ''),
                            "occasion": blob.metadata.get("occasion", "").replace('"', ''),
                            "warmth_rating": int(blob.metadata.get("warmth_rating", 3)),
                            "water_resistant": blob.metadata.get("water_resistant") == "true"
                        })
        except Exception as e:
            print(f"[FetchWardrobe] GCS query skipped ({e}).")

    return {"status": "success", "count": len(items), "source": "gcs_fallback", "filtered_items": items}