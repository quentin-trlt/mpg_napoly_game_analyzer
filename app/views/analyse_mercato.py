import re
from pathlib import Path

import streamlit as st

from app import charts
from app.components import callout, hero, how, section, table_height
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


def _weights_ui() -> dict[str, float]:
    choice = st.segmented_control(
        "Pondération", options=[*ALT_WEIGHTS, CUSTOM], default="par défaut", required=True, key="merc_scenario"
    )
    if choice != CUSTOM:
        w = ALT_WEIGHTS[choice]
        st.caption("Poids : " + ", ".join(f"{COMPONENT_LABELS[k]} {v / sum(w.values()):.0%}" for k, v in w.items()))
        return w
    cols = st.columns(len(COMPONENTS))
    weights = {}
    for col, c in zip(cols, COMPONENTS):
        with col:
            weights[c] = st.slider(COMPONENT_LABELS[c], 0, 100, int(DEFAULT_WEIGHTS[c] * 100), step=5, key=f"mw_{c}")
    if sum(weights.values()) == 0:
        st.warning("Tous les poids sont à zéro : retour à la pondération par défaut.")
        return DEFAULT_WEIGHTS
    return weights


def _read_analysis() -> tuple[int | None, str]:
    if not CONTENT.exists():
        return None, ""
    text = CONTENT.read_text(encoding="utf-8")
    m = re.match(r"<!--\s*journee:\s*(\d+)\s*-->\s*", text)
    return (int(m.group(1)), text[m.end() :]) if m else (None, text)


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    hero(
        "Analyse des mercatos",
        "Le classement des mercatos",
        "Six composantes, plusieurs pondérations possibles, et une lecture équipe par équipe.",
    )

    with st.container(border=True):
        weights = _weights_ui()
    m, ranks = mercato_ranking(a.player_value, a.favourites.set_index("team_id")["cote_banc"], weights)
    m["team_name"] = m["team_id"].map(a.league.team_names)
    ranks.insert(1, "team_name", ranks["team_id"].map(a.league.team_names))

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
            "joueur_plus_cher",
            "enchere_max",
            "surpaiement_median_x",
            "residu_moy_tronque",
            "disponibilite_ponderee",
            "gini_enchere",
        ]
    ].copy()
    table["plage"] = table["rang_min"].astype(str) + "e – " + table["rang_max"].astype(str) + "e"
    st.dataframe(
        table.drop(columns=["rang_min", "rang_max"]),
        hide_index=True,
        column_order=[
            "rang",
            "team_name",
            "score",
            "plage",
            "residu_moy_tronque",
            "surpaiement_median_x",
            "disponibilite_ponderee",
            "gini_enchere",
            "joueur_plus_cher",
            "enchere_max",
        ],
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
            "joueur_plus_cher": "Plus gros achat",
            "enchere_max": st.column_config.NumberColumn("Prix", format="%d M€"),
        },
        height=table_height(len(table)),
    )
    how("score_mercato", meta)

    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        charts.show(charts.component_heatmap(m, COMPONENTS, SHORT_LABELS))
    with right:
        charts.show(charts.rank_ranges(m, "rang_min", "rang_max", "rang", team_id, "Robustesse du classement"))
    with st.expander("Rang de chaque équipe dans chaque scénario"):
        st.dataframe(ranks.drop(columns="team_id"), hide_index=True)

    section("Lecture équipe par équipe")
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
