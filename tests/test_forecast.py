import dataclasses

import numpy as np
import pytest

from mpg.analysis import run
from mpg.forecast import evaluation
from mpg.forecast.models import BaselineModel, EloModel, PoissonModel, StructuralModel, ordered_probs
from mpg.forecast.season import (
    STRUCTURAL_ONLY_GWS,
    build_context,
    ensemble_draws,
    ensemble_weights,
    fixtures_after,
    simulate_season,
    title_odds_history,
)


@pytest.fixture(scope="module")
def analysis():
    return run(n_sim=200)


@pytest.fixture(scope="module")
def ctx(analysis):
    return build_context(analysis)


@pytest.fixture(scope="module")
def fixtures(analysis):
    return fixtures_after(analysis, analysis.league.last_gw)


@pytest.fixture(scope="module")
def draws(ctx, fixtures):
    return ensemble_draws(ctx, fixtures, n_draws=800, seed=3)


def test_ordered_probs_are_distributions():
    p = ordered_probs(np.linspace(-5, 5, 41), 0.4)
    assert np.allclose(p.sum(axis=1), 1) and (p >= 0).all()
    assert p[0, 2] > p[0, 0] and p[-1, 0] > p[-1, 2]


def test_scores_known_values():
    s = evaluation.scores(np.array([[1.0, 0.0, 0.0], [1 / 3, 1 / 3, 1 / 3]]), np.array([0, 0]))
    assert np.isclose(s.loc[0, "rps"], 0) and np.isclose(s.loc[0, "brier"], 0)
    assert np.isclose(s.loc[1, "log_loss"], np.log(3))
    assert np.isclose(s.loc[1, "rps"], ((1 / 3 - 1) ** 2 + (2 / 3 - 1) ** 2) / 2)


@pytest.mark.parametrize("model_cls", [BaselineModel, EloModel, PoissonModel, StructuralModel])
def test_models_return_valid_probabilities(model_cls, ctx, fixtures):
    m = model_cls().fit(ctx)
    p = m.sample_probs(fixtures, 200, np.random.default_rng(0))
    assert p.shape == (200, len(fixtures), 3)
    assert np.allclose(p.sum(axis=2), 1) and (p >= -1e-12).all()


def test_poisson_score_matrix_and_parameters(ctx, fixtures):
    m = PoissonModel().fit(ctx)
    sm = m.score_matrix(fixtures)
    assert np.allclose(sm.sum(axis=(1, 2)), 1)
    assert np.isfinite(m.theta).all() and m.tau in m.tau_grid
    assert len(m.team_parameters()) == len(ctx.team_ids)


def test_models_fit_without_any_match(analysis, fixtures):
    empty = build_context(analysis, 0)
    for model in (EloModel(), PoissonModel(), StructuralModel()):
        p = model.fit(empty).sample_probs(fixtures.head(5), 50, np.random.default_rng(0))
        assert np.allclose(p.sum(axis=2), 1)


def test_injured_player_never_plays_next_gameweek(ctx):
    m = StructuralModel().fit(ctx)
    for groups in m.teams.values():
        for grp in groups.values():
            p = m._play_prob(grp, m.next_gw)
            injured = np.isin(grp["statut"], ["blesse", "suspendu"])
            assert (p[injured] == 0).all()


def test_ensemble_is_mean_of_models(draws):
    models = [d for name, d in draws.by_model.items() if name != "Référence (fréquences)"]
    assert len(models) == 3
    assert np.allclose(draws.ensemble_raw, np.mean(models, axis=0))


def test_season_simulation_is_consistent(analysis, draws):
    sim = simulate_season(analysis, draws)
    assert np.allclose(sim.rank_probs.sum(axis=1), 1)
    assert np.allclose(sim.rank_probs.sum(axis=0), 1)
    assert np.isclose(sim.summary["p_titre"].sum(), 1)
    assert (sim.summary["pts_moy"] >= sim.summary["pts_actuels"]).all()
    assert (
        sim.final_points.max(axis=0)
        <= sim.summary.set_index("team_id").loc[sim.team_ids, "pts_actuels"]
        + 3 * draws.fixtures["home_team_id"].value_counts().reindex(sim.team_ids, fill_value=0)
        + 3 * draws.fixtures["away_team_id"].value_counts().reindex(sim.team_ids, fill_value=0)
    ).all()


def test_forcing_every_match_makes_season_deterministic(analysis, draws):
    forced = dict.fromkeys(range(len(draws.fixtures)), "H")
    sim = simulate_season(analysis, draws, forced=forced)
    assert (sim.final_points == sim.final_points[0]).all()
    home_wins = draws.fixtures["home_team_id"].value_counts()
    cur = sim.summary.set_index("team_id")["pts_actuels"]
    expected = cur + 3 * home_wins.reindex(cur.index, fill_value=0)
    idx = {t: i for i, t in enumerate(sim.team_ids)}
    assert all(sim.final_points[0, idx[t]] == expected[t] for t in sim.team_ids)


def test_forced_score_is_applied(analysis, draws):
    j = 0
    home = int(draws.fixtures.at[j, "home_team_id"])
    win = simulate_season(analysis, draws, forced={j: (3, 0)}, seed=7).summary.set_index("team_id")
    loss = simulate_season(analysis, draws, forced={j: (0, 3)}, seed=7).summary.set_index("team_id")
    assert np.isclose(win.loc[home, "pts_moy"] - loss.loc[home, "pts_moy"], 3)


def test_title_history_covers_every_gameweek(analysis):
    hist = title_odds_history(analysis, n_draws=200)
    assert sorted(hist["apres_journee"].unique()) == list(range(0, analysis.league.last_gw + 1))
    assert np.allclose(hist.groupby("apres_journee")["p_titre"].sum(), 1)


def test_backtest_covers_all_played_matches(analysis):
    bt = evaluation.backtest(analysis, n_draws=200)
    n_played = len(analysis.league.played)
    assert (bt.groupby("modele").size() == n_played).all()
    assert {"Ensemble", "Référence (fréquences)"} <= set(bt["modele"])


def test_freeze_never_overwrites_and_track_record(analysis, draws, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "FROZEN_DIR", tmp_path)
    sim = simulate_season(analysis, draws)
    first = evaluation.freeze_next(analysis, sim, draws)
    assert len(first) == 2 and all(f.exists() for f in first)
    assert evaluation.freeze_next(analysis, sim, draws) == []

    played = analysis.league.played[analysis.league.played["gw"] == 1]
    fake = played[["gw", "home_team_id", "away_team_id", "home_team", "away_team"]].assign(
        modele="Ensemble", p_dom=0.5, p_nul=0.25, p_ext=0.25, score_probable="1-0", fige_apres_journee=0
    )
    fake.to_csv(tmp_path / "J01.csv", index=False)
    fm = evaluation.frozen_matches(analysis)
    scored = fm[fm["joue"]]
    assert len(scored) == len(played)
    assert scored["rps"].between(0, 1).all()
    assert not evaluation.scored_summary(fm).empty
    assert len(evaluation.frozen_seasons()) == len(analysis.league.teams)


def test_team_effect_follows_persistent_note_gaps(ctx):
    m = StructuralModel().fit(ctx)
    assert set(m.team_effect) <= set(ctx.team_ids) and m.team_effect
    weak = ctx.team_ids[0]
    tm = ctx.tm.copy()
    tm.loc[tm["team_id"] == weak, "note_moy_brute"] -= 1.0
    shifted = StructuralModel().fit(dataclasses.replace(ctx, tm=tm))
    n = int((tm["team_id"] == weak).sum())
    assert shifted.team_effect[weak] - m.team_effect[weak] < -0.5 * n / (n + shifted.team_k)
    assert StructuralModel(team_k=float("inf")).fit(ctx).team_effect == {}


def test_team_effect_is_zero_before_any_match(analysis):
    assert StructuralModel().fit(build_context(analysis, 0)).team_effect == {}


def test_ensemble_weights_follow_the_season():
    names = ["Référence (fréquences)", "Elo", "Poisson bayésien", StructuralModel.name]
    early = ensemble_weights(names, 0)
    assert early == {"Elo": 0.0, "Poisson bayésien": 0.0, StructuralModel.name: 1.0}
    late = ensemble_weights(names, STRUCTURAL_ONLY_GWS)
    assert set(late) == set(names[1:]) and np.allclose(list(late.values()), 1 / 3)
    assert np.allclose(list(ensemble_weights(names[:3], 0).values()), 0.5)


def test_early_ensemble_is_the_structural_model(analysis, fixtures):
    d = ensemble_draws(build_context(analysis, 1), fixtures.head(5), n_draws=100, seed=0)
    assert np.allclose(d.ensemble_raw, d.by_model[StructuralModel.name])
    late = ensemble_draws(build_context(analysis), fixtures.head(5), n_draws=100, seed=0)
    others = [v for k, v in late.by_model.items() if k != "Référence (fréquences)"]
    assert np.allclose(late.ensemble_raw, np.mean(others, axis=0))
