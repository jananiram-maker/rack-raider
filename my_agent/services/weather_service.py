"""
Open-Meteo Weather Ingestion & Pre-Processing Service.
Fetches raw meteorological data and transforms it into a concise structured summary for the LLM context.
"""

import json
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, Tuple
from ..config import OPEN_METEO_BASE_URL

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


# Fast-path coordinates for common demo cities — avoids a geocoding round-trip
# for the cities most likely to come up. Anything else falls through to
# geocode_city() below rather than silently defaulting to San Francisco.
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "san francisco": (37.7749, -122.4194),
    "new york": (40.7128, -74.0060),
    "london": (51.5074, -0.1278),
    "tokyo": (35.6762, 139.6503),
    "paris": (48.8566, 2.3522),
    "sydney": (-33.8688, 151.2093),
    "seattle": (47.6062, -122.3321),
    "mumbai": (19.0760, 72.8777),
    "bengaluru": (12.9716, 77.5946),
    "chicago": (41.8781, -87.6298),
}


class WeatherService:
    """
    Ingests weather data from Open-Meteo and compresses raw metrics into clean stylist context.
    """
    def __init__(self, base_url: str = OPEN_METEO_BASE_URL):
        self.base_url = base_url

    def fetch_raw_weather(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        Queries Open-Meteo API for current, hourly, and daily metrics.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,weather_code",
            "hourly": "temperature_2m,precipitation_probability,uv_index",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max",
            "timezone": "auto",
            "forecast_days": 1
        }
        
        query_string = urllib.parse.urlencode(params)
        url = f"{self.base_url}?{query_string}"
        
        req = urllib.request.Request(url, headers={"User-Agent": "NaturallyEasy-WardrobeAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=5.0) as response:
            return json.loads(response.read().decode("utf-8"))

    def geocode_city(self, city: str) -> Optional[Tuple[float, float]]:
        """
        Resolves an arbitrary city name to (latitude, longitude) via Open-Meteo's
        free geocoding endpoint, for any city not in the CITY_COORDINATES fast-path.
        Returns None (rather than raising) on no match or network failure, so callers
        can fall back to a default without needing their own try/except per call site.
        """
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        query_string = urllib.parse.urlencode(params)
        url = f"{OPEN_METEO_GEOCODING_URL}?{query_string}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NaturallyEasy-WardrobeAssistant/1.0"})
            with urllib.request.urlopen(req, timeout=5.0) as response:
                data = json.loads(response.read().decode("utf-8"))
            results = data.get("results") or []
            if not results:
                return None
            return float(results[0]["latitude"]), float(results[0]["longitude"])
        except Exception as e:
            print(f"[Weather Geocoding Error] Failed to resolve city '{city}': {e}")
            return None

    def pre_process_weather_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts and compacts raw metrics into the required structured summary:
        {
          "temp_range": [min_temp, max_temp],
          "current_temp": float,
          "precipitation_risk": float, # 0.0 to 1.0
          "layering_recommended": bool,
          "uv_index": float,
          "weather_condition": str,
          "summary_prompt": str
        }
        """
        # Current temperature
        current = raw_data.get("current", {})
        current_temp = float(current.get("temperature_2m", 20.0))
        
        # Daily temp range
        daily = raw_data.get("daily", {})
        max_temps = daily.get("temperature_2m_max", [current_temp + 3])
        min_temps = daily.get("temperature_2m_min", [current_temp - 3])
        max_temp = float(max_temps[0]) if max_temps else current_temp + 3
        min_temp = float(min_temps[0]) if min_temps else current_temp - 3
        temp_range = [round(min_temp, 1), round(max_temp, 1)]

        # Precipitation Risk
        precip_probs = daily.get("precipitation_probability_max", [0])
        precip_risk_pct = float(precip_probs[0]) if precip_probs else float(current.get("precipitation", 0)) * 10
        precipitation_risk = min(max(precip_risk_pct / 100.0, 0.0), 1.0)

        # UV Index
        uv_max_list = daily.get("uv_index_max", [3.0])
        uv_index = float(uv_max_list[0]) if uv_max_list else 3.0

        # Layering logic: wide temp swing (>7C variation) or cold morning (<14C) or max <16C
        temp_delta = max_temp - min_temp
        layering_recommended = temp_delta >= 7.0 or min_temp < 14.0 or current_temp < 15.0

        # Weather condition description
        weather_code = current.get("weather_code", 0)
        condition = self._interpret_weather_code(weather_code, precipitation_risk)

        # Natural language summary
        summary_prompt = (
            f"Weather: {condition}. Current temp: {current_temp:.1f}°C (Range: {min_temp:.1f}°C - {max_temp:.1f}°C). "
            f"Precipitation Risk: {int(precipitation_risk * 100)}%. UV Index: {uv_index:.1f}. "
            f"{'Layering is highly recommended due to temperature swings.' if layering_recommended else 'Consistent temperature throughout the day.'}"
        )

        return {
            "temp_range": temp_range,
            "current_temp": round(current_temp, 1),
            "precipitation_risk": round(precipitation_risk, 2),
            "layering_recommended": layering_recommended,
            "uv_index": round(uv_index, 1),
            "weather_condition": condition,
            "summary_prompt": summary_prompt
        }

    @staticmethod
    def _interpret_weather_code(code: int, precip_risk: float) -> str:
        """Translates WMO weather codes into readable fashion weather descriptors."""
        if code in [0, 1]:
            return "Clear / Sunny" if precip_risk < 0.2 else "Mostly Sunny"
        elif code in [2, 3]:
            return "Partly Cloudy" if precip_risk < 0.3 else "Overcast"
        elif code in [45, 48]:
            return "Foggy / Mist"
        elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
            return "Rain / Showers"
        elif code in [71, 73, 75, 77, 85, 86]:
            return "Snow / Flurries"
        elif code in [95, 96, 99]:
            return "Thunderstorm"
        return "Showers" if precip_risk > 0.4 else "Mild & Overcast"

    def get_weather_summary(
        self,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        city: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Coordinates or city-based weather summary generation with offline fallback.
        """
        lat, lon = latitude, longitude
        
        if (lat is None or lon is None) and city:
            clean_city = city.lower().strip()
            if clean_city in CITY_COORDINATES:
                lat, lon = CITY_COORDINATES[clean_city]
            else:
                # Not one of the fast-path cities — resolve it for real instead of
                # silently defaulting to San Francisco's coordinates.
                geocoded = self.geocode_city(city)
                if geocoded:
                    lat, lon = geocoded

        if lat is None or lon is None:
            # City was empty, or geocoding found no match / failed — default to San Francisco.
            lat, lon = 37.7749, -122.4194

        try:
            raw = self.fetch_raw_weather(lat, lon)
            return self.pre_process_weather_data(raw)
        except Exception as e:
            # Log the error for debugging
            print(f"[Weather API Error] Failed to fetch from Open-Meteo for ({lat}, {lon}): {e}")
            # Resilient fallback mock response with varied data based on season
            fallback_data = {
                "temp_range": [12.0, 24.0],
                "current_temp": 18.0,
                "precipitation_risk": 0.2,
                "layering_recommended": True,
                "uv_index": 5.0,
                "weather_condition": "Default/Fallback",
                "summary_prompt": "Weather service offline. Using default forecast: mild (12°C - 24°C), 20% rain risk."
            }
            return fallback_data


# Singleton helper
_WEATHER_SERVICE_INSTANCE: Optional[WeatherService] = None

def get_weather_summary(latitude: Optional[float] = None, longitude: Optional[float] = None, city: Optional[str] = None) -> Dict[str, Any]:
    global _WEATHER_SERVICE_INSTANCE
    if _WEATHER_SERVICE_INSTANCE is None:
        _WEATHER_SERVICE_INSTANCE = WeatherService()
    return _WEATHER_SERVICE_INSTANCE.get_weather_summary(latitude, longitude, city)
