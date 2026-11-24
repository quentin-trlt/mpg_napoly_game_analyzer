from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import (
    fixture_grid,
    fmt_signed,
    form_badges,
    how,
    kpi_row,
    limit_banner,
    names_list,
    rank_list,
    section,
    table_height,
    volet_title,
)
from app.navigation import page_link
from mpg.analysis import Analysis, key_figures
from mpg.seasons import coach_by_team

SORT_OPTIONS = {"globale": "Globale", "G": "Gardiens", "D": "Défense", "M": "Milieu", "A": "Attaque"}


def _standings_table(a: Analysis, team_id: int) -> None:
    st_df = a.standings.copy()
    st_df["moi"] = st_df["team_id"] == team_id
    st_df["diff"] = st_df["diff"].map(lambda d: f"{d:+d}")
    st.html(rank_list(a.standings, team_id, coach_by_team(a.league)))
    with st.expander("Toutes les colonnes"):
        _full_standings(st_df)


def _full_standings(st_df: pd.DataFrame) -> None:
    st.dataframe(
        st_df,
        hide_index=True,
        alt="Classement, toutes les colonnes",
        column_order=[
            "rang",
            "team_name",
            "coach",
            "pts",
            "g",
            "n",
            "p",
            "bp",
            "bc",
            "diff",
            "bp_mpg",
            "note_moy",
            "rotaldos",
            "forme",
            "serie",
        ],
        column_config={
            "rang": st.column_config.NumberColumn("#", width="small"),
            "team_name": st.column_config.TextColumn("Équipe", width="medium", pinned=True),
            "coach": st.column_config.TextColumn("Coach"),
            "pts": st.column_config.ProgressColumn(
                "Pts", min_value=0, max_value=int(3 * st_df["j"].max()), format="%d"
            ),
            "j": st.column_config.NumberColumn("J", width="small"),
            "g": st.column_config.NumberColumn("V", width="small"),
            "n": st.column_config.NumberColumn("N", width="small"),
            "p": st.column_config.NumberColumn("D", width="small"),
            "bp": st.column_config.NumberColumn("BP", width="small", help="Buts marqués, CSC adverses inclus"),
            "bc": st.column_config.NumberColumn("BC", width="small"),
            "diff": st.column_config.TextColumn("Diff", width="small"),
            "bp_mpg": st.column_config.NumberColumn("Buts MPG", help="Buts accordés par MPG sur la note"),
            "note_moy": st.column_config.NumberColumn("Moy.", format="%.2f", help="Note moyenne bonus inclus (+B.)"),
            "rotaldos": st.column_config.NumberColumn("Rotaldos"),
            "forme": st.column_config.TextColumn("Forme", help="5 derniers résultats, du plus ancien au plus récent"),
            "serie": st.column_config.TextColumn("Série", help="Série en cours (ex. 2V = 2 victoires)"),
        },
        height=table_height(len(st_df)),
    )


def _next_fixtures(a: Analysis, team_id: int) -> None:
    nf = a.next_fixtures
    if a.meta["capacites"].terminee or nf.empty:
        return
    gw = int(nf["gw"].iloc[0])
    section(f"Journée {gw} : les affiches", "Triées de la plus serrée (écart de rang minimal) à la plus déséquilibrée.")
    cards = []
    for _, f in nf.iterrows():
        me = team_id in (f["home_team_id"], f["away_team_id"])
        date = f["date"].strftime("%d/%m") if hasattr(f["date"], "strftime") else ""
        heure = f" à {f['heure']}" if isinstance(f.get("heure"), str) else ""
        sides = [
            f'<div class="side"><div class="team">{escape(f[f"{s}_team"])}</div>'
            f'<div class="meta">{int(f[f"{s}_rang"])}e, {int(f[f"{s}_pts"])} pts</div>'
            f'<div class="form">{form_badges(f.get(f"{s}_forme", "") or "")}</div></div>'
            for s in ("home", "away")
        ]
        cards.append(
            f'<div class="fixture{" me" if me else ""}"><div class="meta">{date}{heure}</div>'
            f'<div class="pair mt-8">{sides[0]}<div class="vs">contre</div>{sides[1]}</div></div>'
        )
    fixture_grid(cards, len(cards))


def _hero(a: Analysis, leader: dict) -> None:
    meta = a.meta
    if meta["capacites"].terminee:
        volet_title(
            f"Saison {meta['saison']}, terminée",
            f"{escape(leader['equipe'])} a gagné la ligue, coach {escape(leader['coach'])}. "
            f"{len(a.standings)} équipes, {meta['nb_journees']} journées, {meta['matchs_joues']} matchs.",
        )
        return
    volet_title(
        f"Journée {meta['derniere_journee']} sur {meta['nb_journees']}",
        f"{meta['matchs_joues']} matchs joués. Le classement et les statistiques se mettent à jour après chaque "
        "journée jouée.",
    )


def _leader_cell(leader: dict, finished: bool) -> dict:
    lead = leader["ecart_2e"]
    gap = f"{lead} d'avance" if lead else "à égalité de points avec le 2e"
    return {
        "label": "Champion" if finished else "Leader",
        "value": leader["equipe"],
        "small": True,
        "sub": f"{leader['pts']} pts, {gap}. Coach {leader['coach']}",
    }


def _scorer_cell(kf: dict) -> dict:
    pl, mpg = kf["buteur_pl"], kf["buteur_mpg"]
    if pl is None:
        return {
            "label": "Meilleur buteur de la ligue",
            "value": names_list(mpg["joueurs"]),
            "small": True,
            "sub": f"{mpg['buts']} buts dans la ligue",
        }
    return {
        "label": "Meilleur buteur PL de la ligue",
        "value": names_list(pl["joueurs"]),
        "small": True,
        "sub": f"{pl['buts']} buts ({names_list(pl['equipes'])}). En MPG : {names_list(mpg['joueurs'])}, "
        f"{mpg['buts']} buts",
    }


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    finished = meta["capacites"].terminee
    kf = key_figures(a)
    mine = a.standings.set_index("team_id").loc[team_id]
    _hero(a, kf["leader"])
    limit_banner(meta["limites"])

    kpi_row(
        [
            _leader_cell(kf["leader"], finished),
            {
                "label": mine["team_name"],
                "value": f"{int(mine['rang'])}e",
                "sub": f"{int(mine['pts'])} pts, série {mine['serie']}",
                "me": True,
            },
            _scorer_cell(kf),
            {
                "label": "Roi des Rotaldos",
                "value": names_list(kf["roi_rotaldos"]["equipes"]),
                "small": True,
                "sub": f"{kf['roi_rotaldos']['rotaldos']} Rotaldos alignés",
            },
        ]
    )

    section("Classement final" if finished else "Classement")
    _standings_table(a, team_id)

    charts.show(charts.bump_chart(a.standings_by_gw, team_id, len(a.league.teams)), height=440)
    luck = a.luck.set_index("team_id").loc[team_id]
    st.markdown(
        f"**{mine['team_name']}** : tu as {int(luck['pts'])} points, tes notes en méritaient "
        f"{luck['xpts_allplay']:.1f} ({fmt_signed(luck['pts'] - luck['xpts_allplay'])} pts de chance)."
    )
    page_link("pourquoi", "Comprendre ce classement : mérite ou chance ?", icon=":material/casino:", volet="chance")
    how("all_play", meta)

    section("Force par ligne et attaque")
    sort_by = st.segmented_control(
        "Trier la heatmap par",
        options=list(SORT_OPTIONS),
        format_func=SORT_OPTIONS.get,
        default="globale",
        required=True,
        key="lines_sort",
    )
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        charts.show(charts.line_heatmap(a.lines, sort_by or "globale"))
        how(["force_ligne", "note_brute"], meta)
    with right:
        charts.show(charts.stacked_goals(a.standings), height=440)
        st.caption(
            "Un but MPG est accordé quand un joueur sans but réel obtient une note suffisante face aux lignes "
            "adverses. Les CSC Rotaldo sont comptés avec les CSC."
        )

    _next_fixtures(a, team_id)
