from types import SimpleNamespace

import numpy as np
import pandas as pd

from mpg.coach.rules import Draws
from mpg.coach.typical import typical_lineup, usage

N = 20
SQUAD = {
    "G": ["g1", "g_new"],
    "D": ["d1", "d2", "d3", "d_bench", "d_new"],
    "M": ["m1", "m2", "m3", "m4", "m_new"],
    "A": ["a1", "a2", "a3", "a_bench"],
}
STARTERS = ["g1", "d1", "d2", "d3", "m1", "m2", "m3", "m4", "a1", "a2", "a3"]
BENCH = ["d_bench", "a_bench"]


def _analysis(formations: dict[int, str]) -> SimpleNamespace:
    rows = []
    for gw in formations:
        rows += [{"gw": gw, "player_key": k, "statut": "titulaire", "capitaine": int(k == "a1")} for k in STARTERS]
        rows += [{"gw": gw, "player_key": k, "statut": "remplacant_non_entre", "capitaine": 0} for k in BENCH]
    lineups = pd.DataFrame(rows).assign(team_id=0, match_id=lambda d: "m" + d["gw"].astype(str))
    tm = pd.DataFrame({"gw": list(formations), "formation": list(formations.values())})
    return SimpleNamespace(lineups=lineups, team_match=tm.assign(team_id=0, match_id="m" + tm["gw"].astype(str)))


def _draws(absent: set[str]) -> Draws:
    keys = [k for line in "GDMA" for k in SQUAD[line]]
    note = np.array([7.5 if k.endswith("_new") else 5.0 for k in keys])
    plays = np.array([k not in absent for k in keys])
    return Draws(
        keys=keys,
        line=np.array([line for line in "GDMA" for _ in SQUAD[line]]),
        plays=np.repeat(plays[:, None], N, axis=1),
        note=np.repeat(note[:, None], N, axis=1),
        goals=np.zeros((len(keys), N), dtype=int),
        own_goals=np.zeros((len(keys), N), dtype=int),
    )


def _starters(d: Draws, formations: dict[int, str] | None = None) -> tuple[set[str], str, str]:
    a = _analysis(formations or {1: "3-4-3", 2: "3-4-3"})
    lu = typical_lineup(list(range(len(d.keys))), d, usage(a, 0, max(a.team_match["gw"]) + 1))
    return {d.keys[r] for r in lu.starters}, lu.formation, d.keys[lu.captain]


def test_habits_beat_better_newcomers():
    starters, formation, captain = _starters(_draws(set()))
    assert starters == set(STARTERS) and formation == "3-4-3" and captain == "a1"


def test_absent_regular_is_replaced_by_usual_substitute():
    starters, _, captain = _starters(_draws({"d1", "a1"}))
    assert "d_bench" in starters and "a_bench" in starters
    assert not {"d1", "a1", "d_new"} & starters
    assert captain != "a1"


def test_recent_formation_wins():
    _, formation, _ = _starters(_draws(set()), formations={1: "4-4-2", 2: "3-4-3"})
    assert formation == "3-4-3"
