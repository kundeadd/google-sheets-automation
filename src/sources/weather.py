"""Weather from Open-Meteo (free, no key), with retries.
https://open-meteo.com/en/docs
"""
import logging
import time

import requests

from .base import DataSource

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_FIELDS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,"
    "precipitation,weather_code,cloud_cover,pressure_msl,"
    "wind_speed_10m,wind_direction_10m,wind_gusts_10m,is_day"
)

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

RETRIES = 3
RETRY_SLEEP = 2.0
BATCH_PAUSE = 0.3


def _compass(deg):
    if deg is None:
        return ""
    return COMPASS[int((float(deg) + 11.25) % 360 / 22.5)]


def _num(v, digits=1):
    try:
        return round(float(v), digits)
    except (TypeError, ValueError):
        return ""


class WeatherSource(DataSource):
    name = "weather"

    def _get(self, session, params):
        last_err = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = session.get(API_URL, params=params, timeout=15)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                logger.warning("weather: attempt %d/%d failed (%s), retrying",
                               attempt, RETRIES, e.__class__.__name__)
                time.sleep(RETRY_SLEEP * attempt)
        raise last_err

    def fetch(self) -> list[dict]:
        cities = self.config.get("cities", [
            {"name": "Kyiv", "lat": 50.4501, "lon": 30.5234},
        ])

        rows = []
        session = requests.Session()
        session.headers["User-Agent"] = "sheets-automation/1.0"

        for city in cities:
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "current": CURRENT_FIELDS,
                "timezone": "auto",
            }
            try:
                payload = self._get(session, params)
            except Exception as e:
                logger.error("weather: %s skipped after %d retries (%s)",
                             city["name"], RETRIES, e.__class__.__name__)
                continue

            current = payload.get("current", {})
            temp = _num(current.get("temperature_2m"))
            feels = _num(current.get("apparent_temperature"))
            gap = ""
            if temp != "" and feels != "":
                gap = round(feels - temp, 1)

            code = current.get("weather_code")

            rows.append({
                "city": city["name"],
                "temperature_c": temp,
                "feels_like_c": feels,
                "feels_gap": gap,
                "humidity_pct": current.get("relative_humidity_2m", ""),
                "wind_kmh": _num(current.get("wind_speed_10m")),
                "gusts_kmh": _num(current.get("wind_gusts_10m")),
                "wind_dir": _compass(current.get("wind_direction_10m")),
                "pressure_hpa": _num(current.get("pressure_msl"), 0),
                "cloud_cover_pct": current.get("cloud_cover", ""),
                "precipitation_mm": _num(current.get("precipitation")),
                "conditions": WMO_CODES.get(code, f"Code {code}"),
                "daylight": "Day" if current.get("is_day") else "Night",
                "local_time": str(current.get("time", "")).replace("T", " "),
                "timezone": payload.get("timezone", ""),
            })
            time.sleep(BATCH_PAUSE)

        logger.info("weather: fetched %d of %d cities", len(rows), len(cities))
        return rows
