"""
Orchestrator Agent Tool: Passive Wear Logging & Visual De-Duplication.
Supports direct chat image uploads, local paths, public URLs, and GCS URIs.
"""

from typing import Optional, Dict, Any
from ..services.ingestion_service import parse_and_deduplicate_outfit_image
from .image_uploader import upload_image_to_gcs
from ..auth import authenticate_user


def tool_parse_garment_image(
    image_input: str = "",
    user_id: str = "user0001",
    worn_date: Optional[str] = None,
    auth_token: Optional[str] = None,
    tool_context: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Ingests an outfit photo/mirror selfie, decomposes it into distinct garments (Category, Occasion,
    Material, Season Tag, Wear Frequency Expectation), generates Vertex AI visual vector embeddings,
    and runs >0.88 cosine similarity de-duplication against the user's isolated Firestore closet.
    
    Supports:
    - Direct image uploads/attachments in the chat UI (via ADK session artifacts / tool_context).
    - Google Cloud Storage URIs ('gs://...').
    - Public web URLs ('http://' or 'https://').
    - Local file paths.
    
    If similarity > 0.88 -> Increments wear count & logs wear event.
    If similarity <= 0.88 -> Creates new item record and indexes embedding.
    
    Args:
        image_input: Optional image filename, GCS URI, web URL, or local file path (can be empty if attached in chat)
        user_id: Target user ID
        worn_date: Optional ISO date string (YYYY-MM-DD)
        auth_token: Optional authentication token for user isolation
        tool_context: Automatically injected by ADK runtime to access chat upload artifacts
    """
    # Authenticate and validate user session
    session = authenticate_user(auth_token or user_id)
    target_user_id = session.user_id

    # 1. Resolve / Upload to GCS if needed (extracts bytes from chat artifact if attached in UI)
    upload_res = upload_image_to_gcs(
        image_input=image_input,
        tool_context=tool_context,
        user_id=target_user_id
    )
    gcs_uri = upload_res.get("gcs_uri", image_input)

    # 2. Decompose and de-duplicate
    return parse_and_deduplicate_outfit_image(
        user_id=target_user_id,
        image_uri=gcs_uri,
        worn_date=worn_date,
        auth_user_id=target_user_id
    )
