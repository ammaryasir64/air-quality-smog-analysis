"""
extract.py

EXTRACT stage of the ETL pipeline (OpenWeather Air Pollution API).

For every city it fetches three things:
  - current   : the latest reading
  - history   : hourly readings for the last N days
  - forecast  : the 4-day hourly forecast
and saves the raw responses of each city as one JSON file in
data/raw_openweather/<City>/.

The API key comes from the environment variable OPENWEATHER_API_KEY
(.env locally, GitHub Secrets in Actions). It is never saved in JSON files
and never written to logs.

IMPORTANT: Values are MODEL-BASED ESTIMATES (OpenWeather uses the SILAM model),
not direct ground-station measurements.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    import config
except ImportError:  # when imported as src.extract
    from src import config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_openweather"
SECOND_CHANCE_PAUSE_SECONDS = 30


class ApiKeyError(RuntimeError):
    """The key is missing or was rejected. Trying the other cities is pointless."""


def get_api_key():
    load_dotenv(PROJECT_ROOT / ".env")
    key = (os.getenv(config.API_KEY_ENV_VAR) or "").strip()
    if not key:
        raise ApiKeyError(
            f"{config.API_KEY_ENV_VAR} is missing (.env locally, GitHub Secret in Actions)"
        )
    return key


def api_get(path, params, key, attempts):
    """One API call with retries. Returns the list of hourly rows."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                config.API_BASE_URL + path,
                params={**params, "appid": key},
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code in (401, 403):
                raise ApiKeyError(f"HTTP {response.status_code}: API key rejected or not allowed")
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.RequestException(
                    f"HTTP {response.status_code} (rate limit or server error)"
                )
            response.raise_for_status()
            rows = response.json().get("list")
            if not isinstance(rows, list):
                raise ValueError("response has no 'list'")
            return rows
        except ApiKeyError:
            raise
        except (requests.RequestException, ValueError) as exc:
            last = str(exc).replace(key, "***")  # never leak the key
            logger.warning(
                "%s: attempt %d/%d failed: %s", path or "/current", attempt, attempts, last
            )
            if attempt < attempts:
                time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"all {attempts} attempts failed: {last}")


def fetch_city(latitude, longitude, key, days, attempts):
    """Current + history + forecast for one city (3 API calls)."""
    now = int(time.time())
    base = {"lat": latitude, "lon": longitude}

    current = api_get("", base, key, attempts)
    time.sleep(config.PAUSE_BETWEEN_CALLS_SECONDS)
    history = api_get("/history", {**base, "start": now - days * 86400, "end": now}, key, attempts)
    time.sleep(config.PAUSE_BETWEEN_CALLS_SECONDS)
    forecast = api_get("/forecast", base, key, attempts)

    if not current or not history:
        raise ValueError("API returned no current or history rows")
    return {"current": current, "history": history, "forecast": forecast}


def save_raw_json(city, data, fetched_at, days):
    """Save one city's raw responses as JSON (no secrets inside)."""
    city_dir = RAW_DIR / city
    city_dir.mkdir(parents=True, exist_ok=True)
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    path = city_dir / f"{city}_{stamp}.json"
    payload = {
        "metadata": {
            "city": city,
            "source": config.API_BASE_URL,
            "fetched_at_utc": fetched_at.isoformat(),
            "history_days": days,
            "note": "Model-based estimates (OpenWeather / SILAM), not ground-station "
                    "measurements. The API key is never stored here.",
        },
        "response": data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _fetch_and_store(city, key, days, fetched_at, attempts):
    lat, lon, province = config.CITIES[city]
    data = fetch_city(lat, lon, key, days, attempts)
    path = save_raw_json(city, data, fetched_at, days)
    logger.info(
        "%s: fetched OK (current %d, history %d, forecast %d rows), saved %s",
        city, len(data["current"]), len(data["history"]), len(data["forecast"]), path.name,
    )
    return {
        "city": city,
        "province": province,
        "latitude": lat,
        "longitude": lon,
        "fetched_at": fetched_at,
        **data,
    }


def _run_pass(names, key, days, fetched_at, attempts):
    ok, failed = [], []
    for city in names:
        try:
            ok.append(_fetch_and_store(city, key, days, fetched_at, attempts))
        except ApiKeyError:
            raise
        except Exception as exc:
            logger.error("%s: FAILED: %s", city, str(exc).replace(key, "***"))
            failed.append(city)
        time.sleep(config.PAUSE_BETWEEN_CALLS_SECONDS)
    return ok, failed


def extract_all(history_days=None, only=None):
    """
    Fetch all cities (or only the given ones). Returns a list of dicts:
        {"city", "province", "latitude", "longitude", "fetched_at",
         "current", "history", "forecast"}
    Raises RuntimeError if every city fails, ApiKeyError if the key is bad.
    """
    key = get_api_key()
    days = history_days or config.HISTORY_DAYS
    if not 1 <= days <= config.MAX_HISTORY_DAYS:
        raise ValueError(f"history_days must be between 1 and {config.MAX_HISTORY_DAYS}")

    names = list(only) if only else list(config.CITIES)
    unknown = [c for c in names if c not in config.CITIES]
    if unknown:
        raise ValueError(f"Unknown city name(s): {', '.join(unknown)}")

    fetched_at = datetime.now(timezone.utc)
    results, failed = _run_pass(names, key, days, fetched_at, config.MAX_RETRIES)

    if failed and results:
        logger.info(
            "Second chance for %d city(ies) after %d s pause: %s",
            len(failed), SECOND_CHANCE_PAUSE_SECONDS, ", ".join(failed),
        )
        time.sleep(SECOND_CHANCE_PAUSE_SECONDS)
        more, failed = _run_pass(failed, key, days, fetched_at, attempts=1)
        results.extend(more)

    if not results:
        raise RuntimeError("Extract failed for ALL cities. Stopping pipeline.")
    if failed:
        logger.warning("Extract finished with failures for: %s", ", ".join(failed))

    logger.info("Extract done: %d succeeded, %d failed", len(results), len(failed))
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test the OpenWeather extract stage")
    parser.add_argument("cities", nargs="*", help="city names (default: all cities)")
    parser.add_argument("--days", type=int, default=None, help="days of history")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    extracted = extract_all(history_days=args.days, only=args.cities or None)
    first = extracted[0]
    print(f"\nCities fetched: {len(extracted)}")
    print("First city:", first["city"])
    print("Rows -> current:", len(first["current"]), "| history:", len(first["history"]),
          "| forecast:", len(first["forecast"]))
    print("Latest current row:", first["current"][0])