from html import escape

import streamlit as st

from app import charts
from app.components import callout, fixture_grid, form_badges, hero, how, kpi_row, names_list, section, table_height
from mpg.analysis import Analysis, key_figures

SORT_OPTIONS = {"globale": "Globale", "G": "Gardiens", "D": "Défense", "M": "Milieu", "A": "Attaque"}


def _standings_table(a: Analysis, team_id: int) -> None:
    st_df = a.standings.copy()
    st_df["moi"] = st_df["team_id"] == team_id
    st_df["diff"] = st_df["diff"].map(lambda d: f"{d:+d}")
    st.dataframe(
        st_df,
        hide_index=True,
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
            "team_name": st.column_config.TextColumn("Équipe", width="medium"),
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
    if nf.empty:
        callout("La saison est terminée : plus aucun match à venir.")
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
            f'<div style="margin-top:8px">{sides[0]}</div><div class="vs">contre</div>{sides[1]}</div>'
        )
    fixture_grid(cards, min(len(cards), 5))


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    kf = key_figures(a)
    mine = a.standings.set_index("team_id").loc[team_id]
    hero(
        "Ligue Napoly Game, Premier League",
        f"Journée {meta['derniere_journee']} sur {meta['nb_journees']}",
        f"{meta['matchs_joues']} matchs joués. Tout est recalculé à partir des fichiers de <code>data/</code> : "
        "remplacez-les pour mettre l'app à jour.",
    )

    leader, pl, mpg = kf["leader"], kf["buteur_pl"], kf["buteur_mpg"]
    kpi_row(
        [
            {
                "label": "Leader",
                "value": leader["equipe"],
                "small": True,
                "sub": f"{leader['pts']} pts, {leader['ecart_2e']} d'avance. Coach {leader['coach']}",
            },
            {
                "label": mine["team_name"],
                "value": f"{int(mine['rang'])}e",
                "sub": f"{int(mine['pts'])} pts, série {mine['serie']}",
                "me": True,
            },
            {
                "label": "Meilleur buteur PL de la ligue",
                "value": names_list(pl["joueurs"]),
                "small": True,
                "sub": f"{pl['buts']} buts ({names_list(pl['equipes'])}). En MPG : {names_list(mpg['joueurs'])}, "
                f"{mpg['buts']} buts",
            },
            {
                "label": "Roi des Rotaldos",
                "value": names_list(kf["roi_rotaldos"]["equipes"]),
                "small": True,
                "sub": f"{kf['roi_rotaldos']['rotaldos']} Rotaldos alignés",
            },
        ]
    )

    section("Classement")
    _standings_table(a, team_id)

    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(charts.bump_chart(a.standings_by_gw, team_id, len(a.league.teams)), height=440)
    with right:
        abbrev = dict(zip(a.league.teams["team_id"], a.league.teams["abrev"]))
        charts.show(charts.luck_scatter(a.luck.copy(), abbrev, team_id))
    how(["points_vs_niveau", "all_play"], meta)

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
