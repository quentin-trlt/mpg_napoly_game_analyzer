import re
from pathlib import Path

import streamlit as st

from app import charts
from app.components import callout, empty_state, how, section, table_height, volet_title
from mpg.analysis import Analysis
from mpg.mercato import ALT_WEIGHTS, COMPONENT_LABELS, DEFAULT_WEIGHTS, mercato_ranking

CONTENT = Path(__file__).resolve().parents[2] / "content" / "analyse_mercato.md"
CUSTOM = "Personnalisé"
COMPONENTS = list(DEFAULT_WEIGHTS)
SHORT_LABELS = {
    "rendement": "Rendement",
    "prix": "Prix",
    "fiabilite": "Fiabilité",
    "profondeur": "Profondeur",
    "risque": "Diversif.",
    "equilibre": "Équilibre",
}


GENERIC_SCENARIOS = ("par défaut", "poids égaux")
HEAVY_WEIGHT = 0.3
INCOMPLETE = "effectif de fin de saison incomplet : rang non significatif"


def _components(caps) -> list[str]:
    """Composantes calculables : « prix » exige la cote MPG, « fiabilité » les statistiques de Premier League."""
    missing = {"prix": not caps.cote, "fiabilite": not caps.stats_pl}
    return [c for c in DEFAULT_WEIGHTS if not missing.get(c, False)]


def _usable_scenarios(components: list[str]) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Pondérations restreintes aux composantes calculables, et noms des scénarios écartés.

    Un scénario spécialisé qui perdrait une composante pesant au moins 30 % est écarté : il ne porterait plus son nom.
    """
    usable, dropped = {}, []
    for name, weights in ALT_WEIGHTS.items():
        kept = {k: w for k, w in weights.items() if k in components}
        lost_heavy = any(w >= HEAVY_WEIGHT for k, w in weights.items() if k not in kept)
        if lost_heavy and name not in GENERIC_SCENARIOS:
            dropped.append(name)
        else:
            usable[name] = kept
    return usable, dropped


def _weights_ui(scenarios: dict[str, dict[str, float]], components: list[str], season: str) -> dict[str, float]:
    default = scenarios["par défaut"]
    choice = st.segmented_control(
        "Pondération",
        options=[*scenarios, CUSTOM],
        default="par défaut",
        required=True,
        key=f"merc_scenario_{season}",
    )
    if choice != CUSTOM:
        w = scenarios[choice]
        st.caption("Poids : " + ", ".join(f"{COMPONENT_LABELS[k]} {v / sum(w.values()):.0%}" for k, v in w.items()))
        return w
    cols = st.columns(len(components))
    weights = {}
    for col, c in zip(cols, components):
        with col:
            weights[c] = st.slider(
                COMPONENT_LABELS[c], 0, 100, int(DEFAULT_WEIGHTS[c] * 100), step=5, key=f"mw_{c}_{season}"
            )
    if sum(weights.values()) == 0:
        st.warning("Tous les poids sont à zéro : retour à la pondération par défaut.")
        return default
    return weights


def _read_analysis() -> tuple[int | None, str]:
    if not CONTENT.exists():
        return None, ""
    text = CONTENT.read_text(encoding="utf-8")
    m = re.match(r"<!--\s*journee:\s*(\d+)\s*-->\s*", text)
    return (int(m.group(1)), text[m.end() :]) if m else (None, text)


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    caps = meta["capacites"]
    season = meta["saison"]
    components = _components(caps)
    scenarios, dropped = _usable_scenarios(components)
    volet_title(
        "Le classement des mercatos",
        "Six composantes, plusieurs pondérations possibles, et une lecture équipe par équipe."
        if len(components) == len(DEFAULT_WEIGHTS)
        else f"{len(components)} composantes sur {len(DEFAULT_WEIGHTS)}, plusieurs pondérations possibles.",
    )
    if len(components) < len(DEFAULT_WEIGHTS):
        absent = ", ".join(COMPONENT_LABELS[c].lower() for c in DEFAULT_WEIGHTS if c not in components)
        callout(
            f"Les données de cette saison ne permettent pas de calculer : {absent}. Le classement ne repose que sur "
            "les autres composantes.",
            warn=True,
        )
    if caps.effectif_fin_saison:
        callout(
            "Les effectifs sont ceux de fin de saison : un joueur parti en cours de route n'y figure plus. Une équipe "
            "qui a perdu des joueurs semble donc avoir moins dépensé ou mieux dépensé : le classement peut être "
            "faussé.",
            warn=True,
        )

    with st.container(border=True):
        weights = _weights_ui(scenarios, components, season)
    m, ranks = mercato_ranking(a.player_value, a.favourites.set_index("team_id")["cote_banc"], weights)
    if dropped:
        ranks = ranks.drop(columns=dropped, errors="ignore")
        scenario_ranks = ranks.drop(columns="team_id").set_index(ranks["team_id"])
        m["rang_min"] = m["team_id"].map(scenario_ranks.min(axis=1))
        m["rang_max"] = m["team_id"].map(scenario_ranks.max(axis=1))
    m["team_name"] = m["team_id"].map(a.league.team_names)
    incomplete = set(a.favourites.loc[a.favourites["effectif_incomplet"], "team_id"])
    m["remarque"] = m["team_id"].map(lambda t: INCOMPLETE if t in incomplete else "")
    ranks.insert(1, "team_name", ranks["team_id"].map(a.league.team_names))

    if incomplete:
        names = ", ".join(m.loc[m["team_id"].isin(incomplete), "team_name"])
        callout(
            f"{names} : {INCOMPLETE}. Cette équipe n'a pas assez de joueurs aux bons postes pour composer un 11 : "
            "ne tire aucune conclusion de son rang.",
            warn=True,
        )

    stable = m[m["rang_max"] - m["rang_min"] <= 2]["team_name"].tolist()
    callout(
        "Rangs stables quelle que soit l'hypothèse (écart ≤ 2 places) : "
        + (", ".join(stable) if stable else "aucun")
        + ". Pour les autres, le classement dépend de ce qu'on valorise."
    )

    section("Classement")
    table = m[
        [
            "rang",
            "team_name",
            "score",
            "rang_min",
            "rang_max",
            "surpaiement_median_x",
            "residu_moy_tronque",
            "disponibilite_ponderee",
            "gini_enchere",
            "remarque",
        ]
    ].copy()
    table["plage"] = (
        table["rang_min"].astype(int).astype(str) + "e – " + table["rang_max"].astype(int).astype(str) + "e"
    )
    order = [
        "rang",
        "team_name",
        "score",
        "plage",
        "residu_moy_tronque",
        "surpaiement_median_x",
        "disponibilite_ponderee",
        "gini_enchere",
        "remarque",
    ]
    hidden = {
        *(() if caps.cote else ("surpaiement_median_x",)),
        *(() if caps.stats_pl else ("disponibilite_ponderee",)),
        *(() if incomplete else ("remarque",)),
    }
    st.dataframe(
        table.drop(columns=["rang_min", "rang_max", *hidden]),
        hide_index=True,
        column_order=[c for c in order if c not in hidden],
        column_config={
            "rang": st.column_config.NumberColumn("#", width="small"),
            "team_name": "Équipe",
            "score": st.column_config.NumberColumn("Score", format="%+.2f"),
            "plage": st.column_config.TextColumn("Plage de rangs", help="Rang minimal et maximal selon les scénarios"),
            "residu_moy_tronque": st.column_config.NumberColumn("Rendement vs prix", format="%+.3f"),
            "surpaiement_median_x": st.column_config.NumberColumn("Surpaiement médian", format="× %.2f"),
            "disponibilite_ponderee": st.column_config.ProgressColumn(
                "Fiabilité", min_value=0, max_value=1, format="percent"
            ),
            "gini_enchere": st.column_config.NumberColumn("Gini", format="%.2f"),
            "remarque": "Remarque",
        },
        height=table_height(len(table)),
    )
    how("score_mercato", meta)

    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        charts.show(charts.component_heatmap(m, components, SHORT_LABELS))
    with right:
        charts.show(charts.rank_ranges(m, "rang_min", "rang_max", "rang", team_id, "Robustesse du classement"))
    with st.expander("Rang de chaque équipe dans chaque scénario"):
        st.dataframe(ranks.drop(columns="team_id"), hide_index=True)

    section("Lecture équipe par équipe")
    if not meta["saison_en_cours"]:
        empty_state(
            "Analyse rédigée non affichée",
            f"Le texte rédigé porte sur la saison en cours et ne correspond pas à la saison {season}.",
        )
        return
    gw, text = _read_analysis()
    if not text:
        st.info("L'analyse rédigée n'est pas encore disponible.")
        return
    if gw is not None and gw < meta["derniere_journee"]:
        callout(
            f"Cette analyse a été rédigée après la journée {gw}. Les données vont maintenant jusqu'à la journée "
            f"{meta['derniere_journee']} : les chiffres des graphiques sont à jour, le texte ne l'est peut-être plus.",
            warn=True,
        )
    else:
        st.caption(f"Analyse rédigée à partir des données de la journée {gw}, avec la pondération par défaut.")
    st.markdown(text)
