import streamlit as st

from app import charts
from app.components import fmt_signed, hero, how, kpi_row, section
from mpg.analysis import Analysis
from mpg.luck import schedule_permutation


@st.cache_data(show_spinner=False)
def _simulations(tm, band: float, n_sim: int):
    return schedule_permutation(tm, band, n_sim=n_sim)


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    lk = a.luck
    hero(
        "Chance",
        "Qui a eu de la réussite ?",
        "On compare les points pris à ceux que le niveau de jeu (les notes) aurait dû rapporter, puis on sépare "
        "la chance de calendrier de la chance de conversion.",
    )

    lucky = lk.sort_values("chance_totale").iloc[-1]
    unlucky = lk.sort_values("chance_totale").iloc[0]
    sched = lk.sort_values("percentile_calendrier")
    me = lk.set_index("team_id").loc[team_id]
    kpi_row(
        [
            {
                "label": "Le plus chanceux",
                "value": lucky["team_name"],
                "small": True,
                "sub": f"{fmt_signed(lucky['chance_totale'])} pts par rapport aux xPts",
            },
            {
                "label": "Le plus malchanceux",
                "value": unlucky["team_name"],
                "small": True,
                "sub": f"{fmt_signed(unlucky['chance_totale'])} pts par rapport aux xPts",
            },
            {
                "label": "Pire calendrier",
                "value": sched.iloc[0]["team_name"],
                "small": True,
                "sub": f"{sched.iloc[0]['percentile_calendrier']:.0f}e percentile des calendriers",
            },
            {
                "label": me["team_name"],
                "value": f"{fmt_signed(me['chance_totale'])} pts",
                "sub": f"IC 90 % [{me['chance_ic90_bas']:+.1f} ; {me['chance_ic90_haut']:+.1f}] · calendrier "
                f"{me['percentile_calendrier']:.0f}e pct",
            },
            {
                "label": "Fiabilité de la règle de note",
                "value": f"{meta['concordance_regle_note']:.0%}",
                "sub": "des vrais résultats retrouvés par la note",
            },
        ]
    )
    how("petit_echantillon", meta, "À lire avant d'interpréter")

    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.diverging_bars(
                lk,
                "chance_totale",
                "team_name",
                team_id,
                "Chance totale (points − xPts)",
                low="chance_ic90_bas",
                high="chance_ic90_haut",
                x_title="Points",
            )
        )
        how(["chance_decomposition", "bootstrap"], meta)
    with right:
        charts.show(
            charts.stacked_components(
                lk,
                [("chance_calendrier", "Calendrier"), ("chance_conversion", "Conversion")],
                team_id,
                "D'où vient la chance ?",
                "Points",
            )
        )
        st.caption(
            "Calendrier : avoir croisé ses adversaires un jour sans. Conversion : ce que la mécanique MPG "
            "(buts MPG, arrêts, Rotaldos) a donné ou repris à notes égales."
        )

    section("Le calendrier a-t-il aidé ?")
    summary, totals = _simulations(a.team_match, meta["bande_nul"], meta["n_sim"])
    team_ids = summary["team_id"].astype(int).tolist()
    real = lk.set_index("team_id")["pts_regle"]
    charts.show(charts.sim_distribution(totals, team_ids, a.league.team_names, real, team_id))
    how("calendrier_permute", meta)

    section("Les autres mesures de la chance")
    left, right = st.columns([1, 1.2], gap="medium")
    with left:
        charts.show(
            charts.diverging_bars(
                lk,
                "chance_pythagore",
                "team_name",
                team_id,
                "Points − xPts pythagoriciens (buts pour/contre)",
                x_title="Points",
            )
        )
        how("pythagore", meta)
    with right:
        charts.show(
            charts.diverging_bars(
                lk.assign(s=-lk["sur_regime_adv_moy"]),
                "s",
                "team_name",
                team_id,
                "Adversaires en dessous de leur niveau (+) ou au-dessus (−)",
                x_title="Écart de note adverse",
                fmt="+.2f",
            )
        )
        how("sur_regime_adv", meta)

    section("Le détail", "Tous les ingrédients de la chance, équipe par équipe.")
    st.dataframe(
        lk[
            [
                "team_name",
                "indice_chance",
                "pts",
                "xpts_allplay",
                "pts_regle",
                "chance_totale",
                "chance_calendrier",
                "chance_conversion",
                "percentile_calendrier",
                "xpts_pythagore",
                "sur_regime_adv_moy",
                "buts_mpg_pour",
                "buts_mpg_contre",
                "csc_pour",
                "rotaldos_adverses",
                "suarez_subis",
                "victoires_1but",
                "defaites_1but",
            ]
        ],
        hide_index=True,
        column_config={
            "team_name": "Équipe",
            "indice_chance": st.column_config.NumberColumn("Indice de chance", format="%+.2f"),
            "pts": "Pts",
            "xpts_allplay": st.column_config.NumberColumn("xPts all-play", format="%.1f"),
            "pts_regle": st.column_config.NumberColumn(
                "Pts à la note", help="Points selon la règle de note, vrais adversaires"
            ),
            "chance_totale": st.column_config.NumberColumn("Chance totale", format="%+.1f"),
            "chance_calendrier": st.column_config.NumberColumn("dont calendrier", format="%+.1f"),
            "chance_conversion": st.column_config.NumberColumn("dont conversion", format="%+.1f"),
            "percentile_calendrier": st.column_config.ProgressColumn(
                "Percentile calendrier", min_value=0, max_value=100, format="%.0f"
            ),
            "xpts_pythagore": st.column_config.NumberColumn("xPts pythagore", format="%.1f"),
            "sur_regime_adv_moy": st.column_config.NumberColumn("Sur-régime adverse", format="%+.2f"),
            "buts_mpg_pour": "Buts MPG pour",
            "buts_mpg_contre": "Buts MPG contre",
            "csc_pour": "CSC reçus",
            "rotaldos_adverses": "Rotaldos adverses",
            "suarez_subis": "Suarez subis",
            "victoires_1but": "V d'un but",
            "defaites_1but": "D d'un but",
        },
    )
    how("indice_chance", meta)
