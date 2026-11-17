import pandas as pd
import streamlit as st

from app import charts
from app.components import callout, fmt_signed, how, kpi_row, section, volet_title
from mpg.analysis import Analysis
from mpg.glossary import explain
from mpg.luck import schedule_permutation

SMALL_SAMPLE_GW = 10


@st.cache_data(show_spinner=False)
def _simulations(season: str, tm, band: float, n_sim: int):
    return schedule_permutation(tm, band, n_sim=n_sim)


def _schedule_label(lk: pd.DataFrame, team_id: int) -> str:
    """Place du calendrier de l'équipe, dite côté « faciles » ou « difficiles » selon la moitié du classement."""
    ease = lk.set_index("team_id")["percentile_calendrier"]
    n = len(ease)
    easy = int(ease.rank(ascending=False, method="min").loc[team_id])
    hard = int(ease.rank(ascending=True, method="min").loc[team_id])
    if easy <= hard:
        return f"le calendrier le plus facile des {n}" if easy == 1 else f"classé {easy}e sur {n} des plus faciles"
    return f"le calendrier le plus difficile des {n}" if hard == 1 else f"classé {hard}e sur {n} des plus difficiles"


def _verdict(low: float, high: float) -> str:
    span = f"entre {fmt_signed(low)} et {fmt_signed(high)} points"
    if low <= 0 <= high:
        return (
            f"Trop tôt pour conclure : ta réussite se situe {span} (90 % de confiance), et 0 est dans cette fourchette. "
            "L'écart peut très bien venir du hasard."
        )
    mood = "de la réussite" if low > 0 else "de la malchance"
    return (
        f"L'écart est net : ta réussite se situe {span} (90 % de confiance), sans passer par 0. "
        f"Tu as vraiment eu {mood}."
    )


def _method(keys: list[str], meta: dict) -> None:
    st.markdown("\n\n".join(explain(k, **meta) for k in keys))


def _head(a: Analysis, team_id: int) -> None:
    meta = a.meta
    me = a.luck.set_index("team_id").loc[team_id]
    if meta["derniere_journee"] < SMALL_SAMPLE_GW:
        callout(
            f"Petit échantillon : seulement {meta['derniere_journee']} journées jouées. Un écart de 2 ou 3 points peut "
            "venir d'un seul penalty. Lis ce volet comme une tendance, pas comme un verdict.",
            warn=True,
        )
    section(
        f"Tes notes valaient {me['xpts_allplay']:.1f} points, tu en as {int(me['pts'])} : "
        f"{fmt_signed(me['chance_totale'])} de réussite",
        _verdict(me["chance_ic90_bas"], me["chance_ic90_haut"]),
    )
    kpi_row(
        [
            {
                "label": "Tes notes valaient",
                "value": f"{me['xpts_allplay']:.1f} pts",
                "sub": "points mérités, contre toutes les équipes de la journée",
            },
            {"label": "Tu as pris", "value": f"{int(me['pts'])} pts", "sub": "les points du classement"},
            {
                "label": me["team_name"],
                "value": f"{fmt_signed(me['chance_totale'])} pts",
                "sub": "points pris moins points mérités",
                "me": True,
            },
        ]
    )
    kpi_row(
        [
            {
                "label": "Grâce au calendrier",
                "value": f"{fmt_signed(me['chance_calendrier'])} pts",
                "small": True,
                "sub": _schedule_label(a.luck, team_id),
            },
            {
                "label": "Grâce à la conversion",
                "value": f"{fmt_signed(me['chance_conversion'])} pts",
                "small": True,
                "sub": "ce que les buts MPG, arrêts et Rotaldos ont donné ou repris à notes égales",
            },
            {
                "label": "Fourchette de ta réussite",
                "value": f"entre {fmt_signed(me['chance_ic90_bas'])} et {fmt_signed(me['chance_ic90_haut'])}",
                "small": True,
                "sub": "90 % de confiance, en points",
            },
        ]
    )
    st.caption(
        f"La règle de note retrouve {meta['concordance_regle_note']:.0%} des vrais résultats : c'est la base de tous "
        "les calculs de ce volet."
    )
    how("petit_echantillon", meta, "À lire avant d'interpréter")


def _league(a: Analysis, team_id: int) -> None:
    meta = a.meta
    lk = a.luck
    section("Dans la ligue")
    lucky = lk.sort_values("chance_totale").iloc[-1]
    unlucky = lk.sort_values("chance_totale").iloc[0]
    worst = lk.sort_values("percentile_calendrier").iloc[0]
    kpi_row(
        [
            {
                "label": "Le plus chanceux",
                "value": lucky["team_name"],
                "small": True,
                "sub": f"{fmt_signed(lucky['chance_totale'])} pts par rapport aux points mérités",
            },
            {
                "label": "Le plus malchanceux",
                "value": unlucky["team_name"],
                "small": True,
                "sub": f"{fmt_signed(unlucky['chance_totale'])} pts par rapport aux points mérités",
            },
            {
                "label": "Pire calendrier",
                "value": worst["team_name"],
                "small": True,
                "sub": _schedule_label(lk, int(worst["team_id"])),
            },
        ]
    )
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.diverging_bars(
                lk,
                "chance_totale",
                "team_name",
                team_id,
                "Réussite totale (points pris − points mérités)",
                low="chance_ic90_bas",
                high="chance_ic90_haut",
                x_title="Points",
            ),
            height=440,
        )
        how(["chance_decomposition", "bootstrap"], meta)
    with right:
        charts.show(
            charts.stacked_components(
                lk,
                [("chance_calendrier", "Calendrier"), ("chance_conversion", "Conversion")],
                team_id,
                "D'où vient la réussite ?",
                "Points",
            ),
            height=440,
        )
        st.caption(
            "Calendrier : avoir croisé ses adversaires un jour sans. Conversion : ce que la mécanique MPG "
            "(buts MPG, arrêts, Rotaldos) a donné ou repris à notes égales."
        )


def _other_measures(a: Analysis, team_id: int) -> None:
    meta = a.meta
    lk = a.luck
    with st.expander("Les autres mesures"):
        st.caption(
            "Ces mesures regardent la réussite sous d'autres angles. Elles complètent la lecture, elles ne la remplacent "
            "pas."
        )
        section("Le calendrier a-t-il aidé ?")
        summary, totals = _simulations(meta["saison"], a.team_match, meta["bande_nul"], meta["n_sim"])
        team_ids = summary["team_id"].astype(int).tolist()
        real = lk.set_index("team_id")["pts_regle"]
        charts.show(charts.sim_distribution(totals, team_ids, a.league.team_names, real, team_id))
        _method(["calendrier_permute"], meta)

        section("Les buts et les adversaires")
        left, right = st.columns([1, 1.2], gap="medium")
        with left:
            charts.show(
                charts.diverging_bars(
                    lk,
                    "chance_pythagore",
                    "team_name",
                    team_id,
                    "Points pris − points attendus d'après les buts",
                    x_title="Points",
                )
            )
            _method(["pythagore"], meta)
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
            _method(["sur_regime_adv"], meta)

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
                "indice_chance": st.column_config.NumberColumn(
                    "Indice de chance",
                    format="%+.2f",
                    help="Positif = chanceux. Il combine la réussite totale, les points pris face aux points attendus "
                    "d'après les buts, et le niveau des adversaires croisés.",
                ),
                "pts": "Pts",
                "xpts_allplay": st.column_config.NumberColumn(
                    "Points mérités",
                    format="%.1f",
                    help="Ce que tes notes auraient rapporté contre toutes les équipes de la journée",
                ),
                "pts_regle": st.column_config.NumberColumn(
                    "Pts à la note", help="Points selon la règle de note, vrais adversaires"
                ),
                "chance_totale": st.column_config.NumberColumn("Chance totale", format="%+.1f"),
                "chance_calendrier": st.column_config.NumberColumn("dont calendrier", format="%+.1f"),
                "chance_conversion": st.column_config.NumberColumn("dont conversion", format="%+.1f"),
                "percentile_calendrier": st.column_config.ProgressColumn(
                    "Facilité du calendrier",
                    min_value=0,
                    max_value=100,
                    format="%.0f",
                    help="De 0 (calendrier très dur) à 100 (très facile) : part des calendriers tirés au hasard qui "
                    "auraient rapporté moins de points.",
                ),
                "xpts_pythagore": st.column_config.NumberColumn("Points attendus d'après les buts", format="%.1f"),
                "sur_regime_adv_moy": st.column_config.NumberColumn(
                    "Adversaires au-dessus de leur niveau",
                    format="%+.2f",
                    help="Positif : les adversaires ont joué mieux que d'habitude contre cette équipe.",
                ),
                "buts_mpg_pour": "Buts MPG pour",
                "buts_mpg_contre": "Buts MPG contre",
                "csc_pour": "CSC reçus",
                "rotaldos_adverses": "Rotaldos adverses",
                "suarez_subis": "Suarez subis",
                "victoires_1but": "V d'un but",
                "defaites_1but": "D d'un but",
            },
        )
        _method(["indice_chance"], meta)


def render(a: Analysis, team_id: int) -> None:
    volet_title(
        "Qui a eu de la réussite ?",
        "On compare les points pris à ceux que le niveau de jeu (les notes) aurait dû rapporter, puis on sépare "
        "la chance de calendrier de la chance de conversion.",
    )
    _head(a, team_id)
    _league(a, team_id)
    _other_measures(a, team_id)
