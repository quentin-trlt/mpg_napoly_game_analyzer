import streamlit as st

st.set_page_config(
    page_title="Napoly Game · Analyse MPG",
    page_icon="assets/icon.svg",
    layout="wide",
    initial_sidebar_state="auto",
)

from app import theme  # noqa: E402
from app.state import coach_selector, get_analysis, season_selector  # noqa: E402
from app.views import (  # noqa: E402
    analyse_mercato,
    chance,
    coaching,
    equipe,
    favoris,
    joueurs,
    ligue,
    matchs,
    mercato,
    predictions,
    suivi,
)
from mpg.loader import DataSchemaError  # noqa: E402

theme.inject_css()
st.logo("assets/logo.svg", size="large", icon_image="assets/icon.svg")

with st.sidebar:
    season = season_selector()

try:
    analysis = get_analysis(season.path)
except DataSchemaError as exc:
    st.error(f"Les fichiers de `{season.path.name}/` ne sont pas au format attendu : {exc}")
    st.stop()

with st.sidebar:
    team_id = coach_selector(analysis, season)
    if analysis.meta["saison_en_cours"]:
        st.caption(
            f"Données jusqu'à la J{analysis.meta['derniere_journee']}, "
            f"{analysis.meta['matchs_joues']} matchs joués sur {len(analysis.league.fixtures)}"
        )
    else:
        st.caption(f"Saison terminée : {analysis.meta['nb_journees']} journées, {analysis.meta['matchs_joues']} matchs")


def page(module, title: str, icon: str, url: str, default: bool = False) -> st.Page:
    return st.Page(
        lambda: module.render(analysis, team_id), title=title, icon=f":material/{icon}:", url_path=url, default=default
    )


nav = st.navigation(
    pages={
        "La ligue": [
            page(ligue, "Ligue", "leaderboard", "ligue", default=True),
            page(matchs, "Matchs et calendrier", "calendar_month", "matchs"),
            page(equipe, "Fiche équipe", "shield", "equipe"),
            page(predictions, "Prédictions", "query_stats", "predictions"),
            page(suivi, "Suivi des pronostics", "fact_check", "suivi"),
        ],
        "Analyses": [
            page(favoris, "Favoris vs réalité", "balance", "favoris"),
            page(chance, "Chance", "casino", "chance"),
            page(coaching, "Coaching", "sports", "coaching"),
            page(joueurs, "Joueurs", "person_search", "joueurs"),
        ],
        "Mercato": [
            page(mercato, "Mercato", "payments", "mercato"),
            page(analyse_mercato, "Analyse des mercatos", "military_tech", "analyse-mercato"),
        ],
    },
)
nav.run()
