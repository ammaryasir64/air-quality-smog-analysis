"""
dashboard/app.py

Streamlit dashboard: Air Quality & Smog Analysis for 20 Pakistani cities.

Data sources (Supabase, read-only publishable key SUPABASE_ANON_KEY):
  - current_air_quality : latest stored reading per city (cards, rankings)
  - air_quality         : hourly records (hourly chart)

IMPORTANT: Values are MODEL-BASED ESTIMATES (Open-Meteo / CAMS atmospheric
model), not direct ground-station measurements.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import config  # noqa: E402

load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="Pakistan Air Quality Dashboard",
    page_icon="🌫️",
    layout="wide",
)

CACHE_SECONDS = 300
LOCAL_TZ = "Asia/Karachi"
HOURLY_ROW_LIMIT = 500  # latest 500 hourly rows per city

POLLUTANT_CARDS = [
    ("pm2_5", "PM2.5", "µg/m³"),
    ("pm10", "PM10", "µg/m³"),
    ("carbon_monoxide", "Carbon Monoxide (CO)", "µg/m³"),
    ("sulphur_dioxide", "Sulphur Dioxide (SO₂)", "µg/m³"),
    ("nitrogen_dioxide", "Nitrogen Dioxide (NO₂)", "µg/m³"),
    ("ozone", "Ozone (O₃)", "µg/m³"),
]
POLLUTANT_LABELS = {key: label for key, label, _ in POLLUTANT_CARDS}
POLLUTANT_UNITS = {key: unit for key, _, unit in POLLUTANT_CARDS}

CATEGORY_COLORS = {
    "Good": "#22c55e",
    "Moderate": "#eab308",
    "Unhealthy for Sensitive Groups": "#f97316",
    "Unhealthy": "#ef4444",
    "Very Unhealthy": "#a855f7",
    "Hazardous": "#9f1239",
    "No data": "#94a3b8",
}

CSS = """
<style>
.block-container {padding-top: 1.5rem; max-width: 1200px;}
.card {background:#111a2e; border:1px solid #1f2b45; border-radius:14px;
       padding:16px 18px; margin-bottom:12px;}
.card-label {color:#94a3b8; font-size:0.85rem; margin-bottom:6px;}
.card-value {color:#f1f5f9; font-size:1.9rem; font-weight:700; line-height:1.1;}
.card-unit {color:#64748b; font-size:0.8rem; margin-top:4px;}
.hero {background:#111a2e; border:1px solid #1f2b45; border-radius:16px;
       padding:22px 24px; margin-bottom:16px;}
.hero-title {color:#94a3b8; font-size:0.9rem;}
.hero-aqi {font-size:3.6rem; font-weight:800; line-height:1.05;}
.hero-cat {font-size:1.2rem; font-weight:600; margin-top:2px;}
.hero-sub {color:#94a3b8; font-size:0.85rem; margin-top:10px;}
.note {color:#94a3b8; font-size:0.8rem;}
</style>
"""


def get_setting(name):
    """Read a setting from Streamlit secrets (cloud) or .env (local)."""
    try:
        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    value = os.getenv(name)
    return value.strip() if value else None


@st.cache_resource
def get_client():
    url = get_setting("SUPABASE_URL")
    key = get_setting("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_ANON_KEY is missing")
    return create_client(url, key)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading latest data from Supabase...")
def load_current():
    """Latest stored reading per city (table: current_air_quality)."""
    rows = get_client().table("current_air_quality").select("*").execute().data
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True).dt.tz_convert(LOCAL_TZ)
    df["time"] = pd.to_datetime(df["time"])
    return df


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading hourly data...")
def load_hourly(city):
    """Latest hourly rows for one city (table: air_quality)."""
    rows = (
        get_client()
        .table("air_quality")
        .select("time,us_aqi,european_aqi")
        .eq("city", city)
        .order("time", desc=True)
        .limit(HOURLY_ROW_LIMIT)
        .execute()
        .data
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values("time").reset_index(drop=True)


def us_aqi_category(value):
    if pd.isna(value):
        return "No data", CATEGORY_COLORS["No data"]
    if value <= 50:
        label = "Good"
    elif value <= 100:
        label = "Moderate"
    elif value <= 150:
        label = "Unhealthy for Sensitive Groups"
    elif value <= 200:
        label = "Unhealthy"
    elif value <= 300:
        label = "Very Unhealthy"
    else:
        label = "Hazardous"
    return label, CATEGORY_COLORS[label]


def european_aqi_category(value):
    if pd.isna(value):
        return "No data"
    if value <= 20:
        return "Good"
    if value <= 40:
        return "Fair"
    if value <= 60:
        return "Moderate"
    if value <= 80:
        return "Poor"
    if value <= 100:
        return "Very Poor"
    return "Extremely Poor"


def fmt(value, decimals=1):
    return "N/A" if pd.isna(value) else f"{value:.{decimals}f}"


def fmt_time(ts):
    return "N/A" if pd.isna(ts) else ts.strftime("%d %b %Y, %I:%M %p")


def style_figure(fig, height=480):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig


# ---------------------------------------------------------------- page
st.markdown(CSS, unsafe_allow_html=True)
st.title("🌫️ Pakistan Air Quality & Smog Dashboard")
st.caption("Model-estimated air quality for 20 Pakistani cities")

top_left, top_right = st.columns([3, 1])
with top_left:
    city = st.selectbox("Select city", list(config.CITIES.keys()), index=0)
with top_right:
    st.write("")
    st.write("")
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()

try:
    current = load_current()
except Exception as exc:
    st.error(f"Could not load data from Supabase: {exc}")
    st.stop()

if current.empty:
    st.warning("No data found in current_air_quality yet. Run the ETL pipeline first.")
    st.stop()

match = current[current["city"] == city]
if match.empty:
    st.warning(f"No stored reading for {city} yet.")
    st.stop()
row = match.iloc[0]

# ---- Overall AQI card
us_label, us_color = us_aqi_category(row["us_aqi"])
eu_label = european_aqi_category(row["european_aqi"])
hero = (
    '<div class="hero">'
    f'<div class="hero-title">{city}, {row["province"]} · Overall Air Quality (US AQI)</div>'
    f'<div class="hero-aqi" style="color:{us_color}">{fmt(row["us_aqi"], 0)}</div>'
    f'<div class="hero-cat" style="color:{us_color}">{us_label}</div>'
    f'<div class="hero-sub">European AQI: {fmt(row["european_aqi"], 0)} ({eu_label})'
    f' · Model time: {fmt_time(row["time"])} (PKT)</div>'
    "</div>"
)
st.markdown(hero, unsafe_allow_html=True)

# ---- Six pollutant cards (3 columns x 2 rows; stacks on small screens)
st.subheader("Pollutants")
for start in range(0, len(POLLUTANT_CARDS), 3):
    cols = st.columns(3)
    for col, (key, label, unit) in zip(cols, POLLUTANT_CARDS[start:start + 3]):
        card = (
            '<div class="card">'
            f'<div class="card-label">{label}</div>'
            f'<div class="card-value">{fmt(row[key])}</div>'
            f'<div class="card-unit">{unit}</div>'
            "</div>"
        )
        col.markdown(card, unsafe_allow_html=True)

# ---- Charts
st.subheader("Analysis")
tab_hourly, tab_rank, tab_poll = st.tabs(
    ["📈 Hourly AQI", "🏆 City Rankings", "🧪 Pollutant Comparison"]
)

# Tab 1: hourly AQI for the selected city (table: air_quality)
with tab_hourly:
    try:
        hourly = load_hourly(city)
    except Exception as exc:
        hourly = None
        st.error(f"Could not load hourly data: {exc}")

    if hourly is not None:
        hourly = hourly.dropna(subset=["us_aqi"])
        if hourly.empty:
            st.info(f"No hourly records stored for {city} yet.")
        else:
            now_local = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
            past = hourly[hourly["time"] <= now_local]
            future = hourly[hourly["time"] > now_local]
            if not past.empty and not future.empty:
                # connect the two lines so there is no visual gap
                future = pd.concat([past.tail(1), future])

            fig = go.Figure()
            if not past.empty:
                fig.add_trace(go.Scatter(
                    x=past["time"], y=past["us_aqi"], mode="lines",
                    name="Stored model data (past)",
                    line=dict(color="#38bdf8", width=3)))
            if not future.empty:
                fig.add_trace(go.Scatter(
                    x=future["time"], y=future["us_aqi"], mode="lines",
                    name="Model forecast",
                    line=dict(color="#a78bfa", width=3, dash="dash")))
            for limit in (50, 100, 150, 200):
                fig.add_hline(y=limit, line_dash="dot", line_color="#334155", line_width=1)
            fig.update_layout(
                title=f"Hourly US AQI: {city} (Asia/Karachi time)",
                xaxis_title="Time (PKT)", yaxis_title="US AQI",
                legend=dict(orientation="h", y=-0.2),
            )
            st.plotly_chart(style_figure(fig), use_container_width=True)
            st.caption(
                "Dotted lines mark US AQI category limits (50, 100, 150, 200). The dashed "
                "line shows model FORECAST hours, not recorded readings. "
                f"Showing up to the latest {HOURLY_ROW_LIMIT} stored hourly rows."
            )

# Tab 2: ranking of all 20 cities (table: current_air_quality)
with tab_rank:
    rank = current[["city", "province", "us_aqi", "european_aqi"]].dropna(subset=["us_aqi"]).copy()
    rank["category"] = rank["us_aqi"].apply(lambda v: us_aqi_category(v)[0])
    rank = rank.sort_values("us_aqi", ascending=False).reset_index(drop=True)

    if city in rank["city"].tolist():
        position = rank.index[rank["city"] == city][0] + 1
        st.markdown(
            f"**{city}** is ranked **#{position} of {len(rank)}** "
            "(1 = highest US AQI, most polluted)."
        )

    fig = px.bar(
        rank.sort_values("us_aqi"), x="us_aqi", y="city", orientation="h",
        color="category", color_discrete_map=CATEGORY_COLORS, text="us_aqi",
        hover_data={"province": True, "european_aqi": True, "category": False},
        title="Latest US AQI by city",
        labels={"us_aqi": "US AQI", "city": "", "european_aqi": "European AQI"},
    )
    fig.update_traces(texttemplate="%{x:.0f}", textposition="outside")
    fig.update_layout(legend_title_text="US AQI category")
    st.plotly_chart(style_figure(fig, height=640), use_container_width=True)

# Tab 3: compare one pollutant across all 20 cities (table: current_air_quality)
with tab_poll:
    pollutant = st.selectbox(
        "Pollutant", list(POLLUTANT_LABELS.keys()),
        format_func=lambda k: POLLUTANT_LABELS[k], key="pollutant_select",
    )
    comp = current[["city", pollutant]].dropna().sort_values(pollutant).copy()
    comp["highlight"] = comp["city"].eq(city).map(
        {True: "Selected city", False: "Other cities"}
    )
    fig = px.bar(
        comp, x=pollutant, y="city", orientation="h", color="highlight",
        color_discrete_map={"Selected city": "#f59e0b", "Other cities": "#38bdf8"},
        text=pollutant,
        title=f"{POLLUTANT_LABELS[pollutant]} by city ({POLLUTANT_UNITS[pollutant]})",
        labels={pollutant: POLLUTANT_UNITS[pollutant], "city": ""},
    )
    fig.update_traces(texttemplate="%{x:.1f}", textposition="outside")
    fig.update_layout(legend_title_text="")
    st.plotly_chart(style_figure(fig, height=640), use_container_width=True)
    st.caption("Each pollutant is shown on its own scale; pollutants are not mixed in one chart.")

# ---- Freshness + disclaimer
st.divider()
st.markdown(
    f"**Last Updated:** {fmt_time(row['fetched_at'])} (PKT) · "
    f"Latest stored record (all cities): {fmt_time(current['fetched_at'].max())} (PKT)"
)
st.markdown(
    '<p class="note">"Last Updated" is when our ETL pipeline fetched the data. '
    f"This page caches data for up to {CACHE_SECONDS // 60} minutes. The refresh button reloads "
    "from the database only; it does not call the Open-Meteo API. New data arrives when the "
    "scheduled ETL runs (every 12 hours).</p>",
    unsafe_allow_html=True,
)
st.info(
    "**Data source:** Open-Meteo Air Quality API (CAMS atmospheric model). Values are "
    "model-based estimates, not direct measurements from ground monitoring stations, and "
    "not guaranteed minute-by-minute live readings."
)