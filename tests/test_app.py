from pathlib import Path
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from mpg import analysis as analysis_module
from mpg.forecast.evaluation import season_dirs

ENTRYPOINT = Path(__file__).resolve().parent.parent / "streamlit_app.py"
VIEWS = [
    "ligue",
    "matchs",
    "equipe",
    "favoris",
    "chance",
    "coaching",
    "joueurs",
    "mercato",
    "analyse_mercato",
    "predictions",
    "suivi",
]
SEASONS = list(season_dirs())
POSITIONS = {"premier": 0, "dernier": -1}


def _page(view: str, data_dir: str, position: int) -> None:
    import importlib

    from mpg.analysis import run

    a = run(data_dir, n_sim=200)
    team_id = int(a.standings.iloc[position]["team_id"])
    importlib.import_module(f"app.views.{view}").render(a, team_id)


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("season", SEASONS)
def test_view_renders(season, view, position):
    at = AppTest.from_function(_page, args=(view, str(season_dirs()[season]), POSITIONS[position]), default_timeout=180)
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""


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


def test_forecast_refused_on_a_past_season():
    from app.state import get_forecast

    past = next(path for name, path in season_dirs().items() if name != "en cours")
    with pytest.raises(ValueError, match="saison en cours"):
        get_forecast(past)


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
