import dataclasses

import numpy as np
import pandas as pd
import pytest

from mpg import strength
from mpg.analysis import run
from mpg.forecast.evaluation import paired_delta, season_dirs
from mpg.loader import load_league


def test_season_dirs_list_history_then_current():
    dirs = season_dirs()
    assert list(dirs)[-1] == "en cours"
    assert all((d / "meta.json").exists() for name, d in dirs.items() if name != "en cours")


@pytest.mark.parametrize("data_dir", list(season_dirs().values()), ids=list(season_dirs()))
def test_every_season_runs_the_analysis(data_dir):
    a = run(data_dir, n_sim=20)
    assert a.favourites["indice_force"].notna().all()
    assert (a.lines.filter(like="n_") >= 0).all().all()


def test_strength_index_falls_back_to_auction_prices():
    league = load_league()
    players = league.players.assign(cote=np.nan)
    assert strength.price_column(players) == "enchere"
    feats = strength.squad_features(dataclasses.replace(league, players=players))
    assert feats.attrs["prix"] == "enchere" and (feats["cote_11_max"] > 0).all()


def test_unknown_strength_feature_counts_as_median():
    feats = pd.DataFrame({"team_id": [0, 1, 2], "a": [1.0, 2.0, 3.0], "b": [np.nan] * 3})
    idx = strength.strength_index(feats, {"a": 0.5, "b": 0.5})
    assert idx["indice_force"].notna().all() and (idx["z_b"] == 0).all()


def test_paired_delta_resamples_within_seasons():
    rng = np.random.default_rng(0)
    rows = []
    for season, shift in (("s1", 0.02), ("s2", -0.02)):
        for i in range(200):
            base = rng.random()
            rows.append({"saison": season, "match_id": f"{season}{i}", "modele": "ref", "rps": base})
            rows.append({"saison": season, "match_id": f"{season}{i}", "modele": "m", "rps": base + shift})
    d, lo, hi = paired_delta(pd.DataFrame(rows), "m", "ref")
    assert (
        d == pytest.approx(0.0, abs=1e-12)
        and lo == pytest.approx(0.0, abs=1e-12)
        and hi == pytest.approx(0.0, abs=1e-12)
    )
