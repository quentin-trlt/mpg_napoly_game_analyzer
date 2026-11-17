import shutil

import pandas as pd
import pytest

from mpg.loader import DEFAULT_DATA_DIR, DataSchemaError, load_league
from mpg.premier_league import club_form, club_view, last_results, next_match, next_matches, pl_table, player_totals


@pytest.fixture(scope="module")
def league():
    return load_league()


def test_scored_goals_equal_fixture_scores(league):
    g = league.scored_goals.groupby(["match_id", "team_id"]).size()
    for side in ("home", "away"):
        fx = league.played.set_index(["match_id", f"{side}_team_id"])[f"{side}_goals"]
        listed = g.reindex(fx.index, fill_value=0)
        assert (listed.to_numpy() == fx.to_numpy()).all(), side


def test_blocked_goals_excluded(league):
    assert (league.scored_goals["type_but"] != "bloque").all()
    assert len(league.scored_goals) == (league.goals["type_but"] != "bloque").sum()


def test_unknown_goal_type_rejected(tmp_path):
    for f in DEFAULT_DATA_DIR.glob("*.csv"):
        shutil.copy(f, tmp_path / f.name)
    goals = pd.read_csv(tmp_path / "goals.csv")
    goals.loc[0, "type_but"] = "inconnu"
    goals.to_csv(tmp_path / "goals.csv", index=False)
    with pytest.raises(DataSchemaError, match="type_but"):
        load_league(tmp_path)


def test_pl_tables_optional(tmp_path):
    for f in DEFAULT_DATA_DIR.glob("*.csv"):
        if f.stem not in ("club_results", "pl_goals"):
            shutil.copy(f, tmp_path / f.name)
    lg = load_league(tmp_path)
    assert lg.club_results is None and lg.pl_goals is None and lg.pl_last_gw == 0


def test_club_results_cover_every_club(league):
    v = club_view(league.club_results)
    per_club = v.groupby("club").size()
    n_clubs = len(per_club)
    assert len(league.club_results) == n_clubs * (n_clubs - 1)
    assert (per_club == 2 * (n_clubs - 1)).all()
    assert set(league.players["club"]) <= set(per_club.index)
    played = league.club_results[league.club_results["statut"] == "joue"]
    assert played[["home_score", "away_score"]].notna().all().all()
    assert league.pl_last_gw == played["pl_gw"].max()


def test_pl_goals_sum_to_club_scores(league):
    counted = league.pl_goals[league.pl_goals["type_but"] != "annule_var"]
    per = counted.groupby(["pl_match_id", "club"]).size()
    v = club_view(league.club_results)
    v = v[v["statut"] == "joue"].set_index(["pl_match_id", "club"])["bp"]
    assert (per.reindex(v.index, fill_value=0).to_numpy() == v.to_numpy()).all()


def test_pl_player_totals_match_players(league):
    tot = player_totals(league.pl_goals).set_index("player_key")
    p = league.players.set_index("player_key")
    buts = tot["buts_pl"].reindex(p.index, fill_value=0)
    passes = tot["passes_pl"].reindex(p.index, fill_value=0)
    assert (buts == p["buts_reels_saison"]).all()
    assert (passes == p["passes_decisives_saison"]).all()


def test_last_results_and_next_match(league):
    club = league.players["club"].iloc[0]
    last = last_results(league.club_results, club, n=3)
    assert len(last) == 3 and last["date"].is_monotonic_decreasing
    assert last["resultat"].isin(["V", "N", "D"]).all()
    nxt = next_match(league.club_results, club)
    assert nxt is not None and nxt["date"] > last["date"].iloc[0]
    form = club_form(league.club_results).set_index("club").loc[club]
    assert form["forme_club"] == "".join(last_results(league.club_results, club, n=5)["resultat"].iloc[::-1])
    assert form["prochain_adversaire"] == nxt["adversaire"]


def _synthetic() -> pd.DataFrame:
    rows = [
        (1, 1, "2026-08-01", "A", "B", 2, 0, "joue"),
        (2, 1, "2026-08-01", "C", "A", 1, 1, "joue"),
        (3, 2, "2026-08-08", "B", "C", 1, 1, "joue"),
        (4, 3, "2026-08-15", "A", "C", None, None, "a_venir"),
        (5, 4, "2026-08-22", "B", "A", None, None, "a_venir"),
        (6, 5, "2026-08-29", "A", "B", None, None, "a_venir"),
        (7, 6, "2026-09-05", "C", "A", None, None, "a_venir"),
    ]
    df = pd.DataFrame(
        rows, columns=["pl_match_id", "pl_gw", "date", "home_club", "away_club", "home_score", "away_score", "statut"]
    )
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["home_club_short"] = df["home_club"]
    df["away_club_short"] = df["away_club"]
    return df


def test_next_matches_synthetic():
    res = _synthetic()
    nxt = next_matches(res, "A")
    assert list(nxt["adversaire"]) == ["C", "B", "B"]
    assert list(nxt["domicile"]) == [True, False, True]
    assert list(next_matches(res, "A", 2)["pl_gw"]) == [3, 4]
    assert next_match(res, "A")["adversaire"] == "C"
    assert next_matches(res.assign(statut="joue"), "A").empty
    assert next_match(res.assign(statut="joue"), "A") is None


def test_pl_table_synthetic():
    t = pl_table(_synthetic()).set_index("club")
    assert t.loc["A", ["j", "pts", "diff", "rang"]].tolist() == [2, 4, 2, 1]
    assert t.loc["C", "rang"] == 2 and t.loc["B", "rang"] == 3


def test_next_matches_current_season(league):
    res = league.club_results
    nxt = next_matches(res, res["home_club"].iloc[0])
    assert len(nxt) == 3
    assert nxt["date"].is_monotonic_increasing
    assert (nxt["statut"] == "a_venir").all()


@pytest.mark.parametrize("season", sorted(p.name for p in (DEFAULT_DATA_DIR / "history").iterdir() if p.is_dir()))
def test_next_matches_empty_on_finished_season(season):
    res = load_league(DEFAULT_DATA_DIR / "history" / season).club_results
    assert next_matches(res, res["home_club"].iloc[0]).empty


def test_pl_table_current_season(league):
    res = league.club_results
    t = pl_table(res)
    assert len(t) == 20
    assert t["rang"].tolist() == list(range(1, 21))
    v = club_view(res)
    v = v[v["statut"] == "joue"]
    expected = v.groupby("club")["resultat"].apply(lambda r: 3 * (r == "V").sum() + (r == "N").sum())
    assert (t.set_index("club")["pts"] == expected.reindex(t["club"]).to_numpy()).all()
    assert t["pts"].is_monotonic_decreasing
