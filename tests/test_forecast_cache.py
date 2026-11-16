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
