"""
validate.py

VALIDATE stage of the ETL pipeline (OpenWeather data).

Uses Pydantic to check every row before it is loaded into the database:
  - city must be one of the cities in config.CITIES
  - time and fetched_at must be present
  - pollutant values must be non-negative (or missing)
  - ow_aqi (OpenWeather's own index) must be 1 to 5 (or missing)
  - us_aqi_calc (our calculated US AQI) must be 0 to 500 (or missing)

Rows that fail are rejected and logged. The pipeline stops if NO row is valid,
or if more than half of the rows are rejected (a sign of a systematic problem).

Values are MODEL-BASED ESTIMATES (OpenWeather / SILAM), not station measurements.
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
MAX_REJECT_FRACTION = 0.5


class AirQualityRecord(BaseModel):
    """Schema for one row (used for both the hourly and the current table)."""

    model_config = ConfigDict(extra="ignore")

    city: str
    time: datetime
    fetched_at: datetime

    ow_aqi: Optional[int] = Field(default=None, ge=1, le=5)
    us_aqi_calc: Optional[int] = Field(default=None, ge=0, le=500)

    pm2_5: Optional[float] = Field(default=None, ge=0)
    pm10: Optional[float] = Field(default=None, ge=0)
    carbon_monoxide: Optional[float] = Field(default=None, ge=0)
    sulphur_dioxide: Optional[float] = Field(default=None, ge=0)
    nitrogen_dioxide: Optional[float] = Field(default=None, ge=0)
    ozone: Optional[float] = Field(default=None, ge=0)

    @field_validator("city")
    @classmethod
    def city_must_be_known(cls, value):
        if value not in config.CITIES:
            raise ValueError(f"unknown city: {value}")
        return value


def _validate_frame(df, label):
    """Validate each row of a DataFrame. Returns the valid rows as a DataFrame."""
    # Pydantic needs None (not NaN) for missing values.
    clean = df.astype(object).where(df.notna(), None)

    valid_rows, rejected = [], 0
    for index, row in enumerate(clean.to_dict(orient="records")):
        try:
            valid_rows.append(AirQualityRecord(**row).model_dump())
        except ValidationError as exc:
            rejected += 1
            if rejected <= MAX_LOGGED_ERRORS:
                error = exc.errors()[0]
                logger.warning(
                    "%s row %d rejected (%s): %s",
                    label, index, ".".join(str(p) for p in error["loc"]), error["msg"],
                )

    if rejected:
        logger.warning("%s: %d row(s) rejected, %d valid", label, rejected, len(valid_rows))

    if not valid_rows:
        raise ValueError(f"Validation failed: no valid {label} rows. Stopping pipeline.")
    if rejected / len(df) > MAX_REJECT_FRACTION:
        raise ValueError(
            f"Validation failed: {rejected} of {len(df)} {label} rows rejected. Stopping pipeline."
        )

    out = pd.DataFrame(valid_rows)
    out = out[[column for column in df.columns if column in out.columns]]
    for column in ("ow_aqi", "us_aqi_calc"):  # whole numbers, with missing allowed
        out[column] = out[column].astype("Int64")
    return out


def validate_all(hourly_df, current_df):
    """Validate both DataFrames. Returns (valid_hourly_df, valid_current_df)."""
    valid_hourly = _validate_frame(hourly_df, "hourly")
    valid_current = _validate_frame(current_df, "current")
    logger.info(
        "Validate done: %d hourly rows OK, %d current rows OK",
        len(valid_hourly),
        len(valid_current),
    )
    return valid_hourly, valid_current


if __name__ == "__main__":
    import json
    from pathlib import Path

    import numpy as np

    try:
        import transform
    except ImportError:
        from src import transform

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Rebuild the test input from the raw JSON saved by extract.py (no new API calls).
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw_openweather"
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
    valid_hourly, valid_current = validate_all(hourly, current)
    print("\nValid hourly rows:", len(valid_hourly), "of", len(hourly))
    print("Valid current rows:", len(valid_current), "of", len(current))
    print("\nColumn types after validation:")
    print(valid_hourly.dtypes.to_string())

    # Negative tests: every bad row must be rejected
    print("\nNegative tests:")
    for name, column, bad_value in [
        ("negative pm2_5", "pm2_5", -5.0),
        ("ow_aqi above 5", "ow_aqi", 7.0),
        ("us_aqi_calc above 500", "us_aqi_calc", 600.0),
        ("unknown city", "city", "Atlantis"),
    ]:
        bad = hourly.head(1).copy()
        bad[column] = bad_value
        try:
            _validate_frame(bad, "negative-test")
            print("  FAIL: bad row was accepted:", name)
        except ValueError:
            print("  PASS: rejected -", name)

    # A missing AQI is allowed (nothing is invented)
    ok = hourly.head(1).copy()
    ok["us_aqi_calc"] = np.nan
    try:
        _validate_frame(ok, "missing-test")
        print("  PASS: accepted - missing us_aqi_calc")
    except ValueError:
        print("  FAIL: row with missing us_aqi_calc was rejected")