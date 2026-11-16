import pytest

from mpg import strength
from mpg.analysis import run
from mpg.forecast.evaluation import season_dirs
from mpg.loader import load_league

CURRENT = "en cours"
PAST = ["2024-2025_SRMEG7VW", "2025-2026_SRMEG7VW"]

EMPTY_ON_PAST_SEASONS = [
    "valeur_effectif_meur",
    "note_reelle_11",
    "note_reelle_effectif_mediane",
    "taux_titu_11",
    "disponibilite_effectif",
    "points_mpg_11",
]
KEPT_ON_PAST_SEASONS = ["11 titulaire seul", "profondeur d'abord", "production offensive"]

INDICE_FORCE_EN_COURS = {
    "Fc ratpi": 0.686156480159,
    "Nouvelle Energie": 0.415653162994,
    "Tractou'pelle": -0.560732307485,
    "Pictor FC": -0.43813618831,
    "FC CP": 0.396988009902,
    "ЦСКА": -0.545460818591,
    "FC 69latrik": -0.393735748378,
    "équipe de football": 0.10513288882,
    "ThoFessé": -0.373373763186,
    "USPionvillePusitanos": 1.123373551082,
}


@pytest.fixture(scope="module")
def dirs():
    found = season_dirs()
    assert [*found] == [*PAST, CURRENT]
    return found


@pytest.fixture(scope="module")
def features(dirs):
    return {name: strength.squad_features(load_league(d)) for name, d in dirs.items()}


@pytest.fixture(scope="module")
def analyses(dirs):
    return {name: run(d, n_sim=20) for name, d in dirs.items()}


def test_available_features_current_season_has_all(features):
    assert strength.available_features(features[CURRENT]) == list(strength.FEATURE_LABELS)


@pytest.mark.parametrize("season", PAST)
def test_available_features_past_seasons_miss_squad_data(features, season):
    absent = [c for c in strength.FEATURE_LABELS if c not in strength.available_features(features[season])]
    assert absent == EMPTY_ON_PAST_SEASONS


def test_available_features_ignores_unknown_columns_and_empty_ones(features):
    feats = features[CURRENT].assign(inconnue=1.0, note_reelle_11=float("nan"))
    available = strength.available_features(feats)
    assert "inconnue" not in available
    assert "note_reelle_11" not in available
    assert "cote_11_max" in available


def test_strength_scenarios_current_season_keeps_all(features):
    feats = strength.strength_index(features[CURRENT])
    pts = feats.set_index("team_id")["indice_force"]
    ranks, fit = strength.strength_scenarios(feats, pts)
    assert list(fit["scenario"]) == list(strength.SCENARIOS)
    assert list(ranks.columns) == ["team_id", *strength.SCENARIOS]


@pytest.mark.parametrize("season", PAST)
def test_strength_scenarios_past_seasons_drop_unavailable(features, season):
    feats = strength.strength_index(features[season])
    pts = feats.set_index("team_id")["indice_force"]
    ranks, fit = strength.strength_scenarios(feats, pts)
    kept = list(fit["scenario"])
    assert kept == KEPT_ON_PAST_SEASONS
    assert list(ranks.columns) == ["team_id", *kept]
    available = set(strength.available_features(feats))
    for name in kept:
        assert {c for c, w in strength.SCENARIOS[name].items() if w > 0} <= available


def test_strength_scenarios_without_any_scenario_left(features):
    feats = features[PAST[0]]
    pts = feats.set_index("team_id")["cote_11_max"]
    ranks, fit = strength.strength_scenarios(feats, pts, {"note": {"note_reelle_11": 1.0}})
    assert list(ranks.columns) == ["team_id"]
    assert len(ranks) == len(feats)
    assert fit.empty


def test_strength_scenarios_unknown_feature_still_raises(features):
    feats = features[CURRENT]
    with pytest.raises(ValueError, match="inconnues"):
        strength.strength_scenarios(feats, feats.set_index("team_id")["nb_joueurs"], {"x": {"inconnue": 1.0}})


def test_effectif_incomplet_flags_as_ba(analyses):
    fav = analyses[PAST[1]].favourites
    flagged = fav[fav["effectif_incomplet"]]
    assert list(flagged["team_name"]) == ["AS Ba"]
    assert flagged["formation_11_max"].isna().all()
    assert flagged["cote_11_max"].iloc[0] == 0
    assert not fav.loc[fav["team_name"] != "AS Ba", "effectif_incomplet"].any()


def test_effectif_incomplet_false_for_current_season(analyses):
    fav = analyses[CURRENT].favourites
    assert fav["effectif_incomplet"].dtype == bool
    assert not fav["effectif_incomplet"].any()


def test_effectif_incomplet_false_for_first_past_season(analyses):
    assert not analyses[PAST[0]].favourites["effectif_incomplet"].any()


def test_incomplete_team_keeps_its_expected_rank(features):
    feats = strength.strength_index(features[PAST[1]])
    as_ba = feats[feats["team_name"] == "AS Ba"].iloc[0]
    assert as_ba["rang_attendu"] == len(feats)
    assert as_ba["indice_force"] == pytest.approx(-2.007136260475, abs=1e-9)


def test_strength_index_unchanged_on_current_season(features):
    idx = strength.strength_index(features[CURRENT])
    got = dict(zip(idx["team_name"], idx["indice_force"], strict=True))
    assert got == pytest.approx(INDICE_FORCE_EN_COURS, abs=1e-9)


def test_strength_index_unchanged_with_default_loader():
    idx = strength.strength_index(strength.squad_features(load_league()))
    got = dict(zip(idx["team_name"], idx["indice_force"], strict=True))
    assert got == pytest.approx(INDICE_FORCE_EN_COURS, abs=1e-9)
