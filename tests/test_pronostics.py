import math

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app.views import forecast_common, suivi
from mpg.forecast.evaluation import season_dirs
from mpg.forecast.season import REFERENCE

PAST_SEASONS = [name for name in season_dirs() if name != "en cours"]
CURRENT_VOLETS = {
    "journee": {"get_forecast_light", "get_frozen"},
    "fin-de-saison": {"get_forecast_light", "get_title_history"},
    "et-si": {"get_forecast_light"},
    "fiabilite": {"get_forecast_light", "get_frozen", "get_backtest"},
}


@pytest.mark.parametrize(
    ("won", "played", "expected"),
    [
        (4, 5, "J5 : 4 favoris sur 5 ont gagné"),
        (1, 5, "J5 : 1 favori sur 5 a gagné"),
        (0, 5, "J5 : 0 favori sur 5 a gagné"),
        (5, 5, "J5 : 5 favoris sur 5 ont gagné"),
    ],
)
def test_verdict_accorde_le_pluriel(won, played, expected):
    assert suivi.verdict(5, won, played) == expected


def test_error_gain():
    assert math.isclose(forecast_common.error_gain(0.19, 0.26), 1 - 0.19 / 0.26)
    assert forecast_common.error_gain(0.30, 0.26) < 0
    assert forecast_common.error_gain(0.2, float("nan")) is None
    assert forecast_common.error_gain(0.2, 0.0) is None


def test_gain_phrase_arrondit_en_pourcentage():
    assert forecast_common.gain_phrase(0.2712) == "27 % d'erreur en moins que le pronostic de base"
    assert forecast_common.gain_phrase(-0.05) == "5 % d'erreur en plus que le pronostic de base"


def test_count_word():
    assert [forecast_common.count_word(n) for n in (3, 4, 9)] == ["trois", "quatre", "9"]


def test_model_keys_suit_les_modeles_presents():
    class Draws:
        models = [forecast_common.EloModel(), forecast_common.PoissonModel()]

    assert forecast_common.model_keys(Draws()) == ["modele_elo", "modele_poisson"]


def _frozen(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["modele", "joue", "favori_gagne", "p_issue_reelle", "rps"])


def test_season_verdict_compte_favoris_et_gain():
    fm = _frozen(
        [
            ("Ensemble", True, 1.0, 0.5, 0.2),
            ("Ensemble", True, 0.0, 0.2, 0.4),
            ("Ensemble", False, float("nan"), float("nan"), float("nan")),
            (REFERENCE, True, 1.0, 0.3, 0.4),
            (REFERENCE, True, 1.0, 0.3, 0.4),
        ]
    )
    summary = suivi.season_verdict(fm)
    assert summary["matchs"] == 2
    assert summary["favoris"] == 1
    assert math.isclose(summary["p_reelle"], 0.35)
    assert math.isclose(summary["gain"], 1 - 0.3 / 0.4)


def test_season_verdict_sans_match_joue():
    assert suivi.season_verdict(_frozen([("Ensemble", False, float("nan"), float("nan"), float("nan"))])) is None


def test_season_sentences_en_mots():
    text = suivi._season_sentences({"matchs": 25, "favoris": 14, "p_reelle": 0.4, "gain": 0.27})
    assert "25 matchs" in text
    assert "14 fois (56 %)" in text
    assert "27 % d'erreur en moins que le pronostic de base" in text
    assert "RPS" not in text


def _order_app(volet: str, data_dir: str) -> None:
    import streamlit as st

    from app import pages
    from app.views import predictions, suivi
    from mpg.analysis import run

    events: list[str] = []
    targets = [
        (predictions, "volet_title"),
        (predictions, "get_forecast_light"),
        (predictions, "get_frozen"),
        (predictions, "get_title_history"),
        (suivi, "volet_title"),
        (suivi, "get_forecast_light"),
        (suivi, "get_frozen"),
        (suivi, "get_backtest"),
    ]
    originals = [(module, name, getattr(module, name)) for module, name in targets]

    def recording(name, function):
        def wrapper(*args, **kwargs):
            events.append(name)
            return function(*args, **kwargs)

        return wrapper

    a = run(data_dir, n_sim=200)
    try:
        for module, name, function in originals:
            setattr(module, name, recording(name, function))
        pages.pronostics(a, int(a.standings.iloc[0]["team_id"]))
    finally:
        for module, name, function in originals:
            setattr(module, name, function)
    st.session_state["events"] = events


@pytest.mark.parametrize("volet", CURRENT_VOLETS)
def test_titre_de_volet_avant_tout_calcul(volet):
    at = AppTest.from_function(_order_app, args=(volet, str(season_dirs()["en cours"])), default_timeout=240)
    at.query_params["volet"] = volet
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
    events = at.session_state["events"]
    assert events[0] == "volet_title"
    assert set(events[1:]) == CURRENT_VOLETS[volet]
    assert at.get("button_group")[0].value == volet


@pytest.mark.parametrize("season", PAST_SEASONS)
def test_saison_passee_un_seul_volet_le_film(season):
    at = AppTest.from_function(_order_app, args=("fiabilite", str(season_dirs()[season])), default_timeout=240)
    at.query_params["volet"] = "fiabilite"
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
    assert at.session_state["events"] == ["volet_title", "get_title_history"]
    assert [g.key for g in at.get("button_group")] == ["hist_metric"]
    assert "volet" not in at.query_params
    assert any("Pas de pronostic figé" in c.value for c in at.caption)
    assert len(at.get("plotly_chart")) == 1
