from html import escape

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from app import charts
from app.components import hero, how, kpi_row, section
from app.theme import AXIS, HIGHLIGHT, LINE_LABELS, SERIES, SURFACE
from mpg.analysis import Analysis

SORTS = {
    "note_retrecie": "Note rétrécie",
    "note_moy": "Note MPG brute",
    "buts_total": "Buts dans la ligue",
    "ga_saison": "G+A en PL",
    "residu_valeur": "Écart au prix",
    "enchere": "Enchère",
}


def _shrink_chart(ps, team_id: int) -> go.Figure:
    d = ps[ps["n_notes"] > 0]
    fig = go.Figure()
    lo, hi = 2.5, 8.5
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=AXIS, width=1), hoverinfo="skip", showlegend=False
        )
    )
    me = d["team_id"] == team_id
    fig.add_trace(
        go.Scatter(
            x=d["note_moy"],
            y=d["note_retrecie"],
            mode="markers",
            marker=dict(
                size=np.clip(d["n_notes"] * 3 + 3, 5, 16),
                color=[HIGHLIGHT if m else "#8FA3BF" for m in me],
                opacity=[1 if m else 0.55 for m in me],
                line=dict(color=SURFACE, width=1),
            ),
            customdata=np.stack([d["joueur"], d["team_name"], d["n_notes"], d["note_prior"]], axis=1),
            showlegend=False,
            hovertemplate="<b>%{customdata[0]}</b>, %{customdata[1]}<br>Moyenne MPG : %{x:.2f} sur %{customdata[2]} matchs"
            "<br>Moyenne PL (a priori) : %{customdata[3]:.2f}<br>Note rétrécie : %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Moyenne MPG observée et note retenue",
        height=420,
        xaxis_title="Moyenne MPG observée (note brute)",
        yaxis_title="Note rétrécie",
    )
    fig.update_xaxes(range=[lo, hi])
    fig.update_yaxes(range=[lo + 1, hi - 1])
    return fig


def _top5_panel(ps, team_id: int) -> str:
    blocks = []
    for g in "GDMA":
        top = ps[(ps["poste_groupe"] == g) & (ps["n_notes"] >= 2)].sort_values("note_retrecie", ascending=False).head(5)
        rows = "".join(
            f'<div class="p{" me" if r.team_id == team_id else ""}"><div style="min-width:0">'
            f'<div class="who">{escape(r.joueur)}</div><div class="club">{escape(r.team_name)}</div></div>'
            f'<div class="note">{r.note_retrecie:.2f}</div></div>'
            for r in top.itertuples()
        )
        blocks.append(f'<div><div class="head">{LINE_LABELS[g]}</div>{rows}</div>')
    return f'<div class="top5">{"".join(blocks)}</div>'


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    ps = a.player_value
    hero(
        "Joueurs",
        "Les classements individuels",
        f"{len(ps)} joueurs achetés. Les notes MPG sont rétrécies vers la moyenne de saison PL pour ne pas récompenser "
        "un seul gros match.",
    )

    mvp = ps.sort_values(["mvp_match", "top3_match"], ascending=False).iloc[0]
    scorer = ps.sort_values("buts_total", ascending=False).iloc[0]
    passer = ps.sort_values("passes_decisives_saison", ascending=False).iloc[0]
    best = ps[ps["n_notes"] >= 2].sort_values("note_retrecie", ascending=False).iloc[0]
    kpi_row(
        [
            {
                "label": "Meilleure note rétrécie",
                "value": best["joueur"],
                "small": True,
                "sub": f"{best['note_retrecie']:.2f}, {best['team_name']}",
            },
            {
                "label": "Meilleur buteur de la ligue",
                "value": scorer["joueur"],
                "small": True,
                "sub": f"{int(scorer['buts_reels'])} réels + {int(scorer['buts_mpg'])} MPG, {scorer['team_name']}",
            },
            {
                "label": "Meilleur passeur PL",
                "value": passer["joueur"],
                "small": True,
                "sub": f"{passer['passes_decisives_saison']:.0f} passes décisives, {passer['team_name']}",
            },
            {
                "label": "Homme du match le plus souvent",
                "value": mvp["joueur"],
                "small": True,
                "sub": f"{int(mvp['mvp_match'])} fois n°1, {int(mvp['top3_match'])} fois dans le top 3",
            },
        ]
    )

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.9, 1.5, 1.1, 0.9])
        with c1:
            poste = st.segmented_control(
                "Poste",
                options=["Tous", *"GDMA"],
                default="Tous",
                required=True,
                format_func=lambda g: LINE_LABELS.get(g, g),
                key="pl_poste",
            )
        with c2:
            teams = st.multiselect(
                "Équipes",
                options=a.standings["team_id"].tolist(),
                format_func=a.league.team_names.get,
                placeholder="Toutes",
                key="pl_teams",
            )
        with c3:
            sort = st.selectbox("Trier par", options=list(SORTS), format_func=SORTS.get, key="pl_sort")
        with c4:
            min_n = st.number_input(
                "Matchs notés min.", min_value=0, max_value=int(ps["n_notes"].max()), value=2, key="pl_min"
            )
    d = ps[ps["n_notes"] >= min_n]
    if poste != "Tous":
        d = d[d["poste_groupe"] == poste]
    if teams:
        d = d[d["team_id"].isin(teams)]
    d = d.sort_values(sort, ascending=False)
    st.caption(f"{len(d)} joueurs affichés.")
    st.dataframe(
        d[
            [
                "joueur",
                "team_name",
                "poste",
                "club",
                "enchere",
                "cote",
                "n_notes",
                "note_moy",
                "note_ecart_type",
                "note_retrecie",
                "note_moy_reelle",
                "points_mpg_moy",
                "buts_reels",
                "buts_mpg",
                "buts_reels_saison",
                "passes_decisives_saison",
                "ga_par_match",
                "taux_jeu",
                "cartons_jaunes",
                "statut_performance",
                "top3_match",
                "capitanats",
                "residu_valeur",
            ]
        ],
        hide_index=True,
        column_config={
            "joueur": st.column_config.TextColumn("Joueur", pinned=True),
            "team_name": "Équipe",
            "poste": "Poste",
            "club": "Club",
            "enchere": st.column_config.NumberColumn("Enchère", format="%d M€"),
            "cote": st.column_config.NumberColumn("Cote", format="%d M€"),
            "n_notes": st.column_config.NumberColumn("Notes", help="Matchs notés dans la ligue"),
            "note_moy": st.column_config.NumberColumn("Moy. MPG", format="%.2f"),
            "note_ecart_type": st.column_config.NumberColumn("Écart-type", format="%.2f", help="Régularité"),
            "note_retrecie": st.column_config.NumberColumn("Note rétrécie", format="%.2f"),
            "note_moy_reelle": st.column_config.NumberColumn("Moy. PL", format="%.1f"),
            "points_mpg_moy": st.column_config.NumberColumn("Pts MPG moy.", format="%.2f"),
            "buts_reels": st.column_config.NumberColumn("Buts ligue"),
            "buts_mpg": st.column_config.NumberColumn("Buts MPG"),
            "buts_reels_saison": st.column_config.NumberColumn("Buts PL"),
            "passes_decisives_saison": st.column_config.NumberColumn("Passes PL", format="%d"),
            "ga_par_match": st.column_config.NumberColumn("G+A / match", format="%.2f"),
            "taux_jeu": st.column_config.ProgressColumn("Taux de jeu", min_value=0, max_value=1, format="percent"),
            "cartons_jaunes": st.column_config.NumberColumn("Jaunes", format="%d"),
            "statut_performance": "Statut",
            "top3_match": st.column_config.NumberColumn("Top 3 match"),
            "capitanats": st.column_config.NumberColumn("Capitaine"),
            "residu_valeur": st.column_config.NumberColumn("Écart au prix", format="%+.2f"),
        },
        height=520,
    )
    how(["shrinkage", "production_pl"], meta)

    section("Top 5 par poste", "Note rétrécie, au moins 2 matchs notés.")
    st.html(_top5_panel(ps, team_id))

    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        charts.show(_shrink_chart(ps, team_id))
        st.caption(
            f"k = {meta['k_shrinkage']:.1f} : chaque joueur reçoit l'équivalent de {meta['k_shrinkage']:.0f} "
            "matchs à sa moyenne PL. Taille du point = nombre de matchs notés."
        )
    with right:
        ga = ps[ps["ga_saison"] > 0].sort_values("ga_saison", ascending=False).head(12).iloc[::-1]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                y=ga["joueur"],
                x=ga["buts_reels_saison"],
                name="Buts",
                orientation="h",
                marker=dict(color=SERIES[0], line=dict(color=SURFACE, width=2)),
                hovertemplate="<b>%{y}</b><br>Buts : %{x}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Bar(
                y=ga["joueur"],
                x=ga["passes_decisives_saison"],
                name="Passes décisives",
                orientation="h",
                marker=dict(color=SERIES[1], line=dict(color=SURFACE, width=2)),
                hovertemplate="<b>%{y}</b><br>Passes : %{x}<extra></extra>",
            )
        )
        fig.update_layout(barmode="stack", title="Les plus décisifs en Premier League (G+A)", height=420)
        fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
        charts.show(fig)
