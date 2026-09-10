import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from ..config import DEFAULT_GEMINI_MODEL, get_genai_client

# Try importing Google GenAI
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class OutfitOption(BaseModel):
    title: str = Field(description="Outfit style title e.g. Minimalist Business Casual, Relaxed Weekend Layering")
    base_structure: str = Field(description="'Two-Piece' (Top + Bottom) or 'One-Piece' (Dress / Jumpsuit)")
    selected_items: List[Dict[str, Any]] = Field(description="List of items in this outfit (Top, Bottom, Dress, Footwear, Outerwear, Accessories)")
    styling_explanation: str = Field(description="Why this outfit works for the given weather and occasion")
    weather_compatibility: str = Field(description="How it handles the forecast temperature and rain risk")


class OutfitSynthesisResponse(BaseModel):
    weather_context_applied: str = Field(description="Summary of weather constraints incorporated")
    target_occasion: str = Field(description="Occasion designed for")
    outfit_options: List[OutfitOption] = Field(description="2-3 layered outfit options")
    bridge_staple_recommendation: Optional[str] = Field(
        default=None,
        description="1 high-utility missing staple that would unlock more combinations"
    )


# ---------------------------------------------------------------------------
# LLM-facing schema: Gemini is asked for item_id REFERENCES in named,
# single-valued slots (one field per category) rather than a flat list.
# This is a structural fix, not a post-hoc filter: a schema with one
# "top_id" field makes "two Tops in one outfit" something the model can't
# even express, instead of something we have to detect and strip out
# afterward. A flat List[Dict[str, Any]] gave structured output nothing to
# constrain against, so Gemini would free-form/truncate/duplicate items;
# a flat List[str] of ids was better but still let it pick the same
# category twice. Named scalar slots are what it can fill most reliably.
# The real item records are re-attached server-side by id afterward.
# ---------------------------------------------------------------------------
class _OutfitOptionRef(BaseModel):
    title: str = Field(description="Outfit style title e.g. Minimalist Business Casual, Relaxed Weekend Layering")
    base_structure: str = Field(description="'Two-Piece' (Top + Bottom) or 'One-Piece' (Dress / Jumpsuit)")
    top_id: Optional[str] = Field(default=None, description="item_id of the Top. Only set when base_structure is 'Two-Piece'; leave null otherwise.")
    bottom_id: Optional[str] = Field(default=None, description="item_id of the Bottom. Only set when base_structure is 'Two-Piece'; leave null otherwise.")
    dress_id: Optional[str] = Field(default=None, description="item_id of the Dress / One-Piece. Only set when base_structure is 'One-Piece'; leave null otherwise.")
    footwear_id: str = Field(description="item_id of the Footwear. Every outfit must include exactly one.")
    outerwear_id: Optional[str] = Field(default=None, description="item_id of an Outerwear piece, if the outfit includes one.")
    accessory_ids: List[str] = Field(default_factory=list, description="item_ids of any Accessories included (e.g. belt, necklace). Can be empty or have several.")
    styling_explanation: str = Field(description="Why this outfit works for the given weather and occasion")
    weather_compatibility: str = Field(description="How it handles the forecast temperature and rain risk")


class _OutfitSynthesisResponseRef(BaseModel):
    weather_context_applied: str = Field(description="Summary of weather constraints incorporated")
    target_occasion: str = Field(description="Occasion designed for")
    outfit_options: List[_OutfitOptionRef] = Field(description="2-3 layered outfit options")
    bridge_staple_recommendation: Optional[str] = Field(
        default=None,
        description="1 high-utility missing staple that would unlock more combinations"
    )


def synthesize_outfits(
    inventory_data: list,
    weather_context: str = "Mild 20°C, Clear",
    occasion: str = "Casual / Daily",
    user_prompt: str = ""
) -> dict:
    """
    Analyzes digitized wardrobe inventory against weather and occasion context
    to generate 2-3 complete layered outfit options (including Dress / One-Piece full outfits).
    """
    system_instruction = (
        "You are Rack Raider, an expert personal fashion stylist and wardrobe optimizer. "
        "Design 2-3 complete layered outfits strictly using items present in the user's wardrobe inventory. "
        "A complete outfit consists of either: "
        "1. Top + Bottom + Footwear (+ optional Outerwear / Accessories) — set base_structure='Two-Piece', "
        "fill top_id and bottom_id, leave dress_id null. "
        "2. Dress / One-Piece + Footwear (+ optional Outerwear / Accessories) — set base_structure='One-Piece', "
        "fill dress_id, leave top_id and bottom_id null. "
        "Every outfit needs exactly one footwear_id. Use outerwear_id only if you're including a layer. "
        "accessory_ids may include zero or more DISTINCT accessories — never repeat the same item_id. "
        "DEFAULT OCCASION is only a fallback baseline — it's what to use when the user hasn't described "
        "anything more specific. If USER'S SPECIFIC CONTEXT describes a particular event, setting, or "
        "dress code (e.g. 'presentation at work', 'black tie wedding', 'gym session'), that description "
        "OVERRIDES the default: infer the correct occasion and formality from it even if that contradicts "
        "the default (e.g. a 'Casual / Daily' default plus 'presentation at work' should upgrade the "
        "outfit toward Work / Professional, Smart Casual or Formal — not stay casual). Set 'target_occasion' "
        "in your response to whichever occasion actually governed your choices, default or overridden. "
        "Weather is context but not a constraint — focus on versatile, occasion-appropriate pieces. "
        "For every *_id field, copy the exact 'item_id' string of the chosen garment from the "
        "WARDROBE INVENTORY below — do not invent garments, ids, or modify the id text. "
        "Keep 'styling_explanation' to 1-2 sentences maximum. "
        "Keep 'weather_compatibility' to a single brief phrase. "
        "Identify 1 high-utility bridge staple recommendation if a wardrobe gap is apparent."
    )

    prompt = f"""
    WARDROBE INVENTORY: {json.dumps(inventory_data)}
    DEFAULT OCCASION & DRESS CODE (fallback baseline only): {occasion}
    WEATHER CONTEXT: {weather_context}
    USER'S SPECIFIC CONTEXT / REQUEST (overrides the default occasion above if it describes something more specific): {user_prompt}
    """

    if GENAI_AVAILABLE and inventory_data:
        try:
            client = get_genai_client()
            if not client:
                raise RuntimeError("Could not initialize GenAI client.")
            response = client.models.generate_content(
                model=DEFAULT_GEMINI_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=_OutfitSynthesisResponseRef,
                    temperature=0.2
                )
            )
            ref_result = _OutfitSynthesisResponseRef.model_validate_json(response.text)
            return _hydrate_outfit_refs(ref_result, inventory_data)
        except Exception as e:
            print(f"[SynthesizeOutfits] Live Gemini generation failed: {e}. Falling back to rule synthesizer.")

    # Fallback heuristic synthesizer for offline / testing runs
    return _synthesize_outfits_heuristic(inventory_data, weather_context, occasion)


# Which real inventory category(ies) each named slot is allowed to hold. The
# named-slot schema stops Gemini from filling "top_id" twice, but nothing stops
# it from putting a second Top's item_id into an unrelated slot like
# outerwear_id — the frontend renders the item's REAL category (from the
# hydrated inventory record, not the slot name), so that would still show up
# as a second "TOP" card. Checking the slot against the item's actual category
# closes that loophole.
_SLOT_EXPECTED_CATEGORIES = {
    "dress_id": ("Dress", "One-Piece"),
    "top_id": ("Top",),
    "bottom_id": ("Bottom",),
    "footwear_id": ("Footwear",),
    "outerwear_id": ("Outerwear",),
}


def _resolve_outfit_slots(opt: "_OutfitOptionRef") -> List[tuple]:
    """
    Collapses the named per-category slots into an ordered (item_id, allowed_categories)
    list. The schema already makes "two Tops" structurally impossible (one top_id
    field), but Gemini can still fill both dress_id and top_id/bottom_id despite the
    prompt saying not to — dress_id wins in that case, since a Dress/One-Piece already
    is the base layer and pairing it with a separate Top isn't a real outfit.
    """
    slots: List[tuple] = []
    if opt.dress_id:
        slots.append((opt.dress_id, _SLOT_EXPECTED_CATEGORIES["dress_id"]))
    else:
        if opt.top_id:
            slots.append((opt.top_id, _SLOT_EXPECTED_CATEGORIES["top_id"]))
        if opt.bottom_id:
            slots.append((opt.bottom_id, _SLOT_EXPECTED_CATEGORIES["bottom_id"]))
    if opt.footwear_id:
        slots.append((opt.footwear_id, _SLOT_EXPECTED_CATEGORIES["footwear_id"]))
    if opt.outerwear_id:
        slots.append((opt.outerwear_id, _SLOT_EXPECTED_CATEGORIES["outerwear_id"]))
    for acc_id in opt.accessory_ids:
        slots.append((acc_id, ("Accessory",)))
    return slots


def _hydrate_outfit_refs(ref_result: "_OutfitSynthesisResponseRef", inventory_data: list) -> dict:
    """
    Converts Gemini's item_id references into the full item records the frontend
    expects (item_name, category, primary_color, gcs_uri, etc.), pulling each
    record straight from the real closet inventory rather than trusting the model
    to regenerate it. Any id Gemini invents, reuses across slots, or assigns to
    the wrong-category slot is silently dropped (better to omit a piece than
    render an "undefined" or mislabeled duplicate card).
    """
    by_id = {i.get("item_id"): i for i in inventory_data if i.get("item_id")}

    hydrated_options = []
    for opt in ref_result.outfit_options:
        seen_ids = set()
        selected_items = []
        for item_id, allowed_categories in _resolve_outfit_slots(opt):
            if item_id in seen_ids:
                continue
            item = by_id.get(item_id)
            if not item or item.get("category") not in allowed_categories:
                continue
            seen_ids.add(item_id)
            selected_items.append(item)
        if not selected_items:
            continue
        hydrated_options.append(OutfitOption(
            title=opt.title,
            base_structure=opt.base_structure,
            selected_items=selected_items,
            styling_explanation=opt.styling_explanation,
            weather_compatibility=opt.weather_compatibility
        ))

    if not hydrated_options:
        raise ValueError("Gemini returned no valid item_id references matching the inventory.")

    return OutfitSynthesisResponse(
        weather_context_applied=ref_result.weather_context_applied,
        target_occasion=ref_result.target_occasion,
        outfit_options=hydrated_options,
        bridge_staple_recommendation=ref_result.bridge_staple_recommendation
    ).model_dump()


def _synthesize_outfits_heuristic(inventory_data: list, weather_context: str, occasion: str) -> dict:
    """Deterministic rule-based outfit assembler for fallback (v2)."""
    tops = [i for i in inventory_data if i.get("category") == "Top"]
    bottoms = [i for i in inventory_data if i.get("category") == "Bottom"]
    dresses = [i for i in inventory_data if i.get("category") in ("Dress", "One-Piece")]
    footwear = [i for i in inventory_data if i.get("category") == "Footwear"]
    outerwear = [i for i in inventory_data if i.get("category") == "Outerwear"]

    default_shoes = footwear[0] if footwear else {
        "item_name": "White Leather Sneakers", "category": "Footwear", "primary_color": "White", "formality": "Casual"
    }

    outfit_options = []

    # Option 1: Top + Bottom
    if tops and bottoms:
        outfit_items = [tops[0], bottoms[0], default_shoes]
        if outerwear:
            outfit_items.append(outerwear[0])
        outfit_options.append(OutfitOption(
            title="Effortless Separates Ensemble",
            base_structure="Two-Piece",
            selected_items=outfit_items,
            styling_explanation=f"Clean coordination of {tops[0].get('item_name')} with {bottoms[0].get('item_name')}.",
            weather_compatibility=f"Comfortable for {weather_context}."
        ))

    # Option 2: Dress or Second Two-Piece
    if dresses:
        dress_items = [dresses[0], default_shoes]
        if outerwear:
            dress_items.append(outerwear[0])
        outfit_options.append(OutfitOption(
            title="Sleek One-Piece Silhouette",
            base_structure="One-Piece",
            selected_items=dress_items,
            styling_explanation=f"Standout single-piece styling with {dresses[0].get('item_name')} and complementary footwear.",
            weather_compatibility=f"Lightweight and breathable for {weather_context}."
        ))
    elif len(tops) > 1 and bottoms:
        alt_items = [tops[1], bottoms[0], default_shoes]
        outfit_options.append(OutfitOption(
            title="Alternative Daily Rotation",
            base_structure="Two-Piece",
            selected_items=alt_items,
            styling_explanation=f"Rotational option featuring {tops[1].get('item_name')}.",
            weather_compatibility=f"Aligned with {weather_context}."
        ))

    # Option 3: Layered Focus
    if outerwear and (tops or dresses):
        layer_items = [tops[0] if tops else dresses[0], bottoms[0] if tops and bottoms else default_shoes, default_shoes, outerwear[0]]
        outfit_options.append(OutfitOption(
            title="Smart Layered Transition",
            base_structure="Two-Piece" if tops else "One-Piece",
            selected_items=list({i.get("item_name", str(idx)): i for idx, i in enumerate(layer_items)}.values()),
            styling_explanation="Incorporates outerwear for adaptable temperature transitions throughout the day.",
            weather_compatibility=f"Ideal for fluctuating temperatures ({weather_context})."
        ))

    # Fallback: if no outfits created, generate synthetic defaults with proper structure
    if not outfit_options:
        default_top = tops[0] if tops else {
            "item_name": "Classic White Cotton Tee", "category": "Top", "primary_color": "White", "formality": "Casual"
        }
        default_bottom = bottoms[0] if bottoms else {
            "item_name": "Light Wash Denim Jeans", "category": "Bottom", "primary_color": "Blue", "formality": "Casual"
        }
        outfit_options = [
            OutfitOption(
                title="Essential Casual Combo",
                base_structure="Two-Piece",
                selected_items=[default_top, default_bottom, default_shoes],
                styling_explanation="Timeless pairing of casual essentials for everyday comfort and style.",
                weather_compatibility=weather_context
            )
        ]

    return OutfitSynthesisResponse(
        weather_context_applied=weather_context,
        target_occasion=occasion,
        outfit_options=outfit_options,
        bridge_staple_recommendation="Navy Tailored Wool Blazer"
    ).model_dump()
