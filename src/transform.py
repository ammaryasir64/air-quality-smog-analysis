"""
transform.py

TRANSFORM stage of the ETL pipeline (OpenWeather data).

Turns the raw API responses (from extract.py) into two clean DataFrames:
  - hourly_df  -> table `openweather_air_quality`          (one row per city + hour)
  - current_df -> table `openweather_current_air_quality`  (one row per city)

Cleaning rules
  - times: API times are UTC; they are converted to Asia/Karachi local time
  - values are converted to numbers; negative values become missing
  - duplicate (city, hour) rows are removed (history wins over forecast)
  - missing values stay missing. Nothing is invented or filled in.

US AQI (column us_aqi_calc) is CALCULATED here; OpenWeather itself only gives a
1-5 index (ow_aqi). The calculation follows the US EPA breakpoint table
(40 CFR Part 58, Appendix G, Table 2, as amended in 2024):
  - PM2.5 / PM10: 24-hour rolling mean; O3 / CO: 8-hour rolling mean;
    SO2 / NO2: 1-hour value (SO2 uses the 24-hour mean if its index reaches 200)
  - concentrations are truncated as EPA requires, the index is rounded, capped at 500
  - overall AQI = highest pollutant index; it needs the PM2.5 index to exist
  - ug/m3 -> ppb/ppm uses 25 C and 1 atm (EPA reference conditions); OpenWeather
    does not state its own conditions, so this is an assumption
This is an approximation from MODEL data (SILAM), not an official AQI.
"""

import logging

import numpy as np
import pandas as pd

try:
    import config
except ImportError:  # when imported as src.transform
    from src import config

logger = logging.getLogger(__name__)

MOLAR_VOLUME = 24.45  # litres per mole at 25 C and 1 atm
MOLECULAR_WEIGHT = {
    "carbon_monoxide": 28.01,
    "sulphur_dioxide": 64.07,
    "nitrogen_dioxide": 46.01,
    "ozone": 48.00,
}

# The first hours of every fetched window cannot have a full 24-hour average
WARMUP_HOURS = 23

# EPA breakpoints. key -> (decimals the concentration is truncated to,
#                          rows of (conc_low, conc_high, aqi_low, aqi_high))
BREAKPOINTS = {
    "pm2_5": (1, [(0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
                  (55.5, 125.4, 151, 200), (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500)]),
    "pm10": (0, [(0, 54, 0, 50), (55, 154, 51, 100), (155, 254, 101, 150),
                 (255, 354, 151, 200), (355, 424, 201, 300), (425, 604, 301, 500)]),
    "co_8h": (1, [(0.0, 4.4, 0, 50), (4.5, 9.4, 51, 100), (9.5, 12.4, 101, 150),
                  (12.5, 15.4, 151, 200), (15.5, 30.4, 201, 300), (30.5, 50.4, 301, 500)]),
    "so2_1h": (0, [(0, 35, 0, 50), (36, 75, 51, 100), (76, 185, 101, 150),
                   (186, 304, 151, 200), (305, 604, 201, 300), (605, 1004, 301, 500)]),
    "no2_1h": (0, [(0, 53, 0, 50), (54, 100, 51, 100), (101, 360, 101, 150),
                   (361, 649, 151, 200), (650, 1249, 201, 300), (1250, 2049, 301, 500)]),
    # 8-hour ozone defines indexes up to 300; higher values come from 1-hour ozone
    "o3_8h": (3, [(0.000, 0.054, 0, 50), (0.055, 0.070, 51, 100), (0.071, 0.085, 101, 150),
                  (0.086, 0.105, 151, 200), (0.106, 0.200, 201, 300)]),
    "o3_1h": (3, [(0.125, 0.164, 101, 150), (0.165, 0.204, 151, 200),
                  (0.205, 0.404, 201, 300), (0.405, 0.604, 301, 500)]),
}

HOURLY_COLUMNS = ["city", "time", "ow_aqi", "us_aqi_calc"] + config.POLLUTANT_COLUMNS + ["fetched_at"]
CURRENT_COLUMNS = HOURLY_COLUMNS


def sub_index(values, key):
    """AQI sub-index for concentrations (EPA units). NaN stays NaN."""
    decimals, rows = BREAKPOINTS[key]
    c_lo = np.array([r[0] for r in rows], dtype="float64")
    c_hi = np.array([r[1] for r in rows], dtype="float64")
    i_lo = np.array([r[2] for r in rows], dtype="float64")
    i_hi = np.array([r[3] for r in rows], dtype="float64")

    factor = 10 ** decimals
    conc = np.floor(np.asarray(values, dtype="float64") * factor + 1e-6) / factor  # truncate

    idx = np.searchsorted(c_lo, conc, side="right") - 1
    valid = ~np.isnan(conc) & (idx >= 0)
    k = np.clip(idx, 0, len(rows) - 1)

    index = (i_hi[k] - i_lo[k]) / (c_hi[k] - c_lo[k]) * (conc - c_lo[k]) + i_lo[k]
    index = np.minimum(index, i_hi[-1])  # cap (500, or 300 for 8-hour ozone)
    index = np.floor(index + 0.5)  # round to nearest integer
    return np.where(valid, index, np.nan)


def _to_ppb(series, pollutant):
    return series * MOLAR_VOLUME / MOLECULAR_WEIGHT[pollutant]


def _to_ppm(series, pollutant):
    return _to_ppb(series, pollutant) / 1000.0


def _rolling_mean(series, hours, min_periods):
    """Mean of the last `hours` hours. Missing hours count as missing."""
    full = series.asfreq("h")
    return full.rolling(hours, min_periods=min_periods).mean().reindex(series.index)


def compute_us_aqi(df):
    """df: hourly rows indexed by time, the six pollutants in ug/m3. Returns a Series."""
    pm25 = sub_index(_rolling_mean(df["pm2_5"], 24, 18), "pm2_5")
    pm10 = sub_index(_rolling_mean(df["pm10"], 24, 18), "pm10")
    co = sub_index(_to_ppm(_rolling_mean(df["carbon_monoxide"], 8, 6), "carbon_monoxide"), "co_8h")
    no2 = sub_index(_to_ppb(df["nitrogen_dioxide"], "nitrogen_dioxide"), "no2_1h")

    so2_1h = sub_index(_to_ppb(df["sulphur_dioxide"], "sulphur_dioxide"), "so2_1h")
    so2_24h = sub_index(
        _to_ppb(_rolling_mean(df["sulphur_dioxide"], 24, 18), "sulphur_dioxide"), "so2_1h"
    )
    so2 = np.where((so2_1h >= 200) & ~np.isnan(so2_24h), so2_24h, so2_1h)

    o3_8h = sub_index(_to_ppm(_rolling_mean(df["ozone"], 8, 6), "ozone"), "o3_8h")
    o3_1h = sub_index(_to_ppm(df["ozone"], "ozone"), "o3_1h")
    o3 = np.fmax(o3_8h, o3_1h)

    stacked = pd.DataFrame(np.vstack([pm25, pm10, co, no2, so2, o3]).T, index=df.index)
    overall = stacked.max(axis=1, skipna=True).to_numpy()
    overall = np.where(np.isnan(pm25), np.nan, overall)  # PM2.5 index must exist
    return pd.Series(overall, index=df.index, name="us_aqi_calc")


def _rows_to_frame(rows):
    """List of OpenWeather rows -> DataFrame (local naive time, 6 pollutants)."""
    records = []
    for row in rows:
        if "dt" not in row:
            continue
        components = row.get("components") or {}
        record = {
            "time": pd.to_datetime(row["dt"], unit="s", utc=True)
            .tz_convert(config.TIMEZONE)
            .tz_localize(None),
            "ow_aqi": (row.get("main") or {}).get("aqi"),
        }
        for api_name, column in config.POLLUTANTS.items():
            record[column] = components.get(api_name)
        records.append(record)
    return pd.DataFrame(records, columns=["time", "ow_aqi"] + config.POLLUTANT_COLUMNS)


def _clean(df):
    """Numbers only; impossible values become missing."""
    for column in config.POLLUTANT_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        negatives = df[column] < 0
        if negatives.any():
            logger.warning("%d negative value(s) in %s set to missing", int(negatives.sum()), column)
            df.loc[negatives, column] = np.nan
    df["ow_aqi"] = pd.to_numeric(df["ow_aqi"], errors="coerce")
    df.loc[~df["ow_aqi"].between(1, 5), "ow_aqi"] = np.nan
    return df


def _transform_city(item):
    """Returns (hourly rows of one city, current row of one city as a dict)."""
    city = item["city"]
    rows = list(item.get("history") or []) + list(item.get("forecast") or [])
    if not rows:
        raise ValueError("no history or forecast rows")

    df = _clean(_rows_to_frame(rows))
    df["time"] = df["time"].dt.floor("h")
    df = (
        df.dropna(subset=["time"])
        .drop_duplicates(subset="time", keep="first")  # history comes first
        .sort_values("time")
        .set_index("time")
    )
    df["us_aqi_calc"] = compute_us_aqi(df)
    full_aqi = df["us_aqi_calc"].copy()

    start = df.index.min() + pd.Timedelta(hours=WARMUP_HOURS)
    hourly = df[df.index >= start].reset_index()
    hourly["city"] = city
    hourly["fetched_at"] = item["fetched_at"]
    hourly = hourly[HOURLY_COLUMNS]

    current_rows = item.get("current") or []
    if not current_rows:
        raise ValueError("no current row")
    cur = _clean(_rows_to_frame(current_rows[:1])).iloc[0]
    cur_time = cur["time"]
    earlier = full_aqi.loc[:cur_time].dropna()
    aqi = np.nan
    if not earlier.empty and cur_time - earlier.index[-1] <= pd.Timedelta(hours=2):
        aqi = earlier.iloc[-1]
    current = {
        "city": city,
        "time": cur_time,
        "ow_aqi": cur["ow_aqi"],
        "us_aqi_calc": aqi,
        **{column: cur[column] for column in config.POLLUTANT_COLUMNS},
        "fetched_at": item["fetched_at"],
    }
    return hourly, current


def transform_all(extracted):
    """Run the full transform. Returns (hourly_df, current_df)."""
    hourly_parts, current_rows = [], []
    for item in extracted:
        try:
            hourly, current = _transform_city(item)
        except Exception as exc:
            logger.error("%s: transform failed: %s", item.get("city"), exc)
            continue
        hourly_parts.append(hourly)
        current_rows.append(current)

    if not hourly_parts:
        raise ValueError("Transform failed: no usable data for any city")

    hourly_df = pd.concat(hourly_parts, ignore_index=True)
    hourly_df = hourly_df.drop_duplicates(subset=["city", "time"], keep="last")
    hourly_df = hourly_df.sort_values(["city", "time"]).reset_index(drop=True)
    current_df = pd.DataFrame(current_rows, columns=CURRENT_COLUMNS)
    current_df = current_df.sort_values("city").reset_index(drop=True)

    logger.info(
        "Transform done: %d hourly rows, %d current rows", len(hourly_df), len(current_df)
    )
    return hourly_df, current_df


def _self_test():
    """Check the AQI maths against values that follow directly from the EPA table."""
    cases = [
        ("pm2_5", [9.0, 35.4, 51.6, 55.4, 225.4, 400.0], [50, 100, 141, 150, 300, 500]),
        ("pm10", [54, 154, 210], [50, 100, 128]),
        ("co_8h", [4.4, 9.4], [50, 100]),
        ("no2_1h", [53, 100], [50, 100]),
        ("o3_8h", [0.054, 0.070, 0.300], [50, 100, 300]),
    ]
    all_ok = True
    for key, values, expected in cases:
        got = [int(x) for x in sub_index(values, key)]
        ok = got == expected
        all_ok = all_ok and ok
        print(f"  {'PASS' if ok else 'FAIL'}  {key}: {values} -> {got} (expected {expected})")
    return all_ok


if __name__ == "__main__":
    import json
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    print("AQI maths self-test:")
    print("ALL PASSED" if _self_test() else "SOME TESTS FAILED")

    # Test with the raw JSON files saved by extract.py (no new API calls)
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

    hourly, current = transform_all(items)
    print("\nHourly shape:", hourly.shape)
    print(hourly.groupby("city")["time"].agg(["min", "max", "count"]).to_string())
    print("\nCurrent shape:", current.shape)
    print(current.drop(columns=["fetched_at"]).to_string())
    print("\nMissing values in hourly:")
    print(hourly.drop(columns=["fetched_at"]).isna().sum().to_string())