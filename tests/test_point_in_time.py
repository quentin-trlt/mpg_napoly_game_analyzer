import dataclasses
import shutil

import numpy as np
import pandas as pd
import pytest

from mpg import point_in_time as pit
from mpg.analysis import run
from mpg.forecast.season import build_context
from mpg.loader import DEFAULT_DATA_DIR, DataSchemaError, load_league
from mpg.premier_league import pl_gw_for


@pytest.fixture(scope="module")
def analysis():
    return run(n_sim=50)


@pytest.fixture(scope="module")
def league(analysis):
    return analysis.league


def test_player_match_notes_loaded_with_kickoff_dates(league):
    notes = league.player_match_notes
    assert notes is not None
    assert notes["date"].notna().equals(notes["pl_match_id"].notna())
    assert (notes["note"].notna() == (notes["a_joue"] == 1)).all()


def test_note_without_appearance_is_rejected(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIR, data, ignore=shutil.ignore_patterns("fpl_cache", "fpl_snapshots"))
    notes = pd.read_csv(data / "player_match_notes.csv")
    row = notes.index[notes["a_joue"] == 1][0]
    notes.loc[row, "a_joue"] = 0
    notes.to_csv(data / "player_match_notes.csv", index=False)
    with pytest.raises(DataSchemaError, match="a_joue"):
        load_league(data)


def test_totals_over_all_notes_match_players_csv(league):
    totals = pit.season_totals(league.player_match_notes)
    p = league.players.set_index("player_key").join(totals.add_suffix("_pmn"))
    assert np.allclose(p["note_moy_reelle"], p["note_moy_reelle_pmn"], atol=0.051, equal_nan=True)
    for col in ("matchs_joues", "matchs_titulaire", "buts_reels_saison", "passes_decisives_saison"):
        assert (p[col] == p[f"{col}_pmn"]).all(), col
    assert ((p["matchs_club"] - p["matchs_club_pmn"]).abs() <= 1).all()


def test_notes_before_stop_at_the_kickoff(league):
    for g in range(1, league.last_gw + 1):
        before = pit.notes_before(league, g)
        assert before["date"].max() < pit.pl_kickoff(league, g)


def test_players_before_ignore_later_notes(league):
    notes = league.player_match_notes.copy()
    later = notes["date"] >= pit.pl_kickoff(league, 2)
    notes.loc[later & notes["note"].notna(), "note"] = 10.0
    notes.loc[later, "buts"] = 3
    tampered = dataclasses.replace(league, player_match_notes=notes)
    pd.testing.assert_frame_equal(pit.players_before(tampered, 2), pit.players_before(league, 2))


def test_past_context_uses_only_earlier_data(analysis, league):
    ctx = build_context(analysis, 1)
    p = ctx.players.set_index("player_key")
    assert p["matchs_club"].max() <= pl_gw_for(league, 2) - 1
    assert p["matchs_club"].max() < league.players["matchs_club"].max()
    assert (p["statut_performance"] == "ok").all()
    assert not np.allclose(
        ctx.strength.sort_index(), analysis.favourites.set_index("team_id")["indice_force"].sort_index()
    )


def test_current_context_unchanged(analysis):
    ctx = build_context(analysis)
    pd.testing.assert_frame_equal(ctx.players.drop(columns="taux_jeu"), analysis.player_value.drop(columns="taux_jeu"))
    pd.testing.assert_series_equal(ctx.strength, analysis.favourites.set_index("team_id")["indice_force"])


def test_without_match_notes_falls_back_to_current_players(analysis):
    bare = dataclasses.replace(
        analysis, league=dataclasses.replace(analysis.league, player_match_notes=None, fpl_players=None)
    )
    ctx = build_context(bare, 1)
    pd.testing.assert_frame_equal(ctx.players, analysis.player_value)
