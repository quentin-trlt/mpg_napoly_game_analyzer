import shutil

import pandas as pd
import pytest

from mpg.analysis import run
from mpg.coaching import bonus_key, bonus_usage, mirrored_bonuses, remaining_bonuses
from mpg.forecast.evaluation import season_dirs
from mpg.loader import DEFAULT_DATA_DIR, load_league


def _bonus(rows):
    return pd.DataFrame(rows, columns=["team_id", "gw", "bonus", "cible_affiche"])


def test_bonus_key_ignores_accents_case_and_article():
    assert bonus_key("La valise à Nanard") == bonus_key("Valise a nanard")
    assert bonus_key(" McDo+ ") == "mcdo+"


def test_remaining_is_stock_minus_used():
    stock = pd.DataFrame({"bonus": ["McDo+", "Suarez", "La valise à Nanard"], "quantite": [3, 2, 1]})
    used = _bonus(
        [
            (1, 1, "McDo+", "A"),
            (1, 3, "McDo+", "B"),
            (1, 2, "Valise à Nanard", None),
            (1, 2, "Capitaine", "C"),
            (1, 2, "4 défenseurs", "Déf."),
            (2, 1, "Suarez", "G"),
        ]
    )
    r = remaining_bonuses(used, stock, [1, 2]).set_index(["team_id", "bonus"])
    assert r.loc[(1, "McDo+"), "restants"] == 1
    assert r.loc[(1, "McDo+"), "journees"] == "J1, J3"
    assert r.loc[(1, "La valise à Nanard"), "restants"] == 0
    assert r.loc[(1, "Suarez"), "restants"] == 2
    assert r.loc[(2, "Suarez"), "restants"] == 1
    assert not r.reset_index()["bonus"].isin(["Capitaine", "4 défenseurs"]).any()


def test_bonus_outside_stock_is_flagged():
    stock = pd.DataFrame({"bonus": ["McDo+"], "quantite": [1]})
    r = remaining_bonuses(_bonus([(1, 1, "Mystère", "X")]), stock, [1]).set_index("bonus")
    assert r.loc["Mystère", "hors_dotation"] and r.loc["Mystère", "restants"] == -1


def test_real_data_matches_bonus_file():
    a = run(n_sim=100)
    br = a.bonus_remaining
    stock = a.league.bonus_stock
    assert len(br) == len(a.league.teams) * len(stock)
    assert (br["restants"] >= 0).all()
    pictor = br[(br["team_id"] == 3) & (br["bonus"] == "McDo+")].iloc[0]
    assert pictor["utilises"] == 3 and pictor["restants"] == 0
    assert br["utilises"].sum() == (~a.league.bonus["bonus"].isin(["Capitaine", "4 défenseurs", "5 défenseurs"])).sum()


def test_stock_file_is_optional(tmp_path):
    for f in DEFAULT_DATA_DIR.glob("*.csv"):
        if f.name != "bonus_stock.csv":
            shutil.copy(f, tmp_path / f.name)
    assert load_league(tmp_path).bonus_stock is None
    assert run(tmp_path, n_sim=100).bonus_remaining is None


STOCK = pd.DataFrame({"bonus": ["Suarez", "Miroir", "McDo+"], "quantite": [2, 1, 1]})
KNOWN_MIRRORS = [
    ("2024-2025_SRMEG7VW", 0, "Suarez"),
    ("2024-2025_SRMEG7VW", 2, "La valise à Nanard"),
    ("2024-2025_SRMEG7VW", 4, "Zahia"),
    ("2024-2025_SRMEG7VW", 5, "Chapron rouge"),
    ("2025-2026_SRMEG7VW", 6, "Tonton Pat"),
]


def _match(rows):
    return pd.DataFrame(rows, columns=["match_id", "team_id", "gw", "bonus", "cible_affiche"])


def _restants(frame, team, name, **kwargs):
    r = remaining_bonuses(frame, STOCK, [1, 2], **kwargs).set_index(["team_id", "bonus"])
    return r.loc[(team, name)]


def test_mirrored_simple_return():
    frame = _match(
        [
            ("m1", 1, 6, "Suarez", "Sels"),
            ("m1", 2, 6, "Miroir", None),
            ("m1", 2, 6, "Suarez", "Sánchez"),
        ]
    )
    assert mirrored_bonuses(frame).tolist() == [False, False, True]
    assert _restants(frame, 1, "Suarez")["utilises"] == 1
    assert _restants(frame, 2, "Suarez")["utilises"] == 0
    assert _restants(frame, 2, "Miroir")["utilises"] == 1
    assert _restants(frame, 2, "Miroir")["restants"] == 0


def test_mirror_without_opponent_bonus_is_counted():
    frame = _match([("m1", 2, 3, "Miroir", None), ("m1", 1, 3, "McDo+", "A")])
    assert not mirrored_bonuses(frame).any()
    assert _restants(frame, 2, "Miroir")["utilises"] == 1
    assert _restants(frame, 1, "McDo+")["utilises"] == 1


def test_mirror_other_match_is_not_affected():
    frame = _match(
        [
            ("m1", 1, 6, "Suarez", "Sels"),
            ("m2", 2, 7, "Miroir", None),
            ("m2", 2, 7, "Suarez", "Sánchez"),
        ]
    )
    assert _restants(frame, 2, "Suarez")["utilises"] == 1


def test_own_bonus_stays_counted_when_mirroring():
    frame = _match(
        [
            ("m1", 1, 6, "Suarez", "Sels"),
            ("m1", 2, 6, "Miroir", None),
            ("m1", 2, 6, "Suarez", "Sánchez"),
            ("m1", 2, 6, "Suarez", "Autre"),
        ]
    )
    assert mirrored_bonuses(frame).sum() == 1
    assert _restants(frame, 2, "Suarez")["utilises"] == 1
    assert _restants(frame, 1, "Suarez")["utilises"] == 1


def test_mirror_never_returns_captain_or_defenders():
    frame = _match(
        [
            ("m1", 1, 6, "Capitaine", "A"),
            ("m1", 1, 6, "4 défenseurs", "Déf."),
            ("m1", 2, 6, "Miroir", None),
            ("m1", 2, 6, "Capitaine", "B"),
            ("m1", 2, 6, "4 défenseurs", "Déf."),
        ]
    )
    assert not mirrored_bonuses(frame).any()


def test_without_match_id_nothing_is_mirrored():
    frame = _bonus([(1, 6, "Suarez", "Sels"), (2, 6, "Miroir", None), (2, 6, "Suarez", "Sánchez")])
    flags = mirrored_bonuses(frame)
    assert flags.index.equals(frame.index) and not flags.any()
    assert _restants(frame, 2, "Suarez")["utilises"] == 1


def test_ignore_mirrored_false_restores_old_count():
    frame = _match(
        [
            ("m1", 1, 6, "Suarez", "Sels"),
            ("m1", 2, 6, "Miroir", None),
            ("m1", 2, 6, "Suarez", "Sánchez"),
        ]
    )
    old = _restants(frame, 2, "Suarez", ignore_mirrored=False)
    assert old["utilises"] == 1 and old["journees"] == "J6" and old["cibles"] == "Sánchez"
    new = _restants(frame, 2, "Suarez")
    assert new["utilises"] == 0 and new["journees"] == "" and new["cibles"] == ""


def test_bonus_usage_skips_mirrored_line():
    frame = _match(
        [
            ("m1", 1, 6, "Suarez", "Sels"),
            ("m1", 2, 6, "Miroir", None),
            ("m1", 2, 6, "Suarez", "Sánchez"),
        ]
    ).assign(effet=["-1pt", None, "-1pt"], effet_pts=[-1.0, None, -1.0])
    tm = pd.DataFrame(
        {
            "match_id": ["m1", "m1"],
            "team_id": [1, 2],
            "gw": [6, 6],
            "pts": [1, 1],
            "resultat": ["N", "N"],
            "opp_name": ["B", "A"],
        }
    )
    assert bonus_usage(frame, tm)["team_id"].tolist() == [1]


@pytest.fixture(scope="module")
def seasons():
    return {name: load_league(path) for name, path in season_dirs().items()}


def test_remaining_never_negative_on_all_seasons(seasons):
    for name, league in seasons.items():
        teams = sorted(league.teams["team_id"])
        assert (remaining_bonuses(league.bonus, league.bonus_stock, teams)["restants"] >= 0).all(), name
        for g in range(1, league.last_gw + 1):
            r = remaining_bonuses(league.bonus[league.bonus["gw"] <= g], league.bonus_stock, teams)
            assert (r["restants"] >= 0).all(), f"{name} J{g}"


@pytest.mark.parametrize(("season", "team", "name"), KNOWN_MIRRORS)
def test_known_mirror_cases(seasons, season, team, name):
    league = seasons[season]
    teams = sorted(league.teams["team_id"])
    r = remaining_bonuses(league.bonus, league.bonus_stock, teams).set_index(["team_id", "bonus"])
    assert r.loc[(team, name), "utilises"] == 1
    assert r.loc[(team, "Miroir"), "utilises"] >= 1
    assert mirrored_bonuses(league.bonus)[league.bonus["team_id"] == team].sum() == 1


def test_current_season_unchanged(seasons):
    league = seasons["en cours"]
    teams = sorted(league.teams["team_id"])
    assert not mirrored_bonuses(league.bonus).any()
    new = remaining_bonuses(league.bonus, league.bonus_stock, teams)
    old = remaining_bonuses(league.bonus, league.bonus_stock, teams, ignore_mirrored=False)
    pd.testing.assert_frame_equal(new, old)
