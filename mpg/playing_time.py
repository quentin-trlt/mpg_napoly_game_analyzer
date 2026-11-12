"""Probabilité qu'un joueur joue (au moins une minute) à une journée de Premier League, d'après l'historique FPL.

MPG note tout joueur entré en jeu, même une minute : la cible est donc minutes > 0. Le modèle est un logit estimé
sur toutes les journées passées des joueurs de la ligue, avec des variables connues la veille : part des 5 dernières
journées jouées, a joué la dernière, part de titularisations sur ces 5 journées, part des journées jouées depuis le
début de la saison. Rejoué sur J1-J5 sans information postérieure, il bat le taux de jeu de la saison (Brier 0,120
contre 0,137 sur 980 joueur-journées, `experiments/backtest_engine.py`).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize

from mpg.loader import League
from mpg.premier_league import pl_gw_for

LOOKBACK = 5
MIN_PLAY_ROUNDS = 3
MIN_OBS = 50
PLAY_RIDGE = 1.0
DEFAULT_RATE = 0.8
HISTORY_COLUMNS = ["round", "minutes", "starts", "goals_scored", "own_goals", "xg", "kickoff_time"]


def by_round(hist: pd.DataFrame | None) -> pd.DataFrame:
    """Historique FPL agrégé par journée (une journée double compte comme une seule)."""
    if hist is None or hist.empty:
        return pd.DataFrame(columns=["round", "minutes", "starts", "xg"])
    return hist.groupby("round", as_index=False).agg(
        minutes=("minutes", "sum"), starts=("starts", "max"), xg=("xg", "sum")
    )


def recent(hist: pd.DataFrame | None, pl_gw: int) -> pd.DataFrame:
    """Les `LOOKBACK` dernières journées strictement avant `pl_gw`."""
    rounds = by_round(hist)
    return rounds[rounds["round"] < pl_gw].sort_values("round").tail(LOOKBACK)


def season_rate(hist: pd.DataFrame | None, pl_gw: int) -> float:
    """Part des journées jouées avant `pl_gw` (NaN sans historique)."""
    rounds = by_round(hist)
    past = rounds[rounds["round"] < pl_gw]
    return float((past["minutes"] > 0).mean()) if len(past) else np.nan


def _features(rounds: pd.DataFrame, pl_gw: int, rate: float) -> np.ndarray | None:
    last = rounds[rounds["round"] < pl_gw].tail(LOOKBACK)
    if len(last) < MIN_PLAY_ROUNDS:
        return None
    played = last["minutes"].to_numpy() > 0
    return np.array([1.0, played.mean(), float(played[-1]), last["starts"].mean(), rate])


def play_features(hist: pd.DataFrame | None, pl_gw: int, rate: float) -> np.ndarray | None:
    """Constante, part des 5 dernières journées jouées, a joué la dernière, part de titularisations, taux saison."""
    return _features(by_round(hist).sort_values("round"), pl_gw, rate)


@dataclass
class PlayModel:
    """Logit de P(minutes > 0 à la journée suivante)."""

    coef: np.ndarray
    n_obs: int
    brier: float

    def prob(self, x: np.ndarray) -> float:
        return float(1 / (1 + np.exp(-(x @ self.coef))))


def fit_play_model(
    fpl_players: pd.DataFrame, fpl_history: dict[int, pd.DataFrame], taux: pd.Series, upto_round: int
) -> PlayModel | None:
    """Une observation par joueur et par journée avant `upto_round`. `taux` : taux de jeu de la saison par
    `player_key`, utilisé comme dernière variable. None s'il y a moins de `MIN_OBS` observations."""
    x_rows, y = [], []
    for key, eid in zip(fpl_players["player_key"], fpl_players["element_id"]):
        if pd.isna(eid) or int(eid) not in fpl_history:
            continue
        rate = float(taux.get(key, np.nan))
        rate = DEFAULT_RATE if np.isnan(rate) else rate
        rounds = by_round(fpl_history[int(eid)]).sort_values("round")
        for r, minutes in zip(rounds["round"], rounds["minutes"]):
            if r >= upto_round:
                continue
            x = _features(rounds, int(r), rate)
            if x is not None:
                x_rows.append(x)
                y.append(float(minutes > 0))
    if len(y) < MIN_OBS:
        return None
    x, y = np.array(x_rows), np.array(y)

    def nll(beta: np.ndarray) -> float:
        z = x @ beta
        return float(np.sum(np.logaddexp(0, z) - y * z) + PLAY_RIDGE * beta[1:] @ beta[1:])

    beta = optimize.minimize(nll, np.zeros(x.shape[1]), method="BFGS").x
    p = 1 / (1 + np.exp(-(x @ beta)))
    return PlayModel(coef=beta, n_obs=len(y), brier=float(np.mean((p - y) ** 2)))


def split_history(long: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Historique au format long (une ligne par joueur et par match FPL) → historique par `element_id`."""
    return {int(eid): g[HISTORY_COLUMNS].reset_index(drop=True) for eid, g in long.groupby("element_id")}


def play_probabilities(fpl_players: pd.DataFrame, fpl_history: dict[int, pd.DataFrame], pl_gw: int) -> pd.Series:
    """P(joue) de chaque joueur apparié à la journée PL `pl_gw`, avec ce qui était connu avant elle.

    Le taux de la saison est lui aussi recalculé avant `pl_gw`, si bien que le résultat ne dépend d'aucune
    information postérieure : on peut s'en servir pour rejouer une journée passée. Sans modèle (trop peu
    d'historique) ou sans variables (moins de 3 journées), c'est le taux de la saison. Les joueurs sans historique
    sont absents de la série.
    """
    keys = fpl_players.dropna(subset=["element_id"])
    keys = keys[keys["element_id"].astype(int).isin(fpl_history)]
    rates = pd.Series(
        {k: season_rate(fpl_history[int(e)], pl_gw) for k, e in zip(keys["player_key"], keys["element_id"])},
        dtype=float,
    )
    rates = rates.fillna(rates.median() if rates.notna().any() else DEFAULT_RATE)
    model = fit_play_model(keys, fpl_history, rates, pl_gw)
    out = {}
    for key, eid in zip(keys["player_key"], keys["element_id"]):
        x = play_features(fpl_history[int(eid)], pl_gw, rates[key]) if model is not None else None
        out[key] = model.prob(x) if x is not None else float(rates[key])
    return pd.Series(out, dtype=float)


def league_play_probabilities(league: League, mpg_gw: int) -> pd.Series | None:
    """P(joue) de chaque joueur de la ligue pour la journée MPG `mpg_gw`, d'après l'instantané FPL de `data/`.

    None si l'instantané, le calendrier de PL ou la journée manquent : l'appelant garde alors le taux de la saison.
    """
    if league.fpl_players is None or league.fpl_history is None or league.club_results is None:
        return None
    if mpg_gw > league.n_gw:
        return None
    return play_probabilities(league.fpl_players, split_history(league.fpl_history), pl_gw_for(league, mpg_gw))
