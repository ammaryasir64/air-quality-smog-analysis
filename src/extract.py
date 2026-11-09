"""
extract.py

EXTRACT stage of the ETL pipeline.

Fetches current conditions and hourly air-quality data for each city from the
Open-Meteo Air Quality API and saves the raw JSON response per city.

Cities that fail in the first pass get ONE second chance after a short pause.

IMPORTANT: Values are MODEL-BASED ESTIMATES (CAMS atmospheric model), not
direct ground-station measurements.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    import config
except ImportError:  # when imported as src.extract
    from src import config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_api"

SECOND_CHANCE_PAUSE_SECONDS = 30


def fetch_city(city, latitude, longitude, max_retries=None):
    """Call the API for one city. Retries on timeouts, rate limits and server errors."""
    attempts = max_retries or config.MAX_RETRIES
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(config.CURRENT_VARIABLES),
        "hourly": ",".join(config.HOURLY_VARIABLES),
        "timezone": config.TIMEZONE,
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
    }

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                config.API_URL, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(
                    f"HTTP {response.status_code} (rate limit or server error)"
                )
            response.raise_for_status()
            data = response.json()
            if "hourly" not in data or "current" not in data:
                raise ValueError("API response is missing 'hourly' or 'current'")
            return data
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning("%s: attempt %d/%d failed: %s", city, attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(f"{city}: all {attempts} attempts failed: {last_error}")


def save_raw_json(city, data, fetched_at):
    """Save one raw API response as JSON inside data/raw_api/<city>/."""
    city_dir = RAW_DIR / city
    city_dir.mkdir(parents=True, exist_ok=True)
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    path = city_dir / f"{city}_{stamp}.json"

    payload = {
        "metadata": {
            "city": city,
            "source": config.API_URL,
            "fetched_at_utc": fetched_at.isoformat(),
            "note": "Model-based estimates (CAMS), not ground-station measurements.",
        },
        "response": data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _fetch_and_store(city, fetched_at, max_retries=None):
    """Fetch one city, save its JSON, and return the result dict."""
    lat, lon, province = config.CITIES[city]
    data = fetch_city(city, lat, lon, max_retries=max_retries)
    path = save_raw_json(city, data, fetched_at)
    logger.info("%s: fetched OK, saved %s", city, path.name)
    return {
        "city": city,
        "province": province,
        "latitude": lat,
        "longitude": lon,
        "fetched_at": fetched_at,
        "data": data,
    }


def extract_all():
    """
    Fetch all cities. Returns a list of dicts:
        {"city", "province", "latitude", "longitude", "fetched_at", "data"}
    Raises RuntimeError if every city fails.
    """
    fetched_at = datetime.now(timezone.utc)
    results = []
    failed = []

    # Pass 1: every city, full retries.
    for city in config.CITIES:
        try:
            results.append(_fetch_and_store(city, fetched_at))
        except Exception as exc:
            logger.error("%s: FAILED: %s", city, exc)
            failed.append(city)
        time.sleep(config.PAUSE_BETWEEN_CITIES_SECONDS)

    # Pass 2: one second chance (single attempt) for cities that failed.
    if failed and len(failed) < len(config.CITIES):
        logger.info(
            "Second chance for %d city(ies) after %d s pause: %s",
            len(failed), SECOND_CHANCE_PAUSE_SECONDS, ", ".join(failed),
        )
        time.sleep(SECOND_CHANCE_PAUSE_SECONDS)
        still_failed = []
        for city in failed:
            try:
                results.append(_fetch_and_store(city, fetched_at, max_retries=1))
            except Exception as exc:
                logger.error("%s: FAILED again in second chance: %s", city, exc)
                still_failed.append(city)
            time.sleep(config.PAUSE_BETWEEN_CITIES_SECONDS)
        failed = still_failed

    if not results:
        raise RuntimeError("Extract failed for ALL cities. Stopping pipeline.")
    if failed:
        logger.warning("Extract finished with failures for: %s", ", ".join(failed))

    logger.info("Extract done: %d succeeded, %d failed", len(results), len(failed))
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    extracted = extract_all()
    print(f"\nCities fetched: {len(extracted)}")
    first = extracted[0]
    print("First city:", first["city"])
    print("Current block:", first["data"]["current"])
    print("Hourly rows:", len(first["data"]["hourly"]["time"]))