import streamlit as st

st.set_page_config(
    page_title="Napoly Game · Analyse MPG",
    page_icon="assets/icon.svg",
    layout="wide",
    initial_sidebar_state="auto",
)

from app import theme  # noqa: E402
from app.navigation import register  # noqa: E402
from app.pages import joueurs_mercato, ma_journee, mon_equipe, page_ligue, pourquoi, pronostics  # noqa: E402
from app.state import coach_selector, get_analysis, season_selector  # noqa: E402
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


def page(render, title: str, icon: str, url: str, default: bool = False) -> st.Page:
    return st.Page(
        lambda: render(analysis, team_id), title=title, icon=f":material/{icon}:", url_path=url, default=default
    )


pages = {
    "mon-equipe": page(mon_equipe, "Mon équipe", "shield", "mon-equipe"),
    "ligue": page(page_ligue, "Ligue", "leaderboard", "ligue", default=not season.current),
    "pronostics": page(pronostics, "Pronostics", "query_stats", "pronostics"),
    "pourquoi": page(pourquoi, "Pourquoi ce classement ?", "balance", "pourquoi"),
    "joueurs-mercato": page(joueurs_mercato, "Joueurs et mercato", "payments", "joueurs-mercato"),
}
my_season = [pages["mon-equipe"]]
if season.current:
    pages["ma-journee"] = page(ma_journee, "Ma journée", "today", "ma-journee", default=True)
    my_season.insert(0, pages["ma-journee"])
register(pages)

nav = st.navigation(
    pages={
        "Ma saison": my_season,
        "La ligue": [pages["ligue"], pages["pronostics"], pages["pourquoi"], pages["joueurs-mercato"]],
    },
)
nav.run()
