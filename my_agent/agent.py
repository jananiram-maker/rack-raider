"""
Rack Raider AI Wardrobe Assistant Agent Definitions & Web Application Server.
Consolidated Primary Orchestrator Agent with Latency-Optimized Tool Calling, Sub-Agent Delegation,
and Full Interactive REST & Web UI Endpoints.
"""

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .config import DEFAULT_GEMINI_MODEL, get_genai_client, get_firebase_auth
from .prompt import orchestrator_agent_instruction
from .tools.evaluate_outfit import evaluate_outfit_rules
from .tools.fetch_wardrobe import fetch_wardrobe_inventory
from .tools.garment_tagger import generate_garment_tags
from .tools.image_uploader import upload_image_to_gcs
from .tools.storage_tool import save_garment_metadata
from .tools.synthesize_outfits import synthesize_outfits
from .tools.weather_tool import tool_get_weather_summary
from .tools.ingestion_tool import tool_parse_garment_image
from .tools.gap_analysis_tool import tool_predictive_gap_analysis
from .tools.circular_tool import tool_evaluate_circular_action
from .services.ingestion_service import parse_and_deduplicate_outfit_image
from .services.weather_service import get_weather_summary
from .services.gap_analysis import analyze_wardrobe_gaps
from .services.circular_commerce import evaluate_circular_actions
from .db.firestore_client import get_firestore_client
from .db.sync_service import SyncService

# Try importing ADK agent classes
try:
    from google.adk.agents import LlmAgent
    from google.adk.models import Gemini
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False

    # Mock lightweight agent class for non-ADK runtimes / tests
    class Gemini:
        def __init__(self, model: str):
            self.model = model

    class LlmAgent:
        def __init__(self, name: str, model: Any, description: str, instruction: str, tools: list = None, sub_agents: list = None):
            self.name = name
            self.model = model
            self.description = description
            self.instruction = instruction
            self.tools = tools or []
            self.sub_agents = sub_agents or []


# ---------------------------------------------------------------------------
# Consolidated Primary Orchestrator Agent
# ---------------------------------------------------------------------------
orchestrator_agent = LlmAgent(
    name="RackRaider_Orchestrator",
    model=Gemini(model=DEFAULT_GEMINI_MODEL),
    description=(
        "AI Wardrobe Assistant handling outfit recommendations, image ingestion & tagging, "
        "wardrobe management, weather integration, gap analysis, and circular commerce."
    ),
    instruction=orchestrator_agent_instruction,
    tools=[
        tool_parse_garment_image,
        upload_image_to_gcs,
        generate_garment_tags,
        save_garment_metadata,
        tool_get_weather_summary,
        fetch_wardrobe_inventory,
        synthesize_outfits,
        evaluate_outfit_rules,
        tool_predictive_gap_analysis,
        tool_evaluate_circular_action
    ],
)

# Root agent export for ADK runtime discovery
root_agent = orchestrator_agent

# ---------------------------------------------------------------------------
# 4. Request / Response Schemas for Web API
# ---------------------------------------------------------------------------
class IngestionRequest(BaseModel):
    user_id: str = "user0001"
    image_data: str = Field(..., description="Base64 data URL, GCS URI ('gs://...'), web URL, or local path")
    worn_date: Optional[str] = None

class WeatherRequest(BaseModel):
    city: str = "San Francisco"
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class OutfitSynthesisRequest(BaseModel):
    user_id: str = "user0001"
    city: str = "San Francisco"
    occasion: str = "Casual / Daily"
    weather_context: Optional[str] = None
    user_prompt: str = ""

class GapAnalysisRequest(BaseModel):
    user_id: str = "user0001"
    target_occasion: str = "Casual / Daily"

class CircularActionRequest(BaseModel):
    user_id: str = "user0001"
    current_season: str = "Summer"

class ItemCreateRequest(BaseModel):
    user_id: str = "user0001"
    item_name: str
    category: str
    sub_category: Optional[str] = "General"
    primary_color: str
    material: Optional[str] = "Cotton"
    pattern: Optional[str] = "Solid"
    formality: Optional[str] = "Casual"
    occasion: Optional[str] = "Casual / Daily"
    season_tag: Optional[str] = "All-Season"
    wear_frequency_expectation: Optional[str] = "Weekly"
    warmth_rating: Optional[int] = 3
    gcs_uri: Optional[str] = ""

class ItemUpdateRequest(BaseModel):
    status: Optional[str] = None
    wear_count: Optional[int] = None
    increment_wear: Optional[bool] = False
    worn_date: Optional[str] = None

class ChatRequest(BaseModel):
    user_id: str = "user0001"
    message: str
    occasion: Optional[str] = "Casual / Daily"
    city: Optional[str] = "San Francisco"
    history: Optional[List[Dict[str, Any]]] = None  # [{role, text}, ...] from the frontend

# ---------------------------------------------------------------------------
# 5. FastAPI Web Server & Full REST / SPA Endpoints
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from fastapi import HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Rack Raider",
        description="Mix your fits. — AI Wardrobe Assistant & Personal Stylist API",
        version="2.0.0",
    )

    # CORS middleware for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize sync service for BigQuery
    sync_service = SyncService()

    # -----------------------------------------------------------------------
    # Current-user resolution — the single seam authentication hooks into.
    # Every endpoint below calls this instead of trusting its raw user_id
    # parameter directly, and passes the result through as both the query
    # target and `auth_user_id` to the already access-controlled
    # services/db layer (firestore_client, circular_commerce, gap_analysis,
    # ingestion_service all already enforce validate_user_access() when
    # auth_user_id is provided).
    #
    # When Firebase Admin is configured (real ADC / service account
    # available), this REQUIRES and verifies a real
    # 'Authorization: Bearer <Firebase ID token>' header and returns the
    # verified uid — client_supplied_user_id is ignored in this mode, since
    # trusting it would let any caller impersonate any user.
    #
    # When Firebase Admin isn't configured (e.g. local dev without
    # credentials), falls back to trusting client_supplied_user_id exactly
    # like the Step 1 stub did, so local testing keeps working without a
    # real Firebase project set up — matching every other service in this
    # app's graceful-degradation pattern.
    # -----------------------------------------------------------------------
    _firebase_auth = get_firebase_auth()

    def get_current_user_id(request: Request, client_supplied_user_id: Optional[str] = None) -> str:
        if _firebase_auth is None:
            return client_supplied_user_id or "user0001"

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Authorization header. Sign in required.")

        token = auth_header[len("Bearer "):].strip()
        try:
            decoded = _firebase_auth.verify_id_token(token)
            return decoded["uid"]
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid or expired authentication token: {e}")

    # Static Directory Setup
    STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
    os.makedirs(STATIC_DIR, exist_ok=True)

    # -----------------------------------------------------------------------
    # Root & Health Check
    # -----------------------------------------------------------------------
    @app.get("/health")
    @app.get("/api/health")
    def health_check():
        return {
            "status": "healthy",
            "service": "Rack Raider AI Wardrobe Assistant",
            "gemini_model": DEFAULT_GEMINI_MODEL,
            "version": "2.0.0"
        }

    # -----------------------------------------------------------------------
    # Digital Closet / Inventory
    # -----------------------------------------------------------------------
    @app.get("/inventory")
    @app.get("/api/inventory")
    def api_fetch_inventory(
        request: Request,
        user_id: str = "user0001",
        category: Optional[str] = None,
        occasion: Optional[str] = None,
        season: Optional[str] = None,
        status: Optional[str] = "active"
    ):
        user_id = get_current_user_id(request, user_id)
        firestore = get_firestore_client()
        items = firestore.list_items(
            user_id=user_id,
            category=category,
            occasion=occasion,
            season=season,
            status=status,
            auth_user_id=user_id
        )
        return {
            "user_id": user_id,
            "count": len(items),
            "items": items
        }

    @app.post("/api/items")
    def api_create_item(req: ItemCreateRequest, request: Request):
        firestore = get_firestore_client()
        item_data = req.model_dump()
        user_id = get_current_user_id(request, item_data.pop("user_id"))
        created = firestore.save_item(user_id=user_id, item_data=item_data, auth_user_id=user_id)
        return {"status": "success", "item": created}

    @app.patch("/api/items/{item_id}")
    def api_update_item(item_id: str, req: ItemUpdateRequest, request: Request, user_id: str = "user0001"):
        user_id = get_current_user_id(request, user_id)
        firestore = get_firestore_client()
        item = firestore.get_item(user_id=user_id, item_id=item_id, auth_user_id=user_id)
        if not item:
            raise HTTPException(status_code=404, detail="Garment item not found")

        if req.increment_wear:
            item = firestore.increment_wear_count(user_id=user_id, item_id=item_id, worn_date=req.worn_date, auth_user_id=user_id)
            firestore.log_wear_event(user_id=user_id, item_id=item_id, worn_date=req.worn_date, auth_user_id=user_id)
        if req.status:
            item["status"] = req.status
            item = firestore.save_item(user_id=user_id, item_data=item, auth_user_id=user_id)
        if req.wear_count is not None:
            item["wear_count"] = req.wear_count
            item = firestore.save_item(user_id=user_id, item_data=item, auth_user_id=user_id)

        return {"status": "success", "item": item}

    @app.delete("/api/items/{item_id}")
    def api_delete_item(item_id: str, request: Request, user_id: str = "user0001"):
        user_id = get_current_user_id(request, user_id)
        firestore = get_firestore_client()
        item = firestore.get_item(user_id=user_id, item_id=item_id, auth_user_id=user_id)
        if not item:
            raise HTTPException(status_code=404, detail="Garment item not found")

        firestore.delete_item(user_id=user_id, item_id=item_id, auth_user_id=user_id)
        sync_service.queue_delete_item(item_id)
        return {"status": "success", "message": f"Item {item_id} deleted"}

    # -----------------------------------------------------------------------
    # Ingestion & Visual De-Duplication
    # -----------------------------------------------------------------------
    @app.post("/api/upload-outfit")
    def api_upload_outfit(req: IngestionRequest, request: Request):
        try:
            user_id = get_current_user_id(request, req.user_id)
            image_input = req.image_data

            # Base64 data URLs (data:image/...) and GCS URIs are handled natively
            # by the ingestion service's decompose_outfit_image method.
            # Only route through the GCS uploader for web URLs and local paths,
            # since those need their bytes fetched and stored first.
            if image_input and not image_input.startswith(("data:image/", "gs://")):
                from .tools.image_uploader import upload_image_to_gcs
                upload_res = upload_image_to_gcs(
                    image_input=image_input,
                    user_id=user_id
                )
                # Only use the GCS URI if the upload actually succeeded and bytes were stored
                if upload_res.get("status") == "success" and upload_res.get("gcs_uri"):
                    image_input = upload_res["gcs_uri"]

            result = parse_and_deduplicate_outfit_image(
                user_id=user_id,
                image_uri=image_input,
                worn_date=req.worn_date,
                sync_service=sync_service,
                auth_user_id=user_id
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    # -----------------------------------------------------------------------
    # Live Weather Ingestion
    # -----------------------------------------------------------------------
    @app.post("/weather")
    @app.post("/api/weather")
    def api_weather_summary(req: Optional[WeatherRequest] = None, city: str = "San Francisco", latitude: float = None, longitude: float = None):
        if req:
            return get_weather_summary(city=req.city, latitude=req.latitude, longitude=req.longitude)
        return get_weather_summary(city=city, latitude=latitude, longitude=longitude)

    # -----------------------------------------------------------------------
    # Outfit Synthesis & Styling
    # -----------------------------------------------------------------------
    @app.post("/api/synthesize-outfits")
    def api_synthesize_outfits(req: OutfitSynthesisRequest, request: Request):
        user_id = get_current_user_id(request, req.user_id)
        firestore = get_firestore_client()
        closet_items = firestore.list_items(user_id=user_id, status="active", auth_user_id=user_id)

        weather_ctx = req.weather_context
        weather_data = None
        if not weather_ctx:
            weather_data = get_weather_summary(city=req.city)
            weather_ctx = weather_data.get("summary_prompt", "")

        synthesis_result = synthesize_outfits(
            inventory_data=closet_items,
            weather_context=weather_ctx,
            occasion=req.occasion,
            user_prompt=req.user_prompt
        )
        return {
            "weather": weather_data,
            "target_occasion": req.occasion,
            "outfit_result": synthesis_result
        }

    # -----------------------------------------------------------------------
    # Predictive Gap Analysis
    # -----------------------------------------------------------------------
    @app.post("/gap-analysis")
    @app.post("/api/gap-analysis")
    def api_gap_analysis(request: Request, req: Optional[GapAnalysisRequest] = None, user_id: str = "user0001", target_occasion: str = "Casual / Daily"):
        user_id = get_current_user_id(request, req.user_id if req else user_id)
        occ = req.target_occasion if req else target_occasion
        return analyze_wardrobe_gaps(user_id=user_id, target_schedule={"occasion": occ}, auth_user_id=user_id)

    # -----------------------------------------------------------------------
    # Circular Commerce & Sustainability
    # -----------------------------------------------------------------------
    @app.post("/circular-action")
    @app.post("/api/circular-action")
    def api_circular_action(request: Request, req: Optional[CircularActionRequest] = None, user_id: str = "user0001", current_season: str = "Summer"):
        user_id = get_current_user_id(request, req.user_id if req else user_id)
        season = req.current_season if req else current_season
        return evaluate_circular_actions(user_id=user_id, current_season=season, auth_user_id=user_id)

    # -----------------------------------------------------------------------
    # Quick Stats Overview
    # -----------------------------------------------------------------------
    @app.get("/api/stats")
    def api_get_stats(request: Request, user_id: str = "user0001"):
        user_id = get_current_user_id(request, user_id)
        firestore = get_firestore_client()
        all_items = firestore.list_items(user_id=user_id, status=None, auth_user_id=user_id)
        active_items = [i for i in all_items if i.get("status") == "active"]
        stored_items = [i for i in all_items if i.get("status") == "stored"]
        donated_items = [i for i in all_items if i.get("status") == "donated"]
        
        total_wears = sum(i.get("wear_count", 0) for i in all_items)
        top_worn = sorted(all_items, key=lambda x: x.get("wear_count", 0), reverse=True)[:5]
        
        return {
            "user_id": user_id,
            "total_items": len(all_items),
            "active_count": len(active_items),
            "stored_count": len(stored_items),
            "donated_count": len(donated_items),
            "total_wears": total_wears,
            "top_worn": top_worn
        }

    # -----------------------------------------------------------------------
    # Seed Sample Capsule Wardrobe
    # -----------------------------------------------------------------------
    SAMPLE_CAPSULE_WARDROBE = [
        {
            "item_name": "Silk Ivory Button-Down Blouse",
            "category": "Top",
            "sub_category": "Blouse",
            "primary_color": "Ivory",
            "material": "Silk",
            "pattern": "Solid",
            "formality": "Smart Casual",
            "occasion": "Work / Professional",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Weekly",
            "warmth_rating": 2,
            "wear_count": 8,
            "last_worn_date": "2026-09-02",
            "status": "active",
            "style_tags": ["Chic", "Minimalist", "Workwear"]
        },
        {
            "item_name": "Charcoal Merino Wool Crewneck",
            "category": "Top",
            "sub_category": "Knit Sweater",
            "primary_color": "Charcoal Grey",
            "material": "Merino Wool",
            "pattern": "Solid",
            "formality": "Smart Casual",
            "occasion": "Casual / Daily",
            "season_tag": "Fall / Winter",
            "wear_frequency_expectation": "Weekly",
            "warmth_rating": 4,
            "wear_count": 14,
            "last_worn_date": "2026-08-28",
            "status": "active",
            "style_tags": ["Cozy", "Classic", "Layering"]
        },
        {
            "item_name": "Organic Slub Cotton White Tee",
            "category": "Top",
            "sub_category": "T-Shirt",
            "primary_color": "White",
            "material": "Cotton",
            "pattern": "Solid",
            "formality": "Casual",
            "occasion": "Casual / Daily",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Daily",
            "warmth_rating": 1,
            "wear_count": 22,
            "last_worn_date": "2026-09-05",
            "status": "active",
            "style_tags": ["Essential", "Staple", "Clean"]
        },
        {
            "item_name": "Parisian Breton Striped Longsleeve",
            "category": "Top",
            "sub_category": "Long Sleeve",
            "primary_color": "Navy/White",
            "material": "Cotton",
            "pattern": "Striped",
            "formality": "Casual",
            "occasion": "Casual / Daily",
            "season_tag": "Spring / Summer",
            "wear_frequency_expectation": "Weekly",
            "warmth_rating": 2,
            "wear_count": 11,
            "last_worn_date": "2026-08-15",
            "status": "active",
            "style_tags": ["French Chic", "Casual", "Timeless"]
        },
        {
            "item_name": "Tailored Charcoal Pleated Trousers",
            "category": "Bottom",
            "sub_category": "Trousers",
            "primary_color": "Charcoal Grey",
            "material": "Wool",
            "pattern": "Solid",
            "formality": "Formal",
            "occasion": "Work / Professional",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Weekly",
            "warmth_rating": 3,
            "wear_count": 9,
            "last_worn_date": "2026-08-30",
            "status": "active",
            "style_tags": ["Tailored", "Power Dressing", "Modern"]
        },
        {
            "item_name": "High-Rise Indigo Straight Leg Denim",
            "category": "Bottom",
            "sub_category": "Jeans",
            "primary_color": "Indigo Blue",
            "material": "Denim",
            "pattern": "Solid",
            "formality": "Casual",
            "occasion": "Casual / Daily",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Daily",
            "warmth_rating": 3,
            "wear_count": 28,
            "last_worn_date": "2026-09-04",
            "status": "active",
            "style_tags": ["Classic Denim", "Versatile", "Daily"]
        },
        {
            "item_name": "Pleated Cream Midi Skirt",
            "category": "Bottom",
            "sub_category": "Midi Skirt",
            "primary_color": "Cream",
            "material": "Viscose",
            "pattern": "Pleated",
            "formality": "Smart Casual",
            "occasion": "Party / Night Out",
            "season_tag": "Spring / Summer",
            "wear_frequency_expectation": "Monthly",
            "warmth_rating": 2,
            "wear_count": 3,
            "last_worn_date": "2026-07-20",
            "status": "active",
            "style_tags": ["Feminine", "Flowy", "Elegant"]
        },
        {
            "item_name": "Emerald Silk Midi Slip Dress",
            "category": "Dress",
            "sub_category": "Slip Dress",
            "primary_color": "Emerald Green",
            "material": "Silk",
            "pattern": "Solid",
            "formality": "Smart Casual",
            "occasion": "Party / Night Out",
            "season_tag": "Spring / Summer",
            "wear_frequency_expectation": "Monthly",
            "warmth_rating": 2,
            "wear_count": 4,
            "last_worn_date": "2026-09-01",
            "status": "active",
            "style_tags": ["Night Out", "Luxe", "Sensual"]
        },
        {
            "item_name": "Black Ribbed Knit Wrap Dress",
            "category": "Dress",
            "sub_category": "Knit Dress",
            "primary_color": "Black",
            "material": "Merino Wool",
            "pattern": "Solid",
            "formality": "Smart Casual",
            "occasion": "Work / Professional",
            "season_tag": "Fall / Winter",
            "wear_frequency_expectation": "Bi-weekly",
            "warmth_rating": 4,
            "wear_count": 6,
            "last_worn_date": "2026-08-10",
            "status": "active",
            "style_tags": ["Effortless", "Structured", "Sleek"]
        },
        {
            "item_name": "Italian Navy Tailored Wool Blazer",
            "category": "Outerwear",
            "sub_category": "Blazer",
            "primary_color": "Navy Blue",
            "material": "Wool",
            "pattern": "Solid",
            "formality": "Smart Casual",
            "occasion": "Work / Professional",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Weekly",
            "warmth_rating": 3,
            "wear_count": 18,
            "last_worn_date": "2026-09-03",
            "status": "active",
            "style_tags": ["Tailored", "Architectural", "Sophisticated"]
        },
        {
            "item_name": "Camel Double-Breasted Trench Coat",
            "category": "Outerwear",
            "sub_category": "Trench Coat",
            "primary_color": "Camel",
            "material": "Cotton Gabardine",
            "pattern": "Solid",
            "formality": "Smart Casual",
            "occasion": "Casual / Daily",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Weekly",
            "warmth_rating": 3,
            "wear_count": 12,
            "last_worn_date": "2026-08-22",
            "status": "active",
            "style_tags": ["Iconic", "Weatherproof", "Heritage"]
        },
        {
            "item_name": "Black Italian Leather Penny Loafers",
            "category": "Footwear",
            "sub_category": "Loafers",
            "primary_color": "Black",
            "material": "Leather",
            "pattern": "Solid",
            "formality": "Smart Casual",
            "occasion": "Work / Professional",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Daily",
            "warmth_rating": 2,
            "wear_count": 25,
            "last_worn_date": "2026-09-05",
            "status": "active",
            "style_tags": ["Staple", "Polished", "Androgynous"]
        },
        {
            "item_name": "Minimalist White Low-Top Leather Sneakers",
            "category": "Footwear",
            "sub_category": "Sneakers",
            "primary_color": "White",
            "material": "Leather",
            "pattern": "Solid",
            "formality": "Casual",
            "occasion": "Casual / Daily",
            "season_tag": "All-Season",
            "wear_frequency_expectation": "Daily",
            "warmth_rating": 2,
            "wear_count": 34,
            "last_worn_date": "2026-09-06",
            "status": "active",
            "style_tags": ["Clean", "Everyday", "Contemporary"]
        },
        {
            "item_name": "Vintage Heavy Wool Cableknit Sweater",
            "category": "Top",
            "sub_category": "Cableknit",
            "primary_color": "Oatmeal",
            "material": "Heavy Wool",
            "pattern": "Knit",
            "formality": "Casual",
            "occasion": "Casual / Daily",
            "season_tag": "Winter",
            "wear_frequency_expectation": "Seasonal",
            "warmth_rating": 5,
            "wear_count": 1,
            "last_worn_date": "2025-12-15",
            "status": "active",
            "style_tags": ["Heritage", "Warm", "Bulky"]
        }
    ]

    @app.post("/api/seed-sample-wardrobe")
    def api_seed_sample_wardrobe(request: Request, user_id: str = "user0001"):
        user_id = get_current_user_id(request, user_id)
        firestore = get_firestore_client()
        seeded = []
        for item in SAMPLE_CAPSULE_WARDROBE:
            rec = firestore.save_item(user_id=user_id, item_data=item, auth_user_id=user_id)
            seeded.append(rec)
        return {
            "status": "success",
            "message": f"Successfully seeded {len(seeded)} curated wardrobe pieces for {user_id}.",
            "items_count": len(seeded)
        }

    # -----------------------------------------------------------------------
    # AI Stylist Chat Endpoint  (multi-turn, memory-aware)
    # -----------------------------------------------------------------------
    # In-memory session store: user_id -> list of {"role": str, "parts": [{"text": str}]}
    # Persists for the lifetime of the server process.
    _chat_sessions: Dict[str, List[Dict[str, Any]]] = {}

    @app.post("/api/chat/reset")
    def api_chat_reset(request: Request, user_id: str = "user0001"):
        """Clear the conversation history for a user (fresh session)."""
        user_id = get_current_user_id(request, user_id)
        _chat_sessions.pop(user_id, None)
        return {"status": "ok", "message": "Chat session reset."}

    @app.post("/api/chat")
    def api_chat(req: ChatRequest, request: Request):
        user_id = get_current_user_id(request, req.user_id)
        firestore = get_firestore_client()
        items = firestore.list_items(user_id=user_id, status="active", auth_user_id=user_id)
        weather = get_weather_summary(city=req.city)

        client = get_genai_client()
        if client:
            try:
                # Build a rich wardrobe context (include wear history & season)
                inventory_summary = "\n".join([
                    f"- [{i.get('category')}] {i.get('item_name')} "
                    f"({i.get('primary_color')}, {i.get('material')}, "
                    f"Formality: {i.get('formality')}, Wears: {i.get('wear_count', 0)}, "
                    f"Last worn: {i.get('last_worn_date', 'never')})"
                    for i in items
                ])

                # One-time context message injected at the start of each session
                session_context = (
                    f"[WARDROBE CONTEXT — {len(items)} active items]\n{inventory_summary}\n\n"
                    f"[TODAY'S WEATHER — {req.city}] {weather.get('summary_prompt')}\n"
                    f"[TARGET OCCASION] {req.occasion}"
                )

                # Retrieve or initialise session history
                history = _chat_sessions.get(user_id, [])

                # If this is the first turn, prepend the wardrobe context as a system-level
                # user turn so the model always has fresh inventory data for this session.
                if not history:
                    history = [
                        {"role": "user", "parts": [{"text": session_context}]},
                        {"role": "model", "parts": [{"text": "Understood — I have full context on your wardrobe and today's weather. How can I help you?"}]}
                    ]
                else:
                    # Refresh the context block silently on every turn so stale data
                    # doesn't accumulate (replace the first user turn).
                    history[0] = {"role": "user", "parts": [{"text": session_context}]}

                # Append the new user message
                history.append({"role": "user", "parts": [{"text": req.message}]})

                # Call the model with the full conversation history
                res = client.models.generate_content(
                    model=DEFAULT_GEMINI_MODEL,
                    contents=history,
                    config={
                        "system_instruction": orchestrator_agent_instruction,
                        "temperature": 0.35
                    }
                )
                reply_text = res.text

                # Append model reply to history and persist
                history.append({"role": "model", "parts": [{"text": reply_text}]})

                # Cap history to last 40 turns (20 exchanges) to avoid token overflow
                if len(history) > 42:  # 2 context turns + 40 turns
                    history = history[:2] + history[-40:]

                _chat_sessions[user_id] = history

                return {
                    "reply": reply_text,
                    "weather_context": weather.get("summary_prompt"),
                    "turn_count": (len(history) - 2) // 2  # exclude context bootstrap
                }
            except Exception as e:
                print(f"[Chat] Gemini generation error: {e}. Using fallback stylist response.")

        # Smart fallback stylist response
        closet_preview = ", ".join([i.get("item_name") for i in items[:3]]) if items else "your curated pieces"
        return {
            "reply": (
                f"✨ **Rack Raider Stylist Advice for {req.city}:**\n\n"
                f"With current temperatures at **{weather.get('temp_range')[0]}°C – {weather.get('temp_range')[1]}°C** "
                f"and **{int(weather.get('precipitation_risk', 0)*100)}% precipitation risk**, I recommend focusing on "
                f"{'weatherproof layering and structured outerwear' if weather.get('layering_recommended') else 'breathable, high-impact silhouettes'}.\n\n"
                f"Based on your closet ({closet_preview}), pairing a crisp neutral base with textured layering like a tailored blazer or slip dress "
                f"achieves the perfect balance of comfort and elevated elegance for **{req.occasion}**."
            ),
            "weather_context": weather.get("summary_prompt")
        }

    # -----------------------------------------------------------------------
    # Serve Web UI SPA & Static Files
    # -----------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def serve_frontend():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<h1>Rack Raider</h1><p>Frontend assets not found at " + str(index_file) + "</p>"
        )

    # Mount static directory for CSS, JS, images
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

else:
    app = None