from pathlib import Path
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from mpg import analysis as analysis_module
from mpg.forecast.evaluation import season_dirs

ENTRYPOINT = Path(__file__).resolve().parent.parent / "streamlit_app.py"
PAGES = {
    "ma_journee": [None],
    "mon_equipe": ["profil", "effectif", "bonus"],
    "page_ligue": ["classement", "matchs"],
    "pronostics": ["journee", "fin-de-saison", "et-si", "fiabilite"],
    "pourquoi": ["favoris", "chance", "coaching"],
    "joueurs_mercato": ["joueurs", "mercato", "analyse-mercato"],
    "palmares": [None],
}
CASES = [(page, volet) for page, volets in PAGES.items() for volet in volets]
SEASONS = list(season_dirs())
POSITIONS = {"premier": 0, "dernier": -1}


def _page(page: str, data_dir: str, position: int) -> None:
    import streamlit as st

    from app import pages
    from app.state import COACH_KEY
    from mpg.analysis import run
    from mpg.seasons import coach_by_team

    a = run(data_dir, n_sim=200)
    team_id = int(a.standings.iloc[position]["team_id"])
    st.session_state[COACH_KEY] = coach_by_team(a.league)[team_id]
    getattr(pages, page)(a, team_id)


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize(("page", "volet"), CASES)
@pytest.mark.parametrize("season", SEASONS)
def test_volet_renders(season, page, volet, position):
    if page == "pronostics" and season != "en cours":
        pytest.skip("saison passée : un seul volet, couvert par test_pronostics.py")
    at = AppTest.from_function(_page, args=(page, str(season_dirs()[season]), POSITIONS[position]), default_timeout=180)
    if volet is not None:
        at.query_params["volet"] = volet
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
    assert not at.get("exception")
    if volet is None:
        assert not at.get("button_group")
    else:
        assert at.get("button_group")[0].value == volet


def _page_without_optional_data(position: int) -> None:
    from dataclasses import replace

    from app import pages
    from mpg.analysis import run

    full = run("data", n_sim=20)
    a = replace(full, league=replace(full.league, club_results=None, fpl_players=None), bonus_remaining=None)
    pages.ma_journee(a, int(a.standings.iloc[position]["team_id"]))


@pytest.mark.parametrize("position", POSITIONS.values())
def test_ma_journee_survives_missing_optional_data(position):
    at = AppTest.from_function(_page_without_optional_data, args=(position,), default_timeout=180).run()
    assert not at.exception
    titles = [s.value for s in at.subheader]
    assert "À savoir avant de valider ta compo" in titles
    assert "Mes bonus" not in titles
    assert "Mes joueurs ce week-end" not in titles


def _entrypoint(**query: str) -> AppTest:
    at = AppTest.from_file(str(ENTRYPOINT), default_timeout=180)
    for key, value in query.items():
        at.query_params[key] = value
    return at.run()


def _sidebar(at: AppTest) -> dict[str, object]:
    return {s.label: s for s in at.sidebar.selectbox}


def test_entrypoint_renders():
    at = _entrypoint()
    assert not at.exception
    selectors = _sidebar(at)
    assert list(selectors) == ["Saison", "Mon équipe"]
    assert selectors["Saison"].value == "2026-2027"
    assert selectors["Saison"].options == ["2026-2027", "2025-2026", "2024-2025"]
    assert selectors["Mon équipe"].value == "Emilinho_"
    assert any(c.value.startswith("Données jusqu'à la J") for c in at.sidebar.caption)


def test_entrypoint_past_season_from_address():
    at = _entrypoint(saison="2024-2025", coach="ketXfentanyl")
    selectors = _sidebar(at)
    assert selectors["Saison"].value == "2024-2025"
    assert selectors["Mon équipe"].value == "ketXfentanyl"
    assert not any("n'a pas joué" in c.value for c in at.sidebar.caption)
    assert any(c.value.startswith("Saison terminée : 14 journées") for c in at.sidebar.caption)


def test_entrypoint_coach_absent_from_season():
    at = _entrypoint(saison="2024-2025", coach="Jiboti")
    selectors = _sidebar(at)
    assert selectors["Mon équipe"].value == "Jiboti"
    assert any("Jiboti n'a pas joué en 2024-2025 : tu vois le champion." == c.value for c in at.sidebar.caption)


def test_entrypoint_default_follows_the_season_leader():
    at = _entrypoint(saison="2024-2025")
    assert _sidebar(at)["Mon équipe"].value == "Victor_RM"


def test_entrypoint_unknown_address_falls_back_to_default():
    at = _entrypoint(saison="1999-2000", coach="inconnu")
    assert not at.exception
    selectors = _sidebar(at)
    assert selectors["Saison"].value == "2026-2027"
    assert selectors["Mon équipe"].value == "Emilinho_"


def test_entrypoint_alias_coach_is_the_same_person():
    at = _entrypoint(coach="vincentprono92")
    assert _sidebar(at)["Mon équipe"].value == "vincentmouly"


def test_entrypoint_chosen_coach_is_in_the_address():
    at = _entrypoint(coach="ketXfentanyl", saison="2025-2026")
    assert _sidebar(at)["Mon équipe"].value == "ketXfentanyl"
    assert at.query_params["coach"] == "ketXfentanyl"
    assert at.query_params["saison"] == "2025-2026"


def test_entrypoint_chosen_coach_survives_a_reload():
    at = _entrypoint(coach="ketXfentanyl", saison="2025-2026")
    at.run()
    assert _sidebar(at)["Mon équipe"].value == "ketXfentanyl"
    assert at.query_params["coach"] == "ketXfentanyl"
    reloaded = _entrypoint(**{"coach": at.query_params["coach"], "saison": at.query_params["saison"]})
    assert _sidebar(reloaded)["Mon équipe"].value == "ketXfentanyl"


def test_entrypoint_chosen_coach_survives_a_season_change():
    at = _entrypoint(coach="ketXfentanyl", saison="2025-2026")
    at.sidebar.selectbox[0].select("2024-2025").run()
    assert not at.exception
    assert _sidebar(at)["Saison"].value == "2024-2025"
    assert _sidebar(at)["Mon équipe"].value == "ketXfentanyl"
    assert at.query_params["coach"] == "ketXfentanyl"


def test_entrypoint_without_coach_follows_the_leader_and_keeps_the_address_clean():
    at = _entrypoint(saison="2024-2025")
    assert _sidebar(at)["Mon équipe"].value == "Victor_RM"
    assert "coach" not in at.query_params
    at.sidebar.selectbox[0].select("2025-2026").run()
    assert _sidebar(at)["Mon équipe"].value != "Victor_RM"
    assert "coach" not in at.query_params


def test_entrypoint_invalid_coach_follows_the_leader_and_is_removed_from_the_address():
    at = _entrypoint(coach="inconnu")
    assert not at.exception
    assert not at.warning
    assert _sidebar(at)["Mon équipe"].value == "Emilinho_"
    assert "coach" not in at.query_params


def test_entrypoint_picking_a_coach_puts_its_key_in_the_address():
    at = _entrypoint(saison="2025-2026")
    at.sidebar.selectbox[1].select("Victor_RM").run()
    assert not at.exception
    assert _sidebar(at)["Mon équipe"].value == "Victor_RM"
    assert at.query_params["coach"] == "Victor_RM"
    at.sidebar.selectbox[0].select("2024-2025").run()
    assert _sidebar(at)["Mon équipe"].value == "Victor_RM"
    assert at.query_params["coach"] == "Victor_RM"


def test_entrypoint_loads_a_season_only_when_selected():
    loaded: list[str] = []
    real_run = analysis_module.run

    def spy(data_dir, *args, **kwargs):
        loaded.append(Path(data_dir).name)
        return real_run(data_dir, *args, **kwargs)

    from app import state

    state._cached.clear()
    with mock.patch.object(state, "run", spy):
        at = _entrypoint()
        assert loaded == ["data"]
        at.sidebar.selectbox[0].select("2025-2026").run()
        assert loaded == ["data", "2025-2026_SRMEG7VW"]
        at.sidebar.selectbox[0].select("2026-2027").run()
        assert loaded == ["data", "2025-2026_SRMEG7VW"]
    state._cached.clear()


@pytest.mark.parametrize("season", SEASONS)
def test_analysis_meta_carries_the_season_contract(season):
    from mpg.analysis import run
    from mpg.seasons import Capabilities

    a = run(season_dirs()[season], n_sim=20)
    expected_key = {"en cours": "2026-2027", "2025-2026_SRMEG7VW": "2025-2026", "2024-2025_SRMEG7VW": "2024-2025"}
    assert a.meta["saison"] == expected_key[season]
    assert a.meta["saison_en_cours"] is (season == "en cours")
    assert isinstance(a.meta["capacites"], Capabilities)
    assert a.meta["capacites"].terminee is (season != "en cours")
    assert isinstance(a.meta["limites"], list)
    assert bool(a.meta["limites"]) is (season != "en cours")


def _open_page(at: AppTest, url_path: str) -> AppTest:
    page_hash = next(h for h, info in at._registered_pages.items() if info.get("url_pathname") == url_path)
    at._page_hash = page_hash
    return at


def _eyebrow(at: AppTest) -> str:
    return next(m.value for m in at.get("html") if 'class="eyebrow"' in m.value)


def _titles(at: AppTest) -> list[str]:
    return [m.value for m in at.get("html") if 'class="volet-title"' in m.value]


def test_navigation_of_the_current_season_has_seven_pages():
    at = _entrypoint()
    assert not at.exception
    urls = {info["url_pathname"] for info in at._registered_pages.values()}
    assert urls == {"", "ligue", "mon-equipe", "pronostics", "pourquoi", "joueurs-mercato", "palmares"}
    assert "Journée " in _eyebrow(at)
    assert "Ligue · 2026-2027" not in _eyebrow(at)


def test_ma_journee_is_the_default_page_of_the_current_season():
    at = _entrypoint()
    default = next(info for info in at._registered_pages.values() if info["url_pathname"] == "")
    assert default["page_name"] == "Ma journée"
    assert next(m for m in at.get("html") if 'class="hero"' in m.value)
    ligue = _open_page(at, "ligue").run()
    assert not ligue.exception
    assert "Ligue · 2026-2027" in _eyebrow(ligue)


def test_navigation_of_a_past_season_has_six_pages_and_no_ma_journee():
    at = _entrypoint(saison="2024-2025")
    assert not at.exception
    urls = {info["url_pathname"] for info in at._registered_pages.values()}
    assert urls == {"", "mon-equipe", "pronostics", "pourquoi", "joueurs-mercato", "palmares"}
    assert "ma-journee" not in urls
    assert "Ligue · 2024-2025" in _eyebrow(at)


def test_volet_chance_opens_on_pourquoi_page():
    at = _entrypoint()
    _open_page(at, "pourquoi")
    at.query_params["volet"] = "chance"
    at.run()
    assert not at.exception
    assert "Pourquoi ce classement ? · 2026-2027" in _eyebrow(at)
    assert at.get("button_group")[0].value == "chance"
    assert any("Qui a eu de la réussite" in title for title in _titles(at))
    assert at.query_params["volet"] == "chance"


def test_invalid_volet_falls_back_to_first():
    at = _entrypoint()
    _open_page(at, "pourquoi")
    at.query_params["volet"] = "nimporte-quoi"
    at.run()
    assert not at.exception
    assert at.get("button_group")[0].value == "favoris"
    assert "volet" not in at.query_params


def _html(at: AppTest, marker: str) -> list[str]:
    return [m.value for m in at.get("html") if marker in m.value]


@pytest.mark.parametrize("query", [{}, {"saison": "2024-2025"}])
def test_palmares_is_listed_and_covers_every_season(query):
    at = _entrypoint(**query)
    page = _open_page(at, "palmares").run()
    assert not page.exception
    assert "Palmarès · 3 saisons, 13 coachs" in _eyebrow(page)
    assert [s.value for s in page.sidebar.selectbox if s.label == "Saison"] == [query.get("saison", "2026-2027")]
    champs = _html(page, 'class="champs"')[0]
    assert champs.count('<div class="champ">') == 3
    assert champs.index("leader") < champs.index("champion")


def test_palmares_follows_the_chosen_coach():
    page = _open_page(_entrypoint(coach="ketXfentanyl"), "palmares").run()
    assert not page.exception
    assert any("ketXfentanyl, toutes saisons" in m for m in _html(page, 'class="stats"'))
    assert len(page.get("plotly_chart")) == 2
    assert page.main.selectbox[-1].label == "Voir les matchs contre"
    page.sidebar.selectbox[1].select("Victor_RM").run()
    assert not page.exception
    assert any("Victor_RM, toutes saisons" in m for m in _html(page, 'class="stats"'))


def test_palmares_for_a_coach_with_a_single_short_season():
    page = _open_page(_entrypoint(coach="Jiboti"), "palmares").run()
    assert not page.exception
    assert any("Tu ne jouais pas cette saison" in m for m in _html(page, 'class="champs"'))
    assert any("n'a joué que 5 matchs" in c.value for c in page.caption)
    assert page.main.selectbox[-1].label == "Voir les matchs contre"
