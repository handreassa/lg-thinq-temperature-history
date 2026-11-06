"""Outdoor reference from Open-Meteo model data (not an on-site sensor)."""
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv


def fetch_weather():
    load_dotenv(Path(__file__).with_name(".env"))
    lat, lon = os.getenv("WEATHER_LATITUDE", ""), os.getenv("WEATHER_LONGITUDE", "")
    if not lat and not lon:
        return None
    latitude, longitude = float(lat), float(lon)
    if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid weather coordinates")
    with httpx.Client(timeout=20) as client:
        response = client.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": latitude, "longitude": longitude,
            "current": "temperature_2m", "temperature_unit": "celsius", "timezone": "UTC",
        })
        response.raise_for_status()
        payload = response.json()
    current = payload["current"]
    temperature = current["temperature_2m"]
    if temperature is None or not math.isfinite(float(temperature)):
        raise ValueError("Missing outdoor temperature")
    source_time = datetime.fromisoformat(current["time"]).replace(tzinfo=timezone.utc)
    return {
        "outdoor_temperature_c": float(temperature),
        "weather_time": source_time.isoformat(),
        "weather_collected_at": datetime.now(timezone.utc).isoformat(),
        "weather_location": os.getenv("WEATHER_LOCATION", "Configured location"),
        "weather_latitude": latitude,
        "weather_longitude": longitude,
        "weather_source": "open-meteo",
    }
