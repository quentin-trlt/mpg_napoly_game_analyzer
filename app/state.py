from pathlib import Path

import pandas as pd
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
    baseline = simulate_season(a, draws) if draws is not None else None
    bonus_effect = None
    if draws is not None and draws.bonus_shift is not None:
        raw = simulate_season(a, draws, use_bonus=False).summary.set_index("team_id")
        adj = baseline.summary.set_index("team_id")
        rest = a.bonus_remaining.groupby("team_id")["restants"].apply(lambda s: s.clip(lower=0).sum())
        bonus_effect = pd.DataFrame(
            {
                "team_id": adj.index,
                "team_name": adj.index.map(a.league.team_names),
                "restants": rest.reindex(adj.index).fillna(0).astype(int).to_numpy(),
                "effet_pts": (adj["pts_moy"] - raw["pts_moy"].reindex(adj.index)).to_numpy(),
                "effet_titre": (adj["p_titre"] - raw["p_titre"].reindex(adj.index)).to_numpy(),
                "effet_dernier": (adj["p_dernier"] - raw["p_dernier"].reindex(adj.index)).to_numpy(),
            }
        ).sort_values("effet_pts", ascending=False)
    return {
        "draws": draws,
        "baseline": baseline,
        "bonus_effect": bonus_effect,
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
