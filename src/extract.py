"""
extract.py

EXTRACT stage of the ETL pipeline (OpenWeather Air Pollution API).

For every city it fetches three things:
  - current   : the latest reading
  - history   : hourly readings for the last N days
  - forecast  : the 4-day hourly forecast
and keeps the raw responses of each city as one JSON file:
  - locally in data/raw_openweather/<City>/            (temporary on GitHub Actions)
  - durably in the private Supabase Storage bucket "raw-openweather" as
    <City_Name>/<City_Name>_<UTC time>.json              (kept after the run ends)

The API key comes from the environment variable OPENWEATHER_API_KEY and the
Supabase credentials from SUPABASE_URL / SUPABASE_KEY (.env locally, GitHub
Secrets in Actions). Secrets are never saved in JSON files and never logged.

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
from supabase import create_client

try:
    import config
except ImportError:  # when imported as src.extract
    from src import config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw_openweather"
SECOND_CHANCE_PAUSE_SECONDS = 30

RAW_BUCKET = "raw-openweather"
UPLOAD_RETRIES = 3


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


def get_storage_client():
    """Supabase client (secret key, server side only) used to archive the raw JSON."""
    load_dotenv(PROJECT_ROOT / ".env")
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is missing (needed to archive raw JSON)")
    return create_client(url, key)


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


def make_payload(city, data, fetched_at, days):
    """The JSON file content (as bytes). It contains no secrets."""
    payload = {
        "metadata": {
            "city": city,
            "source": config.API_BASE_URL,
            "fetched_at_utc": fetched_at.isoformat(),
            "history_days": days,
            "note": "Model-based estimates (OpenWeather / SILAM), not ground-station "
                    "measurements. No API key or credential is stored here.",
        },
        "response": data,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def save_raw_json(city, body, stamp):
    """Save the raw JSON locally in data/raw_openweather/<City>/."""
    city_dir = RAW_DIR / city
    city_dir.mkdir(parents=True, exist_ok=True)
    path = city_dir / f"{city}_{stamp}.json"
    path.write_bytes(body)
    return path


def upload_raw_json(storage, object_path, city, body):
    """Upload the same bytes to the private Supabase Storage bucket (with retries)."""
    last = None
    for attempt in range(1, UPLOAD_RETRIES + 1):
        try:
            storage.storage.from_(RAW_BUCKET).upload(
                object_path, body, {"content-type": "application/json", "upsert": "true"}
            )
            return object_path
        except Exception as exc:
            last = exc
            logger.warning(
                "%s: archive upload attempt %d/%d failed: %s", city, attempt, UPLOAD_RETRIES, exc
            )
            if attempt < UPLOAD_RETRIES:
                time.sleep(3 * attempt)
    raise RuntimeError(f"archive upload failed: {last}")


def _fetch_and_store(city, key, days, fetched_at, attempts, storage):
    lat, lon, province = config.CITIES[city]
    data = fetch_city(lat, lon, key, days, attempts)

    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    body = make_payload(city, data, fetched_at, days)
    path = save_raw_json(city, body, stamp)

    archived = False
    if storage is not None:
        slug = city.replace(" ", "_")
        try:
            upload_raw_json(storage, f"{slug}/{slug}_{stamp}.json", city, body)
            archived = True
        except Exception as exc:
            logger.error("%s: raw JSON archive FAILED: %s", city, exc)

    logger.info(
        "%s: fetched OK (current %d, history %d, forecast %d rows), saved %s%s",
        city, len(data["current"]), len(data["history"]), len(data["forecast"]),
        path.name, " and archived" if archived else "",
    )
    return {
        "city": city,
        "province": province,
        "latitude": lat,
        "longitude": lon,
        "fetched_at": fetched_at,
        "archived": archived,
        **data,
    }


def _run_pass(names, key, days, fetched_at, attempts, storage):
    ok, failed = [], []
    for city in names:
        try:
            ok.append(_fetch_and_store(city, key, days, fetched_at, attempts, storage))
        except ApiKeyError:
            raise
        except Exception as exc:
            logger.error("%s: FAILED: %s", city, str(exc).replace(key, "***"))
            failed.append(city)
        time.sleep(config.PAUSE_BETWEEN_CALLS_SECONDS)
    return ok, failed


def extract_all(history_days=None, only=None, archive=True):
    """
    Fetch all cities (or only the given ones). Returns a list of dicts:
        {"city", "province", "latitude", "longitude", "fetched_at", "archived",
         "current", "history", "forecast"}
    Raises RuntimeError if every city fails (or if no raw JSON could be archived),
    ApiKeyError if the OpenWeather key is bad.
    """
    key = get_api_key()
    storage = get_storage_client() if archive else None
    days = history_days or config.HISTORY_DAYS
    if not 1 <= days <= config.MAX_HISTORY_DAYS:
        raise ValueError(f"history_days must be between 1 and {config.MAX_HISTORY_DAYS}")

    names = list(only) if only else list(config.CITIES)
    unknown = [c for c in names if c not in config.CITIES]
    if unknown:
        raise ValueError(f"Unknown city name(s): {', '.join(unknown)}")

    fetched_at = datetime.now(timezone.utc)
    results, failed = _run_pass(names, key, days, fetched_at, config.MAX_RETRIES, storage)

    if failed and results:
        logger.info(
            "Second chance for %d city(ies) after %d s pause: %s",
            len(failed), SECOND_CHANCE_PAUSE_SECONDS, ", ".join(failed),
        )
        time.sleep(SECOND_CHANCE_PAUSE_SECONDS)
        more, failed = _run_pass(failed, key, days, fetched_at, 1, storage)
        results.extend(more)

    if not results:
        raise RuntimeError("Extract failed for ALL cities. Stopping pipeline.")
    if failed:
        logger.warning("Extract finished with failures for: %s", ", ".join(failed))

    if archive:
        stored = sum(1 for r in results if r["archived"])
        logger.info(
            "Raw JSON archive: %d/%d files uploaded to Supabase Storage (%s)",
            stored, len(results), RAW_BUCKET,
        )
        if stored == 0:
            raise RuntimeError(
                "Raw JSON archive failed for ALL cities (check the bucket and SUPABASE_KEY). "
                "Stopping pipeline."
            )
        not_archived = [r["city"] for r in results if not r["archived"]]
        if not_archived:
            logger.warning("Raw JSON NOT archived for: %s", ", ".join(not_archived))

    logger.info("Extract done: %d succeeded, %d failed", len(results), len(failed))
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test the OpenWeather extract stage")
    parser.add_argument("cities", nargs="*", help="city names (default: all cities)")
    parser.add_argument("--days", type=int, default=None, help="days of history")
    parser.add_argument("--no-archive", action="store_true", help="do not upload to Supabase Storage")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    extracted = extract_all(
        history_days=args.days, only=args.cities or None, archive=not args.no_archive
    )
    first = extracted[0]
    print(f"\nCities fetched: {len(extracted)}")
    print("First city:", first["city"])
    print("Rows -> current:", len(first["current"]), "| history:", len(first["history"]),
          "| forecast:", len(first["forecast"]))
    print("Archived in Supabase Storage:", [r["city"] for r in extracted if r["archived"]])