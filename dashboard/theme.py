"""
dashboard/theme.py

Aeris-inspired visual theme for the Streamlit dashboard (CSS only), plus:
  - nav_css(): an icon-rail sidebar (equal-size buttons) that widens when the menu button is pressed
  - loader_html(): a loading screen made of a small cluster of changing squares, shown ABOVE
    everything (sidebar included) in the dashboard colours (navy, cyan, purple, green)
  - a LIVE badge style, and removal of the empty band at the top of the page

This file contains NO data. All numbers shown come from the Supabase tables.
"""

import math
from contextlib import contextmanager

# No web-font download here on purpose: an @import of Google Fonts blocks the first paint.
CSS = """
<style>
html, body, .stApp, [class*="css"] {
  font-family: 'Plus Jakarta Sans', 'Segoe UI', system-ui, -apple-system, Roboto, sans-serif;
}

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

/* no z-index here: a z-index would trap the loader screen inside this box */
.block-container {position: relative; max-width: 1250px;}

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
  color: #dbeafe; font-weight: 800; font-size: .76rem;
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
# so the shape keeps rearranging. z-index is above Streamlit's sidebar and header.
LOADER_CSS = (
    "<style>"
    # while the loader is on screen the sidebar and header are hidden, so nothing shows through
    'section[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],'
    'header[data-testid="stHeader"]{visibility:hidden !important;}'
    ".ld-overlay{position:fixed;top:0;left:0;right:0;bottom:0;z-index:2147483000;"
    "display:flex;align-items:center;justify-content:center;"
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


def logo_svg(size=40):
    """The site logo (own drawing, no emoji): a gradient tile with three wind / smog streaks."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" '
        'style="flex:none;display:block">'
        '<defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#38bdf8"/><stop offset="1" stop-color="#8b5cf6"/>'
        '</linearGradient></defs>'
        '<rect width="48" height="48" rx="13" fill="url(#lg)"/>'
        '<g fill="none" stroke="#ffffff" stroke-width="3.4" stroke-linecap="round">'
        '<path d="M10 17h19a5 5 0 1 0-5-5"/>'
        '<path d="M10 25h27a5 5 0 1 1-5 5"/>'
        '<path d="M10 33h13a4 4 0 1 1-4 4"/></g></svg>'
    )


def sidebar_brand(is_open):
    """Top of the sidebar: logo + name when open, only the logo when closed (centred)."""
    if is_open:
        return (
            '<div class="sb-brand">' + logo_svg(42) +
            '<div class="sb-name">Pakistan<br>Air Quality</div></div>'
        )
    return '<div class="sb-brand sb-brand-closed">' + logo_svg(42) + "</div>"


def nav_css(is_open):
    """
    Icon-rail sidebar (reference: TraceGit). Simple block layout, no flex on Streamlit's wrappers,
    so nothing can be drawn twice. Only the button itself is styled.
    Closed: 54px buttons centred. Open: full-width buttons, icon + name from the left.
    """
    width = 270 if is_open else 92
    sb = 'section[data-testid="stSidebar"]'
    btn = f'{sb} [data-testid="stButton"] button'
    css = (
        "<style>"
        f"{sb}{{width:{width}px !important;min-width:{width}px !important;"
        f"max-width:{width}px !important;transition:width .25s ease;}}"
        f'{sb} [data-testid="stSidebarHeader"],{sb} [data-testid="stSidebarCollapseButton"]'
        "{display:none !important;}"
        f'{sb} [data-testid="stSidebarUserContent"]{{padding:1rem .6rem !important;}}'
        # wrappers: plain full-width blocks
        f'{sb} [data-testid="stButton"],{sb} [data-testid="stTooltipHoverTarget"]'
        "{display:block !important;width:100% !important;}"
        # logo block
        ".sb-brand{display:flex;align-items:center;gap:12px;padding:6px 6px 14px 6px;}"
        ".sb-name{color:#f1f5f9;font-weight:800;font-size:1.05rem;line-height:1.2;}"
        # every item: no box
        f"{btn}{{display:flex !important;align-items:center !important;height:54px !important;"
        "min-height:54px !important;box-sizing:border-box;white-space:nowrap;"
        "border:none !important;background:transparent !important;box-shadow:none !important;"
        "color:#cbd5e1;font-size:1rem;border-radius:14px;}"
        f"{btn} [data-testid='stIconMaterial']"
        "{font-size:1.55rem !important;flex:none !important;margin:0 !important;"
        "font-weight:400 !important;font-synthesis:none !important;}"
        f"{btn}:hover{{background:rgba(148,163,184,.12) !important;color:#f8fafc;transform:none;}}"
        # active page: the only filled item
        f'{btn}[kind="primary"],{btn}[data-testid="stBaseButton-primary"]'
        "{background:#4f46e5 !important;color:#ffffff !important;"
        "box-shadow:0 6px 20px rgba(79,70,229,.45) !important;}"
    )
    if is_open:
        tg = f"{sb} .st-key-nav_toggle"
        css += (
            f"{btn}{{width:100% !important;justify-content:flex-start !important;"
            "gap:16px !important;padding:0 1rem !important;}"
            + tg + " button{width:44px !important;min-width:44px !important;"
            "padding:0 !important;justify-content:center !important;gap:0 !important;"
            "height:44px !important;min-height:44px !important;margin-left:auto !important;}"
            + tg + ' [data-testid="stMarkdownContainer"]{display:none !important;}'
            + sb + ' [data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;gap:.3rem !important;}'
        )
    else:
        css += (
            f"{btn}{{width:54px !important;min-width:54px !important;max-width:54px !important;"
            "justify-content:center !important;gap:0 !important;padding:0 !important;"
            "margin-left:auto !important;margin-right:auto !important;}"
            f'{btn}[kind="primary"],{btn}[data-testid="stBaseButton-primary"]{{border-radius:50% !important;}}'
            f'{btn} [data-testid="stMarkdownContainer"]{{display:none !important;}}'
        )
    css += "</style>"
    return css


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
