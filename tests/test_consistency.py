import numpy as np
import pandas as pd
import pytest

from mpg.analysis import run
from mpg.coaching import optimal_lineups
from mpg.luck import all_play, calibrate_draw_band, schedule_permutation


@pytest.fixture(scope="module")
def analysis():
    return run(n_sim=2_000)


@pytest.fixture(scope="module")
def official(analysis):
    return analysis.league.teams.set_index("team_id")


def test_eleven_on_pitch_and_eleven_picked(analysis):
    lu = analysis.lineups
    keys = ["match_id", "team_id"]
    assert (lu[lu["sur_terrain"]].groupby(keys).size() == 11).all()
    assert (lu[lu["choix_coach"]].groupby(keys).size() == 11).all()


def test_two_rows_per_played_match(analysis):
    tm = analysis.team_match
    assert len(tm) == 2 * len(analysis.league.played)
    assert (tm.groupby("match_id")["pts"].sum().isin([2, 3])).all()


def test_score_equals_listed_goals(analysis):
    tm = analysis.team_match
    assert (tm["bp"] == tm["bp_reel"] + tm["bp_mpg"] + tm["bp_csc"]).all()


def test_standings_match_site(analysis, official):
    t = analysis.standings.set_index("team_id").sort_index()
    pd.testing.assert_series_equal(t["pts"], official["pts"], check_names=False, check_dtype=False)
    for ours, theirs in [("g", "g"), ("n", "n"), ("p", "p"), ("diff", "diff_buts"), ("rang", "classement")]:
        assert (t[ours] == official[theirs]).all(), ours


def test_goal_breakdown_matches_site(analysis, official):
    g = analysis.team_match.groupby("team_id")[["bp_reel", "bp_mpg", "bc_reel", "bc_csc", "bc_mpg", "n_rotaldos"]].sum()
    assert (g["bp_reel"] == official["buts_pour_reels"]).all()
    assert (g["bp_mpg"] == official["buts_pour_mpg"]).all()
    assert (g["bc_reel"] + g["bc_csc"] == official["buts_contre_reels"]).all()
    assert (g["bc_mpg"] == official["buts_contre_mpg"]).all()
    assert (g["n_rotaldos"] == official["rotaldos_alignes"]).all()


def test_average_with_bonus_matches_site(analysis, official):
    lu = analysis.lineups
    avg = lu[lu["sur_terrain"]].groupby("team_id")["note_avec_bonus"].mean().round(2)
    assert np.allclose(avg, official["moy_equipe_avec_bonus"], atol=0.006)


def test_raw_notes_match_site_without_rotaldo(analysis, official):
    lu = analysis.lineups
    clean = official.index[official["rotaldos_alignes"] == 0]
    assert len(clean) > 0
    avg = lu[lu["sur_terrain"] & lu["team_id"].isin(clean)].groupby("team_id")["note_brute"].mean().round(2)
    assert np.allclose(avg, official.loc[clean, "moy_equipe"], atol=0.006)


def test_optimal_never_below_actual(analysis):
    opt = optimal_lineups(analysis.lineups, analysis.team_match)
    assert (opt["regret"] >= -1e-9).all()
    assert len(opt) == len(analysis.team_match)


def test_all_play_bounds_and_symmetry(analysis):
    tm = analysis.team_match
    ap = all_play(tm, calibrate_draw_band(tm))
    assert ap["xpts_allplay"].between(0, 3).all()
    per_gw = ap.groupby("gw").apply(lambda d: (d["v_allplay"].sum(), d["d_allplay"].sum()), include_groups=False)
    assert all(v == d for v, d in per_gw)


def test_permutation_mean_equals_all_play(analysis):
    tm = analysis.team_match
    band = calibrate_draw_band(tm)
    summary, totals = schedule_permutation(tm, band, n_sim=4_000, seed=1)
    xpts = all_play(tm, band).groupby("team_id")["xpts_allplay"].sum().reindex(summary["team_id"])
    assert np.allclose(summary["pts_sim_moy"], xpts, atol=0.15)
    assert totals.shape == (4_000, tm["team_id"].nunique())


def test_luck_decomposition_adds_up(analysis):
    lk = analysis.luck
    assert np.allclose(lk["chance_conversion"] + lk["chance_calendrier"], lk["chance_totale"])


def test_mercato_scenarios_cover_all_teams(analysis):
    m = analysis.mercato
    assert len(m) == len(analysis.league.teams)
    assert (m["rang_min"] <= m["rang"]).all() and (m["rang"] <= m["rang_max"]).all()


def test_current_streak():
    from mpg.standings import current_streak

    assert current_streak("VDVV") == "2V"
    assert current_streak("NDDD") == "3D"
    assert current_streak("") == ""


def test_full_standings_columns(analysis, official):
    st = analysis.standings.set_index("team_id").sort_index()
    assert (st["rotaldos"] == official["rotaldos_alignes"]).all()
    assert (st["bp_mpg"] == official["buts_pour_mpg"]).all()
    assert (st["forme"] == official["forme"]).all()


def test_line_ratings_consistent_with_global(analysis):
    lines = analysis.lines.set_index("team_id")
    lu = analysis.lineups
    pitch = lu[lu["sur_terrain"] & lu["poste_groupe"].notna()]
    weighted = sum(lines[g] * lines[f"n_{g}"] for g in "GDMA") / sum(lines[f"n_{g}"] for g in "GDMA")
    assert np.allclose(weighted, pitch.groupby("team_id")["note_brute"].mean())


def test_next_fixtures_are_one_gameweek(analysis):
    nf = analysis.next_fixtures
    assert nf["gw"].nunique() == 1 and nf["gw"].iloc[0] == analysis.league.last_gw + 1
    assert len(nf) == len(analysis.league.teams) // 2


def test_strength_weights_validation(analysis):
    from mpg.strength import strength_index

    with pytest.raises(ValueError):
        strength_index(analysis.feature_set, {"inconnue": 1.0})
    with pytest.raises(ValueError):
        strength_index(analysis.feature_set, {"cote_11_max": 0.0})


def test_custom_mercato_weights_add_scenario(analysis):
    from mpg.mercato import mercato_ranking

    m, ranks = mercato_ranking(
        analysis.player_value, analysis.favourites.set_index("team_id")["cote_banc"], {"prix": 1}
    )
    assert "personnalisé" in ranks.columns
    assert m.iloc[0]["prix"] == m["prix"].max()


def test_derived_player_rates(analysis):
    p = analysis.league.players
    assert p["taux_jeu"].dropna().between(0, 1).all()
    assert (p["taux_titu"] <= p["taux_jeu"] + 1e-9).dropna().all()
    assert np.allclose((p["taux_titu"] * 100).round(), p["pct_titularisations"], atol=1, equal_nan=True)


def test_loader_without_optional_columns(tmp_path):
    import shutil

    from mpg.loader import DEFAULT_DATA_DIR, OPTIONAL_PLAYER_COLUMNS

    for f in DEFAULT_DATA_DIR.glob("*.csv"):
        shutil.copy(f, tmp_path / f.name)
    players = pd.read_csv(tmp_path / "players.csv").drop(columns=OPTIONAL_PLAYER_COLUMNS)
    players.to_csv(tmp_path / "players.csv", index=False)
    a = run(tmp_path, n_sim=200)
    assert a.league.players["taux_jeu"].isna().all()
    assert len(a.mercato) == len(a.league.teams)


def test_expected_absences_bounded(analysis):
    tm = analysis.team_match
    assert tm["absents_attendus"].between(0, 11).all()
