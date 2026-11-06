import streamlit as st

from app import charts
from app.components import callout, hero, how, kpi_row, section
from mpg.analysis import Analysis
from mpg.stats import spearman
from mpg.strength import DEFAULT_WEIGHTS, FEATURE_LABELS, SCENARIOS, strength_index, strength_scenarios

CUSTOM = "Personnalisé"


def _weights_ui() -> dict[str, float]:
    scenario = st.segmented_control(
        "Scénario de pondération", options=[*SCENARIOS, CUSTOM], default="par défaut", required=True, key="fav_scenario"
    )
    if scenario != CUSTOM:
        w = SCENARIOS[scenario]
        st.caption("Poids : " + ", ".join(f"{FEATURE_LABELS[k]} {v / sum(w.values()):.0%}" for k, v in w.items()))
        return w
    st.caption("Choisissez les caractéristiques et leur poids relatif (les poids sont normalisés à 100 %).")
    chosen = st.multiselect(
        "Caractéristiques",
        options=list(FEATURE_LABELS),
        default=list(DEFAULT_WEIGHTS),
        format_func=FEATURE_LABELS.get,
        key="fav_features",
    )
    if not chosen:
        st.warning("Sélectionnez au moins une caractéristique : retour à la pondération par défaut.")
        return DEFAULT_WEIGHTS
    cols = st.columns(min(4, len(chosen)))
    weights = {}
    for i, feat in enumerate(chosen):
        with cols[i % len(cols)]:
            weights[feat] = st.slider(
                FEATURE_LABELS[feat], 0, 100, int(DEFAULT_WEIGHTS.get(feat, 0.25) * 100), step=5, key=f"w_{feat}"
            )
    if sum(weights.values()) == 0:
        st.warning("Tous les poids sont à zéro : retour à la pondération par défaut.")
        return DEFAULT_WEIGHTS
    return weights


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    hero(
        "Favoris vs réalité",
        "Qui aurait dû gagner sur le papier ?",
        "L'indice de force résume l'effectif sans regarder les résultats. On compare le rang qu'il prédit au rang réel.",
    )

    with st.container(border=True):
        weights = _weights_ui()

    fav = a.feature_set
    pts = fav.set_index("team_id")["pts"]
    idx = strength_index(fav, weights)
    idx["ecart_rang"] = idx["rang_attendu"] - idx["rang"]
    scenarios = {**SCENARIOS, CUSTOM: weights}
    ranks, fit = strength_scenarios(fav, pts, scenarios)
    ranks = ranks.set_index("team_id")
    idx["rang_min"] = idx["team_id"].map(ranks.min(axis=1))
    idx["rang_max"] = idx["team_id"].map(ranks.max(axis=1))
    corr = spearman(idx.set_index("team_id")["indice_force"], pts)

    fav_team = idx.sort_values("rang_attendu").iloc[0]
    over = idx.sort_values("ecart_rang").iloc[-1]
    under = idx.sort_values("ecart_rang").iloc[0]
    me = idx.set_index("team_id").loc[team_id]
    kpi_row(
        [
            {
                "label": "Favori du scénario",
                "value": fav_team["team_name"],
                "small": True,
                "sub": f"réellement {int(fav_team['rang'])}e",
            },
            {
                "label": "Plus grosse surperformance",
                "value": over["team_name"],
                "small": True,
                "sub": f"attendu {int(over['rang_attendu'])}e → {int(over['rang'])}e",
            },
            {
                "label": "Plus grosse sous-performance",
                "value": under["team_name"],
                "small": True,
                "sub": f"attendu {int(under['rang_attendu'])}e → {int(under['rang'])}e",
            },
            {
                "label": me["team_name"],
                "value": f"{int(me['rang_attendu'])}e attendu",
                "sub": f"{int(me['rang'])}e en vrai, entre {int(me['rang_min'])}e et {int(me['rang_max'])}e "
                "selon le scénario",
                "me": True,
            },
        ]
    )
    power = (
        f"Pouvoir prédictif du scénario : ρ = {corr.rho:+.2f} avec les points (p = {corr.p_value:.2f}, n = {corr.n})."
    )
    if corr.p_value >= 0.05:
        callout(
            f"{power} La force de l'effectif n'explique donc pas significativement le classement après "
            f"{meta['derniere_journee']} journées. À ce stade, les écarts relèvent autant des absences et du hasard "
            "que de la qualité du mercato.",
            warn=True,
        )
    else:
        callout(power)

    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.dumbbell_ranks(
                idx, "rang_attendu", "rang", "Rang attendu", "Rang réel", team_id, "Rang attendu et rang réel"
            )
        )
        how(["indice_force", "ecart_rang"], meta)
    with right:
        charts.show(
            charts.rank_ranges(
                idx.rename(columns={"rang_attendu": "rang_cur"}),
                "rang_min",
                "rang_max",
                "rang_cur",
                team_id,
                "Sensibilité : rang attendu selon les scénarios",
            )
        )
        how("scenarios_force", meta)

    section(
        "Ce qui compte vraiment",
        "Corrélation de chaque caractéristique avec les points, toutes équipes confondues. "
        "Les barres pâles ne sont pas significatives (p ≥ 0,05), l'astérisque marque p < 0,05.",
    )
    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        corrs = {k: spearman(fav.set_index("team_id")[k], pts) for k in FEATURE_LABELS if k in fav}
        corrs["cote_11_aligne_moy"] = spearman(a.favourites.set_index("team_id")["cote_11_aligne_moy"], pts)
        labels = {**FEATURE_LABELS, "cote_11_aligne_moy": "Cote moyenne du 11 réellement aligné"}
        charts.show(charts.corr_bars(corrs, labels))
        how("spearman", meta)
    with right:
        fit_df = fit.assign(rho=fit["rho"].round(2), p_value=fit["p_value"].round(3))
        st.dataframe(
            fit_df,
            hide_index=True,
            column_config={
                "scenario": "Scénario",
                "rho": st.column_config.NumberColumn("ρ avec les points", format="%+.2f"),
                "p_value": st.column_config.NumberColumn("p", format="%.3f"),
                "n": None,
            },
        )
        st.caption("Ne retenez pas le scénario le mieux corrélé : avec 10 équipes, il gagnerait en partie par hasard.")

    section("Caractéristiques des effectifs")
    shown = [
        "team_name",
        "indice_force",
        "rang_attendu",
        "rang",
        "valeur_effectif_meur",
        "cote_11_max",
        "formation_11_max",
        "cote_banc",
        "note_reelle_11",
        "taux_titu_11",
        "disponibilite_effectif",
        "ga_saison",
        "nb_joueurs",
        "nb_indisponibles",
    ]
    table = idx
    st.dataframe(
        table.sort_values("rang_attendu")[shown + ["cote_11_aligne_moy", "taux_utilisation_11"]],
        hide_index=True,
        column_config={
            "team_name": "Équipe",
            "indice_force": st.column_config.NumberColumn("Indice", format="%+.2f"),
            "rang_attendu": st.column_config.NumberColumn("Rang attendu"),
            "rang": st.column_config.NumberColumn("Rang réel"),
            "valeur_effectif_meur": st.column_config.NumberColumn("Valeur effectif", format="%d M€"),
            "cote_11_max": st.column_config.NumberColumn("Cote meilleur 11", format="%d M€"),
            "formation_11_max": "Formation",
            "cote_banc": st.column_config.NumberColumn("Cote banc", format="%d M€"),
            "note_reelle_11": st.column_config.NumberColumn("Note PL du 11", format="%.2f"),
            "taux_titu_11": st.column_config.ProgressColumn(
                "Titu. PL du 11", min_value=0, max_value=1, format="percent"
            ),
            "disponibilite_effectif": st.column_config.ProgressColumn(
                "Taux de jeu effectif", min_value=0, max_value=1, format="percent"
            ),
            "ga_saison": st.column_config.NumberColumn("G+A PL", format="%d"),
            "nb_joueurs": "Joueurs",
            "nb_indisponibles": "Indispos",
            "cote_11_aligne_moy": st.column_config.NumberColumn("Cote 11 aligné (moy.)", format="%.0f M€"),
            "taux_utilisation_11": st.column_config.ProgressColumn(
                "Utilisation du 11", min_value=0, max_value=1, format="percent"
            ),
        },
    )
    how("cote_11_aligne", meta)
