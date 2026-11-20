"""
load.py

LOAD stage of the ETL pipeline (OpenWeather data).

Upserts validated DataFrames into Supabase PostgreSQL:
  - openweather_air_quality          conflict key: (city, time)
  - openweather_current_air_quality  conflict key: city

Upsert = insert new rows, update existing rows. Re-running the ETL never
creates duplicate city/time rows.

Credentials come from the environment variables SUPABASE_URL and SUPABASE_KEY
(.env locally, GitHub Secrets in Actions). They are never written in code.
"""

import logging
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BATCH_SIZE = 500
MAX_RETRIES = 3

HOURLY_TABLE = "openweather_air_quality"
CURRENT_TABLE = "openweather_current_air_quality"


def get_client():
    """Create a Supabase client from environment variables."""
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is missing")
    return create_client(url.strip(), key.strip())


def _to_records(df):
    """DataFrame -> JSON-safe records (missing -> None, times -> ISO text)."""
    df = df.copy()
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            df[column] = df[column].apply(lambda v: v.isoformat() if pd.notna(v) else None)
    df = df.astype(object).where(df.notna(), None)
    records = df.to_dict(orient="records")
    # make sure every value is a plain Python type
    return [
        {key: (value.item() if hasattr(value, "item") else value) for key, value in record.items()}
        for record in records
    ]


def upsert_table(client, table, df, conflict):
    """Upsert a DataFrame into a table in batches, with retries."""
    records = _to_records(df)
    total = len(records)
    for start in range(0, total, BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                client.table(table).upsert(batch, on_conflict=conflict).execute()
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "%s: batch at row %d, attempt %d/%d failed: %s",
                    table, start, attempt, MAX_RETRIES, exc,
                )
                time.sleep(3 * attempt)
        if last_error is not None:
            raise RuntimeError(f"Load failed for table {table}: {last_error}")
        logger.info("%s: upserted rows %d-%d of %d", table, start + 1, start + len(batch), total)
    return total


def load_all(hourly_df, current_df):
    """Load both DataFrames. Returns (hourly_count, current_count)."""
    client = get_client()
    current_df = current_df.assign(updated_at=pd.Timestamp.now(tz="UTC"))
    hourly_count = upsert_table(client, HOURLY_TABLE, hourly_df, "city,time")
    current_count = upsert_table(client, CURRENT_TABLE, current_df, "city")
    logger.info(
        "Load done: %d hourly rows, %d current rows upserted", hourly_count, current_count
    )
    return hourly_count, current_count


if __name__ == "__main__":
    import json

    try:
        import config, transform, validate
    except ImportError:
        from src import config, transform, validate

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Test with the raw JSON saved by extract.py (no new API calls).
    raw_dir = PROJECT_ROOT / "data" / "raw_openweather"
    items = []
    for city, (lat, lon, province) in config.CITIES.items():
        files = sorted((raw_dir / city).glob("*.json"))
        if not files:
            continue
        saved = json.loads(files[-1].read_text(encoding="utf-8"))
        items.append(
            {
                "city": city,
                "province": province,
                "latitude": lat,
                "longitude": lon,
                "fetched_at": pd.Timestamp(saved["metadata"]["fetched_at_utc"]),
                **saved["response"],
            }
        )

    hourly, current = transform.transform_all(items)
    valid_hourly, valid_current = validate.validate_all(hourly, current)
    load_all(valid_hourly, valid_current)
    print("\nLoad test finished. Check Supabase.")