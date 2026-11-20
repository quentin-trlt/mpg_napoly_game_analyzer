import pytest

from mpg.analysis import run
from mpg.forecast.evaluation import season_dirs
from mpg.history import career, head_to_head, honours
from mpg.seasons import list_seasons


@pytest.fixture(scope="module")
def loaded():
    return [(s, run(s.path, n_sim=20)) for s in list_seasons()]


@pytest.fixture(scope="module")
def car(loaded):
    return career(loaded)


@pytest.fixture(scope="module")
def hon(loaded):
    return honours(loaded)


def test_seasons_cover_the_three_folders(loaded):
    assert [s.key for s, _ in loaded] == ["2024-2025", "2025-2026", "2026-2027"]
    assert len(season_dirs()) == 3


def test_career_matches_standings(loaded, car):
    for season, a in loaded:
        mine = car[car["saison"] == season.key].set_index("team_id")
        table = a.standings.set_index("team_id")
        assert set(mine.index) == set(table.index)
        assert (mine["pts"] == table["pts"]).all()
        assert (mine["rang"] == table["rang"]).all()
        assert (mine["j"] == table["j"]).all()
        assert (mine["n_equipes"] == len(table)).all()
        assert mine["en_cours"].eq(season.current).all()


def test_career_has_one_row_per_coach_and_season(car):
    assert not car.duplicated(["saison", "coach"]).any()


def test_alias_is_folded_into_the_canonical_coach(car):
    assert "vincentprono92" not in set(car["coach"])
    assert car[car["coach"] == "vincentmouly"]["saison"].nunique() == 3


def test_honours_are_the_sum_of_career(car, hon):
    by_coach = car.groupby("coach").agg(
        saisons=("saison", "nunique"), matchs=("j", "sum"), pts=("pts", "sum"), chance=("chance", "sum")
    )
    indexed = hon.set_index("coach")
    assert set(indexed.index) == set(by_coach.index)
    for column in by_coach:
        assert indexed[column].sort_index().tolist() == pytest.approx(by_coach[column].sort_index().tolist())
    assert indexed["ppm"].tolist() == pytest.approx((indexed["pts"] / indexed["matchs"]).tolist())


def test_honours_are_sorted_by_points_per_match(hon):
    assert hon["ppm"].is_monotonic_decreasing


def test_titles_count_finished_seasons_only(loaded, car, hon):
    finished = [s for s, _ in loaded if not s.current]
    assert hon["titres"].sum() == len(finished)
    for season in finished:
        champion = car[(car["saison"] == season.key) & (car["rang"] == 1)]
        assert len(champion) == 1
        assert hon.set_index("coach").at[champion.iloc[0]["coach"], "titres"] >= 1


def test_best_rank_comes_with_its_season(car, hon):
    for row in hon.itertuples():
        mine = car[car["coach"] == row.coach]
        assert row.meilleur_rang == mine["rang"].min()
        assert row.meilleure_saison in set(mine[mine["rang"] == row.meilleur_rang]["saison"])


@pytest.mark.parametrize("coach", ["ketXfentanyl", "vincentmouly"])
def test_head_to_head_has_a_mirror_for_every_match(loaded, coach):
    mine = head_to_head(loaded, coach)
    assert not mine.empty
    assert coach not in set(mine["adversaire"])
    opposite = {"V": "D", "D": "V", "N": "N"}
    for row in mine.itertuples():
        theirs = head_to_head(loaded, row.adversaire)
        mirror = theirs[(theirs["saison"] == row.saison) & (theirs["gw"] == row.gw) & (theirs["adversaire"] == coach)]
        assert len(mirror) == 1
        m = mirror.iloc[0]
        assert m["resultat"] == opposite[row.resultat]
        assert (m["bp"], m["bc"]) == (row.bc, row.bp)
        assert m["domicile"] != row.domicile


def test_head_to_head_covers_every_match_of_the_coach(loaded, car):
    coach = "ketXfentanyl"
    assert len(head_to_head(loaded, coach)) == car[car["coach"] == coach]["j"].sum()


def test_unknown_coach_raises(loaded):
    with pytest.raises(ValueError, match="Coach inconnu"):
        head_to_head(loaded, "personne")


@pytest.mark.parametrize("function", [career, honours])
def test_empty_seasons_raise(function):
    with pytest.raises(ValueError, match="Aucune saison"):
        function([])


def test_head_to_head_empty_seasons_raise():
    with pytest.raises(ValueError, match="Aucune saison"):
        head_to_head([], "ketXfentanyl")
