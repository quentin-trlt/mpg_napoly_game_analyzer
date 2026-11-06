import shutil

import pandas as pd

from mpg.analysis import run
from mpg.coaching import bonus_key, remaining_bonuses
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
