import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

BG = "#0B1120"
SURFACE = "#131C2E"
SURFACE_2 = "#1B2538"
BORDER = "rgba(255,255,255,0.08)"
GRID = "#1F2A3F"
AXIS = "#334155"
WHITE = "#FFFFFF"

TEXT = "#E2E8F0"
TEXT_2 = "#94A3B8"
MUTED = "#8A97AC"

ACCENT = "#22C55E"

ME = "#3987E5"
ME_TINT = "#8DB8F0"
ME_BG = "#17253F"

GOOD = "#17A34A"
WARN = "#FAB219"
BAD = "#E66767"

RES_V = "#15803D"
RES_N = "#FAB219"
RES_D = "#C53030"
RESULT_COLORS = {"V": RES_V, "N": RES_N, "D": RES_D}

P_HOME = "#2563C9"
P_DRAW = "#5A6B86"
P_AWAY = "#B8480F"

GOLD = "#E0B341"
SILVER = "#B8C4D6"
BRONZE = "#C58A5A"

SERIES = ["#3987E5", "#D95926", "#199E70", "#9085E9"]
HIGHLIGHT = ME
CONTEXT = "#59687F"
CONTEXT_DIM = "#2A3A55"
CONTEXT_LIGHT = "#8FA3BF"
POS = "#3987E5"
NEG = BAD
NEUTRAL = "#334155"
LINE_COLORS = {"G": "#C98500", "D": "#3987E5", "M": "#D95926", "A": "#199E70"}
LINE_LABELS = {"G": "Gardiens", "D": "Défenseurs", "M": "Milieux", "A": "Attaquants"}
SEQUENTIAL = ["#16233A", "#1A3560", "#1C4A86", "#215FAA", "#2C74CF", "#3987E5"]
DIVERGING = [[0.0, NEG], [0.5, NEUTRAL], [1.0, POS]]

FONT = '"Fira Sans", system-ui, -apple-system, "Segoe UI", sans-serif'
DISPLAY = '"Barlow Condensed", "Fira Sans Condensed", "Arial Narrow", sans-serif'

SPACE = (4, 8, 12, 16, 24)
RADIUS_CARD = 14
RADIUS_TABLE = 12
RADIUS_PILL = 999
BP_PHONE = 640
BP_TABLET = 1100
FONT_FLOOR_REM = 0.75


def rgba(color: str, alpha: float) -> str:
    h = color.removeprefix("#")
    if len(h) != 6:
        raise ValueError(f"Couleur hexadécimale à 6 chiffres attendue, reçu {color!r}")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha:g})"


CSS = f"""
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], button, input, textarea, select {{
    font-family: {FONT};
}}
[data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(1200px 500px at 85% -10%, {rgba(ME, 0.10)}, transparent 60%),
        radial-gradient(900px 400px at -10% 0%, {rgba(ACCENT, 0.07)}, transparent 60%),
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

.tone-good {{ --tone: {GOOD}; }}
.tone-warn {{ --tone: {WARN}; }}
.tone-bad {{ --tone: {BAD}; }}
.tone-mid {{ --tone: {TEXT_2}; }}
.mt-6 {{ margin-top: 6px; }}
.mt-8 {{ margin-top: {SPACE[1]}px; }}
.mt-12 {{ margin-top: {SPACE[2]}px; }}
.pt-6 {{ padding-top: 6px; }}
.grow {{ flex: 1; min-width: 0; }}
.minw0 {{ min-width: 0; }}

.hero {{ margin-bottom: 1.6rem; }}
.hero .eyebrow {{ color: {ACCENT}; font-size: .9rem; font-weight: 600; }}
.hero .title {{ font-family: {DISPLAY}; font-size: 2.9rem; font-weight: 700; line-height: 1.02; margin: .25rem 0 .55rem;
    color: {TEXT}; letter-spacing: -.005em; }}
.hero .subtitle {{ color: {TEXT_2}; font-size: 1rem; max-width: 72ch; line-height: 1.55; }}
.volet-title {{ margin: .4rem 0 1.2rem; }}
.volet-title .title {{ font-family: {DISPLAY}; font-size: 2rem; font-weight: 700; line-height: 1.1; color: {TEXT};
    letter-spacing: -.005em; overflow-wrap: anywhere; }}
.volet-title .subtitle {{ color: {TEXT_2}; font-size: 1rem; max-width: 72ch; line-height: 1.55; margin-top: .35rem; }}

.stats {{ --n: 4; display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 1px; background: {BORDER};
    border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; overflow: hidden; margin: .2rem 0 1.1rem; }}
.stat {{ background: {SURFACE}; padding: 16px 20px 15px; min-width: 0; }}
.stat .label {{ color: {TEXT_2}; font-size: .84rem; font-weight: 500; line-height: 1.3; }}
.stat .value {{ font-family: {DISPLAY}; color: {TEXT}; font-size: 2.15rem; font-weight: 600; line-height: 1.05;
    margin-top: 6px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }}
.stat .value.small {{ font-size: 1.6rem; line-height: 1.1; }}
.stat .value .of {{ font-size: 1.1rem; color: {MUTED}; font-weight: 500; margin-left: 2px; }}
.stat .sub {{ color: {MUTED}; font-size: .82rem; margin-top: 5px; line-height: 1.4; }}
.stat.me {{ box-shadow: inset 3px 0 0 {ME}; background: linear-gradient(90deg, {rgba(ME, 0.09)}, {SURFACE} 70%); }}
.stat.me .label {{ color: {ME_TINT}; }}
.stat.empty {{ opacity: .55; }}
.stat .dots {{ display: flex; gap: 5px; margin: 8px 0 2px; }}
.stat .dot {{ width: 9px; height: 9px; border-radius: 50%; }}
.stat .dot.on {{ background: {ACCENT}; }}
.stat .dot.off {{ border: 1.5px solid {AXIS}; }}
.stat .warn {{ color: {WARN}; }}

.panel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; padding: 4px 22px;
    margin: .2rem 0 .6rem; }}
.ladder {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); column-gap: 36px; }}
.rung {{ display: grid; grid-template-columns: 1fr auto; align-items: end; row-gap: 8px; padding: 14px 0 15px;
    border-bottom: 1px solid {BORDER}; }}
.ladder .rung:nth-last-child(-n+3) {{ border-bottom: none; }}
.rung .name {{ color: {TEXT}; font-weight: 600; font-size: .92rem; }}
.rung .hint {{ color: {MUTED}; font-size: .78rem; margin-top: 1px; }}
.rung .rank {{ font-family: {DISPLAY}; font-size: 1.9rem; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums;
    color: var(--tone, {TEXT}); }}
.rung .rank span {{ font-size: 1rem; color: {MUTED}; font-weight: 500; }}
.rung .track {{ grid-column: 1 / -1; display: flex; gap: 3px; }}
.rung .track i {{ flex: 1; height: 5px; border-radius: 2px; background: {SURFACE_2}; }}
.rung .track i.on {{ background: var(--tone, {TEXT}); }}

.top5 {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; background: {BORDER};
    border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; overflow: hidden; margin-bottom: 1rem; }}
.top5 > div {{ background: {SURFACE}; padding: 14px 18px 10px; min-width: 0; }}
.top5 .head {{ font-family: {DISPLAY}; font-size: 1.25rem; font-weight: 600; color: {TEXT}; margin-bottom: 4px; }}
.top5 .p {{ display: grid; grid-template-columns: 1fr auto; column-gap: 10px; padding: 7px 0; border-top: 1px solid {BORDER}; }}
.top5 .p:first-of-type {{ border-top: none; }}
.top5 .who {{ color: {TEXT}; font-size: .9rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.top5 .club {{ color: {MUTED}; font-size: .78rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.top5 .note {{ font-family: {DISPLAY}; font-size: 1.3rem; font-weight: 600; color: {TEXT}; align-self: center;
    font-variant-numeric: tabular-nums; }}
.top5 .p.me .who {{ color: {ME_TINT}; }}

.chip {{ display: inline-block; padding: 1px 8px; border-radius: {RADIUS_PILL}px; font-size: .76rem; font-weight: 600;
    border: 1px solid {BORDER}; background: {SURFACE_2}; color: {TEXT_2}; margin: 0 4px 4px 0; white-space: nowrap; }}
.chip.good {{ border-color: {rgba(GOOD, 0.7)}; }}
.chip.bad {{ border-color: {rgba(BAD, 0.7)}; }}
.chip.off {{ opacity: .45; }}
.res {{ display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 5px;
    font-size: {FONT_FLOOR_REM}rem; font-weight: 700; color: {BG}; margin-right: 3px; }}
.res.V {{ background: {RES_V}; color: {WHITE}; }}
.res.N {{ background: {RES_N}; }}
.res.D {{ background: {RES_D}; color: {WHITE}; }}

.fixtures {{ --cols: 5; display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 12px;
    margin: .2rem 0 .8rem; }}
.fixture {{ display: flex; flex-direction: column; background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD}px; padding: 14px 16px; min-width: 0; }}
.fixture .row {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
.fixture .team {{ font-weight: 600; color: {TEXT}; font-size: .95rem; line-height: 1.3; overflow-wrap: anywhere; }}
.fixture .meta {{ color: {MUTED}; font-size: .8rem; line-height: 1.45; }}
.fixture .vs {{ display: flex; align-items: center; gap: 8px; color: {MUTED}; font-size: {FONT_FLOOR_REM}rem; margin: 9px 0; }}
.fixture .vs::before, .fixture .vs::after {{ content: ""; flex: 1; height: 1px; background: {BORDER}; }}
.fixture .side + .side {{ margin-top: 2px; }}
.fixture .form {{ margin-top: 6px; }}
.fixture .foot {{ margin-top: auto; padding-top: 10px; }}
.fixture .score {{ font-family: {DISPLAY}; font-weight: 700; font-size: 1.9rem; line-height: 1; color: {TEXT};
    font-variant-numeric: tabular-nums; white-space: nowrap; }}
.fixture.me {{ border-color: {rgba(ME, 0.7)}; box-shadow: inset 0 3px 0 {ME}; }}
.fixture.result .row.top {{ align-items: flex-start; }}
.fixture.result .scorers {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }}
.fixture.result .bonus {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.fixture.result .right {{ text-align: right; }}

.callout {{ border-left: 3px solid {ACCENT}; background: {rgba(ACCENT, 0.06)}; padding: 10px 14px; border-radius: 0 10px 10px 0;
    color: {TEXT}; font-size: .93rem; line-height: 1.5; margin: .4rem 0 1rem; }}
.callout.warn {{ border-left-color: {WARN}; background: {rgba(WARN, 0.07)}; }}
.banner {{ border-left: 3px solid {WARN}; background: {rgba(WARN, 0.07)}; padding: 10px 14px; border-radius: 0 10px 10px 0;
    color: {TEXT}; font-size: .93rem; line-height: 1.5; margin: .4rem 0 1rem; }}
.banner .title {{ font-weight: 600; }}
.banner ul {{ margin: 4px 0 0; padding-left: 1.2rem; color: {TEXT_2}; }}
.empty:not(.stat) {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; padding: 18px 20px;
    margin: .2rem 0 1rem; }}
.empty:not(.stat) .title {{ color: {TEXT}; font-weight: 600; font-size: 1rem; }}
.empty:not(.stat) .reason {{ color: {MUTED}; font-size: .9rem; line-height: 1.5; margin-top: 4px; }}
.muted {{ color: {MUTED}; font-size: .85rem; }}
.pbar {{ display: flex; height: 24px; border-radius: 7px; overflow: hidden; margin: 12px 0 5px; gap: 2px; }}
.pbar div {{ display: flex; align-items: center; justify-content: center; font-size: .76rem; font-weight: 700;
    color: {WHITE}; min-width: 26px; white-space: nowrap; }}
.pbar .h {{ background: {P_HOME}; }}
.pbar .d {{ background: {P_DRAW}; }}
.pbar .a {{ background: {P_AWAY}; }}
.plegend {{ display: flex; justify-content: space-between; color: {MUTED}; font-size: {FONT_FLOOR_REM}rem; }}

.pitch {{ background: linear-gradient(180deg, {rgba(LINE_COLORS["A"], 0.10)}, {rgba(LINE_COLORS["A"], 0.04)});
    border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; padding: 14px 12px; display: flex; flex-direction: column;
    gap: 12px; }}
.pitch .line {{ display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }}
.pp {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_TABLE}px; padding: 8px 10px 7px; width: 132px;
    min-width: 0; border-top: 3px solid var(--tone); position: relative; }}
.pp .nm {{ color: {TEXT}; font-weight: 600; font-size: .86rem; line-height: 1.2; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }}
.pp .mt {{ color: {MUTED}; font-size: {FONT_FLOOR_REM}rem; line-height: 1.35; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }}
.pp .nb {{ display: flex; justify-content: space-between; align-items: baseline; margin-top: 3px; }}
.pp .nt {{ font-family: {DISPLAY}; font-size: 1.25rem; font-weight: 600; color: {TEXT}; font-variant-numeric: tabular-nums; }}
.pp .pj {{ font-size: {FONT_FLOOR_REM}rem; font-weight: 600; color: var(--tone); }}
.pp .badge {{ position: absolute; top: -9px; right: 8px; font-size: {FONT_FLOOR_REM}rem; font-weight: 700;
    border-radius: {RADIUS_PILL}px; padding: 1px 7px; background: {TEXT}; color: {BG}; }}
.pp .badge.mcdo {{ background: {WARN}; right: auto; left: 8px; }}
.bench {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; padding: 6px 16px; }}
.bench .b {{ display: grid; grid-template-columns: 22px 30px minmax(0, 1fr) auto auto; gap: 10px; align-items: center;
    padding: 8px 0; border-top: 1px solid {BORDER}; font-size: .86rem; color: {TEXT}; }}
.bench .b:first-child {{ border-top: none; }}
.bench .ix {{ color: {MUTED}; font-variant-numeric: tabular-nums; }}
.bench .ln {{ font-size: {FONT_FLOOR_REM}rem; font-weight: 700; border-radius: 5px; text-align: center;
    padding: 1px 0; color: {BG}; }}
.ln.G {{ background: {LINE_COLORS["G"]}; }}
.ln.D {{ background: {LINE_COLORS["D"]}; }}
.ln.M {{ background: {LINE_COLORS["M"]}; }}
.ln.A {{ background: {LINE_COLORS["A"]}; }}
.bench .sub {{ color: {MUTED}; font-size: {FONT_FLOOR_REM}rem; }}
.bench .v {{ font-variant-numeric: tabular-nums; color: var(--tone, {TEXT_2}); font-size: .8rem; }}
.tac {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 12px; margin-top: 8px;
    font-size: .85rem; color: {TEXT}; }}
.tac b {{ font-family: {DISPLAY}; font-size: 1rem; }}

.ranks {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; padding: 2px 14px; }}
.ranks .r {{ display: grid; grid-template-columns: 26px minmax(0, 1fr) auto auto; column-gap: 10px; align-items: center;
    padding: 9px 0; border-top: 1px solid {BORDER}; }}
.ranks .r:first-child {{ border-top: none; }}
.ranks .pos {{ font-family: {DISPLAY}; font-size: 1.15rem; font-weight: 600; color: {TEXT_2};
    font-variant-numeric: tabular-nums; }}
.ranks .pos.small {{ font-size: .8rem; }}
.ranks .who {{ color: {TEXT}; font-weight: 600; font-size: .92rem; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }}
.ranks .sub {{ color: {MUTED}; font-size: .76rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.ranks .side {{ color: {TEXT_2}; font-size: .8rem; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.ranks .big {{ font-family: {DISPLAY}; font-size: 1.35rem; font-weight: 600; color: {TEXT};
    font-variant-numeric: tabular-nums; min-width: 2.2ch; text-align: right; }}
.ranks .big small {{ font-size: {FONT_FLOOR_REM}rem; color: {MUTED}; font-weight: 500; margin-left: 2px; }}
.ranks .r.me {{ margin: 0 -14px; padding: 9px 14px; box-shadow: inset 3px 0 0 {ME};
    background: linear-gradient(90deg, {rgba(ME, 0.12)}, transparent 75%); }}
.ranks .r.me .who {{ color: {ME_TINT}; }}
.ranks .hide-s {{ display: inline; }}

.next {{ background: {SURFACE}; border: 1px solid {rgba(ME, 0.55)}; border-radius: 16px; padding: 18px 20px;
    box-shadow: inset 0 3px 0 {ME}; margin-bottom: 1rem; }}
.next .when {{ color: {TEXT_2}; font-size: .84rem; }}
.next .odds {{ font-family: {DISPLAY}; font-size: 3.2rem; font-weight: 700; line-height: 1; color: {TEXT};
    margin: 10px 0 2px; font-variant-numeric: tabular-nums; }}
.next .odds span {{ font-size: 1.15rem; font-weight: 500; color: {TEXT_2}; margin-left: 8px; }}
.next .line {{ color: {TEXT_2}; font-size: .9rem; line-height: 1.5; }}
.next .line b {{ color: {TEXT}; }}

.alerts {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 1rem; }}
.alert {{ display: grid; grid-template-columns: 22px minmax(0, 1fr); column-gap: 10px; background: {SURFACE};
    border: 1px solid {BORDER}; border-left: 3px solid var(--tone, {WARN}); border-radius: 0 {RADIUS_TABLE}px {RADIUS_TABLE}px 0;
    padding: 10px 14px; }}
.alert .ic {{ font-weight: 700; color: var(--tone, {WARN}); font-size: .95rem; }}
.alert .tx {{ color: {TEXT}; font-size: .9rem; line-height: 1.45; }}
.alert .tx span {{ color: {MUTED}; font-size: .8rem; display: block; }}

.grid {{ display: grid; grid-template-columns: var(--tpl); gap: 1px; background: {BORDER}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD}px; overflow: hidden; }}
.grid > div {{ background: {SURFACE}; padding: 9px 10px; min-width: 0; font-size: .86rem; color: {TEXT};
    display: flex; align-items: center; }}
.grid .h {{ color: {TEXT_2}; font-size: {FONT_FLOOR_REM}rem; font-weight: 600; justify-content: center; text-align: center; }}
.grid .c {{ justify-content: center; font-variant-numeric: tabular-nums; }}
.grid .name {{ display: block; }}
.grid .name b {{ display: block; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.grid .name span {{ color: {MUTED}; font-size: {FONT_FLOOR_REM}rem; display: block; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }}
.grid .me {{ background: {ME_BG}; }}
.grid .me b {{ color: {ME_TINT}; }}
.medal {{ display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 26px;
    border-radius: 7px; font-family: {DISPLAY}; font-size: 1.05rem; font-weight: 600; padding: 0 6px;
    background: {SURFACE_2}; color: {TEXT}; }}
.medal.gold {{ background: {GOLD}; color: {BG}; }}
.medal.silver {{ background: {SILVER}; color: {BG}; }}
.medal.bronze {{ background: {BRONZE}; color: {BG}; }}
.medal.none {{ background: transparent; color: {AXIS}; }}
.medal small {{ font-size: {FONT_FLOOR_REM}rem; color: inherit; opacity: .75; margin-left: 1px; }}

.champs {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 1rem; }}
.champ {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; padding: 14px 16px;
    min-width: 0; }}
.champ .season {{ color: {TEXT_2}; font-size: .8rem; font-weight: 600; }}
.champ .team {{ font-family: {DISPLAY}; font-size: 1.55rem; font-weight: 600; color: {TEXT}; line-height: 1.1;
    margin: 6px 0 2px; overflow-wrap: anywhere; }}
.champ .meta {{ color: {MUTED}; font-size: .8rem; line-height: 1.45; }}
.champ .mine {{ color: {ME_TINT}; font-size: .82rem; margin-top: 8px; padding-top: 8px;
    border-top: 1px solid {BORDER}; }}
.tagline {{ color: {MUTED}; font-size: .8rem; margin: -.4rem 0 1rem; }}

@media (max-width: {BP_TABLET}px) {{
    .stats, .fixtures {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .ladder {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .ladder .rung:nth-last-child(-n+3) {{ border-bottom: 1px solid {BORDER}; }}
    .top5 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: {BP_PHONE}px) {{
    .block-container {{ padding: 3.6rem 1rem 4rem; }}
    [data-testid="stHeader"] {{ background: {rgba(BG, 0.88)}; backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px); border-bottom: 1px solid {BORDER}; }}
    [data-testid="stMainBlockContainer"] h3 {{ font-size: 1.4rem !important; padding-top: 1.4rem; }}
    .hero {{ margin-bottom: 1.1rem; }}
    .hero .title {{ font-size: 2.15rem; }}
    .hero .subtitle {{ font-size: .94rem; line-height: 1.5; }}
    .volet-title {{ margin: .3rem 0 1rem; }}
    .volet-title .title {{ font-size: 1.75rem; }}
    .volet-title .subtitle {{ font-size: .94rem; line-height: 1.5; }}

    .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); border-radius: {RADIUS_TABLE}px; }}
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
    .rung .hint {{ font-size: {FONT_FLOOR_REM}rem; }}
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

    .pp {{ width: 104px; padding: 7px 8px 6px; }}
    .pp .nt {{ font-size: 1.1rem; }}

    .ranks .hide-s {{ display: none; }}
    .next {{ padding: 14px 16px; }}
    .next .odds {{ font-size: 2.6rem; }}
    .champs {{ grid-template-columns: minmax(0, 1fr); gap: 8px; }}
    .champ {{ display: grid; grid-template-columns: 78px minmax(0, 1fr); column-gap: 10px; padding: 10px 14px; }}
    .champ .team {{ font-size: 1.25rem; margin: 0; }}
    .champ .mine {{ grid-column: 1 / -1; }}
    .grid > div {{ padding: 8px 6px; font-size: .8rem; }}

    div.chart-title {{ padding: 12px 12px 0; font-size: .9rem; }}
    [data-testid="stButtonGroup"] > div {{ flex-wrap: wrap; }}
}}

[data-testid="stExpander"] details {{ border: 1px solid {BORDER}; border-radius: {RADIUS_TABLE}px; background: {rgba(SURFACE, 0.6)}; }}
[data-testid="stExpander"] summary p {{ color: {TEXT_2}; font-size: .88rem; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: {RADIUS_TABLE}px; overflow: hidden; }}
[data-testid="stPlotlyChart"] {{ border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; overflow: hidden; }}
.chart-title {{ color: {TEXT}; font-size: .95rem; font-weight: 500; line-height: 1.35; padding: 15px 16px 0; }}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .chart-title) {{ gap: 0; background: {SURFACE};
    border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}px; overflow: hidden; }}
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
