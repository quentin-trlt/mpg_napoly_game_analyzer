from collections import namedtuple

import pandas as pd
import pytest

from mpg.coach.replay import optimal_replay, play_match, with_best_eleven
from mpg.coaching import KEYS, _slots, optimal_lineups
from mpg.facts import lineups_enriched, team_match
from mpg.forecast.evaluation import season_dirs
from mpg.loader import load_league
from mpg.premier_league import pl_gw_for

SEASONS = pytest.mark.parametrize("data_dir", list(season_dirs().values()), ids=list(season_dirs()))


def legacy_optimal_lineups(lu: pd.DataFrame, tm: pd.DataFrame) -> pd.DataFrame:
    rotaldo_note = lu.loc[lu["statut"] == "rotaldo", "note_brute"].mean()
    if pd.isna(rotaldo_note):
        rotaldo_note = 2.0
    formations = tm.set_index(KEYS)["formation"]
    rows = []
    for (match_id, team_id), sheet in lu.groupby(KEYS):
        actual = sheet.loc[sheet["sur_terrain"], "note_brute"].sum()
        pool = sheet[sheet["a_joue_irl"] & sheet["poste_groupe"].notna()]
        optimal = 0.0
        swaps = []
        for g, n in _slots(formations.get((match_id, team_id))).items():
            chosen = pool[pool["poste_groupe"] == g].sort_values("note_brute", ascending=False).head(n)
            optimal += chosen["note_brute"].sum() + max(0, n - len(chosen)) * rotaldo_note
            swaps += chosen.loc[~chosen["sur_terrain"], "joueur_affiche"].tolist()
        optimal = max(optimal, actual)
        rows.append(
            {
                "match_id": match_id,
                "team_id": team_id,
                "somme_notes_11": actual,
                "somme_notes_optimal": optimal,
                "regret": optimal - actual,
                "oublies_sur_banc": ", ".join(swaps),
            }
        )
    return pd.DataFrame(rows)


@SEASONS
def test_optimal_lineups_unchanged_by_refactor(data_dir):
    league = load_league(data_dir)
    lu, tm = lineups_enriched(league), team_match(league)
    pd.testing.assert_frame_equal(optimal_lineups(lu, tm), legacy_optimal_lineups(lu, tm))


@SEASONS
def test_replay_without_regret_keeps_the_real_score(data_dir):
    league = load_league(data_dir)
    lu, tm = lineups_enriched(league), team_match(league)
    opt = optimal_lineups(lu, tm)
    replay = optimal_replay(league, lu, tm, opt)
    assert len(replay) + replay.attrs["exclus"] == 2 * len(league.played)
    flat = replay.merge(opt[KEYS + ["regret"]], on=KEYS)
    flat = flat[flat["regret"] <= 0]
    assert len(flat) > 0
    assert (flat["bp_opt"] == flat["bp"]).all() and (flat["bc_opt"] == flat["bc"]).all()
    assert (flat["pts_opt"] == flat["pts"]).all()


def synthetic_sheet(captain: str) -> pd.DataFrame:
    on = [("g", "G", 0, 6.0)] + [(f"d{i}", "D", 1, 6.0) for i in range(4)]
    on += [("m0", "M", 2, 3.0), ("m1", "M", 2, 4.0), ("m2", "M", 2, 5.0), ("m3", "M", 2, 6.0)]
    on += [("a0", "A", 3, 6.0), ("a1", "A", 3, 6.0)]
    rows = [
        {"player_key": k, "poste_groupe": g, "ligne_terrain": line, "note_brute": n, "statut": "titulaire"}
        for k, g, line, n in on
    ]
    rows.append({"player_key": "bench_m", "poste_groupe": "M", "ligne_terrain": None, "note_brute": 8.0})
    rows[-1]["statut"] = "remplacant_non_entre"
    sheet = pd.DataFrame(rows).assign(match_id="m", team_id=1, joueur_affiche=lambda d: d["player_key"].str.upper())
    sheet["sur_terrain"] = sheet["statut"] == "titulaire"
    sheet["a_joue_irl"] = True
    sheet["capitaine"] = (sheet["player_key"] == captain).astype(int)
    sheet["note_avec_bonus"] = sheet["note_brute"] + sheet["capitaine"] * 0.5
    return sheet


def test_best_eleven_swaps_worst_player_and_keeps_the_slot():
    cheat = pd.DataFrame(
        [{"match_id": "m", "team_id": 2, "bonus": "Cheat Code 18-26", "effet_pts": -0.5, "cible_affiche": None}]
    )
    pitch = with_best_eleven(synthetic_sheet("m3"), "4-4-2", cheat).set_index("player_key")
    assert "bench_m" in pitch.index and "m0" not in pitch.index and "m3" in pitch.index
    assert pitch.loc["bench_m", ["ligne_terrain", "statut", "note_avec_bonus"]].tolist() == [2, "remplacant_entre", 7.5]
    assert pitch.loc["m3", "note_avec_bonus"] == 6.5


def test_best_eleven_is_impossible_when_only_the_captain_can_leave():
    sheet = synthetic_sheet("m0")
    sheet.loc[sheet["player_key"].isin(["m1", "m2", "m3"]), "note_brute"] = 9.0
    bonus = pd.DataFrame(columns=["match_id", "team_id", "bonus", "effet_pts", "cible_affiche"])
    assert with_best_eleven(sheet, "4-4-2", bonus) is None


@SEASONS
def test_gameweek_offset_is_unique_and_covers_the_bench(data_dir):
    league = load_league(data_dir)
    lu = lineups_enriched(league)
    bench = lu[(lu["statut"] == "remplacant_non_entre") & lu["a_joue_irl"] & lu["player_key"].notna()].copy()
    bench["pl_gw"] = bench["gw"].map({gw: pl_gw_for(league, gw) for gw in bench["gw"].unique()})
    notes = league.player_match_notes[lambda d: d["a_joue"] == 1]
    found = bench.merge(notes, on=["player_key", "pl_gw"], how="left", suffixes=("", "_pl"))
    matched = found[found["note"] == found["note_brute"]]
    assert matched["pl_gw"].sub(matched["gw"]).nunique() == 1
    assert len(matched) / len(bench) >= 0.99


def test_entrant_goals_raise_the_replayed_score():
    bonus = pd.DataFrame(columns=["match_id", "team_id", "bonus", "effet", "effet_pts", "cible_affiche"])
    goals = pd.DataFrame(columns=["match_id", "team_id", "type_but", "player_key"])
    fx = namedtuple("fx", "match_id home_team_id away_team_id")("m", 1, 2)
    sheet = synthetic_sheet("m3")
    other = sheet[sheet["statut"] == "titulaire"].assign(team_id=2)

    def home_goals(bench_goals: pd.Series) -> int:
        mine = with_best_eleven(sheet, "4-4-2", bonus, bench_goals)
        return play_match(fx, {1: mine, 2: other}, goals, bonus)[0]

    assert home_goals(pd.Series({"bench_m": 2})) > home_goals(pd.Series(dtype=int))
