import numpy as np
import pandas as pd
import pytest

from mpg.analysis import run
from mpg.coach import optimizer as op
from mpg.coach import projection as pr
from mpg.coach.bonus_plan import assign, team_stock
from mpg.coach.recommend import naive_lineup, next_match, recommend
from mpg.coach.rules import BENCH_SIZE, FORMATIONS, slots_of
from mpg.forecast.bonus import MIROIR
from mpg.premier_league import LOCAL_TZ, mpg_gw_date, pl_gw_for


@pytest.fixture(scope="module")
def analysis():
    return run(n_sim=50)


@pytest.fixture(scope="module")
def rec(analysis):
    team = int(analysis.standings.iloc[0]["team_id"])
    return recommend(analysis, team, n_draws=600, seed=3, future_draws=300)


def test_pl_gameweek_mapping_follows_dates(analysis):
    league = analysis.league
    mapping = [pl_gw_for(league, g) for g in range(1, league.n_gw + 1)]
    assert mapping == sorted(mapping) and len(set(mapping)) == len(mapping)
    for g, pl in zip(range(1, league.n_gw + 1), mapping):
        first = league.club_results.loc[league.club_results["pl_gw"] == pl, "date"].min()
        gap = abs(first.tz_convert(LOCAL_TZ).tz_localize(None).normalize() - mpg_gw_date(league, g))
        assert gap <= pd.Timedelta(days=3)


def test_note_model_parameters_are_plausible(analysis):
    m = pr.fit_note_model(analysis)
    assert 0.3 < m.sigma_player < 1.5 and 0 <= m.sigma_club < 1.0
    assert 0.5 < m.goal_bump < 2.5
    assert m.beta_against["G"] < 0 and m.beta_for["A"] > 0


def test_draws_are_consistent(analysis):
    league = analysis.league
    model = pr.fit_note_model(analysis)
    strength = pr.fit_club_strength(league.club_results)
    proj = pr.project_players(analysis, [0, 1], pl_gw_for(league, league.last_gw + 1), model, strength)
    d = pr.sample_draws(proj, model, n_draws=500, seed=1)
    assert d.note.shape == (len(proj), 500)
    assert np.all(np.mod(d.note * 2, 1) == 0)
    assert not (d.goals[~d.plays]).any() and not (d.goals[d.line == "G"]).any()
    injured = proj.index[proj["p_joue"] == 0]
    assert not d.plays[injured].any()


def test_optimised_lineup_is_valid_and_beats_naive(rec):
    best = rec.lineups[0]
    best.validate(rec.draws.line)
    mine = set(rec.proj.index[rec.proj["team_id"] == rec.team_id])
    assert set(best.starters) | set(best.bench) <= mine
    assert len(best.bench) <= BENCH_SIZE
    assert rec.ev_holdout(best) >= rec.ev_holdout(naive_lineup(rec)) - 0.02
    assert best.formation in FORMATIONS
    assert [rec.draws.line[r] for r in best.starters] == list(slots_of(best.formation))


def test_recommendation_is_reproducible(analysis, rec):
    again = recommend(analysis, rec.team_id, n_draws=600, seed=3, with_plan=False)
    assert again.lineups[0] == rec.lineups[0]


def test_summary_probabilities(rec):
    s = rec.summary(rec.best)
    assert np.isclose(s["p_v"] + s["p_n"] + s["p_d"], 1)
    assert 0 <= s["e_pts"] <= 3 and s["se"] > 0


def test_plan_respects_stock(rec):
    used = rec.plan["bonus"].dropna().value_counts()
    for key, n in used.items():
        assert n <= rec.stock[key]
    assert rec.plan["gw"].is_unique and rec.plan["gw"].min() == rec.gw


def test_assign_picks_best_matches_within_stock():
    gains = pd.DataFrame(
        [
            {"gw": 6, "bonus": "zahia", "gain": 0.1},
            {"gw": 7, "bonus": "zahia", "gain": 0.3},
            {"gw": 8, "bonus": "zahia", "gain": 0.2},
            {"gw": 6, "bonus": "suarez", "gain": 0.25},
            {"gw": 7, "bonus": "suarez", "gain": 0.28},
            {"gw": 8, "bonus": "suarez", "gain": -0.1},
        ]
    )
    plan = assign(gains, {"zahia": 1, "suarez": 1}).set_index("gw")["bonus"]
    assert plan.to_dict() == {6: "suarez", 7: "zahia", 8: None}
    plan = assign(gains, {"zahia": 2}).set_index("gw")["bonus"]
    assert plan.to_dict() == {6: None, 7: "zahia", 8: "zahia"}


def test_opponent_bonus_probabilities(analysis):
    team = int(analysis.standings.iloc[-1]["team_id"])
    probs = op.opponent_bonus_probs(analysis.bonus_remaining, team, matches_left=13)
    assert 0 < sum(probs.values()) <= 1 and MIROIR not in probs
    assert op.opponent_bonus_probs(analysis.bonus_remaining, team, matches_left=0) == {}


def test_team_stock_and_next_match(analysis):
    stock, names = team_stock(analysis.bonus_remaining, 0)
    assert all(q > 0 for q in stock.values()) and set(stock) <= set(names)
    gw, opp, _ = next_match(analysis, 0)
    assert gw == analysis.league.last_gw + 1 and opp != 0
