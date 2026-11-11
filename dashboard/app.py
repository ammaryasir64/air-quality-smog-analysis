"""
dashboard/app.py

Air Quality & Smog Analysis dashboard (Streamlit), Aeris-inspired design.

Data (Supabase, read-only key SUPABASE_ANON_KEY):
  current_air_quality : latest stored reading per city
  air_quality         : hourly records (past + model forecast hours)

Values are MODEL-BASED ESTIMATES (Open-Meteo / CAMS), not ground-station
measurements. No number on this dashboard is invented.
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
sys.path.insert(0, str(ROOT / "dashboard"))
import config  # noqa: E402
import theme  # noqa: E402

load_dotenv(ROOT / ".env")
st.set_page_config(page_title="Pakistan Air Quality", page_icon="🌫️", layout="wide")
theme.inject_theme()

CACHE_SECONDS = 300
LOCAL_TZ = "Asia/Karachi"
PAGES = ["🏠 Home", "📊 Air Quality Analytics", "📡 Live Monitoring", "🌫️ Smog Analysis",
         "🕘 Historical Data", "🔮 Model Forecast", "❤️ Health Advisory", "🚨 Alerts"]
POLLUTANTS = [("pm2_5", "PM2.5"), ("pm10", "PM10"), ("carbon_monoxide", "Carbon Monoxide (CO)"),
              ("sulphur_dioxide", "Sulphur Dioxide (SO₂)"), ("nitrogen_dioxide", "Nitrogen Dioxide (NO₂)"),
              ("ozone", "Ozone (O₃)")]
LABELS = dict(POLLUTANTS)
COLORS = {"Good": "#22c55e", "Moderate": "#eab308", "Unhealthy for Sensitive Groups": "#f97316",
          "Unhealthy": "#ef4444", "Very Unhealthy": "#a855f7", "Hazardous": "#9f1239", "No data": "#94a3b8"}
ORDER = list(COLORS)[:-1]
ADVICE = {
    "Good": "Air quality is satisfactory. Normal outdoor activity is fine.",
    "Moderate": "Acceptable for most people. Unusually sensitive people may limit long outdoor exertion.",
    "Unhealthy for Sensitive Groups": "Children, older adults and people with heart or lung disease should reduce prolonged outdoor exertion.",
    "Unhealthy": "Everyone may feel effects. Sensitive groups should avoid outdoor exertion; others should limit it.",
    "Very Unhealthy": "Health alert. Avoid outdoor activity; sensitive groups should stay indoors.",
    "Hazardous": "Emergency conditions. Everyone should avoid outdoor exertion.",
}
RANGES = {
    "Good": "0 to 50",
    "Moderate": "51 to 100",
    "Unhealthy for Sensitive Groups": "101 to 150",
    "Unhealthy": "151 to 200",
    "Very Unhealthy": "201 to 300",
    "Hazardous": "301 and above",
}


def get_setting(name):
    try:
        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    value = os.getenv(name)
    return value.strip() if value else None


@st.cache_resource
def get_client():
    url, key = get_setting("SUPABASE_URL"), get_setting("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_ANON_KEY is missing")
    return create_client(url, key)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading latest data...")
def load_current():
    df = pd.DataFrame(get_client().table("current_air_quality").select("*").execute().data)
    if not df.empty:
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True).dt.tz_convert(LOCAL_TZ)
        df["time"] = pd.to_datetime(df["time"])
    return df


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading hourly data...")
def load_hourly(city):
    rows = (get_client().table("air_quality").select("time,us_aqi,european_aqi").eq("city", city)
            .order("time", desc=True).limit(500).execute().data)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values("time").reset_index(drop=True)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading stored hourly records...")
def load_all_hourly():
    rows, start = [], 0
    while True:
        batch = (get_client().table("air_quality").select("city,time,us_aqi")
                 .order("city").order("time").range(start, start + 999).execute().data)
        rows.extend(batch)
        if len(batch) < 1000:
            break
        start += 1000
    df = pd.DataFrame(rows)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
    return df


def category(v):
    if pd.isna(v):
        return "No data"
    for limit, name in [(50, "Good"), (100, "Moderate"), (150, "Unhealthy for Sensitive Groups"),
                        (200, "Unhealthy"), (300, "Very Unhealthy")]:
        if v <= limit:
            return name
    return "Hazardous"


def fmt(v, d=1):
    return "Data Not Available" if pd.isna(v) else f"{v:.{d}f}"


def fmt_time(ts):
    return "N/A" if pd.isna(ts) else ts.strftime("%d %b %Y, %I:%M %p")


def style(fig, h=420):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=h, margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="Plus Jakarta Sans, sans-serif"))
    return fig


def hourly_fig(hourly, city, past=True, future=True):
    now = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
    p, f = hourly[hourly["time"] <= now], hourly[hourly["time"] > now]
    if past and future and not p.empty and not f.empty:
        f = pd.concat([p.tail(1), f])
    fig = go.Figure()
    if past and not p.empty:
        fig.add_trace(go.Scatter(x=p["time"], y=p["us_aqi"], mode="lines", name="Stored model data",
                                 line=dict(color="#38bdf8", width=3), fill="tozeroy",
                                 fillcolor="rgba(56,189,248,.08)"))
    if future and not f.empty:
        fig.add_trace(go.Scatter(x=f["time"], y=f["us_aqi"], mode="lines", name="Model forecast",
                                 line=dict(color="#a78bfa", width=3, dash="dash")))
    for lim in (50, 100, 150, 200):
        fig.add_hline(y=lim, line_dash="dot", line_color="#334155", line_width=1)
    fig.update_layout(title=f"Hourly US AQI: {city} (Asia/Karachi time)", yaxis_title="US AQI",
                      legend=dict(orientation="h", y=-0.2))
    return style(fig)


def bar_cities(df, col, title, highlight, h=620, fmt_str="%{x:.0f}"):
    d = df[["city", col]].dropna().sort_values(col).copy()
    d["group"] = d["city"].eq(highlight).map({True: "Selected city", False: "Other cities"})
    fig = px.bar(d, x=col, y="city", orientation="h", color="group", text=col, title=title,
                 color_discrete_map={"Selected city": "#f59e0b", "Other cities": "#38bdf8"},
                 labels={col: "", "city": ""})
    fig.update_traces(texttemplate=fmt_str, textposition="outside")
    fig.update_layout(legend_title_text="")
    return style(fig, h)


# ------------------------------------------------------------ sidebar
try:
    current = load_current()
except Exception as exc:
    st.error(f"Could not load data from Supabase: {exc}")
    st.stop()
if current.empty:
    st.warning("No data in current_air_quality yet. Run the ETL pipeline first.")
    st.stop()

with st.sidebar:
    st.markdown("### 🌫️ Pakistan Air Quality")
    page = st.radio("Navigation", PAGES, label_visibility="collapsed")
    city = st.selectbox("City", list(config.CITIES.keys()))
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Latest stored record: {fmt_time(current['fetched_at'].max())} (PKT)")

match = current[current["city"] == city]
if match.empty:
    st.warning(f"No stored reading for {city} yet.")
    st.stop()
row = match.iloc[0]
cat = category(row["us_aqi"])
color = COLORS[cat]


def pollutant_cards(cols_per_row=3):
    for i in range(0, len(POLLUTANTS), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, (key, label) in zip(cols, POLLUTANTS[i:i + cols_per_row]):
            col.markdown(theme.glass_card(label, fmt(row[key]), "µg/m³",
                                          f"Model estimate for {city}. Model time: {fmt_time(row['time'])} (PKT)"),
                         unsafe_allow_html=True)


# ------------------------------------------------------------ pages
if page == PAGES[0]:
    st.title("Air Quality and Smog Analysis")
    st.caption("Monitoring Pakistan's Air Quality • Understanding Smog • Model Forecasts")
    c1, c2, c3 = st.columns([2, 1, 1])
    hero = ('<div class="glass hero-glass">'
            f'<div>{theme.gauge_svg(row["us_aqi"], "US AQI", color)}</div>'
            '<div class="hero-text">'
            f'<div class="hero-title">{city}, {row["province"]}</div>'
            f'<div class="hero-cat" style="color:{color}">{cat}</div>'
            f'<div class="hero-sub">European AQI: {fmt(row["european_aqi"], 0)}<br>'
            f'Model time: {fmt_time(row["time"])} (PKT)</div></div></div>')
    c1.markdown(hero, unsafe_allow_html=True)
    c2.markdown(theme.glass_card("PM2.5", fmt(row["pm2_5"]), "µg/m³", "Fine particles (model estimate)", "#38bdf8"),
                unsafe_allow_html=True)
    c3.markdown(theme.glass_card("PM10", fmt(row["pm10"]), "µg/m³", "Coarse particles (model estimate)", "#a78bfa"),
                unsafe_allow_html=True)
    left, right = st.columns(2)
    hourly = load_hourly(city)
    with left:
        if hourly.empty or hourly["us_aqi"].isna().all():
            st.info("Data Not Available: no hourly records stored for this city.")
        else:
            st.plotly_chart(hourly_fig(hourly.dropna(subset=["us_aqi"]), city))
    with right:
        top = current.dropna(subset=["us_aqi"]).nlargest(10, "us_aqi")
        st.plotly_chart(bar_cities(top, "us_aqi", "10 highest US AQI cities (latest)", city, 420))
    a, b = st.columns(2)
    a.markdown(theme.glass_card("Health advisory", cat, "",
                                ADVICE.get(cat, "No advisory available."), color), unsafe_allow_html=True)
    worst = current.dropna(subset=["us_aqi"]).nlargest(3, "us_aqi")
    txt = "<br>".join(f"{r.city}: US AQI {r.us_aqi:.0f} ({category(r.us_aqi)})" for r in worst.itertuples())
    b.markdown(theme.glass_card("Recent pollution alerts (3 highest)", f"{len(worst)} cities", "", txt, "#ef4444"),
               unsafe_allow_html=True)
    st.caption("CO2, temperature and humidity are not collected by this project, so they are not shown.")

elif page == PAGES[1]:
    st.title("Air Quality Analytics")
    pollutant_cards()
    hourly = load_hourly(city)
    if hourly.empty or hourly["us_aqi"].isna().all():
        st.info("Data Not Available: no hourly records stored for this city.")
    else:
        st.plotly_chart(hourly_fig(hourly.dropna(subset=["us_aqi"]), city))
    sel = st.selectbox("Compare one pollutant across all cities", list(LABELS), format_func=LABELS.get)
    st.plotly_chart(bar_cities(current, sel, f"{LABELS[sel]} by city (µg/m³)", city, fmt_str="%{x:.1f}"))
    pm = current[["city", "pm2_5", "pm10"]].dropna().sort_values("pm2_5", ascending=False)
    fig = px.bar(pm.melt("city", var_name="pollutant", value_name="µg/m³"), x="city", y="µg/m³",
                 color="pollutant", barmode="group", title="PM2.5 and PM10 by city (µg/m³)")
    st.plotly_chart(style(fig))

elif page == PAGES[2]:
    st.title("Live Monitoring")
    st.caption("Latest stored model estimate per city. Data updates when the ETL runs (every 12 hours).")
    m = current.dropna(subset=["us_aqi", "latitude", "longitude"]).copy()
    m["category"] = m["us_aqi"].apply(category)
    fig = px.scatter_map(m, lat="latitude", lon="longitude", color="us_aqi", hover_name="city",
                         hover_data={"province": True, "category": True, "pm2_5": ":.1f", "pm10": ":.1f",
                                     "latitude": False, "longitude": False},
                         color_continuous_scale=["#22c55e", "#eab308", "#f97316", "#ef4444", "#a855f7"],
                         range_color=(0, 300), zoom=4.3, map_style="carto-darkmatter",
                         labels={"us_aqi": "US AQI"}, title="US AQI by city")
    fig.update_traces(marker=dict(size=18))
    fig.update_layout(map=dict(center=dict(lat=30.3, lon=69.3), zoom=4.4))
    st.plotly_chart(style(fig, 560))
    t = current[["city", "province", "us_aqi", "european_aqi", "pm2_5", "pm10", "fetched_at"]].sort_values(
        "us_aqi", ascending=False)
    t["fetched_at"] = t["fetched_at"].dt.strftime("%d %b %I:%M %p")
    t.columns = ["City", "Province", "US AQI", "European AQI",
                 "PM2.5 (µg/m³)", "PM10 (µg/m³)", "Fetched (PKT)"]
    table_html = t.to_html(index=False, border=0, na_rep="Data Not Available",
                           float_format=lambda v: f"{v:.1f}", classes="aq-table")
    st.markdown(
        "<style>.aq-table{width:100%;border-collapse:collapse;font-size:.85rem;color:#e2e8f0}"
        ".aq-table th{text-align:left;padding:8px 10px;color:#94a3b8;"
        "border-bottom:1px solid rgba(56,189,248,.25)}"
        ".aq-table td{padding:7px 10px;border-bottom:1px solid rgba(148,163,184,.1)}"
        ".aq-table tr:hover td{background:rgba(56,189,248,.08)}</style>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="glass" style="overflow-x:auto">' + table_html.replace("\n", "") + "</div>",
        unsafe_allow_html=True,
    )

elif page == PAGES[3]:
    st.title("Smog Analysis")
    st.caption("Cities grouped by US AQI category (standard AQI ranges applied to stored values).")
    counts = (current["us_aqi"].apply(category).value_counts().reindex(ORDER, fill_value=0).reset_index())
    counts.columns = ["category", "cities"]
    fig = px.bar(counts, x="category", y="cities", color="category", color_discrete_map=COLORS, text="cities",
                 title="Number of cities per AQI category")
    st.plotly_chart(style(fig, 380))
    st.markdown(theme.glass_card(f"{city} AQI category", cat, f"US AQI {fmt(row['us_aqi'], 0)}",
                                 ADVICE.get(cat, ""), color), unsafe_allow_html=True)
    st.plotly_chart(bar_cities(current, "pm2_5", "PM2.5 by city (µg/m³)", city, fmt_str="%{x:.1f}"))

elif page == PAGES[4]:
    st.title("Historical Data")
    allh = load_all_hourly()
    now = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
    past = allh[(allh["time"] <= now)].dropna(subset=["us_aqi"]) if not allh.empty else allh
    if past.empty:
        st.info("Data Not Available: no stored history yet.")
    else:
        days = past["time"].dt.date.nunique()
        st.caption(f"Stored history covers {days} day(s). Monthly/yearly trends need more days of data.")
        picks = st.multiselect("Compare cities", list(config.CITIES), default=[city])
        daily = (past[past["city"].isin(picks)].assign(day=lambda d: d["time"].dt.date)
                 .groupby(["day", "city"])["us_aqi"].mean().round(1).reset_index())
        if daily.empty:
            st.info("Select at least one city.")
        else:
            fig = px.line(daily, x="day", y="us_aqi", color="city", markers=True,
                          title="Daily average US AQI (stored model data)", labels={"us_aqi": "US AQI"})
            st.plotly_chart(style(fig))

elif page == PAGES[5]:
    st.title("Model Forecast")
    st.caption("These are forecast hours supplied by the Open-Meteo / CAMS model. This project has no "
               "prediction model of its own.")
    hourly = load_hourly(city).dropna(subset=["us_aqi"]) if not load_hourly(city).empty else pd.DataFrame()
    now = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
    fut = hourly[hourly["time"] > now] if not hourly.empty else hourly
    if fut.empty:
        st.info("Data Not Available: no forecast hours stored for this city.")
    else:
        peak = fut.loc[fut["us_aqi"].idxmax()]
        st.markdown(theme.glass_card(f"Highest forecast US AQI for {city}", f"{peak['us_aqi']:.0f}", "",
                                     f"At {fmt_time(peak['time'])} (PKT), from stored model forecast hours",
                                     COLORS[category(peak['us_aqi'])]), unsafe_allow_html=True)
        st.plotly_chart(hourly_fig(hourly, city, past=False, future=True))

elif page == PAGES[6]:
    st.title("Health Advisory")
    st.caption("General guidance by US AQI category (US EPA scheme). It is not medical advice.")
    st.markdown(theme.glass_card(f"{city} right now", cat, f"US AQI {fmt(row['us_aqi'], 0)}",
                                 ADVICE.get(cat, ""), color), unsafe_allow_html=True)
    for name in ORDER:
        st.markdown(theme.glass_card(name, RANGES[name], "US AQI range", ADVICE[name], COLORS[name]),
                    unsafe_allow_html=True)

else:
    st.title("Alerts")
    limit = st.select_slider("Alert when US AQI is at least", options=[101, 151, 201, 301], value=151)
    hits = current.dropna(subset=["us_aqi"]).query("us_aqi >= @limit").sort_values("us_aqi", ascending=False)
    if hits.empty:
        st.success("No city is at or above this level in the latest stored data.")
    else:
        st.caption(f"{len(hits)} of {len(current)} cities at or above US AQI {limit}.")
        for r in hits.itertuples():
            st.markdown(theme.glass_card(f"{r.city}, {r.province}", f"{r.us_aqi:.0f}",
                                         category(r.us_aqi), f"PM2.5 {fmt(r.pm2_5)} µg/m³ · PM10 {fmt(r.pm10)} µg/m³",
                                         COLORS[category(r.us_aqi)]), unsafe_allow_html=True)

# ------------------------------------------------------------ footer
st.divider()
st.markdown(f'<p class="note"><b>Last Updated:</b> {fmt_time(row["fetched_at"])} (PKT) = when our ETL fetched '
            f'the data. The page caches data for up to {CACHE_SECONDS // 60} min; Refresh reloads from the '
            'database and does not call Open-Meteo.</p>', unsafe_allow_html=True)
st.info("**Data source:** Open-Meteo Air Quality API (CAMS atmospheric model). Values are model-based "
        "estimates, not direct ground-station measurements, and not guaranteed minute-by-minute live readings.")