"""
validate.py

VALIDATE stage of the ETL pipeline.

Uses Pydantic to check every row before it is loaded into the database:
  - city must be one of the 20 known cities
  - latitude/longitude must be in valid ranges
  - pollutant values must be non-negative (or missing)
  - AQI values must be between 0 and 1000 (or missing)
  - time must be present

Rows that fail validation are rejected and logged. Valid rows continue.
If NO rows are valid, the pipeline stops (essential stage failed).

Values are MODEL-BASED ESTIMATES (CAMS), not ground-station measurements.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

try:
    import config
except ImportError:  # when imported as src.validate
    from src import config

logger = logging.getLogger(__name__)

MAX_LOGGED_ERRORS = 5


class AirQualityRecord(BaseModel):
    """Schema for one hourly row (air_quality table)."""

    model_config = ConfigDict(extra="ignore")

    city: str
    province: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    time: datetime

    pm2_5: Optional[float] = Field(default=None, ge=0)
    pm10: Optional[float] = Field(default=None, ge=0)
    carbon_monoxide: Optional[float] = Field(default=None, ge=0)
    sulphur_dioxide: Optional[float] = Field(default=None, ge=0)
    nitrogen_dioxide: Optional[float] = Field(default=None, ge=0)
    ozone: Optional[float] = Field(default=None, ge=0)

    us_aqi: Optional[float] = Field(default=None, ge=0, le=1000)
    european_aqi: Optional[float] = Field(default=None, ge=0, le=1000)

    @field_validator("city")
    @classmethod
    def city_must_be_known(cls, value):
        if value not in config.CITIES:
            raise ValueError(f"unknown city: {value}")
        return value


class CurrentRecord(AirQualityRecord):
    """Schema for one current-conditions row (current_air_quality table)."""

    fetched_at: datetime


def _validate_frame(df, model, label):
    """Validate each row of a DataFrame against a Pydantic model."""
    # Pydantic needs None (not NaN) for missing values.
    clean = df.astype(object).where(df.notna(), None)

    valid_rows = []
    rejected = 0
    for index, row in enumerate(clean.to_dict(orient="records")):
        try:
            record = model(**row)
            valid_rows.append(record.model_dump())
        except ValidationError as exc:
            rejected += 1
            if rejected <= MAX_LOGGED_ERRORS:
                logger.warning("%s row %d rejected: %s", label, index, exc.errors()[0]["msg"])

    if rejected:
        logger.warning("%s: %d row(s) rejected, %d valid", label, rejected, len(valid_rows))

    if not valid_rows:
        raise ValueError(f"Validation failed: no valid {label} rows. Stopping pipeline.")

    return pd.DataFrame(valid_rows)


def validate_all(hourly_df, current_df):
    """Validate both DataFrames. Returns (valid_hourly_df, valid_current_df)."""
    valid_hourly = _validate_frame(hourly_df, AirQualityRecord, "hourly")
    valid_current = _validate_frame(current_df, CurrentRecord, "current")
    logger.info(
        "Validate done: %d hourly rows OK, %d current rows OK",
        len(valid_hourly),
        len(valid_current),
    )
    return valid_hourly, valid_current


if __name__ == "__main__":
    import json
    from pathlib import Path

    try:
        import transform
    except ImportError:
        from src import transform

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Rebuild the test input from saved JSON snapshots (no new API calls).
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

    hourly, current = transform.transform_all(items)
    valid_hourly, valid_current = validate_all(hourly, current)
    print("\nValid hourly rows:", len(valid_hourly))
    print("Valid current rows:", len(valid_current))

    # Negative test: a bad row must be rejected.
    bad = hourly.head(1).copy()
    bad["pm2_5"] = -5.0
    try:
        _validate_frame(bad, AirQualityRecord, "negative-test")
    except ValueError as exc:
        print("\nNegative test OK (bad row was rejected):", exc)