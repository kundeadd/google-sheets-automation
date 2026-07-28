"""Погода через Open-Meteo (безкоштовний, без ключа).

https://open-meteo.com/en/docs
"""
import logging

import requests

from .base import DataSource

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherSource(DataSource):
    name = "weather"

    def fetch(self) -> list[dict]:
        cities = self.config.get("cities", [
            {"name": "Kyiv", "lat": 50.4501, "lon": 30.5234},
        ])

        rows = []
        for city in cities:
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "current": "temperature_2m,wind_speed_10m,weather_code",
            }
            resp = requests.get(API_URL, params=params, timeout=10)
            resp.raise_for_status()
            current = resp.json().get("current", {})

            rows.append({
                "city": city["name"],
                "temperature_c": current.get("temperature_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "weather_code": current.get("weather_code"),
            })

        logger.info("weather: fetched %d cities", len(rows))
        return rows
