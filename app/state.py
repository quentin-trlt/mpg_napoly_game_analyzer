from pathlib import Path

import streamlit as st

from mpg.analysis import Analysis, run
from mpg.forecast import evaluation
from mpg.forecast.evaluation import backtest, backtest_summary, frozen_matches, frozen_seasons
from mpg.forecast.season import build_context, ensemble_draws, fixtures_after, simulate_season, title_odds_history
from mpg.loader import DEFAULT_DATA_DIR

TEAM_KEY = "team_id"


def _data_signature(data_dir: Path) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((p.name, p.stat().st_mtime) for p in data_dir.glob("*.csv")))


@st.cache_resource(show_spinner="Calcul des statistiques…")
def _cached(signature: tuple, data_dir: str) -> Analysis:
    return run(data_dir)


def data_signature(data_dir: Path = DEFAULT_DATA_DIR) -> tuple:
    return _data_signature(data_dir)


def get_analysis(data_dir: Path = DEFAULT_DATA_DIR) -> Analysis:
    return _cached(_data_signature(data_dir), str(data_dir))


def selected_team(a: Analysis) -> int:
    if TEAM_KEY not in st.session_state:
        st.session_state[TEAM_KEY] = int(a.standings.iloc[0]["team_id"])
    return int(st.session_state[TEAM_KEY])


def team_selector(a: Analysis) -> int:
    names = a.league.team_names
    order = a.standings["team_id"].astype(int).tolist()
    current = selected_team(a)
    st.selectbox(
        "Mon équipe",
        options=order,
        index=order.index(current),
        format_func=lambda t: names[t],
        key=TEAM_KEY,
        help="Mise en avant dans tous les graphiques de l'app.",
    )
    return int(st.session_state[TEAM_KEY])


@st.cache_resource(show_spinner="Simulation de la fin de saison…")
def _forecast(signature: tuple, frozen_signature: tuple, data_dir: str) -> dict:
    a = _cached(signature, data_dir)
    fixtures = fixtures_after(a, a.league.last_gw)
    draws = ensemble_draws(build_context(a), fixtures, n_draws=4000) if not fixtures.empty else None
    bt = backtest(a)
    return {
        "draws": draws,
        "baseline": simulate_season(a, draws) if draws is not None else None,
        "history": title_odds_history(a),
        "backtest": bt,
        "backtest_summary": backtest_summary(bt),
        "frozen_matches": frozen_matches(a),
        "frozen_seasons": frozen_seasons(),
    }


def get_forecast(data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    d = evaluation.FROZEN_DIR
    frozen = tuple(sorted((p.name, p.stat().st_mtime) for p in d.glob("*.csv"))) if d.exists() else ()
    return _forecast(_data_signature(data_dir), frozen, str(data_dir))
