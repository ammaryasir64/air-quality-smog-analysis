"""
eda.py

Exploratory Data Analysis (EDA) with pandas and Plotly.

Reads the stored hourly records from the Supabase table `air_quality`
(read-only publishable key) and writes interactive charts to charts/.

NOTE: Values are MODEL-BASED ESTIMATES (Open-Meteo / CAMS), not ground-station
measurements. The hourly table also contains model FORECAST hours.
"""

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = ROOT / "charts"
PAGE_SIZE = 1000  # Supabase returns at most 1000 rows per request

POLLUTANT_LABELS = {
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "carbon_monoxide": "CO",
    "sulphur_dioxide": "SO2",
    "nitrogen_dioxide": "NO2",
    "ozone": "O3",
}
VALUE_COLUMNS = list(POLLUTANT_LABELS) + ["us_aqi", "european_aqi"]
COLUMNS = "city,time," + ",".join(VALUE_COLUMNS)
TEMPLATE = "plotly_dark"


def load_hourly():
    """Download ALL rows of air_quality, page by page."""
    load_dotenv(ROOT / ".env")
    client = create_client(
        os.getenv("SUPABASE_URL").strip(), os.getenv("SUPABASE_ANON_KEY").strip()
    )
    rows, start = [], 0
    while True:
        batch = (
            client.table("air_quality")
            .select(COLUMNS)
            .order("city")
            .order("time")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data
        )
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df


def save(fig, name):
    CHARTS_DIR.mkdir(exist_ok=True)
    path = CHARTS_DIR / name
    fig.write_html(path, include_plotlyjs="cdn")
    print("  saved:", path.name)


def main():
    df = load_hourly()
    if df.empty:
        raise SystemExit("No data found in air_quality.")

    print("=== DATA OVERVIEW ===")
    print("Rows:", len(df), "| Cities:", df["city"].nunique())
    print("Time range:", df["time"].min(), "to", df["time"].max())
    print("Days covered:", df["time"].dt.date.nunique())
    print("Note: includes model forecast hours; only a few days of history so far.")

    # 1. Missing values
    print("\n=== 1. MISSING VALUES ===")
    missing = df[VALUE_COLUMNS].isna().sum().reset_index()
    missing.columns = ["column", "missing_count"]
    missing["missing_percent"] = (missing["missing_count"] / len(df) * 100).round(2)
    print(missing.to_string(index=False))
    fig = px.bar(missing, x="column", y="missing_count", text="missing_count",
                 title="Missing values per column", template=TEMPLATE)
    save(fig, "01_missing_values.html")

    # 2. City ranking by average US AQI
    print("\n=== 2. CITY RANKING (average US AQI) ===")
    rank = df.groupby("city")["us_aqi"].mean().round(1).sort_values(ascending=False)
    print(rank.to_string())
    fig = px.bar(rank.sort_values().reset_index(), x="us_aqi", y="city", orientation="h",
                 title="Average US AQI by city (highest = most polluted)",
                 template=TEMPLATE, labels={"us_aqi": "Average US AQI"})
    fig.update_layout(height=700)
    save(fig, "02_city_aqi_ranking.html")

    # 3. PM2.5 vs PM10 by city
    pm = df.groupby("city")[["pm2_5", "pm10"]].mean().round(1).reset_index()
    pm = pm.sort_values("pm2_5", ascending=False)
    fig = px.bar(pm.melt(id_vars="city", var_name="pollutant", value_name="avg µg/m³"),
                 x="city", y="avg µg/m³", color="pollutant", barmode="group",
                 title="Average PM2.5 and PM10 by city (µg/m³)", template=TEMPLATE)
    save(fig, "03_pm25_pm10_by_city.html")

    # 4. All six pollutants, one panel each (separate scales, no mixing)
    means = df.groupby("city")[list(POLLUTANT_LABELS)].mean().reset_index()
    long = means.melt(id_vars="city", var_name="pollutant", value_name="mean")
    long["pollutant"] = long["pollutant"].map(POLLUTANT_LABELS)
    fig = px.bar(long, x="city", y="mean", facet_col="pollutant", facet_col_wrap=2,
                 title="Average of each pollutant by city (each panel has its own scale)",
                 template=TEMPLATE)
    fig.update_yaxes(matches=None, showticklabels=True)
    fig.update_xaxes(showticklabels=True, tickangle=60)
    fig.update_layout(height=1100)
    save(fig, "04_pollutants_by_city.html")

    # 5. Hourly pattern: average US AQI per hour of day (all cities)
    df["hour"] = df["time"].dt.hour
    hourly = df.groupby("hour")["us_aqi"].mean().round(1).reset_index()
    print("\n=== 5. HOURLY PATTERN (average US AQI by hour of day) ===")
    print("Highest hour:", int(hourly.loc[hourly["us_aqi"].idxmax(), "hour"]),
          "| Lowest hour:", int(hourly.loc[hourly["us_aqi"].idxmin(), "hour"]))
    fig = px.line(hourly, x="hour", y="us_aqi", markers=True,
                  title="Average US AQI by hour of day (all cities, Asia/Karachi time)",
                  template=TEMPLATE, labels={"us_aqi": "Average US AQI", "hour": "Hour"})
    save(fig, "05_hourly_pattern.html")

    # 6. AQI over time for the 5 most polluted cities
    top5 = rank.head(5).index.tolist()
    fig = px.line(df[df["city"].isin(top5)], x="time", y="us_aqi", color="city",
                  title="US AQI over time: 5 most polluted cities",
                  template=TEMPLATE)
    save(fig, "06_top5_aqi_over_time.html")

    # 7. Distributions
    fig = px.histogram(df, x="us_aqi", nbins=40,
                       title="Distribution of hourly US AQI (all cities)",
                       template=TEMPLATE)
    save(fig, "07a_aqi_histogram.html")
    order = rank.index.tolist()
    fig = px.box(df, x="city", y="us_aqi", category_orders={"city": order},
                 title="US AQI distribution by city (sorted by average)",
                 template=TEMPLATE)
    save(fig, "07b_aqi_box_by_city.html")

    print("\nDone. Open the .html files in the charts folder with your browser.")


if __name__ == "__main__":
    main()