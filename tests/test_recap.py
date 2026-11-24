import re
from dataclasses import replace

import pytest

from app.views.matchs import recap_text
from mpg.analysis import Analysis, run
from mpg.forecast.evaluation import frozen_matches, season_dirs

SEASONS = list(season_dirs())


@pytest.fixture(scope="module")
def analyses() -> dict[str, Analysis]:
    return {name: run(path, n_sim=20) for name, path in season_dirs().items()}


@pytest.mark.parametrize("season", SEASONS)
def test_recap_structure(analyses, season):
    a = analyses[season]
    for gw in sorted(a.team_match["gw"].unique()):
        lines = recap_text(a, gw, None).split("\n")
        n_matches = int(a.team_match[a.team_match["gw"] == gw]["domicile"].sum())
        assert lines[0] == f"J{gw} en bref"
        assert not any(line.startswith("Surprise") for line in lines)
        assert all(re.search(r" \d+-\d+ ", line) for line in lines[1 : 1 + n_matches])
        has_best = not a.league.best_players[a.league.best_players["gw"] == gw].empty
        assert any(line.startswith("Homme de la journée") for line in lines) == has_best


def test_recap_surprise_saison_en_cours(analyses):
    a = analyses["en cours"]
    fm = frozen_matches(a)
    gw = int(fm[fm["joue"]]["gw"].max())
    text = recap_text(a, gw, fm)
    surprise = [line for line in text.split("\n") if line.startswith("Surprise")]
    assert len(surprise) == 1
    assert " %" in surprise[0]


def test_recap_garde_les_points_du_nom_du_joueur(analyses):
    a = analyses["en cours"]
    bp = a.league.best_players.copy()
    bp.loc[bp["gw"] == 1, "joueur"] = "L. Goretzka"
    bp.loc[bp["gw"] == 1, "note"] = 8.5
    patched = replace(a, league=replace(a.league, best_players=bp))
    line = next(x for x in recap_text(patched, 1, None).split("\n") if x.startswith("Homme"))
    assert line.startswith("Homme de la journée : L. Goretzka (")
    assert line.endswith("note 8,5")
