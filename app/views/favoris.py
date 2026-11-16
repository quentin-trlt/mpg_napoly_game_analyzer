import numpy as np
import pandas as pd
import streamlit as st

from app import charts
from app.components import callout, empty_state, how, kpi_row, section, volet_title
from mpg.analysis import Analysis
from mpg.stats import spearman
from mpg.strength import (
    DEFAULT_WEIGHTS,
    FEATURE_LABELS,
    SCENARIOS,
    available_features,
    strength_index,
    strength_scenarios,
)

CUSTOM = "Personnalisé"
DEFAULT_SCENARIO = "par défaut"
INCOMPLETE = "effectif de fin de saison incomplet : rang attendu non significatif"


def _price_wording(text: str, prix: str) -> str:
    """Remplace « cote » par « prix d'enchère » quand la force se calcule sur les enchères."""
    return text if prix == "cote" else text.replace("Cote", "Prix d'enchère").replace("cotes", "prix d'enchère")


def _usable_features(fav: pd.DataFrame, stats_pl: bool) -> list[str]:
    """Caractéristiques réellement renseignées. `ga_saison` vaut 0 (et non vide) sans statistiques PL : on l'écarte."""
    return [c for c in available_features(fav) if stats_pl or c != "ga_saison"]


def _usable_scenarios(features: list[str]) -> dict[str, dict[str, float]]:
    """Scénarios dont toutes les caractéristiques existent ; le scénario par défaut perd celles qui manquent."""
    usable = {}
    for name, weights in SCENARIOS.items():
        kept = {k: w for k, w in weights.items() if k in features}
        if kept == weights or (name == DEFAULT_SCENARIO and kept):
            usable[name] = kept
    return usable


def _weights_ui(
    scenarios: dict[str, dict[str, float]], features: list[str], labels: dict[str, str], season: str
) -> dict[str, float]:
    default = scenarios.get(DEFAULT_SCENARIO) or {features[0]: 1.0}
    scenario = st.segmented_control(
        "Scénario de pondération",
        options=[*scenarios, CUSTOM],
        default=next(iter(scenarios), CUSTOM),
        required=True,
        key=f"fav_scenario_{season}",
    )
    if scenario != CUSTOM:
        w = scenarios[scenario]
        st.caption("Poids : " + ", ".join(f"{labels[k]} {v / sum(w.values()):.0%}" for k, v in w.items()))
        if scenario == DEFAULT_SCENARIO and w != SCENARIOS[DEFAULT_SCENARIO]:
            lost = ", ".join(labels[k].lower() for k in SCENARIOS[DEFAULT_SCENARIO] if k not in w)
            st.caption(
                f"Sur cette saison, ces données n'existent pas ({lost}) : leur poids est réparti sur les autres."
            )
        return w
    st.caption("Choisis les caractéristiques et leur poids relatif (les poids sont normalisés à 100 %).")
    chosen = st.multiselect(
        "Caractéristiques",
        options=features,
        default=list(default),
        format_func=labels.get,
        key=f"fav_features_{season}",
    )
    if not chosen:
        st.warning("Sélectionne au moins une caractéristique : retour à la pondération par défaut.")
        return default
    cols = st.columns(min(4, len(chosen)))
    weights = {}
    for i, feat in enumerate(chosen):
        with cols[i % len(cols)]:
            weights[feat] = st.slider(
                labels[feat], 0, 100, int(DEFAULT_WEIGHTS.get(feat, 0.25) * 100), step=5, key=f"w_{feat}_{season}"
            )
    if sum(weights.values()) == 0:
        st.warning("Tous les poids sont à zéro : retour à la pondération par défaut.")
        return default
    return weights


def _rank_text(me: pd.Series) -> str:
    if me["effectif_incomplet"]:
        return INCOMPLETE
    span = (
        f", entre {int(me['rang_min'])}e et {int(me['rang_max'])}e selon le scénario"
        if pd.notna(me["rang_min"])
        else ""
    )
    return f"{int(me['rang'])}e en vrai{span}"


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    caps = meta["capacites"]
    prix = meta["prix"]
    season = meta["saison"]
    fav = a.feature_set
    labels = {k: _price_wording(v, prix) for k, v in FEATURE_LABELS.items()}
    features = _usable_features(fav, caps.stats_pl)
    scenarios = _usable_scenarios(features)
    volet_title(
        "Qui aurait dû gagner sur le papier ?",
        "L'indice de force résume l'effectif sans regarder les résultats. On compare le rang qu'il prédit au rang réel.",
    )
    if prix != "cote":
        callout(
            "MPG n'affiche plus les cotes d'une saison passée : la force des effectifs se calcule ici sur les prix "
            "d'enchère."
        )
    if caps.effectif_fin_saison:
        callout(
            "Les effectifs sont ceux de fin de saison : les joueurs partis en cours de route n'y figurent plus, "
            "ce qui peut fausser la force de certaines équipes.",
            warn=True,
        )

    with st.container(border=True):
        weights = _weights_ui(scenarios, features, labels, season)

    pts = fav.set_index("team_id")["pts"]
    idx = strength_index(fav, weights)
    idx["ecart_rang"] = idx["rang_attendu"] - idx["rang"]
    incomplete = idx["effectif_incomplet"]
    complete = idx[~incomplete]
    scenarios = {**scenarios, CUSTOM: weights}
    ranks, _ = strength_scenarios(fav, pts, scenarios)
    ranks = ranks.set_index("team_id")
    has_ranges = not ranks.empty and len(ranks.columns) > 0
    idx["rang_min"] = idx["team_id"].map(ranks.min(axis=1)) if has_ranges else np.nan
    idx["rang_max"] = idx["team_id"].map(ranks.max(axis=1)) if has_ranges else np.nan
    _, fit = strength_scenarios(fav[~fav["effectif_incomplet"]], pts, scenarios)
    corr = spearman(complete.set_index("team_id")["indice_force"], pts)

    if incomplete.any():
        names = ", ".join(idx.loc[incomplete, "team_name"])
        callout(
            f"{names} : {INCOMPLETE}. Cette équipe n'a pas assez de joueurs aux bons postes pour composer un 11 : "
            "son rang attendu est le dernier par construction, pas à cause de son niveau. Elle est écartée des "
            "comparaisons ci-dessous.",
            warn=True,
        )

    fav_team = complete.sort_values("rang_attendu").iloc[0]
    over = complete.sort_values("ecart_rang").iloc[-1]
    under = complete.sort_values("ecart_rang").iloc[0]
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
                "value": "rang attendu non significatif"
                if me["effectif_incomplet"]
                else f"{int(me['rang_attendu'])}e attendu",
                "sub": _rank_text(me),
                "me": True,
            },
        ]
    )
    power = (
        f"Pouvoir prédictif du scénario : ρ = {corr.rho:+.2f} avec les points (p = {corr.p_value:.2f}, n = {corr.n})."
        if pd.notna(corr.rho)
        else "Pouvoir prédictif du scénario : non calculable avec ces équipes."
    )
    if pd.isna(corr.rho) or corr.p_value >= 0.05:
        horizon = f"après {meta['derniere_journee']} journées" if meta["saison_en_cours"] else "sur la saison"
        stade = "À ce stade" if meta["saison_en_cours"] else "Sur cette saison"
        callout(
            f"{power} La force de l'effectif n'explique donc pas significativement le classement {horizon}. "
            f"{stade}, les écarts relèvent autant des absences et du hasard que de la qualité du mercato.",
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
        if has_ranges:
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
        else:
            empty_state(
                "Sensibilité : rang attendu selon les scénarios",
                "Aucun scénario ne peut être calculé avec les données de cette saison.",
            )
        how("scenarios_force", meta)

    section(
        "Ce qui compte vraiment",
        "Corrélation de chaque caractéristique avec les points, toutes équipes confondues. "
        "Les barres pâles ne sont pas significatives (p ≥ 0,05), l'astérisque marque p < 0,05.",
    )
    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        full = fav[~fav["effectif_incomplet"]].set_index("team_id")
        corrs = {k: spearman(full[k], pts) for k in features}
        corrs["cote_11_aligne_moy"] = spearman(full["cote_11_aligne_moy"], pts)
        corr_labels = {**labels, "cote_11_aligne_moy": _price_wording("Cote moyenne du 11 réellement aligné", prix)}
        if any(pd.notna(c.rho) for c in corrs.values()):
            charts.show(charts.corr_bars(corrs, corr_labels))
        else:
            empty_state(
                "Quelle caractéristique d'effectif suit les points ?",
                "Aucune caractéristique ne varie assez d'une équipe à l'autre pour être comparée aux points.",
            )
        how("spearman", meta)
    with right:
        if fit.empty:
            empty_state("Scénarios", "Aucun scénario n'a pu être comparé aux points.")
        else:
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
        st.caption(
            f"Ne retiens pas le scénario le mieux corrélé : avec {len(fav)} équipes, il gagnerait en partie par hasard."
        )

    section("Caractéristiques des effectifs")
    idx["remarque"] = np.where(idx["effectif_incomplet"], INCOMPLETE, "")
    config = {
        "team_name": "Équipe",
        "indice_force": st.column_config.NumberColumn("Indice", format="%+.2f"),
        "rang_attendu": st.column_config.NumberColumn("Rang attendu"),
        "rang": st.column_config.NumberColumn("Rang réel"),
        "valeur_effectif_meur": st.column_config.NumberColumn("Valeur effectif", format="%d M€"),
        "cote_11_max": st.column_config.NumberColumn(_price_wording("Cote meilleur 11", prix), format="%d M€"),
        "formation_11_max": "Formation",
        "cote_banc": st.column_config.NumberColumn(_price_wording("Cote banc", prix), format="%d M€"),
        "note_reelle_11": st.column_config.NumberColumn("Note PL du 11", format="%.2f"),
        "taux_titu_11": st.column_config.ProgressColumn("Titu. PL du 11", min_value=0, max_value=1, format="percent"),
        "disponibilite_effectif": st.column_config.ProgressColumn(
            "Taux de jeu effectif", min_value=0, max_value=1, format="percent"
        ),
        "ga_saison": st.column_config.NumberColumn("G+A PL", format="%d"),
        "nb_joueurs": "Joueurs",
        "nb_indisponibles": "Indispos",
        "cote_11_aligne_moy": st.column_config.NumberColumn(
            _price_wording("Cote 11 aligné (moy.)", prix), format="%.0f M€"
        ),
        "taux_utilisation_11": st.column_config.ProgressColumn(
            "Utilisation du 11", min_value=0, max_value=1, format="percent"
        ),
        "remarque": "Remarque",
    }
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
        "cote_11_aligne_moy",
        "taux_utilisation_11",
    ]
    columns = [c for c in shown if c in features or c not in FEATURE_LABELS]
    if not caps.stats_pl:
        columns.remove("nb_indisponibles")
    if incomplete.any():
        columns.append("remarque")
    st.dataframe(
        idx.sort_values("rang_attendu")[columns],
        hide_index=True,
        column_config={c: config[c] for c in columns},
    )
    how("cote_11_aligne", meta)
