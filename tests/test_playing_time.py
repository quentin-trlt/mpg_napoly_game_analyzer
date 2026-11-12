import dataclasses
import shutil

import numpy as np
import pandas as pd
import pytest

import build_fpl
from mpg import fpl
from mpg import playing_time as pt
from mpg.analysis import run
from mpg.forecast.season import build_context
from mpg.loader import DEFAULT_DATA_DIR, load_league

ROUNDS = range(1, 11)


def history(pattern) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "round": list(ROUNDS),
            "minutes": [90 if pattern(r) else 0 for r in ROUNDS],
            "starts": [1 if pattern(r) else 0 for r in ROUNDS],
            "goals_scored": 0,
            "own_goals": 0,
            "xg": 0.0,
            "kickoff_time": "2026-10-01T15:00:00Z",
        }
    )


@pytest.fixture
def synthetic():
    patterns = {"titulaire": lambda r: True, "remplacant": lambda r: False, "alterne": lambda r: r % 2 == 0}
    keys, hist = [], {}
    for i in range(60):
        kind = list(patterns)[i % 3]
        keys.append(f"{kind}_{i}")
        hist[i] = history(patterns[kind])
    return pd.DataFrame({"player_key": keys, "element_id": range(60)}), hist


def test_probabilities_follow_recent_play(synthetic):
    players, hist = synthetic
    p = pt.play_probabilities(players, hist, pl_gw=9)
    assert p[p.index.str.startswith("titulaire")].min() > 0.85
    assert p[p.index.str.startswith("remplacant")].max() < 0.15
    assert p.between(0, 1).all() and len(p) == 60


def test_probabilities_ignore_later_rounds(synthetic):
    players, hist = synthetic
    before = pt.play_probabilities(players, hist, pl_gw=8)
    flipped = {e: h.assign(minutes=np.where(h["round"] >= 8, 90 - h["minutes"], h["minutes"])) for e, h in hist.items()}
    after = pt.play_probabilities(players, flipped, pl_gw=8)
    pd.testing.assert_series_equal(before, after)


def test_split_history_round_trip(synthetic):
    _, hist = synthetic
    long = pd.concat([h.assign(element_id=e) for e, h in hist.items()], ignore_index=True)
    back = pt.split_history(long)
    assert set(back) == set(hist)
    pd.testing.assert_frame_equal(back[5], hist[5][pt.HISTORY_COLUMNS])


def test_short_history_falls_back_to_season_rate():
    players = pd.DataFrame({"player_key": ["a"], "element_id": [1]})
    hist = {1: history(lambda r: r == 1).head(2)}
    p = pt.play_probabilities(players, hist, pl_gw=3)
    assert p["a"] == pytest.approx(0.5)


class FakeClient:
    def __init__(self, league):
        self.players = league.players.head(3)
        self.teams = sorted({fpl.CLUB_TO_FPL.get(c, c) for c in league.players["club"]})

    def bootstrap(self) -> dict:
        tid = {name: i + 1 for i, name in enumerate(self.teams)}
        elements = []
        for i, r in enumerate(self.players.itertuples(), start=1):
            first, *rest = r.joueur.split()
            elements.append(
                {
                    "id": i,
                    "first_name": first,
                    "second_name": " ".join(rest) or first,
                    "web_name": r.joueur,
                    "known_name": "",
                    "team": tid[fpl.CLUB_TO_FPL.get(r.club, r.club)],
                    "element_type": 3,
                    "status": "d" if i == 1 else "a",
                    "chance_of_playing_next_round": 75 if i == 1 else None,
                    "news": "",
                    "minutes": 900,
                    "starts": 10,
                    "goals_scored": 1,
                    "own_goals": 0,
                    "expected_goals": "1.0",
                    "expected_goals_per_90": "0.1",
                }
            )
        return {
            "teams": [{"id": i, "name": n} for n, i in tid.items()],
            "events": [{"id": 11, "is_next": True}],
            "elements": elements,
        }

    def element_summary(self, element_id: int) -> dict:
        h = history(lambda r: True)
        return {
            "history": [
                {
                    "round": int(x["round"]),
                    "minutes": int(x["minutes"]),
                    "starts": int(x["starts"]),
                    "goals_scored": 0,
                    "own_goals": 0,
                    "expected_goals": "0.10",
                    "kickoff_time": x["kickoff_time"],
                }
                for _, x in h.iterrows()
            ]
        }


def test_build_fpl_writes_files_the_loader_reads(tmp_path):
    league = load_league()
    players, hist = build_fpl.build(league, FakeClient(league))
    assert len(players) == len(league.players) and players["element_id"].notna().sum() == 3
    assert players.loc[players["element_id"] == 1, "chance_next"].iloc[0] == 75
    assert len(hist) == 3 * len(ROUNDS)

    for f in DEFAULT_DATA_DIR.glob("*.csv"):
        if not f.name.startswith("fpl_"):
            shutil.copy(f, tmp_path / f.name)
    paths = build_fpl.write(players, hist, tmp_path)
    assert (tmp_path / "fpl_snapshots" / "fpl_players_PL11.csv") in paths
    loaded = load_league(tmp_path)
    assert loaded.fpl_players is not None and loaded.fpl_players["element_id"].notna().sum() == 3
    assert set(loaded.fpl_history["element_id"]) == {1, 2, 3}


def test_league_without_snapshot_keeps_season_rate():
    a = run(n_sim=50)
    if a.league.fpl_players is None:
        pytest.skip("pas d'instantané FPL dans data/")
    ctx = build_context(a)
    assert ctx.players["taux_jeu"].between(0, 1).all()
    assert not np.allclose(ctx.players["taux_jeu"], a.player_value["taux_jeu"].fillna(0))

    bare = dataclasses.replace(a, league=dataclasses.replace(a.league, fpl_players=None, fpl_history=None))
    assert pt.league_play_probabilities(bare.league, a.league.last_gw + 1) is None
    pd.testing.assert_series_equal(build_context(bare).players["taux_jeu"], a.player_value["taux_jeu"])
    assert pt.league_play_probabilities(a.league, a.league.n_gw + 1) is None
