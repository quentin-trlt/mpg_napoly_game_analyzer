import math

import pytest

from mpg.analysis import Analysis, key_figures, run, team_card
from mpg.forecast.evaluation import season_dirs

SEASONS = list(season_dirs())
CURRENT = "en cours"
MISSING_IN_PAST = ("valeur_actuelle", "valeur_effectif", "ratio_valeur_prix")
MISSING_PL_STATS = ("note_reelle_mediane", "disponibilite", "indisponibles", "ga_saison")


@pytest.fixture(scope="module")
def analyses() -> dict[str, Analysis]:
    return {name: run(path, n_sim=20) for name, path in season_dirs().items()}


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)


@pytest.mark.parametrize("season", SEASONS)
def test_key_figures_never_fail(analyses, season):
    kf = key_figures(analyses[season])
    assert kf["buteur_mpg"]["joueurs"]
    assert kf["buteur_mpg"]["buts"] > 0
    assert kf["roi_rotaldos"]["equipes"]
    if season == CURRENT:
        assert kf["buteur_pl"]["joueurs"]
        assert kf["buteur_pl"]["buts"] > 0
    else:
        assert kf["buteur_pl"] is None


@pytest.mark.parametrize("season", SEASONS)
def test_meta_prix(analyses, season):
    assert analyses[season].meta["prix"] == ("cote" if season == CURRENT else "enchere")


@pytest.mark.parametrize("season", SEASONS)
def test_team_card_has_no_nan(analyses, season):
    a = analyses[season]
    for team_id in a.standings["team_id"]:
        card = team_card(a, int(team_id))
        assert not [k for k, v in card.items() if _is_nan(v)]
        if season == CURRENT:
            assert not [k for k, v in card.items() if v is None]
        else:
            for key in (*MISSING_IN_PAST, *MISSING_PL_STATS):
                assert card[key] is None, key


def test_team_card_incomplete_squad_hides_expected_rank(analyses):
    a = analyses[CURRENT]
    favourites = a.favourites.assign(effectif_incomplet=lambda d: d["team_id"] == 6)
    card = team_card(Analysis(**{**a.__dict__, "favourites": favourites}), 6)
    assert card["rang_attendu"] is None
    assert team_card(a, 6)["rang_attendu"] is not None


def test_current_season_key_figures_unchanged(analyses):
    kf = key_figures(analyses[CURRENT])
    assert kf["leader"] == {"equipe": "Nouvelle Energie", "coach": "Emilinho_", "pts": 13, "ecart_2e": 1}
    assert kf["buteur_pl"] == {"joueurs": ["Erling Haaland"], "buts": 9, "equipes": ["FC CP"]}
    assert kf["buteur_mpg"] == {"joueurs": ["Nicolas Jackson"], "buts": 5}
    assert kf["roi_rotaldos"] == {"equipes": ["ЦСКА"], "rotaldos": 10}


def test_current_season_team_card_unchanged(analyses):
    card = team_card(analyses[CURRENT], 6)
    assert card["serie"] == "1D"
    for key, expected in {
        "rang": 5,
        "pts": 8,
        "budget_paye": 500.0,
        "valeur_actuelle": 252.0,
        "valeur_effectif": 252.0,
        "ratio_valeur_prix": 0.504,
        "part_top3": 0.306,
        "note_reelle_mediane": 5.1,
        "note_mpg_moy": 5.254545454545455,
        "disponibilite": 0.8893,
        "indisponibles": 1,
        "ga_saison": 26.0,
        "rang_attendu": 7,
        "rang_mercato": 3,
    }.items():
        assert card[key] == pytest.approx(expected), key
