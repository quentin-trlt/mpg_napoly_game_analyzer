import json
import os
import time
import urllib.error

import pandas as pd
import pytest

from mpg import fpl


def element(eid: int, first: str, second: str, web: str, team: int, status: str = "a", chance=None) -> dict:
    return {
        "id": eid,
        "first_name": first,
        "second_name": second,
        "web_name": web,
        "known_name": "",
        "team": team,
        "element_type": 3,
        "status": status,
        "chance_of_playing_next_round": chance,
        "news": "",
        "minutes": 900,
        "starts": 10,
        "goals_scored": 2,
        "own_goals": 0,
        "expected_goals": "2.5",
        "expected_goals_per_90": "0.25",
    }


BOOTSTRAP = {
    "teams": [{"id": 1, "name": "Leeds"}, {"id": 2, "name": "Man City"}, {"id": 3, "name": "Spurs"}],
    "events": [{"id": 11, "is_next": True}],
    "elements": [
        element(1, "Daniel", "James", "James", 1),
        element(2, "James", "Justin", "Justin", 1),
        element(3, "Rúben", "dos Santos Gato Alves Dias", "Rúben", 2),
        element(4, "Phil", "Foden", "Foden", 2, status="d", chance=75),
        element(5, "Dominic", "Solanke-Mitchell", "Solanke", 3),
    ],
}


@pytest.fixture
def players() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_key": ["james_justin__leeds", "daniel_james__leeds", "ruben_dias__man_city", "phil_foden__man_city"]
            + ["dominic_solanke__tottenham", "ghost__leeds"],
            "joueur": ["James Justin", "Daniel James", "Rúben Dias", "Phil Foden", "Dominic Solanke", "Nobody Known"],
            "nom_data": ["J. Justin", "D. James", "R. Dias", "P. Foden", "D. Solanke", "N. Known"],
            "club": ["Leeds", "Leeds", "Man. City", "Man. City", "Tottenham", "Leeds"],
        }
    )


def test_elements_parses_status_and_numbers():
    els = fpl.elements(BOOTSTRAP)
    foden = els.set_index("element_id").loc[4]
    assert foden["fpl_club"] == "Man City" and foden["chance_next"] == 75 and foden["xg90"] == 0.25
    assert pd.isna(els.set_index("element_id").loc[1, "chance_next"])
    assert fpl.next_event(BOOTSTRAP) == 11


def test_match_players_one_to_one_with_club_names(players):
    m = fpl.match_players(players, fpl.elements(BOOTSTRAP)).set_index("player_key")
    assert m.loc["james_justin__leeds", "element_id"] == 2
    assert m.loc["daniel_james__leeds", "element_id"] == 1
    assert m.loc["ruben_dias__man_city", "element_id"] == 3
    assert m.loc["dominic_solanke__tottenham", "element_id"] == 5
    assert m.loc["ghost__leeds", "methode"] == "non_apparie" and pd.isna(m.loc["ghost__leeds", "element_id"])
    assert m["element_id"].dropna().is_unique


def test_match_players_override_wins(players):
    m = fpl.match_players(players, fpl.elements(BOOTSTRAP), overrides={"daniel_james__leeds": 2})
    m = m.set_index("player_key")
    assert m.loc["daniel_james__leeds", "element_id"] == 2
    assert m.loc["daniel_james__leeds", "methode"] == "manuel"
    assert m.loc["james_justin__leeds", "element_id"] != 2


def test_history_parses_rounds():
    summary = {
        "history": [
            {
                "round": 10,
                "minutes": 90,
                "starts": 1,
                "goals_scored": 1,
                "own_goals": 0,
                "expected_goals": "0.40",
                "kickoff_time": "2026-11-07T15:00:00Z",
            }
        ]
    }
    h = fpl.history(summary)
    assert h.loc[0, "xg"] == 0.4 and h.loc[0, "round"] == 10
    assert fpl.history({"history": []}).empty


def test_client_uses_fresh_cache_without_network(tmp_path, monkeypatch):
    (tmp_path / "bootstrap-static.json").write_text(json.dumps(BOOTSTRAP))

    def boom(*args, **kwargs):
        raise AssertionError("pas d'appel réseau attendu")

    monkeypatch.setattr(fpl.urllib.request, "urlopen", boom)
    assert fpl.FplClient(cache_dir=tmp_path).bootstrap()["events"][0]["id"] == 11


def test_client_falls_back_to_stale_cache(tmp_path, monkeypatch):
    file = tmp_path / "bootstrap-static.json"
    file.write_text(json.dumps(BOOTSTRAP))
    old = time.time() - 10 * 24 * 3600
    os.utime(file, (old, old))

    def offline(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(fpl.urllib.request, "urlopen", offline)
    assert fpl.FplClient(cache_dir=tmp_path).bootstrap()["teams"][0]["name"] == "Leeds"
    with pytest.raises(fpl.FplError):
        fpl.FplClient(cache_dir=tmp_path / "vide").bootstrap()
