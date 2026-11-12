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
DISPLAY = '"Barlow Condensed", "Fira Sans Condensed", "Arial Narrow", sans-serif'
ME_TINT = "#8DB8F0"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;600;700&family=Barlow+Condensed:wght@500;600;700&display=swap');

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
.block-container {{ padding-top: 2.2rem; padding-bottom: 5rem; max-width: 1320px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
h1 {{ font-weight: 700; }}
h2 {{ font-size: 1.35rem !important; font-weight: 600; margin-top: 1.6rem !important; }}
[data-testid="stMainBlockContainer"] h3 {{ font-family: {DISPLAY}; font-size: 1.55rem !important; font-weight: 600;
    letter-spacing: .005em; color: {TEXT}; padding-top: 2.1rem; }}
[data-testid="stExpander"] h3 {{ font-family: {FONT}; font-size: 1.05rem !important; padding-top: .6rem; }}

.hero {{ margin-bottom: 1.6rem; }}
.hero .eyebrow {{ color: {ACCENT}; font-size: .9rem; font-weight: 600; }}
.hero .title {{ font-family: {DISPLAY}; font-size: 2.9rem; font-weight: 700; line-height: 1.02; margin: .25rem 0 .55rem;
    color: {TEXT}; letter-spacing: -.005em; }}
.hero .subtitle {{ color: {TEXT_2}; font-size: 1rem; max-width: 72ch; line-height: 1.55; }}

.stats {{ --n: 4; display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 1px; background: {BORDER};
    border: 1px solid {BORDER}; border-radius: 14px; overflow: hidden; margin: .2rem 0 1.1rem; }}
.stat {{ background: {SURFACE}; padding: 16px 20px 15px; min-width: 0; }}
.stat .label {{ color: {TEXT_2}; font-size: .84rem; font-weight: 500; line-height: 1.3; }}
.stat .value {{ font-family: {DISPLAY}; color: {TEXT}; font-size: 2.15rem; font-weight: 600; line-height: 1.05;
    margin-top: 6px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }}
.stat .value.small {{ font-size: 1.6rem; line-height: 1.1; }}
.stat .value .of {{ font-size: 1.1rem; color: {MUTED}; font-weight: 500; margin-left: 2px; }}
.stat .sub {{ color: {MUTED}; font-size: .82rem; margin-top: 5px; line-height: 1.4; }}
.stat.me {{ box-shadow: inset 3px 0 0 {HIGHLIGHT}; background: linear-gradient(90deg, rgba(57,135,229,0.09), {SURFACE} 70%); }}
.stat.me .label {{ color: {ME_TINT}; }}
.stat.empty {{ opacity: .55; }}
.stat .dots {{ display: flex; gap: 5px; margin: 8px 0 2px; }}
.stat .dot {{ width: 9px; height: 9px; border-radius: 50%; }}
.stat .dot.on {{ background: {ACCENT}; }}
.stat .dot.off {{ border: 1.5px solid {AXIS}; }}
.stat .warn {{ color: #FAB219; }}

.panel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; padding: 4px 22px; margin: .2rem 0 .6rem; }}
.ladder {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); column-gap: 36px; }}
.rung {{ display: grid; grid-template-columns: 1fr auto; align-items: end; row-gap: 8px; padding: 14px 0 15px;
    border-bottom: 1px solid {BORDER}; }}
.ladder .rung:nth-last-child(-n+3) {{ border-bottom: none; }}
.rung .name {{ color: {TEXT}; font-weight: 600; font-size: .92rem; }}
.rung .hint {{ color: {MUTED}; font-size: .78rem; margin-top: 1px; }}
.rung .rank {{ font-family: {DISPLAY}; font-size: 1.9rem; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums; }}
.rung .rank span {{ font-size: 1rem; color: {MUTED}; font-weight: 500; }}
.rung .track {{ grid-column: 1 / -1; display: flex; gap: 3px; }}
.rung .track i {{ flex: 1; height: 5px; border-radius: 2px; background: {SURFACE_2}; }}

.top5 {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; background: {BORDER};
    border: 1px solid {BORDER}; border-radius: 14px; overflow: hidden; margin-bottom: 1rem; }}
.top5 > div {{ background: {SURFACE}; padding: 14px 18px 10px; min-width: 0; }}
.top5 .head {{ font-family: {DISPLAY}; font-size: 1.25rem; font-weight: 600; color: {TEXT}; margin-bottom: 4px; }}
.top5 .p {{ display: grid; grid-template-columns: 1fr auto; column-gap: 10px; padding: 7px 0; border-top: 1px solid {BORDER}; }}
.top5 .p:first-of-type {{ border-top: none; }}
.top5 .who {{ color: {TEXT}; font-size: .9rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.top5 .club {{ color: {MUTED}; font-size: .78rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.top5 .note {{ font-family: {DISPLAY}; font-size: 1.3rem; font-weight: 600; color: {TEXT}; align-self: center;
    font-variant-numeric: tabular-nums; }}
.top5 .p.me .who {{ color: {ME_TINT}; }}

.chip {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: .76rem; font-weight: 600;
    border: 1px solid {BORDER}; background: {SURFACE_2}; color: {TEXT_2}; margin: 0 4px 4px 0; white-space: nowrap; }}
.res {{ display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 5px;
    font-size: .7rem; font-weight: 700; color: #0B1120; margin-right: 3px; }}
.res.V {{ background: {RESULT_COLORS["V"]}; color: #FFFFFF; }}
.res.N {{ background: {RESULT_COLORS["N"]}; }}
.res.D {{ background: {RESULT_COLORS["D"]}; color: #FFFFFF; }}

.fixtures {{ --cols: 5; display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 12px; margin: .2rem 0 .8rem; }}
.fixture {{ display: flex; flex-direction: column; background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px;
    padding: 14px 16px; min-width: 0; }}
.fixture .row {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
.fixture .team {{ font-weight: 600; color: {TEXT}; font-size: .95rem; line-height: 1.3; overflow-wrap: anywhere; }}
.fixture .meta {{ color: {MUTED}; font-size: .8rem; line-height: 1.45; }}
.fixture .vs {{ display: flex; align-items: center; gap: 8px; color: {MUTED}; font-size: .74rem; margin: 9px 0; }}
.fixture .vs::before, .fixture .vs::after {{ content: ""; flex: 1; height: 1px; background: {BORDER}; }}
.fixture .side + .side {{ margin-top: 2px; }}
.fixture .form {{ margin-top: 6px; }}
.fixture .foot {{ margin-top: auto; padding-top: 10px; }}
.fixture .score {{ font-family: {DISPLAY}; font-weight: 700; font-size: 1.9rem; line-height: 1; color: {TEXT};
    font-variant-numeric: tabular-nums; white-space: nowrap; }}
.fixture.me {{ border-color: rgba(57,135,229,0.7); box-shadow: inset 0 3px 0 {HIGHLIGHT}; }}
.fixture.result .row.top {{ align-items: flex-start; }}
.fixture.result .scorers {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }}
.fixture.result .bonus {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.fixture.result .right {{ text-align: right; }}

.callout {{ border-left: 3px solid {ACCENT}; background: rgba(34,197,94,0.06); padding: 10px 14px; border-radius: 0 10px 10px 0;
    color: {TEXT}; font-size: .93rem; line-height: 1.5; margin: .4rem 0 1rem; }}
.callout.warn {{ border-left-color: #FAB219; background: rgba(250,178,25,0.07); }}
.muted {{ color: {MUTED}; font-size: .85rem; }}
.pbar {{ display: flex; height: 24px; border-radius: 7px; overflow: hidden; margin: 12px 0 5px; gap: 2px; }}
.pbar div {{ display: flex; align-items: center; justify-content: center; font-size: .76rem; font-weight: 700;
    color: #FFFFFF; min-width: 26px; white-space: nowrap; }}
.pbar .h {{ background: {SERIES[0]}; }}
.pbar .d {{ background: #5A6B86; }}
.pbar .a {{ background: {SERIES[1]}; }}
.plegend {{ display: flex; justify-content: space-between; color: {MUTED}; font-size: .74rem; }}

@media (max-width: 1100px) {{
    .stats, .fixtures {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .ladder {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .ladder .rung:nth-last-child(-n+3) {{ border-bottom: 1px solid {BORDER}; }}
    .top5 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 640px) {{
    .block-container {{ padding: 3.6rem 1rem 4rem; }}
    [data-testid="stHeader"] {{ background: rgba(11,17,32,0.88); backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px); border-bottom: 1px solid {BORDER}; }}
    [data-testid="stMainBlockContainer"] h3 {{ font-size: 1.4rem !important; padding-top: 1.4rem; }}
    .hero {{ margin-bottom: 1.1rem; }}
    .hero .title {{ font-size: 2.15rem; }}
    .hero .subtitle {{ font-size: .94rem; line-height: 1.5; }}

    .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); border-radius: 12px; }}
    .stats > .stat:last-child:nth-child(odd) {{ grid-column: 1 / -1; }}
    .stat {{ padding: 12px 14px; }}
    .stat .label {{ font-size: .78rem; }}
    .stat .value {{ font-size: 1.7rem; margin-top: 4px; }}
    .stat .value.small {{ font-size: 1.3rem; }}
    .stat .value .of {{ font-size: .95rem; }}
    .stat .sub {{ font-size: .76rem; }}

    .panel {{ padding: 2px 14px; }}
    .ladder {{ grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 18px; }}
    .ladder .rung:nth-last-child(-n+3) {{ border-bottom: 1px solid {BORDER}; }}
    .ladder .rung:nth-last-child(-n+2) {{ border-bottom: none; }}
    .rung {{ padding: 12px 0; }}
    .rung .name {{ font-size: .86rem; }}
    .rung .hint {{ font-size: .72rem; }}
    .rung .rank {{ font-size: 1.6rem; }}

    .top5 {{ grid-template-columns: minmax(0, 1fr); }}
    .fixtures {{ grid-template-columns: minmax(0, 1fr); gap: 10px; }}
    .fixture {{ padding: 12px 14px; }}
    .fixture .team {{ font-size: .9rem; }}
    .fixture .pair {{ display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); column-gap: 10px;
        align-items: start; }}
    .fixture .pair > :last-child {{ text-align: right; }}
    .fixture .pair .vs {{ margin: 0; align-self: center; }}
    .fixture .pair .vs::before, .fixture .pair .vs::after {{ display: none; }}
    .fixture .score {{ font-size: 1.6rem; }}
    .fixture.result .row.top {{ gap: 8px; }}
    .fixture.result .scorers {{ gap: 8px; }}

    div.chart-title {{ padding: 12px 12px 0; font-size: .9rem; }}
    [data-testid="stButtonGroup"] > div {{ flex-wrap: wrap; }}
}}

[data-testid="stExpander"] details {{ border: 1px solid {BORDER}; border-radius: 12px; background: rgba(19,28,46,0.6); }}
[data-testid="stExpander"] summary p {{ color: {TEXT_2}; font-size: .88rem; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 12px; overflow: hidden; }}
[data-testid="stPlotlyChart"] {{ border: 1px solid {BORDER}; border-radius: 14px; overflow: hidden; }}
.chart-title {{ color: {TEXT}; font-size: .95rem; font-weight: 500; line-height: 1.35; padding: 15px 16px 0; }}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .chart-title) {{ gap: 0; background: {SURFACE};
    border: 1px solid {BORDER}; border-radius: 14px; overflow: hidden; }}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .chart-title) [data-testid="stPlotlyChart"] {{
    border: none; border-radius: 0; }}
[data-testid="stTabs"] [role="tab"] p {{ font-size: .92rem; font-weight: 500; }}
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
