import pandas as pd
import streamlit as st

from app import charts
from mpg.forecast.models import EloModel, PoissonModel, StructuralModel

BASE_LABEL = "Pronostic de base"
NON_BREAKING_HYPHEN = "‑"
FILM_INTRO = "Chances recalculées après chaque journée avec les seuls résultats connus à ce moment."
MODEL_KEYS = {EloModel: "modele_elo", PoissonModel: "modele_poisson", StructuralModel: "modele_structurel"}
NUMBER_WORDS = {2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six"}
FILM_METRICS = {
    "p_titre": ("Titre", "Chances de titre"),
    "p_podium": ("Podium", "Chances de podium"),
    "p_dernier": ("Dernier", "Chances de finir dernier"),
}


def score(text: object) -> str:
    return str(text).replace("-", NON_BREAKING_HYPHEN)


def count_word(n: int) -> str:
    return NUMBER_WORDS.get(n, str(n))


def model_keys(draws) -> list[str]:
    return [MODEL_KEYS[type(m)] for m in draws.models if type(m) in MODEL_KEYS]


def forecast_meta(a, draws) -> dict:
    poisson = next((m for m in draws.models if isinstance(m, PoissonModel)), None)
    struct = next((m for m in draws.models if isinstance(m, StructuralModel)), None)
    meta = {
        **a.meta,
        "n_saisons": draws.ensemble.shape[0],
    }
    if poisson is not None:
        meta["tau"] = poisson.tau
    if struct is not None:
        meta["rotaldo"] = struct.rotaldo_note
        meta["sigma"] = struct.sigma_match
        meta["note_slope"] = struct.link.b
    return meta


def error_gain(model_rps: float, reference_rps: float) -> float | None:
    """Part d'erreur en moins que le pronostic de base (négative si le modèle fait pire)."""
    if reference_rps != reference_rps or model_rps != model_rps or reference_rps <= 0:
        return None
    return 1 - model_rps / reference_rps


def gain_phrase(gain: float) -> str:
    more_or_less = "en moins" if gain > 0 else "en plus"
    return f"{abs(gain) * 100:.0f} % d'erreur {more_or_less} que le pronostic de base"


def film(history: pd.DataFrame, names: dict[int, str], team_id: int) -> None:
    metric = st.segmented_control(
        "Courbe",
        options=list(FILM_METRICS),
        default="p_titre",
        required=True,
        key="hist_metric",
        format_func=lambda k: FILM_METRICS[k][0],
    )
    charts.show(charts.title_history(history, names, team_id, metric, FILM_METRICS[metric][1]))
