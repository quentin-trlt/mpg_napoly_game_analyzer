from pathlib import Path

import pandas as pd
import streamlit as st

from mpg.analysis import Analysis, run
from mpg.forecast import evaluation
from mpg.forecast.evaluation import backtest, backtest_summary, frozen_matches, frozen_seasons
from mpg.forecast.season import build_context, ensemble_draws, fixtures_after, simulate_season, title_odds_history
from mpg.loader import DEFAULT_DATA_DIR
from mpg.seasons import Season, coach_by_team, coach_key, list_seasons, season_by_key

TEAM_KEY = "team_id"
SEASON_KEY = "saison"
COACH_KEY = "coach"
_COACH_CHOSEN = "_coach_choisi"


def _data_signature(data_dir: Path) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((p.name, p.stat().st_mtime) for p in data_dir.glob("*.csv")))


@st.cache_resource(show_spinner="Calcul des statistiques…", max_entries=4)
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


@st.cache_resource(show_spinner="Simulation de la fin de saison…", max_entries=2)
def _forecast_light(signature: tuple, data_dir: str) -> dict:
    a = _cached(signature, data_dir)
    fixtures = fixtures_after(a, a.league.last_gw)
    draws = ensemble_draws(build_context(a), fixtures, n_draws=4000) if not fixtures.empty else None
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
    return {"draws": draws, "baseline": baseline, "bonus_effect": bonus_effect}


@st.cache_resource(show_spinner="Historique et fiabilité des pronostics…", max_entries=2)
def _forecast_heavy(signature: tuple, frozen_signature: tuple, data_dir: str) -> dict:
    a = _cached(signature, data_dir)
    bt = backtest(a)
    return {
        "history": title_odds_history(a),
        "backtest": bt,
        "backtest_summary": backtest_summary(bt),
        "frozen_matches": frozen_matches(a),
        "frozen_seasons": frozen_seasons(),
    }


def _current_season_signature(data_dir: Path) -> tuple:
    current = seasons()[-1]
    if Path(data_dir).resolve() != current.path:
        raise ValueError(
            f"Les pronostics figés ne valent que pour la saison en cours ({current.key}) : "
            f"pas de simulation pour {data_dir}."
        )
    return _data_signature(data_dir)


def get_forecast_light(data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    return _forecast_light(_current_season_signature(data_dir), str(data_dir))


def get_forecast(data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    signature = _current_season_signature(data_dir)
    d = evaluation.FROZEN_DIR
    frozen = tuple(sorted((p.name, p.stat().st_mtime) for p in d.glob("*.csv"))) if d.exists() else ()
    return {**_forecast_light(signature, str(data_dir)), **_forecast_heavy(signature, frozen, str(data_dir))}


@st.cache_resource(max_entries=1)
def seasons() -> list[Season]:
    return list_seasons()


@st.cache_data(max_entries=1)
def _all_coaches(signature: tuple[tuple[str, float], ...]) -> list[str]:
    coaches = {
        coach_key(str(c))
        for path, _ in signature
        for c in pd.read_csv(Path(path) / "teams.csv", usecols=["coach"])["coach"]
    }
    return sorted(coaches, key=str.lower)


def season_selector() -> Season:
    all_seasons = seasons()
    keys = [s.key for s in reversed(all_seasons)]
    key = st.selectbox(
        "Saison",
        options=keys,
        key=SEASON_KEY,
        bind="query-params",
        help="La saison en cours est la plus récente.",
    )
    return season_by_key(key, all_seasons)


def _leader(a: Analysis) -> tuple[int, str]:
    team_id = int(a.standings.iloc[0]["team_id"])
    return team_id, coach_by_team(a.league)[team_id]


def _mark_coach_chosen() -> None:
    st.session_state[_COACH_CHOSEN] = True


def _follow_leader(coaches: list[str], leader_coach: str) -> None:
    if _COACH_CHOSEN not in st.session_state:
        asked = st.query_params.get(COACH_KEY)
        st.session_state[_COACH_CHOSEN] = asked is not None and coach_key(asked) in coaches
        if st.session_state[_COACH_CHOSEN]:
            st.session_state[COACH_KEY] = coach_key(asked)
    if not st.session_state[_COACH_CHOSEN]:
        st.session_state[COACH_KEY] = leader_coach


def _sync_coach_url(coach: str) -> None:
    chosen = st.session_state[_COACH_CHOSEN]
    if chosen and st.query_params.get(COACH_KEY) != coach:
        st.query_params[COACH_KEY] = coach
    elif not chosen and COACH_KEY in st.query_params:
        del st.query_params[COACH_KEY]


def coach_selector(a: Analysis, season: Season) -> int:
    """Affiche « Mon équipe » et renvoie l'équipe correspondante dans la saison affichée.

    Le widget n'est pas lié à l'adresse (`bind="query-params"`) : Streamlit y écrirait le libellé affiché
    et non la clé du coach. L'adresse est lue à l'arrivée, puis réécrite à chaque exécution pour que le coach
    survive aux changements de page.
    """
    signature = tuple((str(s.path), (s.path / "teams.csv").stat().st_mtime) for s in seasons())
    coaches = _all_coaches(signature)
    leader_id, leader_coach = _leader(a)
    _follow_leader(coaches, leader_coach)
    team_of_coach = {c: t for t, c in coach_by_team(a.league).items()}
    names = a.league.team_names

    def label(coach: str) -> str:
        return (
            f"{names[team_of_coach[coach]]} ({coach})"
            if coach in team_of_coach
            else f"{coach} (absent en {season.key})"
        )

    coach = st.selectbox(
        "Mon équipe",
        options=coaches,
        format_func=label,
        key=COACH_KEY,
        on_change=_mark_coach_chosen,
        help="Retenue dans l'adresse de la page : un favori rouvre l'app sur ton équipe.",
    )
    _sync_coach_url(coach)
    if coach in team_of_coach:
        return team_of_coach[coach]
    champion = "le leader" if season.current else "le champion"
    st.sidebar.caption(f"{coach} n'a pas joué en {season.key} : tu vois {champion}.")
    return leader_id
