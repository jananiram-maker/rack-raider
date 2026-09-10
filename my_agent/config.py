import os
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Load .env from my_agent directory (where it lives) before reading any env var
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment

# ---------------------------------------------------------------------------
# Global AI & Gemini Model Configuration
# Change here to switch all models across the entire application instantly
# ---------------------------------------------------------------------------
DEFAULT_GEMINI_MODEL: str = os.getenv("DEFAULT_GEMINI_MODEL", "gemini-3.5-flash-lite")
DEFAULT_EMBEDDING_MODEL: str = os.getenv("DEFAULT_EMBEDDING_MODEL", "text-embedding-004")
DEFAULT_MULTIMODAL_EMBEDDING_MODEL: str = os.getenv("DEFAULT_MULTIMODAL_EMBEDDING_MODEL", "multimodalembedding@001")
GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))

# ---------------------------------------------------------------------------
# Google Cloud Platform & Storage Configuration
# ---------------------------------------------------------------------------
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "spring-florals-stylist")
GCP_LOCATION: str = os.getenv("GCP_LOCATION", "global")
GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "wardrobe_sfs")

# ---------------------------------------------------------------------------
# BigQuery Data Warehouse Configuration
# ---------------------------------------------------------------------------
BIGQUERY_DATASET: str = os.getenv("BIGQUERY_DATASET", "naturally_easy_analytics")
BIGQUERY_TABLE_ITEMS: str = os.getenv("BIGQUERY_TABLE_ITEMS", "Items")
BIGQUERY_TABLE_OUTFITS: str = os.getenv("BIGQUERY_TABLE_OUTFITS", "Outfits")
BIGQUERY_TABLE_OUTFIT_ITEMS: str = os.getenv("BIGQUERY_TABLE_OUTFIT_ITEMS", "Outfit_Items")

# Full BigQuery table identifiers
def get_bq_table_id(table_name: str, project_id: str = GCP_PROJECT_ID, dataset: str = BIGQUERY_DATASET) -> str:
    return f"{project_id}.{dataset}.{table_name}"


# ---------------------------------------------------------------------------
# GenAI Client Initialization Helper (ADC / Vertex AI & API Key Support)
# ---------------------------------------------------------------------------
def get_genai_client():
    """
    Initializes and returns a Google GenAI Client (google.genai.Client).
    
    Authentication Resolution:
    1. If GEMINI_API_KEY / GOOGLE_API_KEY is present (and GOOGLE_GENAI_USE_VERTEXAI is not true),
       uses Google AI Studio with the API key.
    2. Otherwise, defaults to Google Cloud Vertex AI using Application Default Credentials (ADC),
       targeting GCP_PROJECT_ID and GCP_LOCATION.
    """
    try:
        from google import genai
    except ImportError:
        return None

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    use_vertexai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("true", "1", "yes")

    try:
        if api_key and not use_vertexai:
            return genai.Client(api_key=api_key)

        # Vertex AI mode using ADC (Application Default Credentials)
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or GCP_PROJECT_ID
        location = os.getenv("GOOGLE_CLOUD_LOCATION") or GCP_LOCATION
        try:
            return genai.Client(vertexai=True)
        except:
            return genai.Client(vertexai=True, project=project, location=location)
    except Exception as e:
        print(f"[Config] GenAI client initialization failed: {e}. Multimodal features will use local fallbacks.")
        return None


# ---------------------------------------------------------------------------
# Firebase Admin SDK Initialization Helper (ID token verification)
# ---------------------------------------------------------------------------
def get_firebase_auth():
    """
    Initializes the Firebase Admin SDK (once per process) and returns its
    `auth` module, used server-side to verify ID tokens issued by the
    frontend's Firebase Auth (Google) sign-in flow.

    Uses Application Default Credentials — no explicit service account file
    needed when running with `gcloud beta code dev` / on GCP infra with a
    service account already configured.

    Returns None if firebase-admin isn't installed or initialization fails
    (no ADC available, wrong project, etc.) — callers should fall back to
    trusting client-supplied identity in that case, matching every other
    service in this app (Firestore, BigQuery, Gemini) which degrades the
    same way when credentials aren't present.
    """
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth
    except ImportError:
        return None

    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return firebase_auth
    except Exception as e:
        print(f"[Config] Firebase Admin initialization failed: {e}. Falling back to unauthenticated dev mode.")
        return None


# ---------------------------------------------------------------------------
# Firestore Collections & Paths
# ---------------------------------------------------------------------------
FIRESTORE_USERS_COLLECTION: str = "users"
FIRESTORE_ITEMS_SUBCOLLECTION: str = "items"
FIRESTORE_OUTFITS_SUBCOLLECTION: str = "outfits"
FIRESTORE_WEAR_LOGS_SUBCOLLECTION: str = "wear_logs"

# ---------------------------------------------------------------------------
# Ingestion & De-Duplication Thresholds
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.88"))

# ---------------------------------------------------------------------------
# Open-Meteo Weather API
# ---------------------------------------------------------------------------
OPEN_METEO_BASE_URL: str = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")

# ---------------------------------------------------------------------------
# Wardrobe Categories & Allowed Enums
# Includes "Dress" and "One-Piece" as first-class categories
# ---------------------------------------------------------------------------
AllowedCategory = Literal[
    "Top", 
    "Bottom", 
    "Dress", 
    "One-Piece", 
    "Outerwear", 
    "Footwear", 
    "Accessory"
]

AllowedOccasion = Literal[
    "Casual / Daily", 
    "Work / Professional", 
    "Formal / Black Tie",
    "Festive / Celebratory", 
    "Party / Night Out", 
    "Athletic / Activewear", 
    "Lounge / Sleepwear"
]

AllowedFormality = Literal["Casual", "Smart Casual", "Formal"]

AllowedSeason = Literal[
    "Spring", 
    "Summer", 
    "Fall", 
    "Winter", 
    "Spring / Summer", 
    "Fall / Winter", 
    "All-Season"
]

AllowedWearFrequency = Literal[
    "Daily",
    "Weekly",
    "Bi-weekly",
    "Monthly",
    "Seasonal",
    "Special Occasion"
]
