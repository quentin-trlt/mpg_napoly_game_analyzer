import streamlit as st

from app import charts
from app.components import fmt_m, hero, how, kpi_row, section, table_height
from mpg.analysis import Analysis

PLAYER_COLS = {
    "joueur": "Joueur",
    "team_name": "Équipe",
    "poste": "Poste",
    "club": "Club",
    "enchere": st.column_config.NumberColumn("Enchère", format="%d M€"),
    "cote": st.column_config.NumberColumn("Cote", format="%d M€"),
    "surpaiement_x": st.column_config.NumberColumn("× cote", format="%.2f"),
    "n_notes": st.column_config.NumberColumn("Notes", help="Matchs notés retenus pour la note estimée"),
    "note_retrecie": st.column_config.NumberColumn(
        "Note estimée", format="%.2f", help="Note attendue quand il joue, tirée vers son poste"
    ),
    "note_attendue": st.column_config.NumberColumn("Attendue pour le prix", format="%.2f"),
    "residu_valeur": st.column_config.NumberColumn("Écart au prix", format="%+.2f"),
    "ga_saison": st.column_config.NumberColumn("G+A PL", format="%d"),
    "cout_par_ga_saison": st.column_config.NumberColumn("M€ par G+A", format="%.1f"),
    "taux_jeu": st.column_config.ProgressColumn("Taux de jeu PL", min_value=0, max_value=1, format="percent"),
}


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    m = a.mercato
    pv = a.player_value
    hero(
        "Mercato",
        "Qui a bien dépensé son argent ?",
        "Toutes les mesures sont robustes : médianes, log-ratios et moyennes tronquées, pour qu'un seul gros achat "
        "ne fausse pas le tableau.",
    )

    top = pv.sort_values("enchere", ascending=False).iloc[0]
    steal = pv[pv["n_notes"] > 0].sort_values("residu_valeur").iloc[-1]
    flop = pv[pv["n_notes"] > 0].sort_values("residu_valeur").iloc[0]
    infirm = m.sort_values("part_budget_indisponible").iloc[-1]
    kpi_row(
        [
            {
                "label": "Plus gros achat",
                "value": top["joueur"],
                "small": True,
                "sub": f"{fmt_m(top['enchere'])}, {top['team_name']}, cote {top['cote']:.0f}",
            },
            {
                "label": "Meilleur rapport prix/rendement",
                "value": steal["joueur"],
                "small": True,
                "sub": f"{fmt_m(steal['enchere'])}, {steal['team_name']}, {steal['residu_valeur']:+.2f} pt",
            },
            {
                "label": "Plus grosse déception",
                "value": flop["joueur"],
                "small": True,
                "sub": f"{fmt_m(flop['enchere'])}, {flop['team_name']}, {flop['residu_valeur']:+.2f} pt",
            },
            {
                "label": "Infirmerie la plus chère",
                "value": infirm["team_name"],
                "small": True,
                "sub": f"{infirm['part_budget_indisponible']:.0%} du budget blessé ou suspendu",
            },
        ]
    )

    section(
        "Comment chacun a réparti ses enchères",
        "Chaque point est un joueur. La boîte couvre la moitié centrale des achats, le trait vertical est la médiane.",
    )
    charts.show(charts.team_boxes(pv, "enchere", team_id, "Enchères par joueur", "Enchère (M€, échelle log)", log=True))
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.team_boxes(
                pv,
                "surpaiement_x",
                team_id,
                "Surpaiement : enchère / cote",
                "× la cote (échelle log)",
                log=True,
                hover_fmt=".2f",
            ),
            height=480,
        )
        how("surpaiement", meta)
    with right:
        charts.show(
            charts.ranked_bars(
                m.assign(g=m["gini_enchere"]),
                "g",
                "team_name",
                team_id,
                "Concentration du budget (Gini des enchères)",
                fmt=".2f",
                ascending=True,
                x_title="Gini (0 = budget réparti, 1 = tout sur un joueur)",
            ),
            height=480,
        )
        how("concentration", meta)

    section("Rendement par rapport au prix")
    charts.show(charts.price_note_facets(pv, team_id))
    how(["residu_valeur", "shrinkage" if meta.get("k_postes") else "shrinkage_compos"], meta)
    cols = ["joueur", "team_name", "poste", "enchere", "n_notes", "note_retrecie", "note_attendue", "residu_valeur"]
    rated = pv[pv["n_notes"] >= 2]
    st.caption("Joueurs avec au moins 2 matchs notés.")
    tab_good, tab_bad = st.tabs(["Les bonnes affaires", "Les déceptions"])
    with tab_good:
        st.dataframe(
            rated.sort_values("residu_valeur", ascending=False).head(10)[cols],
            hide_index=True,
            column_config=PLAYER_COLS,
            height=table_height(10),
        )
    with tab_bad:
        st.dataframe(
            rated.sort_values("residu_valeur").head(10)[cols],
            hide_index=True,
            column_config=PLAYER_COLS,
            height=table_height(10),
        )

    section("Fiabilité : a-t-on acheté des joueurs qui jouent ?")
    charts.show(
        charts.ranked_bars(
            m.assign(d=m["disponibilite_ponderee"] * 100),
            "d",
            "team_name",
            team_id,
            "Taux de jeu PL pondéré par l'enchère",
            fmt=".0f",
            x_title="%",
        ),
        height=380,
    )
    how("fiabilite", meta)
    st.dataframe(
        m.sort_values("part_budget_indisponible", ascending=False)[
            [
                "team_name",
                "part_budget_titulaires_pl",
                "part_budget_indisponible",
                "nb_indisponibles",
                "nb_incertains_pl",
                "cartons_jaunes",
                "cartons_rouges",
            ]
        ],
        hide_index=True,
        column_config={
            "team_name": "Équipe",
            "part_budget_titulaires_pl": st.column_config.ProgressColumn(
                "Sur titulaires PL",
                min_value=0,
                max_value=1,
                format="percent",
                help="Part des enchères sur des joueurs titulaires dans au moins la moitié des matchs de leur club",
            ),
            "part_budget_indisponible": st.column_config.ProgressColumn(
                "À l'infirmerie",
                min_value=0,
                max_value=1,
                format="percent",
                help="Part du budget blessé ou suspendu",
            ),
            "nb_indisponibles": st.column_config.NumberColumn("Indispo.", width="small", help="Blessés ou suspendus"),
            "nb_incertains_pl": st.column_config.NumberColumn("Incert.", width="small", help="Incertains en PL"),
            "cartons_jaunes": st.column_config.NumberColumn("CJ", width="small", help="Cartons jaunes"),
            "cartons_rouges": st.column_config.NumberColumn("CR", width="small", help="Cartons rouges"),
        },
        height=table_height(len(m)),
    )
    how("discipline", meta)

    section("Répartition par ligne et production")
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(charts.budget_shares(m))
        how("equilibre", meta)
    with right:
        charts.show(
            charts.ranked_bars(
                m,
                "cout_median_par_ga",
                "team_name",
                team_id,
                "Coût médian par but ou passe décisive PL",
                fmt=".1f",
                ascending=False,
                x_title="M€ par G+A (médiane des joueurs décisifs)",
            )
        )
        how("production_pl", meta)

    section("Tableau de bord du mercato")
    st.dataframe(
        m[
            [
                "team_name",
                "enchere_totale",
                "enchere_mediane",
                "enchere_moy_tronquee",
                "enchere_ecart_type",
                "enchere_iqr",
                "enchere_max",
                "joueur_plus_cher",
                "part_top3",
                "surpaiement_median_x",
                "surpaiement_global_x",
                "ga_saison",
            ]
        ],
        hide_index=True,
        column_config={
            "team_name": "Équipe",
            "enchere_totale": st.column_config.NumberColumn("Dépensé", format="%d M€"),
            "enchere_mediane": st.column_config.NumberColumn("Médiane", format="%.1f M€"),
            "enchere_moy_tronquee": st.column_config.NumberColumn("Moy. tronquée", format="%.1f M€"),
            "enchere_ecart_type": st.column_config.NumberColumn("Écart-type", format="%.1f"),
            "enchere_iqr": st.column_config.NumberColumn("IQR", format="%.1f"),
            "enchere_max": st.column_config.NumberColumn("Max", format="%d M€"),
            "joueur_plus_cher": "Plus cher",
            "part_top3": st.column_config.ProgressColumn("Part top 3", min_value=0, max_value=1, format="percent"),
            "surpaiement_median_x": st.column_config.NumberColumn("Surpaiement médian", format="× %.2f"),
            "surpaiement_global_x": st.column_config.NumberColumn("Surpaiement global", format="× %.2f"),
            "ga_saison": st.column_config.NumberColumn("G+A PL", format="%d"),
        },
    )

    section(f"Clubs PL dans l'effectif de {a.league.team_names[team_id]}")
    clubs = a.clubs[a.clubs["team_id"] == team_id]
    st.dataframe(
        clubs[["club", "n", "enchere"]],
        hide_index=True,
        column_config={
            "club": "Club",
            "n": st.column_config.ProgressColumn(
                "Joueurs", min_value=0, max_value=int(a.clubs["n"].max()), format="%d"
            ),
            "enchere": st.column_config.NumberColumn("Enchères", format="%d M€"),
        },
        height=table_height(len(clubs)),
    )
