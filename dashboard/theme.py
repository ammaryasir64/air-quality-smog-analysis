"""
dashboard/theme.py

Aeris-inspired visual theme for the Streamlit dashboard (CSS only), plus:
  - nav_css(): an icon-rail sidebar that widens when the menu button is pressed
  - loading() / loader_html(): a loading screen made of a small cluster of squares
    that keep changing, in the dashboard colours (navy, cyan, purple, green)
  - a LIVE badge style, and removal of the empty band at the top of the page

This file contains NO data. All numbers shown come from the Supabase tables.
"""

import math
from contextlib import contextmanager

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, .stApp, [class*="css"] {font-family: 'Plus Jakarta Sans', sans-serif;}

.stApp {
  background:
    radial-gradient(1100px 600px at 8% -10%, rgba(56,189,248,.16), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(139,92,246,.13), transparent 55%),
    radial-gradient(700px 500px at 50% 110%, rgba(34,197,94,.08), transparent 60%),
    #050b16;
}

/* floating glowing dots */
.stApp::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0; opacity: .55;
  background-image:
    radial-gradient(circle at 12% 22%, rgba(56,189,248,.9) 0 2px, transparent 3px),
    radial-gradient(circle at 28% 68%, rgba(139,92,246,.8) 0 2px, transparent 3px),
    radial-gradient(circle at 46% 14%, rgba(34,197,94,.7) 0 2px, transparent 3px),
    radial-gradient(circle at 63% 52%, rgba(56,189,248,.8) 0 2px, transparent 3px),
    radial-gradient(circle at 81% 24%, rgba(139,92,246,.8) 0 2px, transparent 3px),
    radial-gradient(circle at 92% 74%, rgba(56,189,248,.9) 0 2px, transparent 3px),
    radial-gradient(circle at 70% 90%, rgba(34,197,94,.7) 0 2px, transparent 3px),
    radial-gradient(circle at 6% 88%, rgba(56,189,248,.7) 0 2px, transparent 3px);
  animation: floaty 16s ease-in-out infinite alternate;
}
@keyframes floaty {from {transform: translateY(0);} to {transform: translateY(-28px);}}

.block-container {position: relative; z-index: 1; max-width: 1250px;}

/* remove the empty band at the top (Streamlit header and toolbar) */
header[data-testid="stHeader"] {
  background: transparent !important; height: 0 !important; min-height: 0 !important;
}
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
  display: none !important;
}
[data-testid="stMainBlockContainer"], .block-container {padding-top: .8rem !important;}

/* headings */
h1 {font-weight: 800 !important;
    background: linear-gradient(90deg, #e0f2fe, #38bdf8 55%, #a78bfa);
    -webkit-background-clip: text; background-clip: text; color: transparent !important;}
h2, h3 {font-weight: 700 !important; color: #e2e8f0 !important;}

/* sidebar */
section[data-testid="stSidebar"] {
  background: rgba(7,14,29,.92); backdrop-filter: blur(16px);
  border-right: 1px solid rgba(56,189,248,.2);
}

/* buttons */
.stButton > button {
  border: 1px solid rgba(56,189,248,.5); background: rgba(56,189,248,.08);
  color: #e2e8f0; border-radius: 12px; transition: all .25s ease;
}
.stButton > button:hover {
  border-color: #38bdf8; background: rgba(56,189,248,.18);
  box-shadow: 0 0 20px rgba(56,189,248,.4); transform: translateY(-1px);
}

/* tabs */
.stTabs [data-baseweb="tab-list"] {gap: 6px;}
.stTabs [data-baseweb="tab"] {
  background: rgba(17,26,46,.6); border: 1px solid rgba(56,189,248,.15);
  border-radius: 12px; padding: 8px 16px; transition: all .25s ease;
}
.stTabs [data-baseweb="tab"]:hover {border-color: rgba(56,189,248,.5);}
.stTabs [aria-selected="true"] {
  background: rgba(56,189,248,.16) !important; border-color: #38bdf8 !important;
  box-shadow: 0 0 16px rgba(56,189,248,.25);
}
.stTabs [data-baseweb="tab-highlight"] {display: none;}

/* glass cards */
.glass {
  position: relative; overflow: hidden;
  background: linear-gradient(145deg, rgba(17,26,46,.78), rgba(10,18,36,.60));
  backdrop-filter: blur(14px);
  border: 1px solid rgba(56,189,248,.18); border-radius: 18px;
  padding: 16px 18px; margin-bottom: 14px;
  box-shadow: 0 8px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.04);
  transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
  animation: fadeUp .6s ease backwards;
}
.glass:hover {
  transform: translateY(-4px); border-color: rgba(56,189,248,.55);
  box-shadow: 0 14px 40px rgba(0,0,0,.45), 0 0 26px rgba(56,189,248,.25);
}
@keyframes fadeUp {from {opacity: 0; transform: translateY(16px);}}

.g-label {color: #94a3b8; font-size: .82rem; font-weight: 500; letter-spacing: .02em;}
.g-value {color: #f8fafc; font-size: 2rem; font-weight: 800; line-height: 1.15; margin-top: 4px;}
.g-unit {color: #64748b; font-size: .78rem; margin-top: 2px;}
.glass .more {
  max-height: 0; opacity: 0; overflow: hidden; color: #94a3b8; font-size: .78rem;
  transition: all .3s ease;
}
.glass:hover .more {max-height: 100px; opacity: 1; margin-top: 8px;}

/* hero (gauge + text) */
.hero-glass {display: flex; align-items: center; gap: 24px; flex-wrap: wrap;}
.hero-text {flex: 1; min-width: 220px;}
.hero-title {color: #94a3b8; font-size: .9rem;}
.hero-cat {font-size: 1.7rem; font-weight: 800; margin: 4px 0;}
.hero-sub {color: #94a3b8; font-size: .85rem; line-height: 1.6;}
.gauge-fill {animation: gaugefill 1.5s ease-out backwards;}
@keyframes gaugefill {from {stroke-dasharray: 0 600;}}

.pill {display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: .78rem;
       font-weight: 600; border: 1px solid; margin-right: 6px;}
.note {color: #94a3b8; font-size: .8rem;}

/* header brand + LIVE badge (dark blue "crystal" pill) */
.brand {color: #e2e8f0; font-weight: 800; font-size: 1.1rem; line-height: 1.3; padding-top: 2px;}
.live-row {display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 6px;}
.live-pill {
  display: inline-flex; align-items: center; gap: 8px; padding: 5px 14px; border-radius: 999px;
  background: linear-gradient(145deg, rgba(20,48,112,.9), rgba(8,18,48,.9));
  border: 1px solid rgba(96,165,250,.55);
  box-shadow: 0 0 18px rgba(37,99,235,.35), inset 0 1px 0 rgba(255,255,255,.18),
              inset 0 -6px 12px rgba(2,8,24,.5);
  backdrop-filter: blur(10px); color: #dbeafe; font-weight: 800; font-size: .76rem;
  letter-spacing: .16em; cursor: help;
}
.live-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #38bdf8;
  box-shadow: 0 0 8px #38bdf8; animation: live-pulse 1.6s ease-in-out infinite;
}
@keyframes live-pulse {0%, 100% {opacity: 1; transform: scale(1);} 50% {opacity: .4; transform: scale(.7);}}
.live-time {color: #94a3b8; font-size: .78rem; font-weight: 500;}
</style>
"""

# Loading screen: a small cluster of 3x3 squares, turned 45 degrees (diamonds). Each square
# fades in, changes colour (cyan -> purple -> green) and vanishes at its own moment,
# so the shape keeps rearranging.
LOADER_CSS = (
    "<style>"
    ".ld-overlay{position:fixed;inset:0;z-index:1000000;display:flex;align-items:center;"
    "justify-content:center;"
    "background:radial-gradient(900px 500px at 10% -10%,rgba(56,189,248,.16),transparent 60%),"
    "radial-gradient(800px 500px at 100% 0%,rgba(139,92,246,.14),transparent 55%),#050b16;}"
    ".ld-cluster{display:grid;grid-template-columns:repeat(3,15px);gap:5px;transform:rotate(45deg);}"
    ".ld-sq{width:15px;height:15px;border-radius:3px;background:#38bdf8;opacity:0;"
    "animation:ld-shuffle 2.4s ease-in-out infinite;}"
    "@keyframes ld-shuffle{"
    "0%{opacity:0;transform:scale(.2);background:#38bdf8}"
    "18%{opacity:1;transform:scale(1);background:#38bdf8;box-shadow:0 0 10px rgba(56,189,248,.7)}"
    "50%{opacity:1;transform:scale(1);background:#a78bfa;box-shadow:0 0 10px rgba(167,139,250,.6)}"
    "78%{opacity:1;transform:scale(1);background:#22c55e;box-shadow:0 0 10px rgba(34,197,94,.6)}"
    "100%{opacity:0;transform:scale(.2);background:#22c55e}}"
    "</style>"
)

# Start each square at a different point of its cycle so the shape changes from the first frame.
LOADER_DELAYS = [-2.2, -0.4, -1.5, -0.9, -1.9, -0.1, -1.2, -2.0, -0.7]


def inject_theme():
    """Call once at the top of app.py (after st.set_page_config)."""
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)


def nav_css(is_open):
    """CSS for the icon-rail sidebar. Narrow when closed, wide (with labels) when open."""
    width = 250 if is_open else 84
    align = "flex-start" if is_open else "center"
    sb = 'section[data-testid="stSidebar"]'
    return (
        "<style>"
        f"{sb}{{width:{width}px !important;min-width:{width}px !important;"
        f"max-width:{width}px !important;transition:width .25s ease;}}"
        f'{sb} [data-testid="stSidebarHeader"],{sb} [data-testid="stSidebarCollapseButton"]'
        "{display:none !important;}"
        f'{sb} [data-testid="stButton"],{sb} .stButton{{width:100% !important;margin-bottom:.15rem;}}'
        f"{sb} .stButton>button{{width:100%;justify-content:{align};gap:12px;min-height:46px;"
        "padding:.55rem .75rem;border-radius:14px;border:1px solid transparent;"
        "background:transparent;color:#94a3b8;box-shadow:none;}"
        f"{sb} .stButton>button:hover{{background:rgba(56,189,248,.12);"
        "border-color:rgba(56,189,248,.35);color:#e2e8f0;"
        "box-shadow:0 0 16px rgba(56,189,248,.18);transform:none;}"
        f'{sb} .stButton>button[kind="primary"],'
        f'{sb} .stButton>button[data-testid="stBaseButton-primary"]'
        "{background:rgba(56,189,248,.16);border-color:rgba(56,189,248,.6);"
        "color:#38bdf8;box-shadow:0 0 18px rgba(56,189,248,.3);}"
        "</style>"
    )


def loader_html(message="Loading"):
    """
    The loading screen: a small cluster of squares that keep changing (one line, no blank
    lines). `message` is kept so older code still works; it is not shown.
    """
    squares = "".join(
        f'<div class="ld-sq" style="animation-delay:{delay}s"></div>' for delay in LOADER_DELAYS
    )
    return LOADER_CSS + '<div class="ld-overlay"><div class="ld-cluster">' + squares + "</div></div>"


@contextmanager
def loading(message="Loading"):
    """Show the loading screen while the code inside the `with` block runs."""
    import streamlit as st

    slot = st.empty()
    slot.markdown(loader_html(message), unsafe_allow_html=True)
    try:
        yield
    finally:
        slot.empty()


def gauge_svg(value, caption, color, scale_max=500, size=220):
    """
    Animated circular gauge. `value` must come from the database.
    scale_max=500 is the top of the US AQI scale (drawing scale only).
    """
    if value is None or value != value:  # None or NaN
        return '<div class="g-value">Data Not Available</div>'
    circ = 2 * math.pi * 80
    arc = circ * 0.75
    fraction = max(0.0, min(float(value), scale_max)) / scale_max
    progress = arc * fraction
    return (
        f'<svg viewBox="0 0 200 200" width="{size}" height="{size}">'
        f'<circle cx="100" cy="100" r="80" fill="none" stroke="rgba(148,163,184,.18)" '
        f'stroke-width="14" stroke-linecap="round" stroke-dasharray="{arc:.1f} {circ:.1f}" '
        f'transform="rotate(135 100 100)"/>'
        f'<circle class="gauge-fill" cx="100" cy="100" r="80" fill="none" stroke="{color}" '
        f'stroke-width="14" stroke-linecap="round" stroke-dasharray="{progress:.1f} {circ:.1f}" '
        f'transform="rotate(135 100 100)" style="filter:drop-shadow(0 0 8px {color})"/>'
        f'<text x="100" y="108" text-anchor="middle" fill="#f8fafc" '
        f'font-size="46" font-weight="800">{float(value):.0f}</text>'
        f'<text x="100" y="132" text-anchor="middle" fill="#94a3b8" '
        f'font-size="12">{caption}</text></svg>'
    )


def glass_card(label, value, unit="", more="", accent="#38bdf8"):
    """Glass card. `more` is revealed when the mouse hovers over the card."""
    more_html = f'<div class="more">{more}</div>' if more else ""
    return (
        f'<div class="glass" style="border-left:3px solid {accent}">'
        f'<div class="g-label">{label}</div>'
        f'<div class="g-value">{value}</div>'
        f'<div class="g-unit">{unit}</div>'
        f"{more_html}</div>"
    )