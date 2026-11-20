import dataclasses
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from mpg import strength
from mpg.analysis import run
from mpg.forecast.evaluation import paired_delta, season_dirs
from mpg.loader import DEFAULT_DATA_DIR, load_league
from mpg.seasons import (
    capabilities,
    coach_by_team,
    coach_key,
    limits,
    list_seasons,
    season_by_key,
    team_of,
)


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


@pytest.fixture(scope="module")
def catalogue():
    seasons = list_seasons()
    return seasons, {s.key: load_league(s.path) for s in seasons}


def test_list_seasons_orders_past_then_current():
    seasons = list_seasons()
    assert [s.key for s in seasons] == ["2024-2025", "2025-2026", "2026-2027"]
    assert [s.current for s in seasons] == [False, False, True]
    assert seasons[-1].path == DEFAULT_DATA_DIR
    assert [s.short for s in seasons] == ["24-25", "25-26", "26-27"]
    assert seasons[0].label == "2024-2025" and seasons[0].meta["nb_equipes"] == 8


def test_current_key_without_history(tmp_path):
    seasons = list_seasons(tmp_path)
    assert [(s.key, s.current, s.short) for s in seasons] == [("Saison en cours", True, "Saison en cours")]


def test_list_seasons_does_not_load_any_league():
    with patch("mpg.loader.load_league", side_effect=AssertionError("chargement interdit")):
        assert len(list_seasons()) == 3


def test_season_by_key():
    assert season_by_key("2025-2026").key == "2025-2026"
    with pytest.raises(KeyError, match="2030-2031"):
        season_by_key("2030-2031")


def test_season_meta_is_ignored_by_comparison():
    a, b = list_seasons()[0], list_seasons()[0]
    assert a == b and hash(a) == hash(dataclasses.replace(b, meta={}))


def test_coach_key_merges_aliases():
    assert coach_key("vincentprono92") == "vincentmouly"
    assert coach_key("vincentmouly") == "vincentmouly"
    assert coach_key("Serunos") == "Serunos"


def test_coaches_across_seasons(catalogue):
    seasons, leagues = catalogue
    per_season = {s.key: set(coach_by_team(leagues[s.key]).values()) for s in seasons}
    past = per_season["2024-2025"] | per_season["2025-2026"]
    returning = per_season["2026-2027"] & past
    assert len(returning) == 8 and "vincentmouly" in returning
    assert len(set().union(*per_season.values())) == 13


def test_team_of_follows_the_coach_across_seasons(catalogue):
    _, leagues = catalogue
    ids = [team_of(leagues[k], "ketXfentanyl") for k in ("2024-2025", "2025-2026", "2026-2027")]
    assert ids == [6, 5, 6]
    assert all(leagues[k].teams.set_index("team_id").loc[t, "team_name"] == "FC 69latrik" for k, t in zip(leagues, ids))
    assert team_of(leagues["2025-2026"], "vincentmouly") == 1 == team_of(leagues["2025-2026"], "vincentprono92")
    assert team_of(leagues["2024-2025"], "Poulougoal") is None


def test_past_seasons_capabilities(catalogue):
    seasons, leagues = catalogue
    for s in seasons[:-1]:
        caps = capabilities(leagues[s.key], s.meta)
        assert not (caps.cote or caps.stats_pl or caps.fpl or caps.calendrier_pl or caps.meilleurs_joueurs)
        assert caps.terminee and caps.effectif_fin_saison
        assert limits(caps)


def test_current_season_capabilities(catalogue):
    seasons, leagues = catalogue
    current = seasons[-1]
    caps = capabilities(leagues[current.key], current.meta)
    assert all((caps.cote, caps.stats_pl, caps.fpl, caps.matchs_a_venir, caps.calendrier_pl, caps.meilleurs_joueurs))
    assert caps.forme_site and caps.president_stade
    assert not caps.terminee and not caps.effectif_fin_saison
    assert limits(caps) == []


def test_limits_wording(catalogue):
    seasons, leagues = catalogue
    texts = limits(capabilities(leagues["2025-2026"], seasons[1].meta))
    assert "Pas de cote MPG : la force des effectifs se calcule sur les prix d'enchère." in texts
    assert "Pas de meilleurs joueurs par match." in texts
