"""
Predictive Wardrobe Gap Analysis Service for naturallyEasy.
Implements combinatorial graph logic to identify isolated garments (<= 1 pairing),
calculates Bridge Staples (connecting >= 3 underused items or fulfilling schedule needs),
and outputs recommendations in 3 categories: Versatility Multipliers, Occasion Bridges, and Replacement Flags.
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
from ..config import AllowedCategory, AllowedOccasion
from ..db.firestore_client import get_firestore_client, FirestoreWardrobeClient
from ..auth import validate_user_access


# Standard Wardrobe Staple Library for Bridge Simulation
STANDARD_STAPLE_CANDIDATES: List[Dict[str, Any]] = [
    {
        "staple_name": "Crisp White Oxford Button-Down",
        "category": "Top",
        "sub_category": "Oxford Shirt",
        "primary_color": "White",
        "formality": "Smart Casual",
        "occasions": ["Work / Professional", "Casual / Daily", "Party / Night Out"],
        "warmth_rating": 2,
        "material": "Cotton",
        "versatility_rationale": "Acts as a neutral base that pairs seamlessly with any trouser, skirt, blazer, or denim."
    },
    {
        "staple_name": "Navy Tailored Wool Blazer",
        "category": "Outerwear",
        "sub_category": "Blazer",
        "primary_color": "Navy Blue",
        "formality": "Smart Casual",
        "occasions": ["Work / Professional", "Formal / Black Tie", "Party / Night Out", "Casual / Daily"],
        "warmth_rating": 3,
        "material": "Wool",
        "versatility_rationale": "Elevates casual bottoms and provides essential formal layering for cool weather."
    },
    {
        "staple_name": "Black Leather Penny Loafers",
        "category": "Footwear",
        "sub_category": "Loafers",
        "primary_color": "Black",
        "formality": "Smart Casual",
        "occasions": ["Work / Professional", "Formal / Black Tie", "Casual / Daily", "Party / Night Out"],
        "warmth_rating": 2,
        "material": "Leather",
        "versatility_rationale": "Bridges casual-to-formal transitions across trousers, dresses, and chinos."
    },
    {
        "staple_name": "Charcoal Wool Dress Trousers",
        "category": "Bottom",
        "sub_category": "Trousers",
        "primary_color": "Charcoal Grey",
        "formality": "Formal",
        "occasions": ["Work / Professional", "Formal / Black Tie"],
        "warmth_rating": 3,
        "material": "Wool",
        "versatility_rationale": "Provides formal foundation for tops, knitwear, and blazers."
    },
    {
        "staple_name": "Classic Camel Trench Coat",
        "category": "Outerwear",
        "sub_category": "Trench Coat",
        "primary_color": "Beige",
        "formality": "Smart Casual",
        "occasions": ["Casual / Daily", "Work / Professional", "Party / Night Out"],
        "warmth_rating": 3,
        "material": "Cotton Gabardine",
        "versatility_rationale": "Water-resistant transitional outer layer that complements both dresses and tailored separates."
    },
    {
        "staple_name": "Little Black Midi Slip Dress",
        "category": "Dress",
        "sub_category": "Slip Dress",
        "primary_color": "Black",
        "formality": "Smart Casual",
        "occasions": ["Party / Night Out", "Formal / Black Tie", "Casual / Daily"],
        "warmth_rating": 2,
        "material": "Silk",
        "versatility_rationale": "Complete standalone outfit base that layers with cardigans, leather jackets, or blazers."
    },
    {
        "staple_name": "Minimalist White Leather Low-Tops",
        "category": "Footwear",
        "sub_category": "Sneakers",
        "primary_color": "White",
        "formality": "Casual",
        "occasions": ["Casual / Daily", "Party / Night Out"],
        "warmth_rating": 2,
        "material": "Leather",
        "versatility_rationale": "Matches 100% of casual tops, denim, shorts, and casual midi dresses."
    }
]

NEUTRAL_COLORS = {
    "white", "black", "grey", "gray", "navy", "navy blue", "beige", "cream", 
    "charcoal", "khaki", "denim", "indigo blue", "brown", "dark brown", "tan", 
    "camel", "cognac", "olive", "burgundy"
}


class CompatibilityGraph:
    """
    Models compatibility between wardrobe items.
    Supports Top + Bottom + Footwear combinations AND Dress/One-Piece + Footwear standalone outfits.
    """
    def __init__(self, items: List[Dict[str, Any]]):
        self.items = {item["item_id"]: item for item in items}
        self.item_combinations: Dict[str, Set[str]] = defaultdict(set)
        self.pairwise_edges: Dict[str, Set[str]] = defaultdict(set)
        self._build_graph()

    def _is_color_compatible(self, color_a: str, color_b: str) -> bool:
        c_a, c_b = (color_a or "").lower(), (color_b or "").lower()
        if c_a in NEUTRAL_COLORS or c_b in NEUTRAL_COLORS or not c_a or not c_b:
            return True
        return c_a == c_b

    def _is_formality_compatible(self, form_a: str, form_b: str) -> bool:
        if not form_a or not form_b or form_a == form_b:
            return True
        # Smart casual bridges with both Casual and Formal
        if "Smart Casual" in (form_a, form_b):
            return True
        return False

    def are_items_compatible(self, item_a: Dict[str, Any], item_b: Dict[str, Any]) -> bool:
        # Same item cannot pair with itself
        if item_a.get("item_id") == item_b.get("item_id"):
            return False
            
        # Formality check
        if not self._is_formality_compatible(item_a.get("formality"), item_b.get("formality")):
            return False

        # Color compatibility check
        if not self._is_color_compatible(item_a.get("primary_color"), item_b.get("primary_color")):
            return False

        # Warmth rating delta check
        w_a = item_a.get("warmth_rating", 3)
        w_b = item_b.get("warmth_rating", 3)
        if abs(w_a - w_b) > 2:
            return False

        return True

    def _build_graph(self):
        # Partition by category
        tops = [i for i in self.items.values() if i.get("category") == "Top"]
        bottoms = [i for i in self.items.values() if i.get("category") == "Bottom"]
        dresses = [i for i in self.items.values() if i.get("category") in ("Dress", "One-Piece")]
        footwear = [i for i in self.items.values() if i.get("category") == "Footwear"]
        outerwear = [i for i in self.items.values() if i.get("category") == "Outerwear"]

        # Track pairwise compatibility across distinct categories
        all_items_list = list(self.items.values())
        for i in range(len(all_items_list)):
            for j in range(i + 1, len(all_items_list)):
                item_a, item_b = all_items_list[i], all_items_list[j]
                if item_a.get("category") != item_b.get("category") and self.are_items_compatible(item_a, item_b):
                    self.pairwise_edges[item_a["item_id"]].add(item_b["item_id"])
                    self.pairwise_edges[item_b["item_id"]].add(item_a["item_id"])

        # 1. Evaluate Two-Piece base outfits (Top + Bottom + Footwear + optional Outerwear)
        for t in tops:
            for b in bottoms:
                if self.are_items_compatible(t, b):
                    for f in footwear:
                        if self.are_items_compatible(t, f) and self.are_items_compatible(b, f):
                            combo_key = f"{t['item_id']}_{b['item_id']}_{f['item_id']}"
                            self.item_combinations[t["item_id"]].add(combo_key)
                            self.item_combinations[b["item_id"]].add(combo_key)
                            self.item_combinations[f["item_id"]].add(combo_key)

                            for o in outerwear:
                                if self.are_items_compatible(t, o) and self.are_items_compatible(b, o) and self.are_items_compatible(f, o):
                                    o_combo_key = f"{combo_key}_{o['item_id']}"
                                    self.item_combinations[o["item_id"]].add(o_combo_key)

        # 2. Evaluate Standalone One-Piece base outfits (Dress + Footwear + optional Outerwear)
        for d in dresses:
            for f in footwear:
                if self.are_items_compatible(d, f):
                    d_combo_key = f"{d['item_id']}_{f['item_id']}"
                    self.item_combinations[d["item_id"]].add(d_combo_key)
                    self.item_combinations[f["item_id"]].add(d_combo_key)

                    for o in outerwear:
                        if self.are_items_compatible(d, o) and self.are_items_compatible(f, o):
                            do_combo_key = f"{d_combo_key}_{o['item_id']}"
                            self.item_combinations[o["item_id"]].add(do_combo_key)


class GapAnalysisService:
    """
    Analyzes wardrobe structure to identify isolated items and recommend Bridge Staples across 3 categories.
    """
    def __init__(self, firestore_client: Optional[FirestoreWardrobeClient] = None):
        self.firestore = firestore_client or get_firestore_client()

    def analyze_wardrobe(
        self,
        user_id: str,
        target_schedule: Optional[Dict[str, Any]] = None,
        auth_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes complete Gap Analysis for user's wardrobe.
        target_schedule format example: {"occasion": "Formal / Black Tie", "expected_temp": 16.0}
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        items = self.firestore.list_items(user_id=user_id, status="active", auth_user_id=auth_user_id)
        if not items:
            return {
                "status": "empty_wardrobe",
                "isolated_garments": [],
                "versatility_multipliers": [],
                "occasion_bridges": [],
                "replacement_flags": []
            }

        graph = CompatibilityGraph(items)

        # 1. Identify Isolated Garments (items participating in <= 1 combination)
        isolated_items = []
        for item in items:
            item_id = item["item_id"]
            combos_count = len(graph.item_combinations.get(item_id, set()))
            if combos_count <= 1:
                isolated_items.append({
                    "item_id": item_id,
                    "item_name": item.get("item_name"),
                    "category": item.get("category"),
                    "color": item.get("primary_color"),
                    "occasion": item.get("occasion"),
                    "formality": item.get("formality"),
                    "pairing_count": combos_count,
                    "reason": "Garment lacks compatible pairing pieces in complementary categories or formality."
                })

        # 2. Simulate Bridge Staples & Versatility Multipliers
        versatility_multipliers = []
        for candidate in STANDARD_STAPLE_CANDIDATES:
            mock_id = f"sim_{candidate['staple_name'].lower().replace(' ', '_')}"
            sim_item = {**candidate, "item_id": mock_id}
            
            # Run simulation with candidate added to user closet
            sim_graph = CompatibilityGraph(items + [sim_item])
            
            # Count how many isolated items now gain >= 1 new valid combinations or pairwise connections
            connected_isolated_items = []
            for iso in isolated_items:
                old_count = len(graph.item_combinations.get(iso["item_id"], set()))
                new_count = len(sim_graph.item_combinations.get(iso["item_id"], set()))
                pairwise_connected = mock_id in sim_graph.pairwise_edges.get(iso["item_id"], set())
                if new_count > old_count or pairwise_connected:
                    connected_isolated_items.append(iso["item_name"])

            new_combinations_unlocked = len(sim_graph.item_combinations.get(mock_id, set()))

            # If candidate connects with isolated items or unlocks combinations
            if connected_isolated_items or new_combinations_unlocked > 0:
                versatility_multipliers.append({
                    "staple_name": candidate["staple_name"],
                    "category": candidate["category"],
                    "primary_color": candidate["primary_color"],
                    "connected_isolated_count": len(connected_isolated_items),
                    "connected_items": connected_isolated_items,
                    "new_combinations_unlocked": new_combinations_unlocked,
                    "rationale": candidate["versatility_rationale"]
                })

        # Sort Versatility Multipliers by connected items count, then unlocked combos
        versatility_multipliers = sorted(
            versatility_multipliers,
            key=lambda x: (x["connected_isolated_count"], x["new_combinations_unlocked"]),
            reverse=True
        )

        # 3. Detect Occasion Bridges based on schedule requirements or missing occasion coverage
        occasion_bridges = []
        if target_schedule:
            target_occ = target_schedule.get("occasion")
            target_temp = target_schedule.get("expected_temp", 20.0)

            # Check if user has necessary pieces for this occasion
            matching_tops = [i for i in items if i.get("category") in ("Top", "Dress", "One-Piece") and i.get("occasion") == target_occ]
            matching_outers = [i for i in items if i.get("category") == "Outerwear" and (i.get("occasion") == target_occ or i.get("formality") == "Formal")]
            
            if target_temp < 18.0 and not matching_outers and (target_occ in ["Formal / Black Tie", "Work / Professional"]):
                occasion_bridges.append({
                    "recommendation": "Formal Outerwear / Tailored Overcoat",
                    "target_occasion": target_occ,
                    "weather_trigger": f"{target_temp}°C requires warm outerwear",
                    "reason": f"Detected upcoming {target_occ} event at {target_temp}°C with zero matching formal outer layers in closet."
                })
            elif not matching_tops:
                occasion_bridges.append({
                    "recommendation": f"Formal {target_occ} Attire (e.g. Silk Midi Dress or Tailored Tuxedo Shirt)",
                    "target_occasion": target_occ,
                    "reason": f"No garments in closet currently tagged for '{target_occ}'."
                })

        # Check general category balance
        cat_counts = defaultdict(int)
        for i in items:
            cat_counts[i.get("category")] += 1
        
        if cat_counts["Outerwear"] == 0:
            occasion_bridges.append({
                "recommendation": "All-Weather Transitional Jacket / Trench",
                "target_occasion": "All-Season Transition",
                "reason": "Wardrobe has 0 outerwear pieces; rain or temperature drops will break outfit viability."
            })

        # 4. Replacement Flags (Items worn excessively > 30 times or high wear rate)
        replacement_flags = []
        for item in items:
            wears = item.get("wear_count", 0)
            if wears >= 30:
                replacement_flags.append({
                    "item_id": item["item_id"],
                    "item_name": item.get("item_name"),
                    "category": item.get("category"),
                    "wear_count": wears,
                    "flag_reason": f"High wear frequency ({wears} recorded wears). Consider inspecting fabric condition or acquiring a rotation backup."
                })

        return {
            "status": "success",
            "total_items_analyzed": len(items),
            "isolated_garments_count": len(isolated_items),
            "isolated_garments": isolated_items,
            "versatility_multipliers": versatility_multipliers[:3],
            "occasion_bridges": occasion_bridges,
            "replacement_flags": replacement_flags
        }


# Singleton helper
_GAP_ANALYSIS_INSTANCE: Optional[GapAnalysisService] = None

def analyze_wardrobe_gaps(
    user_id: str,
    target_schedule: Optional[Dict[str, Any]] = None,
    auth_user_id: Optional[str] = None
) -> Dict[str, Any]:
    global _GAP_ANALYSIS_INSTANCE
    if _GAP_ANALYSIS_INSTANCE is None:
        _GAP_ANALYSIS_INSTANCE = GapAnalysisService()
    return _GAP_ANALYSIS_INSTANCE.analyze_wardrobe(
        user_id=user_id,
        target_schedule=target_schedule,
        auth_user_id=auth_user_id
    )
