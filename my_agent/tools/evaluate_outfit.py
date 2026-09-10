def evaluate_outfit_rules(
    selected_items: list[dict], 
    target_occasion: str = "Casual / Daily", 
    temperature_c: float = 20.0, 
    is_raining: bool = False
) -> dict:
    """
    Evaluates outfit feasibility against weather, occasion constraints, and category rules.
    Supports two-piece base outfits (Top + Bottom) AND standalone one-piece outfits (Dress or One-Piece).
    Returns a score (0-10) and targeted feedback for retry loops.
    """
    score = 10
    feedback = []

    categories_present = {item.get("category") for item in selected_items}
    
    # 1. Check Mandatory Base Outfit Structure
    has_two_piece_base = ("Top" in categories_present and "Bottom" in categories_present)
    has_one_piece_base = ("Dress" in categories_present or "One-Piece" in categories_present)

    if not (has_two_piece_base or has_one_piece_base):
        score -= 4
        feedback.append("Missing complete base outfit: requires either (Top + Bottom) OR a (Dress / One-Piece).")
    
    # Check Footwear
    if "Footwear" not in categories_present:
        score -= 3
        feedback.append("Missing footwear.")

    # 2. Temperature & Warmth Evaluation
    total_warmth = sum(item.get("warmth_rating", 2) for item in selected_items)
    if temperature_c < 10 and total_warmth < 6:
        score -= 3
        feedback.append(f"Outfit too cold for {temperature_c}°C. Add a warm outerwear layer or heavier knitwear.")
    elif temperature_c > 25 and total_warmth > 5:
        score -= 3
        feedback.append(f"Outfit too warm for {temperature_c}°C. Choose lighter, breathable pieces.")

    # 3. Rain Check
    if is_raining:
        has_protection = any(item.get("water_resistant", False) for item in selected_items)
        if not has_protection:
            score -= 2
            feedback.append("It is raining, but no water-resistant outerwear or footwear was included.")

    # 4. Formality Check
    for item in selected_items:
        item_formality = item.get("formality", "Casual")
        if target_occasion in ["Formal / Black Tie", "Work / Professional"]:
            if item_formality == "Casual" and target_occasion == "Formal / Black Tie":
                score -= 3
                feedback.append(f"Item '{item.get('item_name')}' is too casual for formal / black tie occasions.")

    status = "PASS" if score >= 8 else "FAIL"
    return {
        "status": status,
        "score": max(score, 0),
        "feedback": feedback,
        "is_valid": score >= 8
    }