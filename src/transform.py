"""
transform.py

TRANSFORM stage of the ETL pipeline.

Turns the raw nested API responses (from extract.py) into two clean pandas
DataFrames:
  - hourly_df  -> for the `air_quality` table (one row per city + hour)
  - current_df -> for the `current_air_quality` table (one row per city)

Cleaning rules:
  - Convert time columns to proper datetimes.
  - Convert value columns to numbers (bad values become NaN).
  - Negative pollutant values are impossible, so they become NaN.
  - Drop duplicate (city, time) rows.
  - Missing values stay missing. Nothing is invented or filled in.

Values are MODEL-BASED ESTIMATES (CAMS), not ground-station measurements.
"""

import logging

import pandas as pd

try:
    import config
except ImportError:  # when imported as src.transform
    from src import config

logger = logging.getLogger(__name__)

VALUE_COLUMNS = list(config.POLLUTANTS.values()) + config.AQI_FIELDS
HOURLY_COLUMNS = ["city", "province", "latitude", "longitude", "time"] + VALUE_COLUMNS
CURRENT_COLUMNS = [
    "city", "province", "latitude", "longitude", "time", "fetched_at"
] + VALUE_COLUMNS


def _clean_values(df):
    """Convert value columns to numeric and null out impossible negatives."""
    for col in VALUE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")
        negatives = df[col] < 0
        if negatives.any():
            logger.warning(
                "%d negative value(s) in %s set to missing", int(negatives.sum()), col
            )
            df.loc[negatives, col] = pd.NA
        df[col] = df[col].astype("float64")
    return df


def build_hourly(extracted):
    """Build the hourly DataFrame from the list returned by extract_all()."""
    frames = []
    for item in extracted:
        hourly = item["data"].get("hourly", {})
        if "time" not in hourly:
            logger.warning("%s: no hourly time data, skipped", item["city"])
            continue
        df = pd.DataFrame(hourly)
        df["city"] = item["city"]
        df["province"] = item["province"]
        df["latitude"] = item["latitude"]
        df["longitude"] = item["longitude"]
        frames.append(df)

    if not frames:
        raise ValueError("Transform failed: no hourly data available")

    hourly_df = pd.concat(frames, ignore_index=True)
    hourly_df["time"] = pd.to_datetime(hourly_df["time"], errors="coerce")

    bad_time = hourly_df["time"].isna()
    if bad_time.any():
        logger.warning("Dropping %d row(s) with invalid time", int(bad_time.sum()))
        hourly_df = hourly_df[~bad_time]

    hourly_df = _clean_values(hourly_df)

    before = len(hourly_df)
    hourly_df = hourly_df.drop_duplicates(subset=["city", "time"], keep="last")
    if before != len(hourly_df):
        logger.info("Removed %d duplicate city+time row(s)", before - len(hourly_df))

    return hourly_df[HOURLY_COLUMNS].sort_values(["city", "time"]).reset_index(drop=True)


def build_current(extracted):
    """Build the current-conditions DataFrame (one row per city)."""
    rows = []
    for item in extracted:
        current = item["data"].get("current")
        if not current or "time" not in current:
            logger.warning("%s: no current data, skipped", item["city"])
            continue
        row = dict(current)
        row["city"] = item["city"]
        row["province"] = item["province"]
        row["latitude"] = item["latitude"]
        row["longitude"] = item["longitude"]
        row["fetched_at"] = item["fetched_at"]
        rows.append(row)

    if not rows:
        raise ValueError("Transform failed: no current data available")

    current_df = pd.DataFrame(rows)
    current_df["time"] = pd.to_datetime(current_df["time"], errors="coerce")
    current_df = current_df.dropna(subset=["time"])
    current_df = _clean_values(current_df)
    current_df = current_df.drop_duplicates(subset=["city"], keep="last")

    return current_df[CURRENT_COLUMNS].sort_values("city").reset_index(drop=True)


def transform_all(extracted):
    """Run the full transform. Returns (hourly_df, current_df)."""
    hourly_df = build_hourly(extracted)
    current_df = build_current(extracted)
    logger.info(
        "Transform done: %d hourly rows, %d current rows",
        len(hourly_df),
        len(current_df),
    )
    return hourly_df, current_df


if __name__ == "__main__":
    import json
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Test using the JSON snapshots saved earlier (no new API calls).
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw_api"
    items = []
    for city, (lat, lon, province) in config.CITIES.items():
        files = sorted((raw_dir / city).glob("*.json"))
        if not files:
            continue
        with open(files[-1], encoding="utf-8") as f:
            saved = json.load(f)
        items.append(
            {
                "city": city,
                "province": province,
                "latitude": lat,
                "longitude": lon,
                "fetched_at": pd.Timestamp(saved["metadata"]["fetched_at_utc"]),
                "data": saved["response"],
            }
        )

    hourly, current = transform_all(items)
    print("\nHourly shape:", hourly.shape)
    print(hourly.head(3).to_string())
    print("\nCurrent shape:", current.shape)
    print(current.head(3).to_string())
    print("\nMissing values in hourly:")
    print(hourly[VALUE_COLUMNS].isna().sum().to_string())