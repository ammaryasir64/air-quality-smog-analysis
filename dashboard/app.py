"""
dashboard/app.py

Air Quality & Smog Analysis dashboard (Streamlit), Aeris-inspired design.

Data (Supabase, read-only key SUPABASE_ANON_KEY):
  openweather_current_air_quality : latest stored reading per city
  openweather_air_quality         : hourly records (past + 4-day model forecast)

Source: OpenWeather Air Pollution API (SILAM model). Values are MODEL-BASED
ESTIMATES, not ground-station measurements. us_aqi_calc is a US AQI calculated by
our ETL from OpenWeather's concentrations (see the Methodology box at the bottom);
OpenWeather's own index (ow_aqi) uses a 1-5 scale.
No number on this dashboard is invented.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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
st.set_page_config(page_title="Pakistan Air Quality", page_icon="🌫️", layout="wide",
                   initial_sidebar_state="expanded")
theme.inject_theme()

CACHE_SECONDS = 900

# ------------------------------------------------------------ loading screen before the sidebar
# The squares are drawn first (before the sidebar and header exist) and hide the sidebar while they
# are on screen. They are removed as soon as the data is ready.
_needs_load = time.time() - st.session_state.get("loaded_at", 0) > CACHE_SECONDS - 10
loader_slot = st.empty()
if _needs_load:
    loader_slot.markdown(theme.loader_html(), unsafe_allow_html=True)

LOCAL_TZ = "Asia/Karachi"
CURRENT_TABLE = "openweather_current_air_quality"
HOURLY_TABLE = "openweather_air_quality"
HOURLY_ROWS_PER_CITY = 700
MIN_HOURS_PER_DAY = 18  # a day needs at least 18 hours of calculated AQI (75%) to be plotted

PAGES = ["Home", "Air Quality Analytics", "Live Monitoring", "Smog Analysis",
         "Historical Data", "Health Advisory"]
ICONS = ["home", "bar_chart", "sensors", "cloud", "history", "favorite"]
POLLUTANTS = [("pm2_5", "PM2.5"), ("pm10", "PM10"), ("carbon_monoxide", "Carbon Monoxide (CO)"),
              ("sulphur_dioxide", "Sulphur Dioxide (SO₂)"), ("nitrogen_dioxide", "Nitrogen Dioxide (NO₂)"),
              ("ozone", "Ozone (O₃)")]
LABELS = dict(POLLUTANTS)
OW_LABELS = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
COLORS = {"Good": "#22c55e", "Moderate": "#eab308", "Unhealthy for Sensitive Groups": "#f97316",
          "Unhealthy": "#ef4444", "Very Unhealthy": "#a855f7", "Hazardous": "#9f1239", "No data": "#94a3b8"}
ORDER = list(COLORS)[:-1]
RANGES = {
    "Good": "0 to 50",
    "Moderate": "51 to 100",
    "Unhealthy for Sensitive Groups": "101 to 150",
    "Unhealthy": "151 to 200",
    "Very Unhealthy": "201 to 300",
    "Hazardous": "301 and above",
}
ADVICE = {
    "Good": "Air quality is satisfactory. Normal outdoor activity is fine.",
    "Moderate": "Acceptable for most people. Unusually sensitive people may limit long outdoor exertion.",
    "Unhealthy for Sensitive Groups": "Children, older adults and people with heart or lung disease should reduce prolonged outdoor exertion.",
    "Unhealthy": "Everyone may feel effects. Sensitive groups should avoid outdoor exertion; others should limit it.",
    "Very Unhealthy": "Health alert. Avoid outdoor activity; sensitive groups should stay indoors.",
    "Hazardous": "Emergency conditions. Everyone should avoid outdoor exertion.",
}
HEAT_SCALE = [[0, "#22c55e"], [.17, "#eab308"], [.33, "#f97316"], [.5, "#ef4444"], [1, "#a855f7"]]


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


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_current():
    df = pd.DataFrame(get_client().table(CURRENT_TABLE).select("*").execute().data)
    if df.empty:
        return df
    df = df[df["city"].isin(config.CITIES)].copy()
    if df.empty:
        return df
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True).dt.tz_convert(LOCAL_TZ)
    df["time"] = pd.to_datetime(df["time"])
    df["province"] = df["city"].map(lambda c: config.CITIES[c][2])
    df["latitude"] = df["city"].map(lambda c: config.CITIES[c][0])
    df["longitude"] = df["city"].map(lambda c: config.CITIES[c][1])
    return df.reset_index(drop=True)


HOURLY_COLUMNS = "city,time,ow_aqi,us_aqi_calc,pm2_5,pm10"
PAGE_SIZE = 1000
HISTORY_DAYS = 45  # only the last 45 days of stored hours (plus the forecast) are fetched


def _fetch_page(client, since, start):
    return (client.table(HOURLY_TABLE).select(HOURLY_COLUMNS).gte("time", since)
            .order("city").order("time").range(start, start + PAGE_SIZE - 1).execute().data)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_hourly_all():
    """All cities' hourly rows in ONE cached call (pages are fetched in parallel).
    Every page and city switch then works on this in-memory table, with no new database call."""
    client = get_client()
    since = (pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None) - pd.Timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    total = client.table(HOURLY_TABLE).select("city", count="exact").gte("time", since).limit(1).execute().count
    rows = []
    if total:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for page in pool.map(lambda start: _fetch_page(client, since, start), range(0, total, PAGE_SIZE)):
                rows.extend(page)
    elif total is None:  # count not supported: fall back to one page after another
        start = 0
        while True:
            page = _fetch_page(client, since, start)
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                break
            start += PAGE_SIZE
    df = pd.DataFrame(rows, columns=HOURLY_COLUMNS.split(","))
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values(["city", "time"]).reset_index(drop=True)
    return df


def load_hourly(city):
    allh = load_hourly_all()
    if allh.empty:
        return allh
    return allh[allh["city"] == city].reset_index(drop=True)


def load_all_hourly():
    return load_hourly_all()


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


def ow_text(v):
    if pd.isna(v):
        return "Data Not Available"
    return f"{int(v)} ({OW_LABELS.get(int(v), '?')})"


def style(fig, h=420):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=h, margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="Plus Jakarta Sans, Segoe UI, sans-serif"))
    return fig


def hourly_fig(hourly, city, past=True, future=True):
    now = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
    p, f = hourly[hourly["time"] <= now], hourly[hourly["time"] > now]
    if past and future and not p.empty and not f.empty:
        f = pd.concat([p.tail(1), f])
    fig = go.Figure()
    if past and not p.empty:
        fig.add_trace(go.Scatter(x=p["time"], y=p["us_aqi_calc"], mode="lines", name="Stored model data",
                                 line=dict(color="#38bdf8", width=3), fill="tozeroy",
                                 fillcolor="rgba(56,189,248,.08)"))
    if future and not f.empty:
        fig.add_trace(go.Scatter(x=f["time"], y=f["us_aqi_calc"], mode="lines", name="Model forecast",
                                 line=dict(color="#a78bfa", width=3, dash="dash")))
    for lim in (50, 100, 150, 200, 300):
        fig.add_hline(y=lim, line_dash="dot", line_color="#334155", line_width=1)
    fig.update_layout(title=f"Hourly US AQI (calculated): {city} (Asia/Karachi time)",
                      yaxis_title="US AQI (calculated)", legend=dict(orientation="h", y=-0.2))
    return style(fig)


def bar_cities(df, col, title, highlight, h=None, fmt_str="%{x:.0f}"):
    d = df[["city", col]].dropna().sort_values(col).copy()
    h = h or max(420, 20 * len(d))
    d["group"] = d["city"].eq(highlight).map({True: "Selected city", False: "Other cities"})
    fig = px.bar(d, x=col, y="city", orientation="h", color="group", text=col, title=title,
                 color_discrete_map={"Selected city": "#f59e0b", "Other cities": "#38bdf8"},
                 labels={col: "", "city": ""})
    fig.update_traces(texttemplate=fmt_str, textposition="outside")
    fig.update_yaxes(dtick=1, categoryorder="array", categoryarray=d["city"].tolist())
    fig.update_layout(legend_title_text="")
    return style(fig, h)


def week_heatmap(hourly, city):
    """Selected city, last 7 days (today included): one square per hour. None if nothing to show."""
    now = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
    start = now.normalize() - pd.Timedelta(days=6)
    w = hourly[(hourly["time"] >= start) & (hourly["time"] <= now)].dropna(subset=["us_aqi_calc"]).copy()
    if w.empty:
        return None
    w["day"] = w["time"].dt.normalize()
    w["hour"] = w["time"].dt.hour
    days = pd.date_range(start, periods=7)
    grid = (w.pivot_table(index="day", columns="hour", values="us_aqi_calc", aggfunc="mean")
            .reindex(index=days, columns=range(24)))
    hours = [f"{h:02d}:00" for h in range(24)]
    day_labels = [d.strftime("%a %d %b") for d in days]
    fig = go.Figure(go.Heatmap(
        z=grid.values.round(0), x=hours, y=day_labels,
        colorscale=HEAT_SCALE, zmin=0, zmax=300, xgap=3, ygap=3, hoverongaps=False,
        colorbar=dict(title="US AQI"),
        hovertemplate="%{y}, %{x}<br>US AQI %{z}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", categoryorder="array", categoryarray=day_labels)
    fig.update_xaxes(tickmode="array", tickvals=hours[::3])
    fig.update_layout(title=f"This week, hour by hour: US AQI (calculated) for {city} (Asia/Karachi time)")
    return style(fig, 380)


# ------------------------------------------------------------ navigation state
st.session_state.setdefault("page", PAGES[0])
st.session_state.setdefault("nav_open", False)


def toggle_nav():
    st.session_state.nav_open = not st.session_state.nav_open


def go_to(name):
    st.session_state.page = name
    st.session_state["scroll_top"] = True  # new page starts at the top


def nav_button(label, **kwargs):
    """Full-width button, so every sidebar box has the same size (works on old and new Streamlit)."""
    try:
        return st.button(label, width="stretch", **kwargs)
    except TypeError:
        return st.button(label, use_container_width=True, **kwargs)


# ------------------------------------------------------------ data (loader is still covering the screen)
try:
    current = load_current()
    if not current.empty:
        load_hourly_all()  # everything is fetched now, behind the squares; later clicks are instant
except Exception as exc:
    loader_slot.empty()
    st.error(f"Could not load data from Supabase: {exc}")
    st.stop()
st.session_state["loaded_at"] = time.time()
loader_slot.empty()  # data is ready: remove the squares

if current.empty:
    st.warning("No data in the OpenWeather tables yet. Run the ETL pipeline first.")
    st.stop()

# ------------------------------------------------------------ sidebar: icon rail + menu button
st.markdown(theme.nav_css(st.session_state.nav_open), unsafe_allow_html=True)
open_ = st.session_state.nav_open
with st.sidebar:
    nav_button(("Close menu" if open_ else " "),
               icon=":material/menu_open:" if open_ else ":material/menu:",
               key="nav_toggle", on_click=toggle_nav, help="Show or hide the menu")
    for name, icon in zip(PAGES, ICONS):
        nav_button((name if open_ else " "), icon=f":material/{icon}:", key=f"nav_{name}",
                   on_click=go_to, args=(name,), help=name,
                   type="primary" if st.session_state.page == name else "secondary")
page = st.session_state.page if st.session_state.page in PAGES else PAGES[0]

# ------------------------------------------------------------ header: brand + LIVE badge, city selector
cities_sorted = sorted(config.CITIES)
head_a, head_b = st.columns([3, 2])
live_title = ("Latest stored model data. The ETL pipeline refreshes it about every 12 hours; "
              "it is not a minute-by-minute feed.")
head_a.markdown(
    '<div class="brand">🌫️ Pakistan Air Quality'
    '<div class="live-row">'
    f'<span class="live-pill" title="{live_title}"><i class="live-dot"></i>LIVE</span>'
    '</div></div>',
    unsafe_allow_html=True)
city = head_b.selectbox("City", cities_sorted,
                        index=cities_sorted.index("Lahore") if "Lahore" in cities_sorted else 0,
                        key="city", label_visibility="collapsed")

match = current[current["city"] == city]
if match.empty:
    st.warning(f"No stored reading for {city} yet.")
    st.stop()
row = match.iloc[0]
aqi_value = None if pd.isna(row["us_aqi_calc"]) else float(row["us_aqi_calc"])
cat = category(row["us_aqi_calc"])
color = COLORS[cat]


def pollutant_cards(cols_per_row=3):
    for i in range(0, len(POLLUTANTS), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, (key, label) in zip(cols, POLLUTANTS[i:i + cols_per_row]):
            col.markdown(theme.glass_card(label, fmt(row[key]), "µg/m³",
                                          f"Model estimate for {city}. Model time: {fmt_time(row['time'])} (PKT)"),
                         unsafe_allow_html=True)


# ------------------------------------------------------------ pages
if page == "Home":
    st.title("Air Quality and Smog Analysis")
    st.caption("Monitoring Pakistan's Air Quality • Understanding Smog • Model Forecasts")
    c1, right = st.columns([2, 2])
    hero = ('<div class="glass hero-glass">'
            f'<div>{theme.gauge_svg(aqi_value, "US AQI (calculated)", color)}</div>'
            '<div class="hero-text">'
            f'<div class="hero-title">{city}, {row["province"]}</div>'
            f'<div class="hero-cat" style="color:{color}">{cat}</div>'
            f'<div class="hero-sub">OpenWeather index: {ow_text(row["ow_aqi"])}<br>'
            f'Model time: {fmt_time(row["time"])} (PKT)</div></div></div>')
    c1.markdown(hero, unsafe_allow_html=True)
    top_row = right.columns(2)
    bottom_row = right.columns(2)
    top_row[0].markdown(theme.glass_card("PM2.5", fmt(row["pm2_5"]), "µg/m³",
                                         "Fine particles (model estimate)", "#38bdf8"),
                        unsafe_allow_html=True)
    top_row[1].markdown(theme.glass_card("PM10", fmt(row["pm10"]), "µg/m³",
                                         "Coarse particles (model estimate)", "#a78bfa"),
                        unsafe_allow_html=True)
    bottom_row[0].markdown(theme.glass_card("Nitrogen Dioxide (NO₂)", fmt(row["nitrogen_dioxide"]), "µg/m³",
                                            "Mostly from vehicles and burning fuel (model estimate)",
                                            "#22c55e"),
                           unsafe_allow_html=True)
    bottom_row[1].markdown(theme.glass_card("Ozone (O₃)", fmt(row["ozone"]), "µg/m³",
                                            "Forms when sunlight reacts with other pollutants (model estimate)",
                                            "#f59e0b"),
                           unsafe_allow_html=True)
    left, right = st.columns(2)
    hourly = load_hourly(city)
    with left:
        if hourly.empty or hourly["us_aqi_calc"].isna().all():
            st.info("Data Not Available: no hourly records stored for this city.")
        else:
            st.plotly_chart(hourly_fig(hourly.dropna(subset=["us_aqi_calc"]), city))
    with right:
        top = current.dropna(subset=["us_aqi_calc"]).nlargest(10, "us_aqi_calc")
        st.plotly_chart(bar_cities(top, "us_aqi_calc", "10 highest US AQI cities (latest)", city, 420))
    a, b = st.columns(2)
    a.markdown(theme.glass_card("Health advisory", cat, "",
                                ADVICE.get(cat, "No advisory available."), color), unsafe_allow_html=True)
    worst = current.dropna(subset=["us_aqi_calc"]).nlargest(3, "us_aqi_calc")
    txt = "<br>".join(f"{r.city}: US AQI {r.us_aqi_calc:.0f} ({category(r.us_aqi_calc)})"
                      for r in worst.itertuples())
    b.markdown(theme.glass_card("Highest US AQI right now (top 3)", f"{len(worst)} cities", "", txt, "#ef4444"),
               unsafe_allow_html=True)
    heat = week_heatmap(hourly, city) if not hourly.empty else None
    if heat is None:
        st.info("Data Not Available: no stored hourly data for this city in the last 7 days.")
    else:
        st.plotly_chart(heat)
        st.caption("Each square is one hour of the last 7 days for the selected city (calculated US AQI, "
                   "model data). Dark squares mean no data for that hour.")
    st.caption("The US AQI here is calculated from OpenWeather's model concentrations (see Methodology below). "
               "CO2, temperature and humidity are not collected by this project.")

elif page == "Air Quality Analytics":
    st.title("Air Quality Analytics")
    pollutant_cards()
    hourly = load_hourly(city)
    if hourly.empty or hourly["us_aqi_calc"].isna().all():
        st.info("Data Not Available: no hourly records stored for this city.")
    else:
        st.plotly_chart(hourly_fig(hourly.dropna(subset=["us_aqi_calc"]), city))
    sel = st.selectbox("Compare one pollutant across all cities", list(LABELS), format_func=LABELS.get)
    st.plotly_chart(bar_cities(current, sel, f"{LABELS[sel]} by city (µg/m³)", city, fmt_str="%{x:.1f}"))
    pm = current[["city", "pm2_5", "pm10"]].dropna().sort_values("pm2_5")
    fig = px.bar(pm.melt("city", var_name="pollutant", value_name="µg/m³"), x="µg/m³", y="city",
                 orientation="h", color="pollutant", barmode="group",
                 title="PM2.5 and PM10 by city (µg/m³)")
    fig.update_yaxes(dtick=1, categoryorder="array", categoryarray=pm["city"].tolist())
    st.plotly_chart(style(fig, max(560, 30 * len(pm))))

elif page == "Live Monitoring":
    st.title("Live Monitoring")
    st.caption("Latest stored model estimate per city. Data updates when the ETL runs (every 12 hours).")
    m = current.dropna(subset=["us_aqi_calc", "latitude", "longitude"]).copy()
    m["category"] = m["us_aqi_calc"].apply(category)
    fig = px.scatter_map(m, lat="latitude", lon="longitude", color="us_aqi_calc", hover_name="city",
                         hover_data={"province": True, "category": True, "pm2_5": ":.1f", "pm10": ":.1f",
                                     "latitude": False, "longitude": False},
                         color_continuous_scale=["#22c55e", "#eab308", "#f97316", "#ef4444", "#a855f7"],
                         range_color=(0, 300), zoom=4.3, map_style="carto-darkmatter",
                         labels={"us_aqi_calc": "US AQI (calculated)"}, title="US AQI (calculated) by city")
    fig.update_traces(marker=dict(size=18))
    fig.update_layout(map=dict(center=dict(lat=30.3, lon=69.3), zoom=4.4))
    st.plotly_chart(style(fig, 560))

    t = current[["city", "province", "us_aqi_calc", "ow_aqi", "pm2_5", "pm10", "fetched_at"]].sort_values(
        "us_aqi_calc", ascending=False).copy()
    t["us_aqi_calc"] = t["us_aqi_calc"].astype("Int64")
    t["ow_aqi"] = t["ow_aqi"].astype("Int64")
    t["fetched_at"] = t["fetched_at"].dt.strftime("%d %b %I:%M %p")
    t.columns = ["City", "Province", "US AQI (calculated)", "OpenWeather index (1-5)",
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

elif page == "Smog Analysis":
    st.title("Smog Analysis")
    st.caption("Cities grouped by US AQI category (standard AQI ranges applied to our calculated AQI).")
    counts = (current["us_aqi_calc"].apply(category).value_counts().reindex(ORDER, fill_value=0).reset_index())
    counts.columns = ["category", "cities"]
    fig = px.bar(counts, x="category", y="cities", color="category", color_discrete_map=COLORS, text="cities",
                 title="Number of cities per AQI category")
    st.plotly_chart(style(fig, 380))
    st.markdown(theme.glass_card(f"{city} AQI category", cat, f"US AQI {fmt(row['us_aqi_calc'], 0)}",
                                 ADVICE.get(cat, ""), color), unsafe_allow_html=True)
    st.plotly_chart(bar_cities(current, "pm2_5", "PM2.5 by city (µg/m³)", city, fmt_str="%{x:.1f}"))

elif page == "Historical Data":
    st.title("Historical Data")
    allh = load_all_hourly()
    now = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
    past = allh[allh["time"] <= now].dropna(subset=["us_aqi_calc"]) if not allh.empty else allh
    if past.empty:
        st.info("Data Not Available: no stored history yet.")
    else:
        days = past["time"].dt.date.nunique()
        st.caption(f"Stored history covers {days} day(s) (calculated US AQI from model data). "
                   "Monthly or yearly trends need many more days of data.")
        picks = st.multiselect("Compare cities", sorted(config.CITIES), default=[city])
        if not picks:
            st.info("Select at least one city.")
        else:
            counts = (past[past["city"].isin(picks)].assign(day=lambda d: d["time"].dt.date)
                      .groupby(["day", "city"])["us_aqi_calc"].agg(["mean", "count"]).reset_index())
            complete = counts[counts["count"] >= MIN_HOURS_PER_DAY].copy()
            complete["us_aqi_calc"] = complete["mean"].round(1)
            complete = complete.sort_values(["city", "day"])
            if complete.empty:
                st.info("Data Not Available: no complete day for the selected cities.")
            else:
                # one solid line per city; it goes straight from one available day to the next
                fig = px.line(complete, x="day", y="us_aqi_calc", color="city", markers=True,
                              title="Daily average US AQI (calculated)",
                              labels={"us_aqi_calc": "US AQI (calculated)"})
                fig.update_traces(line=dict(width=3), connectgaps=True)
                st.plotly_chart(style(fig))
            left_out = sorted(counts.loc[counts["count"] < MIN_HOURS_PER_DAY, "day"].unique())
            note = (f"Only days with at least {MIN_HOURS_PER_DAY} hours of calculated AQI are plotted; "
                    "the line joins the days that have data.")
            if left_out:
                note += " Days left out for the selected cities: " + ", ".join(
                    d.strftime("%d %b") for d in left_out) + "."
            st.caption(note)

    st.divider()
    st.subheader("Model Forecast")
    st.caption("These are forecast hours supplied by OpenWeather (4 days). This project has no "
               "prediction model of its own.")
    hourly = load_hourly(city)
    hourly = hourly.dropna(subset=["us_aqi_calc"]) if not hourly.empty else hourly
    now = pd.Timestamp.now(tz=LOCAL_TZ).tz_localize(None)
    fut = hourly[hourly["time"] > now] if not hourly.empty else hourly
    if fut.empty:
        st.info("Data Not Available: no forecast hours stored for this city.")
    else:
        peak = fut.loc[fut["us_aqi_calc"].idxmax()]
        st.markdown(theme.glass_card(f"Highest forecast US AQI (calculated) for {city}", f"{peak['us_aqi_calc']:.0f}", "",
                                     f"At {fmt_time(peak['time'])} (PKT), from stored model forecast hours",
                                     COLORS[category(peak['us_aqi_calc'])]), unsafe_allow_html=True)
        st.plotly_chart(hourly_fig(hourly, city, past=False, future=True))

else:  # Health Advisory
    st.title("Health Advisory")
    st.caption("General guidance by US AQI category (US EPA scheme). It is not medical advice.")
    st.markdown(theme.glass_card(f"{city} right now", cat, f"US AQI {fmt(row['us_aqi_calc'], 0)}",
                                 ADVICE.get(cat, ""), color), unsafe_allow_html=True)
    for name in ORDER:
        st.markdown(theme.glass_card(name, RANGES[name], "US AQI range", ADVICE[name], COLORS[name]),
                    unsafe_allow_html=True)

# ------------------------------------------------------------ footer (Home page only)
if page == "Home":
    st.divider()
    st.info("**Data source:** OpenWeather Air Pollution API (SILAM atmospheric model). Values are model-based "
            "estimates, not direct ground-station measurements, and not guaranteed minute-by-minute live readings.")

    with st.expander("How is the US AQI calculated here?"):
        st.markdown(
            "- OpenWeather supplies hourly pollutant concentrations (µg/m³, SILAM model) and its own 1-5 index.\n"
            "- Our ETL calculates a US AQI (0-500) from the six pollutants with the US EPA breakpoint table "
            "(40 CFR Part 58, Appendix G, as amended in 2024).\n"
            "- Averaging: PM2.5 and PM10 use a 24-hour rolling mean, O₃ and CO an 8-hour mean, NO₂ and SO₂ the "
            "1-hour value.\n"
            "- Gas concentrations are converted from µg/m³ to ppb/ppm assuming 25 °C and 1 atm (an assumption).\n"
            "- The overall AQI is the highest pollutant index and is capped at 500.\n"
            "- Because PM is averaged over 24 hours, the AQI reacts slowly to sudden spikes, while the PM2.5 "
            "card shows the latest hourly value.\n"
            "- This is an approximation from model data, not an official AQI."
        )

    with st.expander("Why can these values differ from official ground-station AQI?"):
        st.markdown(
            "- **Model vs. sensors:** this dashboard shows model-based estimates (OpenWeather / SILAM), "
            "one value per city for the city-centre coordinates. Official dashboards use ground "
            "stations placed at specific spots.\n"
            "- **Resolution:** the model grid covers many kilometres, so local hotspots (busy roads, "
            "industrial areas) can look lower than a station reading. Nearby cities may show similar values.\n"
            "- **Labels:** some local dashboards use different category names or breakpoints, so the "
            "same number can carry a different label. This dashboard uses the US EPA scale "
            "(Hazardous starts at 301).\n"
            "- **Timing:** data is fetched by the ETL pipeline (every 12 hours) from model output, "
            "not minute-by-minute sensor feeds.\n"
            "- For official health decisions, check your local environmental agency's station data."
        )


# ------------------------------------------------------------ new page: start at the top
# (Streamlit keeps the old scroll position when only the page changes)
if st.session_state.pop("scroll_top", False):
    try:
        import streamlit.components.v1 as components

        components.html(
            "<script>(function(){var d=window.parent.document;"
            "function up(){['[data-testid=stMain]','section.main','.main','.stMain'].forEach(function(q){"
            "var e=d.querySelector(q);if(e&&e.scrollTo){e.scrollTo(0,0);}});"
            "if(d.scrollingElement){d.scrollingElement.scrollTop=0;}}"
            "up();setTimeout(up,60);setTimeout(up,300);})();"
            f"//{time.time()}</script>",
            height=0,
        )
    except Exception:
        pass
