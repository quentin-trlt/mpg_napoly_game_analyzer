import pandas as pd

from app.views.journee import _kpis, _score, likely_rank


def _rank_probs() -> pd.DataFrame:
    return pd.DataFrame(
        {1: [0.56, 0.03], 2: [0.25, 0.05], 3: [0.19, 0.50], 4: [0.0, 0.42]},
        index=pd.Index([7, 9], name="team_id"),
    )


def test_likely_rank_is_the_mode_of_the_rank_distribution():
    probs = _rank_probs()
    assert likely_rank(probs, 7) == (1, 0.56)
    assert likely_rank(probs, 9) == (3, 0.50)


def test_kpi_shows_the_most_likely_rank_not_the_mean_rank():
    me = pd.Series({"p_titre": 0.56, "p_podium": 0.99, "pts_moy": 30, "pts_p05": 25, "pts_p95": 35, "rang_moy": 1.7})
    kpis = _kpis(me, 1, 13, likely_rank(_rank_probs(), 7))
    assert kpis[3]["value"] == "1er"
    assert kpis[3]["sub"] == "dans 56 % des cas"


def test_score_cannot_wrap_on_the_hyphen():
    assert "-" not in _score("2-1")
    assert _score("2-1").replace("‑", "-") == "2-1"
