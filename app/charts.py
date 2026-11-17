import math
import re
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.theme import (
    AXIS,
    CONTEXT,
    CONTEXT_DIM,
    CONTEXT_LIGHT,
    DIVERGING,
    HIGHLIGHT,
    LINE_COLORS,
    LINE_LABELS,
    MUTED,
    NEG,
    POS,
    RESULT_COLORS,
    SEQUENTIAL,
    SERIES,
    SURFACE,
    TEXT,
    TEXT_2,
    rgba,
)

CONFIG = {"displayModeBar": False, "scrollZoom": False}
DEFAULT_TOP = 78
TITLE_ROOM = 46
MAX_TICKS = 10
LABEL_MAX_CHARS = 15
LABEL_SIZE = 11
END_SHIFT = 8
PHONE_WIDTH = 330
PLOT_CHROME = 100
PHASE_LABEL = re.compile(r"^(Après|Avant) (J\d+)$")


def is_mobile() -> bool:
    return "Mobi" in (st.context.headers.get("User-Agent") or "")


def _has_legend(fig: go.Figure) -> bool:
    shown = [t for t in fig.data if t.showlegend is not False and t.name]
    return bool(shown) if fig.layout.showlegend else fig.layout.showlegend is None and len(shown) >= 2


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _clip(text: str, n: int = LABEL_MAX_CHARS) -> str:
    """Tronque proprement chaque ligne d'une étiquette qui dépasse `n` caractères."""
    return "<br>".join(_short(line, n) for line in text.split("<br>"))


def _thin(values, max_ticks: int = MAX_TICKS) -> list:
    """Garde au plus `max_ticks` valeurs à pas régulier, la dernière étant toujours conservée."""
    vals = list(values)
    if len(vals) <= max_ticks:
        return vals
    step = math.ceil(len(vals) / max_ticks)
    return vals[::-1][::step][::-1]


def _gw_axis(values, labels: dict[int, str] | None = None) -> tuple[list, list[str], str]:
    """Graduations d'un axe de journées : valeurs retenues, libellés courts (« J12 ») et titre d'axe."""
    ticks = _thin(sorted(set(values)))
    full = {t: (labels or {}).get(t, f"Avant J{t}") for t in ticks}
    found = {t: PHASE_LABEL.match(text) for t, text in full.items()}
    prefixes = [m.group(1) for m in found.values() if m]
    if not prefixes:
        return ticks, list(full.values()), "Journée"
    phase = max(set(prefixes), key=prefixes.count)
    text = [m.group(2) if m and m.group(1) == phase else full[t] for t, m in found.items()]
    return ticks, text, f"{phase} la journée"


def _legend_above(fig: go.Figure) -> None:
    """Légende horizontale au-dessus de la zone de tracé ; la marge haute s'agrandit si elle passe sur deux lignes."""
    names = [t.name for t in fig.data if t.showlegend is not False and t.name]
    fig.update_layout(legend=dict(orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom"))
    lines = math.ceil(sum(34 + 6.4 * len(n) for n in names) / PHONE_WIDTH)
    if lines > 1:
        fig.update_layout(margin_t=(fig.layout.margin.t or DEFAULT_TOP) + 20 * (lines - 1))


def _end_margin(texts: list[str], size: int = LABEL_SIZE) -> int:
    """Marge droite qui laisse la place aux étiquettes de fin de ligne les plus longues."""
    width = min(max(len(line) for t in texts for line in t.split("<br>")), LABEL_MAX_CHARS)
    return round(10 + 0.58 * size * width) + END_SHIFT


def _y_range(values, zero: bool = False) -> tuple[float, float]:
    """Étendue verticale approchée d'une courbe, avec la marge que Plotly ajoute de lui-même."""
    lo, hi = float(min(values)), float(max(values))
    pad = (hi - lo) * 0.06 or 1.0
    return (0.0 if zero else lo - pad), hi + pad


def _end_labels(
    fig: go.Figure,
    x: float,
    items: list[tuple[str, float, str]],
    y_range: tuple[float, float],
    reverse: bool = False,
    size: int = LABEL_SIZE,
) -> None:
    """Étiquettes de fin de ligne (texte, y, couleur) ; celles qui se chevauchent sont décalées à la verticale."""
    if not items:
        return
    plot_h = max((fig.layout.height or 400) - PLOT_CHROME, 100)
    lo, hi = y_range
    span = (hi - lo) or 1.0
    pos = [((hi - y) if reverse else (y - lo)) / span * plot_h for _, y, _ in items]
    heights = [size * 1.3 * (text.count("<br>") + 1) for text, _, _ in items]
    order = sorted(range(len(items)), key=pos.__getitem__)
    placed: dict[int, float] = {}
    for rank, i in enumerate(order):
        placed[i] = pos[i]
        if rank:
            below = order[rank - 1]
            placed[i] = max(pos[i], placed[below] + (heights[below] + heights[i]) / 2)
    ceiling = plot_h
    for i in reversed(order):
        placed[i] = min(placed[i], ceiling - heights[i] / 2)
        ceiling = placed[i] - heights[i] / 2
    for i, (text, y, color) in enumerate(items):
        fig.add_annotation(
            x=x,
            y=y,
            text=_clip(text),
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            xshift=END_SHIFT,
            yshift=round(placed[i] - pos[i]),
            font=dict(color=color, size=size),
        )
    fig.update_layout(margin_r=_end_margin([text for text, _, _ in items], size))


def _rank_dtick(n: int) -> int:
    """Pas des graduations d'un axe de rangs : une graduation sur deux ou trois au-delà de 10 équipes."""
    return max(1, math.ceil(n / MAX_TICKS))


def _labelled(best_first: list[int], team_id: int, n: int = 3) -> list[int]:
    """Mon équipe et les `n` premières du graphique : au plus quatre étiquettes de fin de ligne."""
    return list(dict.fromkeys([team_id, *best_first[:n]]))


def _compact(fig: go.Figure) -> None:
    """Version téléphone : étiquettes de fin de ligne en police réduite, titres d'axe sur deux lignes."""
    ends = [a for a in fig.layout.annotations if a.xanchor == "left" and a.text and a.xshift]
    if ends:
        for ann in ends:
            ann.text = _clip(ann.text)
            ann.font.size = 10
        fig.update_layout(margin_r=min(fig.layout.margin.r or 999, _end_margin([a.text for a in ends], 10)))
    for ax in (fig.layout.xaxis, fig.layout.yaxis):
        text = ax.title.text
        if text and len(text) > 28 and "<br>" not in text:
            ax.title.text = _two_lines(text)
    fig.update_layout(legend_font_size=11, hoverlabel_font_size=12, dragmode=False)


def show(fig: go.Figure, height: int | None = None) -> None:
    """Affiche la figure dans une carte ; le titre passe en HTML pour revenir à la ligne sur petit écran."""
    if height:
        fig.update_layout(height=height)
    if is_mobile():
        _compact(fig)
    title = fig.layout.title.text
    if not title:
        st.plotly_chart(fig, theme=None, config=CONFIG)
        return
    top = fig.layout.margin.t if fig.layout.margin.t is not None else DEFAULT_TOP
    fig.update_layout(title_text=None, margin_t=max(top - TITLE_ROOM, 30) if _has_legend(fig) else max(top - 56, 24))
    with st.container():
        st.html(f'<div class="chart-title">{escape(title)}</div>')
        st.plotly_chart(fig, theme=None, config=CONFIG)


def _bar_colors(team_ids: pd.Series, team_id: int, base: str = SERIES[0]) -> list[str]:
    return [base if t == team_id else CONTEXT for t in team_ids]


def ranked_bars(
    df: pd.DataFrame,
    value: str,
    label: str,
    team_id: int,
    title: str,
    fmt: str = ".1f",
    hover: str | None = None,
    ascending: bool = True,
    x_title: str = "",
) -> go.Figure:
    """Barres horizontales triées, équipe sélectionnée en couleur, les autres en gris (emphase)."""
    d = df.sort_values(value, ascending=ascending)
    fig = go.Figure(
        go.Bar(
            x=d[value],
            y=d[label],
            orientation="h",
            marker=dict(color=_bar_colors(d["team_id"], team_id), line=dict(width=0)),
            text=[f"{v:{fmt}}" for v in d[value]],
            textposition="outside",
            textfont=dict(color=TEXT_2, size=12),
            cliponaxis=False,
            hovertemplate=hover or f"<b>%{{y}}</b><br>{x_title or value} : %{{x:{fmt}}}<extra></extra>",
        )
    )
    fig.update_layout(title=title, xaxis_title=x_title, showlegend=False, height=max(300, 34 * len(d) + 80))
    fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    lo, hi = float(d[value].min()), float(d[value].max())
    if lo < 0:
        span = hi - lo
        fig.update_xaxes(range=[lo - 0.35 * span, hi + 0.2 * span])
    return fig


def diverging_bars(
    df: pd.DataFrame,
    value: str,
    label: str,
    team_id: int,
    title: str,
    low: str | None = None,
    high: str | None = None,
    x_title: str = "",
    fmt: str = "+.1f",
) -> go.Figure:
    """Barres divergentes autour de zéro : bleu positif, rouge négatif, fourchette optionnelle en moustaches."""
    d = df.sort_values(value)
    colors = [POS if v >= 0 else NEG for v in d[value]]
    widths = [2.5 if t == team_id else 0 for t in d["team_id"]]
    error = None
    if low and high:
        error = dict(
            type="data",
            symmetric=False,
            array=d[high] - d[value],
            arrayminus=d[value] - d[low],
            color=MUTED,
            thickness=1.2,
            width=4,
        )
    custom = np.stack([d[low], d[high]], axis=1) if low and high else None
    ci = "<br>Fourchette : entre %{customdata[0]:+.1f} et %{customdata[1]:+.1f}" if custom is not None else ""
    fig = go.Figure(
        go.Bar(
            x=d[value],
            y=d[label],
            orientation="h",
            error_x=error,
            customdata=custom,
            marker=dict(color=colors, line=dict(color=TEXT, width=widths)),
            hovertemplate=f"<b>%{{y}}</b><br>{x_title} : %{{x:{fmt}}}{ci}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    fig.update_layout(title=title, xaxis_title=x_title, showlegend=False, height=max(320, 34 * len(d) + 80))
    fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    return fig


def bump_chart(sbg: pd.DataFrame, team_id: int, n_teams: int) -> go.Figure:
    fig = go.Figure()
    last_gw = sbg["gw"].max()
    final = sbg[sbg["gw"] == last_gw].sort_values("rang")
    labelled = _labelled(final["team_id"].tolist(), team_id)
    items = []
    for tid, grp in sorted(sbg.groupby("team_id"), key=lambda kv: kv[0] == team_id):
        me = tid == team_id
        grp = grp.sort_values("gw")
        fig.add_trace(
            go.Scatter(
                x=grp["gw"],
                y=grp["rang"],
                mode="lines+markers",
                name=grp["team_name"].iloc[0],
                line=dict(color=HIGHLIGHT if me else CONTEXT, width=3 if me else 1.6, shape="spline", smoothing=0.6),
                marker=dict(size=9 if me else 7, color=HIGHLIGHT if me else CONTEXT, line=dict(color=SURFACE, width=2)),
                customdata=grp[["pts"]],
                hovertemplate="<b>%{fullData.name}</b><br>J%{x} : %{y}e · %{customdata[0]} pts<extra></extra>",
                showlegend=False,
            )
        )
        end = grp[grp["gw"] == last_gw]
        if tid in labelled and not end.empty:
            items.append((grp["team_name"].iloc[0], float(end["rang"].iloc[0]), TEXT if me else TEXT_2))
    fig.update_layout(title="Évolution du classement", height=420)
    _end_labels(fig, last_gw, items, (0.5, n_teams + 0.5), reverse=True)
    ticks, text, x_title = _gw_axis(sbg["gw"], {int(g): f"Après J{g}" for g in sbg["gw"].unique()})
    fig.update_yaxes(
        autorange="reversed", tick0=1, dtick=_rank_dtick(n_teams), range=[n_teams + 0.5, 0.5], title="Rang"
    )
    fig.update_xaxes(
        tickangle=0, tickvals=ticks, ticktext=text, range=[0.8, last_gw + 0.2], gridcolor="rgba(0,0,0,0)", title=x_title
    )
    return fig


def luck_scatter(lk: pd.DataFrame, abbrev: dict[int, str], team_id: int) -> go.Figure:
    lo = min(lk["xpts_allplay"].min(), lk["pts"].min()) - 0.6
    hi = max(lk["xpts_allplay"].max(), lk["pts"].max()) + 0.6
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=AXIS, width=1), hoverinfo="skip", showlegend=False
        )
    )
    fig.add_annotation(
        x=hi,
        y=hi,
        text="points réels = points mérités",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font=dict(color=MUTED, size=11),
    )
    colors = [HIGHLIGHT if t == team_id else CONTEXT_LIGHT for t in lk["team_id"]]
    fig.add_trace(
        go.Scatter(
            x=lk["xpts_allplay"],
            y=lk["pts"],
            mode="markers+text",
            text=lk["team_id"].map(abbrev),
            textposition="top center",
            textfont=dict(color=TEXT_2, size=11),
            marker=dict(size=13, color=colors, line=dict(color=SURFACE, width=2)),
            customdata=np.stack([lk["team_name"], lk["chance_totale"]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>Points mérités : %{x:.1f}<br>Points réels : %{y}<br>Chance : %{customdata[1]:+.1f}<extra></extra>",
            showlegend=False,
        )
    )
    fig.add_annotation(
        x=lo + 0.2, y=hi - 0.2, text="Chanceux ↑", showarrow=False, xanchor="left", font=dict(color=POS, size=12)
    )
    fig.add_annotation(
        x=hi - 0.2, y=lo + 0.2, text="↓ Malchanceux", showarrow=False, xanchor="right", font=dict(color=NEG, size=12)
    )
    fig.update_layout(
        title="Points réels contre points mérités",
        height=440,
        xaxis_title="Points mérités (contre toutes les équipes de la journée)",
        yaxis_title="Points réels",
    )
    fig.update_xaxes(range=[lo, hi], nticks=6)
    fig.update_yaxes(range=[lo, hi], nticks=6)
    return fig


def line_heatmap(lines: pd.DataFrame, sort_by: str) -> go.Figure:
    cols = ["globale", "G", "D", "M", "A"]
    names = {"globale": "Globale", **LINE_LABELS}
    d = lines.sort_values(sort_by, ascending=True)
    z = d[cols].to_numpy()
    n = np.stack([d[[f"n_{c}" for c in "GDMA"]].sum(axis=1)] + [d[f"n_{c}"] for c in "GDMA"], axis=1)
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[names[c] for c in cols],
            y=d["team_name"],
            colorscale=[[i / 5, c] for i, c in enumerate(SEQUENTIAL)],
            text=[[f"{v:.2f}" for v in row] for row in z],
            texttemplate="%{text}",
            textfont=dict(size=13, color=TEXT),
            customdata=n,
            xgap=3,
            ygap=3,
            hovertemplate="<b>%{y}</b> · %{x}<br>Note brute moyenne : %{z:.2f}<br>Nombre de notes : %{customdata}<extra></extra>",
            colorbar=dict(
                title=dict(text="Note", font=dict(color=TEXT_2, size=11)),
                tickfont=dict(color=MUTED),
                thickness=10,
                outlinewidth=0,
            ),
        )
    )
    fig.update_layout(title="Force par ligne (note brute moyenne des joueurs alignés)", height=440)
    fig.update_xaxes(side="top", gridcolor="rgba(0,0,0,0)", title=None)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    fig.update_layout(margin=dict(t=100))
    return fig


def stacked_goals(st_df: pd.DataFrame) -> go.Figure:
    d = st_df.assign(total=st_df["bp_reel"] + st_df["bp_mpg"] + st_df["bp_csc"]).sort_values("total")
    fig = go.Figure()
    for col, name, color in [
        ("bp_reel", "Buts réels", SERIES[0]),
        ("bp_mpg", "Buts MPG", SERIES[1]),
        ("bp_csc", "CSC adverses", SERIES[2]),
    ]:
        fig.add_trace(
            go.Bar(
                y=d["team_name"],
                x=d[col],
                name=name,
                orientation="h",
                marker=dict(color=color, line=dict(color=SURFACE, width=2)),
                hovertemplate=f"<b>%{{y}}</b><br>{name} : %{{x}}<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            y=d["team_name"],
            x=d["total"],
            mode="text",
            text=d["total"],
            textposition="middle right",
            textfont=dict(color=TEXT_2, size=12),
            showlegend=False,
            hoverinfo="skip",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        barmode="stack",
        title="Buts marqués : réels, MPG et contre son camp",
        height=420,
        xaxis_title="Buts",
        bargap=0.32,
    )
    fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    _legend_above(fig)
    return fig


def dumbbell_ranks(df: pd.DataFrame, a: str, b: str, a_name: str, b_name: str, team_id: int, title: str) -> go.Figure:
    d = df.sort_values(a, ascending=False)
    fig = go.Figure()
    for _, r in d.iterrows():
        me = r["team_id"] == team_id
        fig.add_trace(
            go.Scatter(
                x=[r[a], r[b]],
                y=[r["team_name"]] * 2,
                mode="lines",
                line=dict(color=TEXT_2 if me else AXIS, width=3 if me else 2),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig.add_trace(
        go.Scatter(
            x=d[a],
            y=d["team_name"],
            mode="markers",
            name=a_name,
            marker=dict(size=13, color=SERIES[0], line=dict(color=SURFACE, width=2)),
            hovertemplate=f"<b>%{{y}}</b><br>{a_name} : %{{x}}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=d[b],
            y=d["team_name"],
            mode="markers",
            name=b_name,
            marker=dict(size=13, color=SERIES[1], symbol="diamond", line=dict(color=SURFACE, width=2)),
            hovertemplate=f"<b>%{{y}}</b><br>{b_name} : %{{x}}<extra></extra>",
        )
    )
    fig.update_xaxes(autorange="reversed", tick0=1, dtick=_rank_dtick(len(d)), title="Rang (1 = premier)")
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    fig.update_layout(title=title, height=440)
    _legend_above(fig)
    return fig


def rank_ranges(df: pd.DataFrame, lo: str, hi: str, cur: str, team_id: int, title: str) -> go.Figure:
    d = df.sort_values(cur, ascending=False)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=d["team_name"],
            x=d[hi] - d[lo] + 0.001,
            base=d[lo] - 0.001,
            orientation="h",
            width=0.42,
            marker=dict(color=[HIGHLIGHT if t == team_id else CONTEXT_DIM for t in d["team_id"]], line=dict(width=0)),
            customdata=np.stack([d[lo], d[hi]], axis=1),
            name="Plage de rangs",
            hovertemplate="<b>%{y}</b><br>Entre %{customdata[0]}e et %{customdata[1]}e<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            y=d["team_name"],
            x=d[cur],
            mode="markers",
            name="Scénario choisi",
            marker=dict(size=12, color=SERIES[1], symbol="diamond", line=dict(color=SURFACE, width=2)),
            hovertemplate="<b>%{y}</b><br>Rang : %{x}<extra></extra>",
        )
    )
    fig.update_xaxes(autorange="reversed", tick0=1, dtick=_rank_dtick(len(d)), title="Rang")
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    fig.update_layout(title=title, height=440, barcornerradius=8)
    _legend_above(fig)
    return fig


def corr_bars(corr: dict, labels: dict[str, str]) -> go.Figure:
    rows = [{"k": k, "label": labels.get(k, k), "rho": c.rho, "p": c.p_value} for k, c in corr.items()]
    d = pd.DataFrame(rows).dropna().sort_values("rho")
    colors = [POS if v >= 0 else NEG for v in d["rho"]]
    opac = [1.0 if p < 0.05 else 0.45 for p in d["p"]]
    chance = ["peu probable par hasard" if p < 0.05 else "peut venir du hasard" for p in d["p"]]
    fig = go.Figure(
        go.Bar(
            x=d["rho"],
            y=d["label"],
            orientation="h",
            marker=dict(color=colors, opacity=opac),
            text=[f"{r:+.2f}{' *' if p < 0.05 else ''}" for r, p in zip(d["rho"], d["p"])],
            customdata=chance,
            textposition="outside",
            cliponaxis=False,
            textfont=dict(color=TEXT_2, size=11),
            hovertemplate="<b>%{y}</b><br>Lien : %{x:+.2f}, %{customdata}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    fig.update_xaxes(range=[-1.25, 1.25], title="Lien (corrélation) avec les points")
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    fig.update_layout(
        title="Quelle caractéristique d'effectif suit les points ?", showlegend=False, height=max(320, 36 * len(d) + 80)
    )
    return fig


def sim_distribution(
    totals: np.ndarray, team_ids: list[int], names: dict[int, str], real: pd.Series, team_id: int
) -> go.Figure:
    fig = go.Figure()
    order = real.sort_values().index.tolist()
    for tid in order:
        i = team_ids.index(tid)
        vals = totals[:, i]
        me = tid == team_id
        fig.add_trace(
            go.Box(
                x=vals,
                name=names[tid],
                orientation="h",
                boxpoints=False,
                whiskerwidth=0.4,
                line=dict(width=1.2),
                marker=dict(color=HIGHLIGHT if me else CONTEXT),
                fillcolor=rgba(HIGHLIGHT, 0.25) if me else rgba(CONTEXT, 0.18),
                showlegend=False,
                hoverinfo="skip",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=real.loc[order],
            y=[names[t] for t in order],
            mode="markers",
            name="Avec le vrai calendrier",
            marker=dict(size=12, color=SERIES[1], symbol="diamond", line=dict(color=SURFACE, width=2)),
            hovertemplate="<b>%{y}</b><br>Vrai calendrier : %{x} pts<extra></extra>",
        )
    )
    fig.update_layout(
        title="Points selon 10 000 calendriers tirés au hasard", height=460, xaxis_title="Points (règle de note)"
    )
    fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    _legend_above(fig)
    return fig


def stacked_components(
    df: pd.DataFrame, parts: list[tuple[str, str]], team_id: int, title: str, x_title: str = ""
) -> go.Figure:
    d = df.assign(_t=df[[p for p, _ in parts]].sum(axis=1)).sort_values("_t")
    fig = go.Figure()
    for (col, name), color in zip(parts, SERIES):
        fig.add_trace(
            go.Bar(
                y=d["team_name"],
                x=d[col],
                name=name,
                orientation="h",
                marker=dict(color=color, line=dict(color=SURFACE, width=2)),
                hovertemplate=f"<b>%{{y}}</b><br>{name} : %{{x:+.1f}}<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            y=d["team_name"],
            x=d["_t"],
            mode="markers",
            name="Total",
            marker=dict(size=9, color=TEXT, symbol="line-ns", line=dict(width=2.5, color=TEXT)),
            hovertemplate="<b>%{y}</b><br>Total : %{x:+.1f}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    fig.update_layout(barmode="relative", title=title, xaxis_title=x_title, height=max(320, 34 * len(d) + 90))
    fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    _legend_above(fig)
    return fig


def team_boxes(
    pv: pd.DataFrame, value: str, team_id: int, title: str, x_title: str, log: bool = False, hover_fmt: str = ".0f"
) -> go.Figure:
    order = pv.groupby("team_name")[value].median().sort_values().index.tolist()
    fig = go.Figure()
    for name in order:
        g = pv[pv["team_name"] == name]
        me = g["team_id"].iloc[0] == team_id
        fig.add_trace(
            go.Box(
                x=g[value],
                name=name,
                orientation="h",
                boxpoints="all",
                jitter=0.45,
                pointpos=0,
                marker=dict(size=6, color=HIGHLIGHT if me else CONTEXT_LIGHT, opacity=0.85, line=dict(width=0)),
                line=dict(color=HIGHLIGHT if me else CONTEXT, width=1.3),
                fillcolor="rgba(0,0,0,0)",
                customdata=np.stack([g["joueur"], g["poste_groupe"]], axis=1),
                showlegend=False,
                hovertemplate=f"<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>{x_title} : %{{x:{hover_fmt}}}<extra></extra>",
            )
        )
    fig.update_layout(title=title, xaxis_title=x_title, height=max(380, 40 * len(order) + 80))
    if log:
        vals = [v for v in (0.5, 1, 2, 5, 10, 20, 50, 100, 200) if pv[value].min() * 0.8 <= v <= pv[value].max() * 1.25]
        fig.update_xaxes(type="log", tickvals=vals, ticktext=[f"{v:g}" for v in vals])
    else:
        fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    return fig


def price_note_facets(pv: pd.DataFrame, team_id: int) -> go.Figure:
    from plotly.subplots import make_subplots

    mobile = is_mobile()
    n_cols = 2 if mobile else 4
    ticks = [2, 5, 20, 50] if mobile else [2, 5, 10, 20, 50, 100]
    fig = make_subplots(
        rows=4 // n_cols,
        cols=n_cols,
        subplot_titles=[LINE_LABELS[g] for g in "GDMA"],
        shared_yaxes=True,
        horizontal_spacing=0.05 if mobile else 0.03,
        vertical_spacing=0.14,
    )
    for i, g in enumerate("GDMA"):
        row, col = divmod(i, n_cols)
        row, col = row + 1, col + 1
        d = pv[(pv["poste_groupe"] == g) & (pv["n_notes"] > 0)].sort_values("enchere")
        me = d["team_id"] == team_id
        fig.add_trace(
            go.Scatter(
                x=d["enchere"],
                y=d["note_retrecie"],
                mode="markers",
                marker=dict(
                    size=[10 if m else 7 for m in me],
                    color=[HIGHLIGHT if m else CONTEXT_LIGHT for m in me],
                    opacity=[1 if m else 0.6 for m in me],
                    line=dict(color=SURFACE, width=1),
                ),
                customdata=np.stack([d["joueur"], d["team_name"], d["residu_valeur"]], axis=1),
                showlegend=False,
                hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>Enchère : %{x:.0f} M€<br>"
                "Note estimée : %{y:.2f}<br>Écart au prix : %{customdata[2]:+.2f}<extra></extra>",
            ),
            row=row,
            col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=d["enchere"],
                y=d["note_attendue"],
                mode="lines",
                line=dict(color=SERIES[1], width=2),
                hoverinfo="skip",
                showlegend=i == 0,
                name="Note attendue pour le prix",
            ),
            row=row,
            col=col,
        )
        fig.update_xaxes(
            type="log",
            row=row,
            col=col,
            tickvals=ticks,
            ticktext=[str(t) for t in ticks],
            title_text="Enchère (M€, log)" if i == 4 - n_cols else None,
        )
        if col == 1:
            fig.update_yaxes(title_text="Note estimée", row=row, col=col)
    for ann in fig.layout.annotations:
        ann.font = dict(color=TEXT_2, size=12)
    fig.update_layout(
        title="Prix payé et rendement, par poste",
        height=640 if mobile else 430,
        margin=dict(t=120),
    )
    fig.update_layout(
        legend=dict(orientation="h", x=0, xanchor="left", y=1.12 if not mobile else 1.06, yanchor="bottom")
    )
    return fig


def budget_shares(m: pd.DataFrame) -> go.Figure:
    d = m.sort_values("part_A")
    fig = go.Figure()
    for g in "GDMA":
        fig.add_trace(
            go.Bar(
                y=d["team_name"],
                x=d[f"part_{g}"] * 100,
                name=LINE_LABELS[g],
                orientation="h",
                marker=dict(color=LINE_COLORS[g], line=dict(color=SURFACE, width=2)),
                hovertemplate=f"<b>%{{y}}</b><br>{LINE_LABELS[g]} : %{{x:.0f}} %<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack", title="Répartition du budget par ligne", xaxis_title="% des enchères", height=420, bargap=0.3
    )
    fig.update_xaxes(range=[0, 100], ticksuffix=" %", nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    _legend_above(fig)
    return fig


def paired_bars(
    df: pd.DataFrame, label: str, a: str, b: str, a_name: str, b_name: str, title: str, x_title: str
) -> go.Figure:
    d = df.sort_values(a)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=d[label],
            x=d[a],
            name=a_name,
            orientation="h",
            marker=dict(color=SERIES[0]),
            hovertemplate=f"<b>%{{y}}</b><br>{a_name} : %{{x:.0f}}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=d[label],
            x=d[b],
            name=b_name,
            orientation="h",
            marker=dict(color=SERIES[1]),
            hovertemplate=f"<b>%{{y}}</b><br>{b_name} : %{{x:.0f}}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        title=title,
        xaxis_title=x_title,
        height=max(380, 30 * len(d) + 100),
        bargap=0.25,
        bargroupgap=0.08,
    )
    fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    _legend_above(fig)
    return fig


def _two_lines(text: str) -> str:
    words = text.split()
    if len(words) < 2:
        return text
    cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:cut]) + "<br>" + " ".join(words[cut:])


def component_heatmap(m: pd.DataFrame, comps: list[str], labels: dict[str, str]) -> go.Figure:
    mobile = is_mobile()
    d = m.sort_values("score")
    z = d[comps].to_numpy()
    lim = max(2.0, float(np.nanmax(np.abs(z))))
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[labels[c] if mobile else _two_lines(labels[c]) for c in comps],
            y=d["team_name"],
            zmid=0,
            zmin=-lim,
            zmax=lim,
            colorscale=DIVERGING,
            text=[[f"{v:+.1f}" for v in row] for row in z],
            texttemplate="%{text}",
            textfont=dict(color=TEXT, size=12),
            xgap=3,
            ygap=3,
            colorbar=dict(
                title=dict(text="Écart", font=dict(color=TEXT_2)),
                tickfont=dict(color=MUTED),
                thickness=10,
                outlinewidth=0,
            ),
            hovertemplate="<b>%{y}</b><br>%{x} : %{z:+.2f} (écart à la médiane)<extra></extra>",
        )
    )
    fig.update_xaxes(side="top", gridcolor="rgba(0,0,0,0)", tickangle=-90 if mobile else 0, tickfont=dict(size=11))
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    if mobile:
        fig.update_traces(textfont_size=10, showscale=False)
    fig.update_layout(
        title="Composantes du score (écart à la médiane de la ligue, 0 = médiane)",
        height=440,
        margin=dict(t=120 if mobile else 110),
    )
    return fig


def gw_points(tm: pd.DataFrame, team_id: int) -> go.Figure:
    d = tm[tm["team_id"] == team_id].sort_values("gw")
    scores = [f"{r} {a}-{b}" for r, a, b in zip(d["resultat"], d["bp"], d["bc"])]
    fig = go.Figure(
        go.Bar(
            x=d["gw"],
            y=d["note_moy"],
            marker=dict(color=[RESULT_COLORS[r] for r in d["resultat"]]),
            name="Note de l'équipe",
            showlegend=False,
            customdata=np.stack([d["opp_name"], d["note_moy_adv"], scores], axis=1),
            hovertemplate="J%{x} contre <b>%{customdata[0]}</b> (%{customdata[2]})<br>Note : %{y:.2f} · adverse : %{customdata[1]:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=d["gw"],
            y=d["note_moy_adv"],
            mode="markers",
            name="Note adverse",
            marker=dict(size=10, color=TEXT, symbol="line-ew", line=dict(width=3, color=TEXT)),
            hovertemplate="Note adverse : %{y:.2f}<extra></extra>",
        )
    )
    few = len(d) <= MAX_TICKS
    texts = {g: f"J{g}<br><b>{score}</b>" if few else f"J{g}" for g, score in zip(d["gw"], scores)}
    ticks = _thin(d["gw"])
    fig.update_xaxes(
        tickangle=0,
        tickvals=ticks,
        ticktext=[texts[g] for g in ticks],
        gridcolor="rgba(0,0,0,0)",
        title="Journée et résultat" if few else "Journée",
    )
    fig.update_yaxes(range=[3.5, max(7, d["note_moy"].max() + 0.6)], title="Note moyenne (bonus inclus)")
    fig.update_layout(
        title="Match par match : note de l'équipe et résultat",
        height=360,
        showlegend=True,
        bargap=0.6 if len(d) < 6 else 0.28,
    )
    _legend_above(fig)
    return fig


def rank_heatmap(rank_probs: pd.DataFrame, names: dict[int, str], order: list[int]) -> go.Figure:
    d = rank_probs.loc[order[::-1]] * 100
    z = d.to_numpy()
    text = [[f"{v:.0f}" if v >= 0.5 else "" for v in row] for row in z]
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[f"{r}e" for r in d.columns],
            y=[names[t] for t in d.index],
            colorscale=[[i / 5, c] for i, c in enumerate(SEQUENTIAL)],
            zmin=0,
            text=text,
            texttemplate="%{text}",
            textfont=dict(color=TEXT, size=12),
            xgap=2,
            ygap=2,
            hovertemplate="<b>%{y}</b> termine %{x} : %{z:.0f} %<extra></extra>",
            colorbar=dict(
                title=dict(text="%", font=dict(color=TEXT_2)), tickfont=dict(color=MUTED), thickness=10, outlinewidth=0
            ),
        )
    )
    places = _thin([f"{r}e" for r in d.columns])
    fig.update_xaxes(side="top", gridcolor="rgba(0,0,0,0)", title=None, tickvals=places, ticktext=places)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    fig.update_layout(title="Chances de finir à chaque place (%)", height=460, margin=dict(t=100))
    return fig


def title_history(
    history: pd.DataFrame,
    names: dict[int, str],
    team_id: int,
    col: str = "p_titre",
    label: str = "Chances de titre",
) -> go.Figure:
    fig = go.Figure()
    last = history["apres_journee"].max()
    top = history[history["apres_journee"] == last].sort_values(col, ascending=False)["team_id"].tolist()
    labelled = _labelled(top, team_id)
    items = []
    for tid, grp in sorted(history.groupby("team_id"), key=lambda kv: kv[0] == team_id):
        me = tid == team_id
        grp = grp.sort_values("apres_journee")
        fig.add_trace(
            go.Scatter(
                x=grp["apres_journee"],
                y=grp[col] * 100,
                mode="lines+markers",
                name=names[tid],
                showlegend=False,
                line=dict(color=HIGHLIGHT if me else CONTEXT, width=3 if me else 1.6),
                marker=dict(size=8 if me else 6, color=HIGHLIGHT if me else CONTEXT, line=dict(color=SURFACE, width=2)),
                hovertemplate=f"<b>{names[tid]}</b><br>%{{y:.0f}} %<extra></extra>",
            )
        )
        end = grp[grp["apres_journee"] == last]
        if tid in labelled and not end.empty:
            items.append((names[tid], float(end[col].iloc[0]) * 100, TEXT if me else TEXT_2))
    fig.update_layout(title=f"{label} au fil des journées", height=400)
    _end_labels(fig, last, items, _y_range((history[col] * 100).tolist(), zero=True))
    steps = {t: "Avant J1" if t == 0 else f"Après J{t}" for t in history["apres_journee"].unique()}
    ticks, text, x_title = _gw_axis(history["apres_journee"], steps)
    fig.update_xaxes(
        tickangle=0, tickvals=ticks, ticktext=text, gridcolor="rgba(0,0,0,0)", range=[-0.2, last + 0.2], title=x_title
    )
    fig.update_yaxes(title=f"{label} (%)", rangemode="tozero", ticksuffix=" %", nticks=6)
    return fig


def final_points_box(sim, names: dict[int, str], team_id: int) -> go.Figure:
    order = sim.summary.sort_values("pts_moy")["team_id"].tolist()
    idx = {t: i for i, t in enumerate(sim.team_ids)}
    fig = go.Figure()
    for tid in order:
        me = tid == team_id
        vals = sim.final_points[:, idx[tid]]
        q = np.quantile(vals, [0.05, 0.25, 0.5, 0.75, 0.95])
        fig.add_trace(
            go.Box(
                y=[names[tid]],
                q1=[q[1]],
                median=[q[2]],
                q3=[q[3]],
                lowerfence=[q[0]],
                upperfence=[q[4]],
                orientation="h",
                name=names[tid],
                showlegend=False,
                line=dict(color=HIGHLIGHT if me else CONTEXT, width=1.3),
                fillcolor=rgba(HIGHLIGHT, 0.25) if me else rgba(CONTEXT, 0.18),
                whiskerwidth=0.4,
                hovertemplate=f"<b>{names[tid]}</b><br>Médiane {q[2]:.0f} pts · fourchette : entre {q[0]:.0f} et {q[4]:.0f}<extra></extra>",
            )
        )
    cur = sim.summary.set_index("team_id")["pts_actuels"]
    fig.add_trace(
        go.Scatter(
            x=[cur[t] for t in order],
            y=[names[t] for t in order],
            mode="markers",
            name="Points actuels",
            marker=dict(size=10, color=SERIES[1], symbol="diamond", line=dict(color=SURFACE, width=2)),
            hovertemplate="<b>%{y}</b><br>Aujourd'hui : %{x} pts<extra></extra>",
        )
    )
    fig.update_layout(
        title="Points prévus en fin de saison (boîte : la moitié centrale des cas, moustaches : 9 cas sur 10)",
        height=440,
        xaxis_title="Points",
    )
    fig.update_xaxes(nticks=6)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    _legend_above(fig)
    return fig


def snapshot_lines(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    names: dict[int, str],
    team_id: int,
    title: str,
    y_title: str,
    reverse: bool = False,
    pct: bool = False,
    final: dict[int, float] | None = None,
    x_labels: dict[int, str] | None = None,
) -> go.Figure:
    """Une ligne par équipe au fil des instantanés, équipe sélectionnée en couleur, étiquettes en bout de ligne."""
    fig = go.Figure()
    last = df[x_col].max()
    scale = 100 if pct else 1
    at_end = df[df[x_col] == last].sort_values(y_col, ascending=reverse)
    labelled = _labelled(at_end["team_id"].tolist(), team_id)
    items = []
    for tid, grp in sorted(df.groupby("team_id"), key=lambda kv: kv[0] == team_id):
        me = tid == team_id
        grp = grp.sort_values(x_col)
        fig.add_trace(
            go.Scatter(
                x=grp[x_col],
                y=grp[y_col] * scale,
                mode="lines+markers",
                name=names[tid],
                showlegend=False,
                line=dict(color=HIGHLIGHT if me else CONTEXT, width=3 if me else 1.6),
                marker=dict(size=9 if me else 7, color=HIGHLIGHT if me else CONTEXT, line=dict(color=SURFACE, width=2)),
                hovertemplate=f"<b>{names[tid]}</b><br>%{{y:{'.0f' if pct else '.1f'}}}{' %' if pct else ''}<extra></extra>",
            )
        )
        end = grp[grp[x_col] == last]
        if tid in labelled and not end.empty:
            items.append((names[tid], float(end[y_col].iloc[0]) * scale, TEXT if me else TEXT_2))
    if final:
        fig.add_trace(
            go.Scatter(
                x=[last] * len(final),
                y=list(final.values()),
                mode="markers",
                name="Classement final réel",
                marker=dict(size=12, color=SERIES[1], symbol="diamond", line=dict(color=SURFACE, width=2)),
                customdata=[names[t] for t in final],
                hovertemplate="<b>%{customdata}</b><br>Rang final réel : %{y}<extra></extra>",
            )
        )
    fig.update_layout(title=title, height=440)
    values = [v * scale for v in df[y_col]] + (list(final.values()) if final else [])
    _end_labels(fig, last, items, _y_range(values, zero=pct and not reverse), reverse=reverse)
    ticks, text, x_title = _gw_axis(df[x_col], x_labels)
    fig.update_xaxes(
        tickangle=0,
        tickvals=ticks,
        ticktext=text,
        gridcolor="rgba(0,0,0,0)",
        range=[df[x_col].min() - 0.3, last + 0.3],
        title=x_title,
    )
    fig.update_yaxes(title=y_title, autorange="reversed" if reverse else True, ticksuffix=" %" if pct else "", nticks=6)
    if final:
        _legend_above(fig)
    return fig


def rps_evolution(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    style = {"Ensemble": (HIGHLIGHT, 3), "Référence (fréquences)": (SERIES[1], 2)}
    shown = {"Référence (fréquences)": "Pronostic de base"}
    last = g["gw"].max()
    items = []
    legend_done = False
    for model, grp in sorted(g.groupby("modele"), key=lambda kv: kv[0] in style):
        color, width = style.get(model, (CONTEXT, 1.6))
        model_label = shown.get(model, model)
        grp = grp.sort_values("gw")
        other = model not in style
        fig.add_trace(
            go.Scatter(
                x=grp["gw"],
                y=grp["rps_cumule"],
                mode="lines+markers",
                name="Autres modèles" if other else model_label,
                legendgroup="autres" if other else None,
                showlegend=other and not legend_done,
                line=dict(color=color, width=width),
                marker=dict(size=8, color=color, line=dict(color=SURFACE, width=2)),
                customdata=grp[["rps", "matchs"]].to_numpy(),
                hovertemplate=f"<b>{model_label}</b><br>J%{{x}} : erreur de prévision de la journée %{{customdata[0]:.3f}} "
                "(%{customdata[1]} matchs)<br>Cumulé : %{y:.3f}<extra></extra>",
            )
        )
        legend_done = legend_done or other
        end = grp[grp["gw"] == last]
        if not other and not end.empty:
            items.append((_two_lines(model_label), float(end["rps_cumule"].iloc[0]), TEXT))
    fig.update_layout(title="Qualité des pronostics figés au fil de la saison", height=380, showlegend=legend_done)
    _end_labels(fig, last, items, _y_range(g["rps_cumule"].tolist(), zero=True))
    ticks, text, x_title = _gw_axis(g["gw"], {int(t): f"Après J{t}" for t in g["gw"].unique()})
    fig.update_xaxes(
        tickangle=0,
        tickvals=ticks,
        ticktext=text,
        gridcolor="rgba(0,0,0,0)",
        range=[g["gw"].min() - 0.3, last + 0.3],
        title=x_title,
    )
    fig.update_yaxes(title="Erreur de prévision cumulée (bas = mieux)", rangemode="tozero", nticks=6)
    if legend_done:
        _legend_above(fig)
    return fig


def calibration_chart(cal: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=AXIS, width=1), hoverinfo="skip", showlegend=False)
    )
    fig.add_annotation(
        x=0.98,
        y=0.98,
        text="prévision parfaite",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font=dict(color=MUTED, size=11),
    )
    fig.add_trace(
        go.Scatter(
            x=cal["p_annoncee"],
            y=cal["frequence_observee"],
            mode="markers+lines",
            marker=dict(
                size=np.clip(cal["n"] / cal["n"].max() * 22, 8, 22), color=HIGHLIGHT, line=dict(color=SURFACE, width=2)
            ),
            line=dict(color=HIGHLIGHT, width=1.5),
            customdata=cal[["classe", "n"]].to_numpy(),
            showlegend=False,
            hovertemplate="Annoncé %{customdata[0]} (moy. %{x:.0%})<br>Arrivé : %{y:.0%}<br>%{customdata[1]} cas<extra></extra>",
        )
    )
    fig.update_xaxes(range=[0, 1], tickformat=".0%", title="Chance annoncée")
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title="Part réellement arrivée")
    fig.update_layout(title="Les pronostics à 60 % se réalisent-ils 60 % du temps ?", height=380)
    return fig
