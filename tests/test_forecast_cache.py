from pathlib import Path

import pytest

from app import state
from mpg.forecast.evaluation import season_dirs

LIGHT_KEYS = {"draws", "baseline", "bonus_effect"}


@pytest.fixture(scope="module")
def light() -> dict:
    return state.get_forecast_light()


def test_light_keys(light):
    assert set(light) == LIGHT_KEYS


def test_past_season_rejected():
    past = next(path for name, path in season_dirs().items() if name != "en cours")
    with pytest.raises(ValueError, match="saison en cours"):
        state.get_forecast_light(past)


FROZEN_KEYS = {"frozen_matches", "frozen_seasons"}
HISTORY_COLUMNS = {"apres_journee", "team_id", "p_titre", "p_dernier"}


def _past_season() -> Path:
    return next(path for name, path in season_dirs().items() if name != "en cours")


def test_frozen_keys():
    assert set(state.get_frozen()) == FROZEN_KEYS


def test_frozen_rejects_past_season():
    with pytest.raises(ValueError, match="saison en cours"):
        state.get_frozen(_past_season())


def test_title_history_on_past_season():
    history = state.get_title_history(_past_season())
    assert HISTORY_COLUMNS <= set(history.columns)
    assert len(history) >= 1


def test_backtest_keys_and_cache():
    bt = state.get_backtest()
    assert set(bt) == {"backtest", "backtest_summary"}
    assert state.get_backtest()["backtest"] is bt["backtest"]


def test_backtest_past_season_rejected():
    past = next(path for name, path in season_dirs().items() if name != "en cours")
    with pytest.raises(ValueError, match="saison en cours"):
        state.get_backtest(past)
