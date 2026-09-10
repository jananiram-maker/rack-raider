"""
Circular Commerce Domain Logic for naturallyEasy.
Evaluates garment underutilization against seasonal weather windows and 14-day calendar schedules.
Generates targeted circular recommendations:
1. "Style It Differently": In-season, unworn in N days, >= 2 potential unused combinations.
2. "Move to Storage": Out of current season window, but utilized during active season.
3. "Consider Donating": In-season, unworn across >= 2 seasons (> 180 days), low combinability.
"""

import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ..db.firestore_client import get_firestore_client, FirestoreWardrobeClient
from .gap_analysis import CompatibilityGraph
from ..auth import validate_user_access


SEASONS_ORDER = ["Spring", "Summer", "Fall", "Winter"]

def get_current_season_from_date(dt: Optional[datetime] = None) -> str:
    """Returns the current meteorological season for the Northern Hemisphere."""
    now = dt or datetime.now()
    month = now.month
    if month in [3, 4, 5]:
        return "Spring"
    elif month in [6, 7, 8]:
        return "Summer"
    elif month in [9, 10, 11]:
        return "Fall"
    else:
        return "Winter"


class CircularCommerceService:
    """
    Evaluates closet items and generates actionable circular commerce triggers.
    """
    def __init__(self, firestore_client: Optional[FirestoreWardrobeClient] = None):
        self.firestore = firestore_client or get_firestore_client()

    def evaluate_closet(
        self,
        user_id: str,
        current_season: Optional[str] = None,
        days_unworn_threshold: int = 30,
        auth_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs circular domain rules across all items in the user's wardrobe.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        active_season = current_season or get_current_season_from_date()
        items = self.firestore.list_items(user_id=user_id, status="active", auth_user_id=auth_user_id)
        
        if not items:
            return {
                "status": "empty",
                "active_season": active_season,
                "style_it_differently": [],
                "move_to_storage": [],
                "consider_donating": []
            }

        graph = CompatibilityGraph(items)
        now_dt = datetime.now()

        style_it_differently = []
        move_to_storage = []
        consider_donating = []

        for item in items:
            item_id = item["item_id"]
            season_tag = item.get("season_tag") or item.get("season") or "All-Season"
            wear_count = item.get("wear_count", 0)
            last_worn_str = item.get("last_worn_date")
            combos_count = len(graph.item_combinations.get(item_id, set()))

            # Calculate days since last worn
            days_since_last_worn = 999
            if last_worn_str:
                try:
                    last_worn_dt = datetime.strptime(last_worn_str, "%Y-%m-%d")
                    days_since_last_worn = (now_dt - last_worn_dt).days
                except Exception:
                    days_since_last_worn = 60

            is_in_season = (active_season in season_tag) or (season_tag == "All-Season")

            # -------------------------------------------------------------------
            # RULE 1: "Move to Storage"
            # Out of current season window, but has been utilized previously
            # -------------------------------------------------------------------
            if not is_in_season and season_tag != "All-Season":
                if wear_count >= 1 or days_since_last_worn < 240:
                    move_to_storage.append({
                        "item_id": item_id,
                        "item_name": item.get("item_name"),
                        "category": item.get("category"),
                        "season_tag": season_tag,
                        "action": "Move to Storage",
                        "reason": f"Garment is designed for {season_tag}. Storing it frees up visual closet space for {active_season}."
                    })
                    continue

            # -------------------------------------------------------------------
            # RULE 2: "Consider Donating"
            # In-season, unworn for > 180 days (or >= 2 seasons) and low combinability (<= 1)
            # -------------------------------------------------------------------
            if is_in_season:
                if (days_since_last_worn > 180 or wear_count == 0) and combos_count <= 1:
                    consider_donating.append({
                        "item_id": item_id,
                        "item_name": item.get("item_name"),
                        "category": item.get("category"),
                        "days_unworn": days_since_last_worn,
                        "wear_count": wear_count,
                        "action": "Consider Donating",
                        "reason": f"In-season for {active_season} but unworn for >180 days with only {combos_count} styling combination. High candidate for resale or donation."
                    })
                    continue

            # -------------------------------------------------------------------
            # RULE 3: "Style It Differently"
            # In-season, unworn in N days (> 30), and has >= 2 potential unused combinations
            # -------------------------------------------------------------------
            if is_in_season and days_since_last_worn >= days_unworn_threshold and combos_count >= 2:
                style_it_differently.append({
                    "item_id": item_id,
                    "item_name": item.get("item_name"),
                    "category": item.get("category"),
                    "days_unworn": days_since_last_worn,
                    "available_combinations_count": combos_count,
                    "action": "Style It Differently",
                    "suggestion": f"This in-season piece has {combos_count} untapped pairings. Try pairing with complementary neutrals this week."
                })

        return {
            "status": "success",
            "active_season": active_season,
            "evaluated_items_count": len(items),
            "style_it_differently": style_it_differently,
            "move_to_storage": move_to_storage,
            "consider_donating": consider_donating
        }


_CIRCULAR_SERVICE_INSTANCE: Optional[CircularCommerceService] = None

def evaluate_circular_actions(
    user_id: str,
    current_season: Optional[str] = None,
    days_unworn_threshold: int = 30,
    auth_user_id: Optional[str] = None
) -> Dict[str, Any]:
    global _CIRCULAR_SERVICE_INSTANCE
    if _CIRCULAR_SERVICE_INSTANCE is None:
        _CIRCULAR_SERVICE_INSTANCE = CircularCommerceService()
    return _CIRCULAR_SERVICE_INSTANCE.evaluate_closet(
        user_id=user_id,
        current_season=current_season,
        days_unworn_threshold=days_unworn_threshold,
        auth_user_id=auth_user_id
    )
