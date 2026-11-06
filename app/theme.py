import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

BG = "#0B1120"
SURFACE = "#131C2E"
SURFACE_2 = "#1B2538"
BORDER = "rgba(255,255,255,0.08)"
TEXT = "#E2E8F0"
TEXT_2 = "#94A3B8"
MUTED = "#7C8AA0"
GRID = "#1F2A3F"
AXIS = "#334155"
ACCENT = "#22C55E"

SERIES = ["#3987E5", "#D95926", "#199E70", "#9085E9"]
HIGHLIGHT = SERIES[0]
CONTEXT = "#3B475C"
POS = "#3987E5"
NEG = "#E66767"
NEUTRAL = "#334155"
LINE_COLORS = {"G": "#C98500", "D": "#3987E5", "M": "#D95926", "A": "#199E70"}
LINE_LABELS = {"G": "Gardiens", "D": "Défenseurs", "M": "Milieux", "A": "Attaquants"}
RESULT_COLORS = {"V": "#0CA30C", "N": "#FAB219", "D": "#D03B3B"}
SEQUENTIAL = ["#16233A", "#1A3560", "#1C4A86", "#215FAA", "#2C74CF", "#3987E5"]
DIVERGING = [[0.0, NEG], [0.5, NEUTRAL], [1.0, POS]]

FONT = '"Fira Sans", system-ui, -apple-system, "Segoe UI", sans-serif'

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;600;700&family=Fira+Code:wght@500;600&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], button, input, textarea, select {{
    font-family: {FONT};
}}
[data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(1200px 500px at 85% -10%, rgba(57,135,229,0.10), transparent 60%),
        radial-gradient(900px 400px at -10% 0%, rgba(34,197,94,0.07), transparent 60%),
        {BG};
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1400px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
h1 {{ font-weight: 700; }}
h2 {{ font-size: 1.35rem !important; font-weight: 600; margin-top: 1.6rem !important; }}
h3 {{ font-size: 1.05rem !important; font-weight: 600; color: {TEXT}; }}

.hero {{ margin-bottom: 1.2rem; }}
.hero .eyebrow {{ color: {ACCENT}; font-size: .78rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; }}
.hero .title {{ font-size: 2.1rem; font-weight: 700; line-height: 1.15; margin: .2rem 0 .35rem;
    background: linear-gradient(90deg, {TEXT} 0%, #B7D3F6 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.hero .subtitle {{ color: {TEXT_2}; font-size: 1rem; max-width: 820px; line-height: 1.5; }}

.kpi {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; padding: 14px 16px 12px;
    height: 100%; min-height: 112px; transition: border-color .2s ease, transform .2s ease; }}
.kpi:hover {{ border-color: rgba(34,197,94,0.45); transform: translateY(-1px); }}
.kpi .label {{ color: {TEXT_2}; font-size: .78rem; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; }}
.kpi .value {{ color: {TEXT}; font-size: 1.55rem; font-weight: 700; line-height: 1.25; margin-top: 4px;
    overflow-wrap: anywhere; }}
.kpi .value.small {{ font-size: 1.15rem; }}
.kpi .sub {{ color: {MUTED}; font-size: .82rem; margin-top: 2px; line-height: 1.35; }}
.kpi .accent {{ display: inline-block; width: 22px; height: 3px; border-radius: 2px; background: {ACCENT}; margin-bottom: 8px; }}

.chip {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: .78rem; font-weight: 600;
    border: 1px solid {BORDER}; background: {SURFACE_2}; color: {TEXT}; margin-right: 4px; white-space: nowrap; }}
.res {{ display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 6px;
    font-size: .74rem; font-weight: 700; color: #0B1120; margin-right: 3px; }}
.res.V {{ background: {RESULT_COLORS["V"]}; color: #FFFFFF; }}
.res.N {{ background: {RESULT_COLORS["N"]}; }}
.res.D {{ background: {RESULT_COLORS["D"]}; color: #FFFFFF; }}

.fixture {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; padding: 12px 14px; margin-bottom: 10px; }}
.fixture .row {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; }}
.fixture .team {{ font-weight: 600; color: {TEXT}; font-size: .95rem; }}
.fixture .meta {{ color: {MUTED}; font-size: .8rem; }}
.fixture .score {{ font-family: "Fira Code", monospace; font-weight: 600; font-size: 1.1rem; color: {TEXT}; }}
.fixture.me {{ border-color: rgba(57,135,229,0.65); }}

.callout {{ border-left: 3px solid {ACCENT}; background: rgba(34,197,94,0.06); padding: 10px 14px; border-radius: 0 10px 10px 0;
    color: {TEXT}; font-size: .93rem; line-height: 1.5; margin: .4rem 0 1rem; }}
.callout.warn {{ border-left-color: #FAB219; background: rgba(250,178,25,0.07); }}
.muted {{ color: {MUTED}; font-size: .85rem; }}
.pbar {{ display: flex; height: 26px; border-radius: 8px; overflow: hidden; margin: 10px 0 6px; gap: 2px; }}
.pbar div {{ display: flex; align-items: center; justify-content: center; font-size: .78rem; font-weight: 700;
    color: #FFFFFF; min-width: 26px; white-space: nowrap; }}
.pbar .h {{ background: {SERIES[0]}; }}
.pbar .d {{ background: #5A6B86; }}
.pbar .a {{ background: {SERIES[1]}; }}
.plegend {{ display: flex; justify-content: space-between; color: {MUTED}; font-size: .75rem; }}

[data-testid="stExpander"] details {{ border: 1px solid {BORDER}; border-radius: 12px; background: rgba(19,28,46,0.6); }}
[data-testid="stExpander"] summary p {{ color: {TEXT_2}; font-size: .88rem; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 12px; overflow: hidden; }}
[data-testid="stPlotlyChart"] {{ border: 1px solid {BORDER}; border-radius: 14px; overflow: hidden; }}
button:focus-visible, [role="tab"]:focus-visible, [role="radio"]:focus-visible {{ outline: 2px solid {ACCENT} !important; outline-offset: 2px; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def _template() -> go.layout.Template:
    t = go.layout.Template()
    axis = dict(
        gridcolor=GRID,
        linecolor=AXIS,
        zerolinecolor=AXIS,
        zerolinewidth=1,
        tickfont=dict(color=MUTED, size=12),
        title=dict(font=dict(color=TEXT_2, size=12)),
        showline=False,
        ticks="",
        automargin=True,
    )
    t.layout = go.Layout(
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=TEXT, size=13),
        colorway=SERIES,
        xaxis=axis,
        yaxis=axis,
        margin=dict(l=12, r=16, t=78, b=56),
        title=dict(
            font=dict(size=15, color=TEXT), x=0.01, xanchor="left", y=1, yref="container", yanchor="top", pad=dict(t=14)
        ),
        legend=dict(
            traceorder="normal",
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(color=TEXT_2, size=12),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=AXIS, font=dict(family=FONT, color=TEXT, size=13)),
        hovermode="closest",
        barcornerradius=4,
        bargap=0.28,
    )
    return t


pio.templates["napoly"] = _template()
pio.templates.default = "napoly"
