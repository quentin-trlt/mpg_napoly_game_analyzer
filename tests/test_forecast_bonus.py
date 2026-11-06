import dataclasses

import numpy as np
import pandas as pd
import pytest

from mpg.analysis import run
from mpg.forecast.bonus import (
    MCDO,
    ZAHIA,
    apply_shift,
    bonus_shifts,
    note_value,
    valise_shift,
)
from mpg.forecast.season import build_context, ensemble_draws, fixtures_after, simulate_season


@pytest.fixture(scope="module")
def analysis():
    return run(n_sim=100)


@pytest.fixture(scope="module")
def ctx(analysis):
    return build_context(analysis)


@pytest.fixture(scope="module")
def fixtures(analysis):
    return fixtures_after(analysis, analysis.league.last_gw)


def test_apply_shift_identity_and_direction():
    p = np.array([[0.45, 0.22, 0.33], [0.2, 0.3, 0.5]])
    assert np.allclose(apply_shift(p, np.zeros(2)), p, atol=1e-9)
    up = apply_shift(p, np.full(2, 0.5))
    assert (up[:, 0] > p[:, 0]).all() and (up[:, 2] < p[:, 2]).all()
    assert np.allclose(up.sum(axis=1), 1) and (up >= 0).all()


def test_note_values():
    assert np.isclose(note_value(MCDO, "3-4-3", 0, 0.8), 1 / 11)
    assert np.isclose(note_value(ZAHIA, "3-4-3", 0, 0.8), 0.4)
    assert note_value("424", "3-4-3", 0, 0.8) > 0
    assert note_value("424", "4-3-3", 0, 0.8) == 0
    assert note_value("424", "5-3-2", 0, 0.8) == 0


def test_valise_helps_the_poster(ctx, fixtures, analysis):
    d = ensemble_draws(ctx, fixtures.head(5), n_draws=50)
    home, away = valise_shift(d.score_matrix)
    assert (home > 0).all() and (away > 0).all()


def _ctx_with_stock(ctx, rows):
    return dataclasses.replace(ctx, bonus_remaining=pd.DataFrame(rows, columns=["team_id", "bonus", "restants"]))


def test_no_stock_means_no_shift(ctx, fixtures):
    rng = np.random.default_rng(0)
    assert bonus_shifts(dataclasses.replace(ctx, bonus_remaining=None), fixtures, None, 10, rng) is None


def test_full_stock_is_used_on_every_match(ctx, fixtures):
    team = int(fixtures["home_team_id"].iloc[0])
    n_matches = int(((fixtures["home_team_id"] == team) | (fixtures["away_team_id"] == team)).sum())
    c = _ctx_with_stock(ctx, [(team, "Zahia", n_matches)])
    sm = np.ones((len(fixtures), 2, 2)) / 4
    shift = bonus_shifts(c, fixtures, sm, 20, np.random.default_rng(0))
    expected = c.note_slope * note_value(ZAHIA, "3-4-3", 0, c.start_share)
    is_home = (fixtures["home_team_id"] == team).to_numpy()
    is_away = (fixtures["away_team_id"] == team).to_numpy()
    assert np.allclose(shift[:, is_home], expected) and np.allclose(shift[:, is_away], -expected)
    assert np.allclose(shift[:, ~(is_home | is_away)], 0)


def test_mirror_returns_opponent_bonus(ctx, fixtures):
    match = fixtures.head(1)
    home, away = int(match["home_team_id"].iloc[0]), int(match["away_team_id"].iloc[0])
    sm = np.ones((1, 2, 2)) / 4
    mirror_vs_mcdo = _ctx_with_stock(ctx, [(home, "Miroir", 1), (away, "McDo+", 1)])
    shift = bonus_shifts(mirror_vs_mcdo, match, sm, 10, np.random.default_rng(0))
    assert np.allclose(shift, ctx.note_slope / 11)
    lost_mirror = _ctx_with_stock(ctx, [(home, "Miroir", 1)])
    assert np.allclose(bonus_shifts(lost_mirror, match, sm, 10, np.random.default_rng(0)), 0)


def test_past_bonus_effects_are_zero_sum(ctx):
    pb = ctx.past_bonus
    assert np.allclose(pb.groupby("match_id")["d_note"].sum(), 0)
    assert (pb["d_note"] != 0).any()


def test_use_bonus_flag(analysis, ctx, fixtures):
    d = ensemble_draws(ctx, fixtures, n_draws=300, seed=2)
    assert d.bonus_shift is not None
    with_b = simulate_season(analysis, d, seed=4).summary.set_index("team_id")
    without = simulate_season(analysis, d, seed=4, use_bonus=False).summary.set_index("team_id")
    assert not np.allclose(with_b["pts_moy"], without["pts_moy"].reindex(with_b.index))
    assert np.isclose(with_b["p_titre"].sum(), 1)
