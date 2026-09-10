"""
Core Domain Services for naturallyEasy.
"""

from .vector_search import VectorSearchService, compute_cosine_similarity
from .weather_service import WeatherService, get_weather_summary
from .ingestion_service import IngestionService, parse_and_deduplicate_outfit_image
from .gap_analysis import GapAnalysisService, analyze_wardrobe_gaps
from .circular_commerce import CircularCommerceService, evaluate_circular_actions

__all__ = [
    "VectorSearchService",
    "compute_cosine_similarity",
    "WeatherService",
    "get_weather_summary",
    "IngestionService",
    "parse_and_deduplicate_outfit_image",
    "GapAnalysisService",
    "analyze_wardrobe_gaps",
    "CircularCommerceService",
    "evaluate_circular_actions",
]
