import numpy as np
import pandas as pd
import pytest

from mpg.coach.rules import (
    FORMATION_424,
    Draws,
    Lineup,
    Sheet,
    Tactic,
    mpg_goals,
    resolve_bonuses,
    score_sheets,
    simulate,
)
from mpg.forecast.bonus import CHEAT, F424, MCDO, MIROIR, SUAREZ, TONTON, VALISE, ZAHIA
from mpg.forecast.evaluation import season_dirs
from mpg.loader import load_league

FIELD_LINE = {0: "G", 1: "D", 2: "M", 3: "M", 4: "A"}


def _sheet_from_rows(rows: pd.DataFrame, goals: dict[str, int], own_goals: int) -> Sheet:
    """`ligne_terrain` est la rangée à l'écran : la plus haute est l'attaque (rangée 3 en 4-2-4, 4 sinon)."""
    rows = rows.sort_values("ligne_terrain")
    level = rows["ligne_terrain"].astype(int)
    top = level.max()
    return Sheet(
        line=tuple("A" if r == top and r >= 3 else FIELD_LINE[r] for r in level),
        note=rows["note_avec_bonus"].to_numpy(float)[:, None],
        goals=np.array([goals.get(k, 0) if isinstance(k, str) else 0 for k in rows["player_key"]])[:, None],
        rotaldo=(rows["statut"] == "rotaldo").to_numpy()[:, None],
        own_goals=np.array([own_goals]),
    )


@pytest.mark.parametrize("data_dir", list(season_dirs().values()), ids=list(season_dirs()))
def test_replay_matches_every_played_score(data_dir):
    league = load_league(data_dir)
    lu = league.lineups
    pitch = lu[lu["statut"].isin(["titulaire", "remplacant_entre", "rotaldo"])]
    g = league.goals
    real = g[g["type_but"].isin(["reel", "bloque"])]
    csc = g[g["type_but"] == "csc"]
    bonus = league.bonus
    valise = bonus[bonus["bonus"].str.contains("valise", case=False) & bonus["effet"].notna()]
    mismatches = []
    for fx in league.played.itertuples():
        sheets = {}
        for team, opp in ((fx.home_team_id, fx.away_team_id), (fx.away_team_id, fx.home_team_id)):
            rows = pitch[(pitch["match_id"] == fx.match_id) & (pitch["team_id"] == team)]
            mine = real[(real["match_id"] == fx.match_id) & (real["team_id"] == team)]
            own = int(((csc["match_id"] == fx.match_id) & (csc["team_id"] == opp)).sum())
            sheets[team] = _sheet_from_rows(rows, mine["player_key"].value_counts().to_dict(), own)
        posed = set(valise.loc[valise["match_id"] == fx.match_id, "team_id"])
        hg, ag = score_sheets(
            sheets[fx.home_team_id],
            sheets[fx.away_team_id],
            valise_home=fx.home_team_id in posed,
            valise_away=fx.away_team_id in posed,
        )
        if (int(hg[0]), int(ag[0])) != (fx.home_goals, fx.away_goals):
            mismatches.append((fx.match_id, (int(hg[0]), int(ag[0])), (fx.home_goals, fx.away_goals)))
    assert not mismatches


SQUAD = [("g1", "G"), ("d1", "D"), ("d2", "D"), ("d3", "D"), ("d4", "D"), ("m1", "M"), ("m2", "M"), ("m3", "M")]
SQUAD += [("m4", "M"), ("a1", "A"), ("a2", "A"), ("a3", "A")]
BENCH = [("g2", "G"), ("d5", "D"), ("m5", "M"), ("a4", "A")]


def make_draws(notes: dict[str, float], absent: set[str] = frozenset(), goals: dict[str, int] | None = None) -> Draws:
    goals = goals or {}
    players = [(f"h_{k}", line) for k, line in SQUAD + BENCH] + [(f"o_{k}", line) for k, line in SQUAD + BENCH]
    keys = [k for k, _ in players]
    return Draws(
        keys=keys,
        line=np.array([line for _, line in players]),
        plays=np.array([[k not in absent] for k in keys]),
        note=np.array([[notes.get(k, 5.0)] for k in keys], dtype=float),
        goals=np.array([[goals.get(k, 0)] for k in keys]),
        own_goals=np.zeros((len(keys), 1), dtype=int),
    )


def lineup(d: Draws, side: str, formation: str = "4-4-2", **kw) -> Lineup:
    counts = dict(zip("DMA", (int(x) for x in formation.split("-"))))
    starters = [d.row(f"{side}_g1")]
    for line in "DMA":
        starters += [d.row(f"{side}_{line.lower()}{i}") for i in range(1, counts[line] + 1)]
    bench = tuple(r for r in (d.row(f"{side}_{k}") for k, _ in BENCH) if r not in starters)
    return Lineup(formation=formation, starters=tuple(starters), bench=bench, **kw)


def play(d: Draws, home: Lineup, away: Lineup) -> tuple[int, int]:
    home.validate(d.line)
    away.validate(d.line)
    r = simulate(home, away, d)
    return int(r.home_goals[0]), int(r.away_goals[0])


def test_flat_match_is_goalless_draw():
    d = make_draws({})
    assert play(d, lineup(d, "h"), lineup(d, "o")) == (0, 0)


def test_home_wins_ties_on_line_and_keeper():
    d = make_draws({"h_a1": 6.5, "o_d1": 5.5, "o_d2": 5.5, "o_d3": 5.5, "o_g1": 5.5})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (1, 0)
    d = make_draws({"o_a1": 6.5, "h_d1": 5.5, "h_d2": 5.5, "h_d3": 5.5, "h_g1": 5.5})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 0)
    d = make_draws({"o_a1": 6.0, "h_d1": 6.0, "h_d2": 6.0, "h_d3": 6.0, "h_g1": 4.0})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 0)


def test_attacker_beats_defence_then_keeper_after_minus_one():
    d = make_draws({"h_a1": 7.0, "o_g1": 5.5})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (1, 0)
    d = make_draws({"h_a1": 6.5, "o_g1": 6.0})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 0)


def test_midfielder_path_loses_one_then_half():
    d = make_draws({"o_m1": 7.0, "h_g1": 5.0})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 1)
    d = make_draws({"o_m1": 6.5, "h_g1": 5.0})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 0)


def test_real_scorer_cannot_score_mpg_goal_and_keeper_save():
    d = make_draws({"h_a1": 8.0, "o_g1": 5.0}, goals={"h_a1": 1})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (1, 0)
    d = make_draws({"o_g1": 8.0}, goals={"h_a1": 2})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (1, 0)


def test_absent_starter_replaced_same_line_then_lower_with_malus():
    d = make_draws({"o_a4": 7.0, "h_g1": 5.0}, absent={"o_a1"})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 1)
    d = make_draws({"o_m5": 6.5, "h_g1": 5.0}, absent={"o_a1", "o_a4"})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 0)
    d = make_draws({"o_m5": 7.5, "h_g1": 5.0}, absent={"o_a1", "o_a4"})
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 1)


def test_three_rotaldos_give_an_own_goal():
    absent = {"h_d1", "h_d2", "h_d3", "h_d5"}
    d = make_draws({}, absent=absent)
    assert play(d, lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")) == (0, 1)


def test_tactical_sub_fires_below_threshold_and_cancels_real_goal():
    d = make_draws({"h_a1": 4.5}, goals={"h_a1": 1})
    base = lineup(d, "h", formation="3-4-3")
    tactic = Tactic(out=d.row("h_a1"), inp=d.row("h_a4"), threshold=5.0)
    away = lineup(d, "o", formation="3-4-3")
    assert play(d, base, away) == (1, 0)
    assert play(d, base.with_(tactics=(tactic,)), away) == (0, 0)
    assert play(d, base.with_(tactics=(tactic,)), away.with_(bonus=TONTON)) == (1, 0)


def test_tactical_sub_does_nothing_if_replacement_did_not_play():
    d = make_draws({"h_a1": 4.5}, absent={"h_a4"}, goals={"h_a1": 1})
    tactic = Tactic(out=d.row("h_a1"), inp=d.row("h_a4"), threshold=5.0)
    home = lineup(d, "h", formation="3-4-3", tactics=(tactic,))
    assert play(d, home, lineup(d, "o", formation="3-4-3")) == (1, 0)


def test_captain_bonus_only_if_captain_plays_and_not_with_mcdo():
    d = make_draws({"o_a1": 6.5, "h_g1": 5.5})
    home = lineup(d, "h", formation="3-4-3")
    away = lineup(d, "o", formation="3-4-3")
    assert play(d, home, away) == (0, 0)
    assert play(d, home, away.with_(captain=d.row("o_a1"))) == (0, 1)
    d = make_draws({"o_a1": 5.5, "h_g1": 5.5})
    away = lineup(d, "o", formation="3-4-3")
    both = away.with_(captain=d.row("o_a1"), bonus=MCDO, mcdo_target=d.row("o_a1"))
    assert play(d, home, both) == (0, 0)
    d = make_draws({"o_a1": 6.5, "h_g1": 5.5}, absent={"o_a1"})
    away = lineup(d, "o", formation="3-4-3", captain=d.row("o_a1"))
    assert play(d, home, away) == (0, 0)


def test_defence_bonus_only_for_starting_defenders():
    d = make_draws({"o_a1": 6.0, "h_g1": 4.5})
    away = lineup(d, "o", formation="3-4-3")
    assert play(d, lineup(d, "h", formation="3-4-3"), away) == (0, 1)
    assert play(d, lineup(d, "h", formation="5-3-2"), away) == (0, 0)
    d = make_draws({"o_a1": 6.0, "h_g1": 4.5}, absent={"h_d1"})
    home = lineup(d, "h", formation="4-4-2")
    assert play(d, home, away) == (0, 1)


def test_suarez_cheat_zahia_and_valise():
    d = make_draws({"o_a1": 6.5, "h_g1": 5.5})
    home, away = lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")
    assert play(d, home, away) == (0, 0)
    assert play(d, home, away.with_(bonus=SUAREZ)) == (0, 1)
    assert play(d, home, away.with_(bonus=ZAHIA)) == (0, 1)
    d = make_draws({"o_a1": 6.0, "h_d1": 6.0, "h_d2": 6.0, "h_d3": 6.0, "h_g1": 4.5})
    home, away = lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")
    assert play(d, home, away) == (0, 0)
    assert play(d, home, away.with_(bonus=CHEAT)) == (0, 1)
    d = make_draws({"o_a1": 7.0, "h_g1": 5.0}, goals={"o_a2": 1})
    home, away = lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")
    assert play(d, home, away) == (0, 2)
    assert play(d, home.with_(bonus=VALISE), away) == (0, 1)


def test_mirror_reflects_bonus():
    d = make_draws({"h_a1": 6.5, "o_g1": 6.0, "o_a1": 6.5, "h_g1": 5.5})
    home, away = lineup(d, "h", formation="3-4-3"), lineup(d, "o", formation="3-4-3")
    assert play(d, home, away) == (0, 0)
    assert play(d, home.with_(bonus=SUAREZ), away) == (1, 0)
    assert play(d, home.with_(bonus=SUAREZ), away.with_(bonus=MIROIR)) == (0, 1)
    home_fx, away_fx = resolve_bonuses(F424, MIROIR)
    assert home_fx.defence_bonus_lost and away_fx.extra_defence_bonus == 0.5
    assert resolve_bonuses(MIROIR, None) == resolve_bonuses(None, None)


def test_424_requires_bonus():
    d = make_draws({})
    with pytest.raises(ValueError):
        lineup(d, "h", formation=FORMATION_424).validate(d.line)
    lineup(d, "h", formation=FORMATION_424, bonus=F424).validate(d.line)


def test_mpg_goals_vectorised_over_draws():
    s_att = Sheet(
        line=("G", "D", "D", "D", "M", "M", "M", "M", "A", "A", "A"),
        note=np.tile(np.array([5.0] * 10 + [7.0])[:, None], (1, 3)),
        goals=np.zeros((11, 3), dtype=int),
        rotaldo=np.zeros((11, 3), dtype=bool),
        own_goals=np.zeros(3, dtype=int),
    )
    s_def = Sheet(
        line=s_att.line,
        note=np.tile(np.full(11, 5.0)[:, None], (1, 3)),
        goals=np.zeros((11, 3), dtype=int),
        rotaldo=np.zeros((11, 3), dtype=bool),
        own_goals=np.zeros(3, dtype=int),
    )
    s_def.note[0] = [5.0, 6.0, 6.5]
    assert mpg_goals(s_att, s_def, att_home=False).tolist() == [1, 0, 0]
