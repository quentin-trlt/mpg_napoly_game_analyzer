from pathlib import Path

import pytest

from app import state
from mpg.forecast.evaluation import season_dirs

LIGHT_KEYS = {"draws", "baseline", "bonus_effect"}
HEAVY_KEYS = {"history", "backtest", "backtest_summary", "frozen_matches", "frozen_seasons"}


@pytest.fixture(scope="module")
def light() -> dict:
    return state.get_forecast_light()


@pytest.fixture(scope="module")
def full(light) -> dict:
    return state.get_forecast()


def test_light_keys(light):
    assert set(light) == LIGHT_KEYS


def test_full_keys(full):
    assert set(full) == LIGHT_KEYS | HEAVY_KEYS


def test_full_reuses_light_cache(light, full):
    assert full["draws"] is light["draws"]
    assert full["baseline"] is light["baseline"]


def test_past_season_rejected():
    past = next(path for name, path in season_dirs().items() if name != "en cours")
    with pytest.raises(ValueError, match="saison en cours"):
        state.get_forecast_light(past)
    with pytest.raises(ValueError, match="saison en cours"):
        state.get_forecast(past)


FROZEN_KEYS = {"frozen_matches", "frozen_seasons"}
HISTORY_COLUMNS = {"apres_journee", "team_id", "p_titre", "p_dernier"}


def _past_season() -> Path:
    return next(path for name, path in season_dirs().items() if name != "en cours")


def test_frozen_keys():
    assert set(state.get_frozen()) == FROZEN_KEYS


def test_forecast_reuses_split_caches(full):
    frozen = state.get_frozen()
    assert full["history"] is state.get_title_history()
    assert full["frozen_matches"] is frozen["frozen_matches"]
    assert full["frozen_seasons"] is frozen["frozen_seasons"]


def test_frozen_rejects_past_season():
    with pytest.raises(ValueError, match="saison en cours"):
        state.get_frozen(_past_season())


def test_title_history_on_past_season():
    history = state.get_title_history(_past_season())
    assert HISTORY_COLUMNS <= set(history.columns)
    assert len(history) >= 1


def test_backtest_shares_the_full_cache(full):
    bt = state.get_backtest()
    assert set(bt) == {"backtest", "backtest_summary"}
    assert bt["backtest"] is full["backtest"]


def test_backtest_past_season_rejected():
    past = next(path for name, path in season_dirs().items() if name != "en cours")
    with pytest.raises(ValueError, match="saison en cours"):
        state.get_backtest(past)
