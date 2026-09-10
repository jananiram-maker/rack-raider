"""
Orchestrator Agent Tool: Weather Summary Ingestion.
"""

from typing import Optional, Dict, Any
from ..services.weather_service import get_weather_summary


def tool_get_weather_summary(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetches raw forecast data from Open-Meteo and compresses it into a structured weather summary:
    temp_range, current_temp, precipitation_risk (0-1), layering_recommended (bool), uv_index, and condition.
    
    Args:
        latitude: Geographic latitude (e.g. 37.7749)
        longitude: Geographic longitude (e.g. -122.4194)
        city: City name for quick coordinate resolution (e.g. 'San Francisco', 'New York', 'London')
    """
    return get_weather_summary(latitude=latitude, longitude=longitude, city=city)
