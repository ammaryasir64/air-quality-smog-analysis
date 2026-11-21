"""
eda.py

Exploratory Data Analysis (EDA) with pandas and Plotly (no Matplotlib).

Reads the stored hourly records from the Supabase table `openweather_air_quality`
with the read-only key (SUPABASE_ANON_KEY) and writes interactive charts to charts/.

Notes
- Only PAST hours are analysed. The table also holds model FORECAST hours; they are
  excluded because they are estimates of the future, not stored history.
- All cities are compared over the same time window.
- Values are MODEL-BASED ESTIMATES (OpenWeather / SILAM), not station measurements.
- us_aqi_calc is a US AQI calculated by our ETL (PM2.5 and PM10 use 24-hour means).
"""

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv
from plotly.subplots import make_subplots
from supabase import create_client

try:
    import config
except ImportError:  # when imported as src.eda
    from src import config

ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = ROOT / "charts"
TABLE = "openweather_air_quality"
PAGE_SIZE = 1000  # Supabase returns at most 1000 rows per request
TEMPLATE = "plotly_dark"

POLLUTANTS = {
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "carbon_monoxide": "CO",
    "sulphur_dioxide": "SO2",
    "nitrogen_dioxide": "NO2",
    "ozone": "O3",
}
VALUE_COLUMNS = ["us_aqi_calc", "ow_aqi"] + list(POLLUTANTS)
COLUMNS = "city,time," + ",".join(VALUE_COLUMNS)
OW_LABELS = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
COLORS = {
    "Good": "#22c55e", "Moderate": "#eab308", "Unhealthy for Sensitive Groups": "#f97316",
    "Unhealthy": "#ef4444", "Very Unhealthy": "#a855f7", "Hazardous": "#9f1239",
}


def category(value):
    if pd.isna(value):
        return "No data"
    for limit, name in [(50, "Good"), (100, "Moderate"), (150, "Unhealthy for Sensitive Groups"),
                        (200, "Unhealthy"), (300, "Very Unhealthy")]:
        if value <= limit:
            return name
    return "Hazardous"


def load_hourly():
    """Download ALL rows of the hourly table, page by page."""
    load_dotenv(ROOT / ".env")
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("SUPABASE_URL or SUPABASE_ANON_KEY is missing in .env")
    client = create_client(url, key)

    rows, start = [], 0
    while True:
        batch = (
            client.table(TABLE).select(COLUMNS).order("city").order("time")
            .range(start, start + PAGE_SIZE - 1).execute().data
        )
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit(f"No data found in {TABLE}.")
    df["time"] = pd.to_datetime(df["time"])
    for column in VALUE_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def style(fig, height=None):
    fig.update_layout(template=TEMPLATE)
    if height:
        fig.update_layout(height=height)
    return fig


def save(fig, name):
    CHARTS_DIR.mkdir(exist_ok=True)
    path = CHARTS_DIR / name
    fig.write_html(path, include_plotlyjs="cdn")
    print("  saved:", path.name)


def main():
    df = load_hourly()
    now = pd.Timestamp.now(tz=config.TIMEZONE).tz_localize(None)
    past = df[df["time"] <= now].copy()
    if past.empty:
        raise SystemExit("No past hours stored yet.")

    # one common window for all cities, so rankings are fair
    window_start = past.groupby("city")["time"].min().max()
    window_end = past.groupby("city")["time"].max().min()
    w = past[(past["time"] >= window_start) & (past["time"] <= window_end)].copy()

    print("=== DATA OVERVIEW ===")
    print("Stored rows:", len(df), "| forecast rows excluded:", len(df) - len(past))
    print("Cities:", w["city"].nunique())
    print("Analysis window (all cities, past hours only):", window_start, "to", window_end)
    print("Days covered:", w["time"].dt.date.nunique(), "| rows analysed:", len(w))
    print("Rows per city (min/max):", w.groupby("city").size().min(), "/", w.groupby("city").size().max())

    # 1. Data completeness / missing values
    print("\n=== 1. MISSING VALUES ===")
    missing = w[VALUE_COLUMNS].isna().sum().reset_index()
    missing.columns = ["column", "missing_count"]
    missing["missing_percent"] = (missing["missing_count"] / len(w) * 100).round(2)
    print(missing.to_string(index=False))
    missing["available_percent"] = 100 - missing["missing_percent"]
    fig = px.bar(missing, x="column", y="available_percent", text="available_percent",
                 title="Data completeness: share of hours with a value (%)")
    fig.update_traces(texttemplate="%{text:.1f}%")
    fig.update_yaxes(range=[0, 105], title="Available (%)")
    save(style(fig), "01_data_completeness.html")

    # 2. City ranking by average calculated US AQI
    print("\n=== 2. CITY RANKING (average calculated US AQI) ===")
    stats = (
        w.groupby("city").agg(
            mean_aqi=("us_aqi_calc", "mean"),
            max_aqi=("us_aqi_calc", "max"),
            mean_pm25=("pm2_5", "mean"),
            mean_pm10=("pm10", "mean"),
            pct_hours_above_150=("us_aqi_calc", lambda s: (s > 150).mean() * 100),
        ).round(1).sort_values("mean_aqi", ascending=False)
    )
    print(stats.to_string())
    rank = stats.reset_index()
    rank["category"] = rank["mean_aqi"].apply(category)
    fig = px.bar(rank, x="mean_aqi", y="city", orientation="h", color="category",
                 color_discrete_map=COLORS, text="mean_aqi",
                 title="Average US AQI (calculated) by city, highest at the top",
                 labels={"mean_aqi": "Average US AQI (calculated)", "city": ""})
    fig.update_yaxes(categoryorder="array", dtick=1,
                     categoryarray=rank.sort_values("mean_aqi")["city"].tolist())
    save(style(fig, max(520, 24 * len(rank))), "02_city_aqi_ranking.html")

    # 3. PM2.5 and PM10 by city
    pm = stats[["mean_pm25", "mean_pm10"]].sort_values("mean_pm25").reset_index()
    long = pm.melt("city", var_name="pollutant", value_name="average (ug/m3)")
    long["pollutant"] = long["pollutant"].map({"mean_pm25": "PM2.5", "mean_pm10": "PM10"})
    fig = px.bar(long, x="average (ug/m3)", y="city", color="pollutant", orientation="h",
                 barmode="group", title="Average PM2.5 and PM10 by city (µg/m³)")
    fig.update_yaxes(categoryorder="array", categoryarray=pm["city"].tolist(), dtick=1, title="")
    save(style(fig, max(600, 30 * len(pm))), "03_pm25_pm10_by_city.html")

    # 4. All six pollutants by city (heatmap; colour is relative per pollutant)
    means = w.groupby("city")[list(POLLUTANTS)].mean().sort_values("pm2_5", ascending=False)
    relative = means / means.max()
    fig = go.Figure(go.Heatmap(
        z=relative.values, x=[POLLUTANTS[c] for c in means.columns], y=means.index.tolist(),
        text=means.round(1).values, texttemplate="%{text}", colorscale="YlOrRd",
        colorbar=dict(title="Relative to the<br>highest city"),
    ))
    fig.update_yaxes(autorange="reversed", dtick=1)
    fig.update_layout(title="Average of each pollutant by city (µg/m³). Colour is relative within each pollutant")
    save(style(fig, max(600, 24 * len(means))), "04_pollutant_heatmap.html")

    # 5. Hourly pattern: average by hour of day (all cities)
    w["hour"] = w["time"].dt.hour
    by_hour = w.groupby("hour")[["pm2_5", "us_aqi_calc"]].mean().round(1)
    hi, lo = int(by_hour["pm2_5"].idxmax()), int(by_hour["pm2_5"].idxmin())
    print("\n=== 5. HOURLY PATTERN (PM2.5, all cities) ===")
    print("Highest hour:", hi, "| Lowest hour:", lo)
    print("Average PM2.5 at those hours:", by_hour.loc[hi, "pm2_5"], "/", by_hour.loc[lo, "pm2_5"], "ug/m3")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
                        subplot_titles=("Average PM2.5 by hour of day (µg/m³)",
                                        "Average US AQI (calculated) by hour of day"))
    fig.add_trace(go.Scatter(x=by_hour.index, y=by_hour["pm2_5"], mode="lines+markers",
                             name="PM2.5"), row=1, col=1)
    fig.add_trace(go.Scatter(x=by_hour.index, y=by_hour["us_aqi_calc"], mode="lines+markers",
                             name="US AQI (calculated)"), row=2, col=1)
    fig.update_xaxes(title_text="Hour of day (Asia/Karachi)", row=2, col=1)
    save(style(fig, 650), "05_hourly_pattern.html")

    # 6. Five most polluted cities over time
    top5 = stats.head(5).index.tolist()
    fig = px.line(w[w["city"].isin(top5)], x="time", y="us_aqi_calc", color="city",
                  title="US AQI (calculated) over time: 5 cities with the highest average")
    save(style(fig), "06_top5_aqi_over_time.html")

    # 7. Distributions
    fig = px.histogram(w, x="us_aqi_calc", nbins=40,
                       title="Distribution of hourly US AQI (calculated), all cities")
    for limit in (50, 100, 150, 200, 300):
        fig.add_vline(x=limit, line_dash="dot", line_color="#94a3b8")
    save(style(fig), "07a_aqi_histogram.html")
    order = stats.sort_values("mean_aqi").index.tolist()
    fig = px.box(w, x="us_aqi_calc", y="city", orientation="h", category_orders={"city": order},
                 title="US AQI (calculated) distribution by city (sorted by average)")
    fig.update_yaxes(dtick=1, title="")
    save(style(fig, max(600, 24 * len(order))), "07b_aqi_box_by_city.html")

    # 8. Correlation between pollutants
    corr = w[list(POLLUTANTS)].corr().round(2)
    labels = [POLLUTANTS[c] for c in corr.columns]
    fig = px.imshow(corr.values, x=labels, y=labels, text_auto=True, zmin=-1, zmax=1,
                    color_continuous_scale="RdBu_r",
                    title="Correlation between pollutants (hourly values, all cities)")
    save(style(fig, 560), "08_pollutant_correlation.html")

    # 9. OpenWeather's 1-5 index versus our 0-500 US AQI
    ow = w.dropna(subset=["ow_aqi", "us_aqi_calc"]).copy()
    ow["ow_int"] = ow["ow_aqi"].astype(int)
    ow["OpenWeather index"] = ow["ow_int"].map(lambda v: f"{v} ({OW_LABELS[v]})")
    summary = ow.groupby("ow_int")["us_aqi_calc"].agg(hours="count", min="min", mean="mean", max="max").round(1)
    print("\n=== 9. OPENWEATHER 1-5 INDEX vs CALCULATED US AQI ===")
    print(summary.to_string())
    order_ow = [f"{k} ({v})" for k, v in OW_LABELS.items()]
    fig = px.box(ow, x="OpenWeather index", y="us_aqi_calc",
                 category_orders={"OpenWeather index": order_ow},
                 title="Calculated US AQI inside each OpenWeather index level")
    save(style(fig), "09_openweather_vs_us_aqi.html")

    print("\nDone. Open the .html files in the charts folder with your browser.")


if __name__ == "__main__":
    main()