import streamlit as st

from app import charts
from app.components import callout, form_badges, how, kpi_row, names_list, section
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
        height=38 * (len(st_df) + 1) + 2,
    )


def _next_fixtures(a: Analysis, team_id: int) -> None:
    nf = a.next_fixtures
    if nf.empty:
        callout("La saison est terminée : plus aucun match à venir.")
        return
    gw = int(nf["gw"].iloc[0])
    section(f"Journée {gw} — les affiches", "Triées de la plus serrée (écart de rang minimal) à la plus déséquilibrée.")
    cols = st.columns(len(nf))
    for col, (_, f) in zip(cols, nf.iterrows()):
        me = team_id in (f["home_team_id"], f["away_team_id"])
        date = f["date"].strftime("%d/%m") if hasattr(f["date"], "strftime") else ""
        heure = f" · {f['heure']}" if isinstance(f.get("heure"), str) else ""
        with col:
            st.html(f"""
            <div class="fixture{" me" if me else ""}">
              <div class="meta">{date}{heure}</div>
              <div class="team" style="margin-top:6px">{f["home_team"]}</div>
              <div class="meta">{int(f["home_rang"])}e · {int(f["home_pts"])} pts</div>
              <div style="margin:4px 0">{form_badges(f.get("home_forme", "") or "")}</div>
              <div class="meta" style="margin:6px 0;text-align:center">contre</div>
              <div class="team">{f["away_team"]}</div>
              <div class="meta">{int(f["away_rang"])}e · {int(f["away_pts"])} pts</div>
              <div style="margin-top:4px">{form_badges(f.get("away_forme", "") or "")}</div>
            </div>""")


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    kf = key_figures(a)
    mine = a.standings.set_index("team_id").loc[team_id]
    st.html(f"""<div class="hero"><div class="eyebrow">Ligue Napoly Game · Premier League</div>
        <div class="title">Journée {meta["derniere_journee"]} sur {meta["nb_journees"]}</div>
        <div class="subtitle">{meta["matchs_joues"]} matchs joués. Tout est recalculé à partir des fichiers de
        <code>data/</code> : remplacez-les pour mettre l'app à jour.</div></div>""")

    kpi_row(
        [
            {
                "label": "Leader",
                "value": kf["leader"]["equipe"],
                "small": True,
                "sub": f"{kf['leader']['pts']} pts · {kf['leader']['ecart_2e']} d'avance · {kf['leader']['coach']}",
            },
            {
                "label": f"Classement de {mine['team_name']}",
                "value": f"{int(mine['rang'])}e",
                "sub": f"{int(mine['pts'])} pts · série {mine['serie']}",
            },
            {
                "label": "Meilleur buteur PL de la ligue",
                "value": names_list(kf["buteur_pl"]["joueurs"]),
                "small": True,
                "sub": f"{kf['buteur_pl']['buts']} buts en PL · {names_list(kf['buteur_pl']['equipes'])}",
            },
            {
                "label": "Meilleur buteur MPG",
                "value": names_list(kf["buteur_mpg"]["joueurs"]),
                "small": True,
                "sub": f"{kf['buteur_mpg']['buts']} buts réels + MPG dans la ligue",
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
        charts.show(charts.bump_chart(a.standings_by_gw, team_id, len(a.league.teams)))
    with right:
        lk = a.luck.copy()
        abbrev = dict(zip(a.league.teams["team_id"], a.league.teams["abrev"]))
        charts.show(charts.luck_scatter(lk, abbrev, team_id))
        how(["points_vs_niveau", "all_play"], meta)

    section("Force par ligne et attaque")
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        sort_by = st.segmented_control(
            "Trier par",
            options=list(SORT_OPTIONS),
            format_func=SORT_OPTIONS.get,
            default="globale",
            required=True,
            key="lines_sort",
        )
        charts.show(charts.line_heatmap(a.lines, sort_by or "globale"))
        how(["force_ligne", "note_brute"], meta)
    with right:
        st.html('<div style="height:62px"></div>')
        charts.show(charts.stacked_goals(a.standings))
        st.caption(
            "Un but MPG est accordé quand un joueur sans but réel obtient une note suffisante face aux lignes "
            "adverses. Les CSC Rotaldo sont comptés avec les CSC."
        )

    _next_fixtures(a, team_id)
