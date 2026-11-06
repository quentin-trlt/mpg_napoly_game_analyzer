from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
import pandas as pd

from mpg.analysis import Analysis
from mpg.coaching import remaining_bonuses
from mpg.forecast.bonus import apply_shift, bonus_shifts, fit_goal_note_slope, past_bonus_effects, tactical_gains
from mpg.forecast.models import (
    OUTCOMES,
    RESULT_TO_IDX,
    BaselineModel,
    Context,
    OrderedLogit,
    PoissonModel,
    default_models,
)

POINTS = np.array([[3, 1, 0], [0, 1, 3]])
REFERENCE = BaselineModel.name


def build_context(a: Analysis, upto_gw: int | None = None) -> Context:
    """Contexte de prédiction avec les matchs joués jusqu'à `upto_gw` (par défaut la dernière journée).

    Les données joueurs (taux de jeu, moyennes PL, notes rétrécies) sont celles du jour : en rejouant le passé,
    elles contiennent de l'information postérieure à la journée prédite. Tout le reste (résultats, bonus posés,
    stock de bonus restant, pentes estimées) est limité aux journées ≤ `upto_gw`.
    """
    league = a.league
    upto = league.last_gw if upto_gw is None else upto_gw
    tm = a.team_match[a.team_match["gw"] <= upto]
    lu = a.lineups[a.lineups["gw"] <= upto]
    team_ids = sorted(league.teams["team_id"].astype(int).tolist())

    fallback = a.favourites.set_index("team_id")["formation_11_max"].to_dict()
    formations = {**fallback, **tm.groupby("team_id")["formation"].agg(lambda f: f.mode().iloc[0]).to_dict()}
    picks = lu[lu["choix_coach"]]
    start_share = float((picks["statut"] == "titulaire").mean()) if len(picks) else 0.82
    gains = tactical_gains(league.substitutions[league.substitutions["gw"] <= upto], tm)

    home = tm[tm["domicile"]]
    delta = (home["note_moy_brute"] - home["note_moy_brute_adv"]).to_numpy(float)
    note_slope = OrderedLogit(b0=2.0).fit(delta, home["resultat"].map(RESULT_TO_IDX).to_numpy()).b

    bonus_used = league.bonus[league.bonus["gw"] <= upto]
    remaining = remaining_bonuses(bonus_used, league.bonus_stock, team_ids) if league.bonus_stock is not None else None
    return Context(
        tm=tm,
        strength=a.favourites.set_index("team_id")["indice_force"],
        players=a.player_value,
        lineups=lu,
        team_ids=team_ids,
        upto_gw=upto,
        bonus_remaining=remaining,
        past_bonus=past_bonus_effects(bonus_used, tm, formations, gains, start_share),
        formations=formations,
        tactical_gain=gains,
        start_share=start_share,
        note_slope=float(note_slope),
        goal_note_slope=fit_goal_note_slope(tm),
    )


def fixtures_after(a: Analysis, gw: int) -> pd.DataFrame:
    fx = a.league.fixtures
    out = fx[fx["gw"] > gw][["gw", "date", "home_team_id", "away_team_id", "home_team", "away_team"]]
    return out.sort_values(["gw", "home_team_id"]).reset_index(drop=True)


@dataclass
class EnsembleDraws:
    """Probabilités tirées pour chaque modèle (n_draws, n_matchs, 3) et matrices de score du Poisson."""

    fixtures: pd.DataFrame
    by_model: dict[str, np.ndarray]
    score_matrix: np.ndarray
    models: list = field(default_factory=list)
    bonus_shift: np.ndarray | None = None

    @cached_property
    def ensemble_raw(self) -> np.ndarray:
        """Moyenne à poids égaux des modèles, hors référence, sans les bonus à venir."""
        return np.mean([d for name, d in self.by_model.items() if name != REFERENCE], axis=0)

    @cached_property
    def ensemble(self) -> np.ndarray:
        """Ensemble ajusté des bonus restants (identique à `ensemble_raw` si la dotation est inconnue)."""
        if self.bonus_shift is None:
            return self.ensemble_raw
        return apply_shift(self.ensemble_raw, self.bonus_shift)

    def mean_probs(self) -> pd.DataFrame:
        rows = []
        for name, draws in {**self.by_model, "Ensemble": self.ensemble}.items():
            p = draws.mean(axis=0)
            rows.append(self.fixtures.assign(modele=name, p_dom=p[:, 0], p_nul=p[:, 1], p_ext=p[:, 2]))
        return pd.concat(rows, ignore_index=True)


def ensemble_draws(
    ctx: Context, fixtures: pd.DataFrame, n_draws: int = 4000, seed: int = 0, models: list | None = None
) -> EnsembleDraws:
    rng = np.random.default_rng(seed)
    models = [m.fit(ctx) for m in (models or [BaselineModel(), *default_models()])]
    by_model = {m.name: m.sample_probs(fixtures, n_draws, rng) for m in models}
    poisson = next((m for m in models if isinstance(m, PoissonModel)), None) or PoissonModel().fit(ctx)
    score_matrix = poisson.score_matrix(fixtures)
    return EnsembleDraws(
        fixtures=fixtures,
        by_model=by_model,
        score_matrix=score_matrix,
        models=models,
        bonus_shift=bonus_shifts(ctx, fixtures, score_matrix, n_draws, rng),
    )


def _sample_scores(
    score_matrix: np.ndarray, outcome: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Tire un score cohérent avec l'issue, selon la loi jointe du Poisson restreinte à cette issue."""
    n_sims, n_matches = outcome.shape
    g = score_matrix.shape[1]
    hg, ag = np.indices((g, g))
    category = np.where(hg > ag, 0, np.where(hg == ag, 1, 2)).ravel()
    home_goals, away_goals = np.zeros_like(outcome), np.zeros_like(outcome)
    u = rng.random((n_sims, n_matches))
    for j in range(n_matches):
        flat = score_matrix[j].ravel()
        for k in range(3):
            mask = outcome[:, j] == k
            if not mask.any():
                continue
            w = np.where(category == k, flat, 0.0)
            cdf = np.cumsum(w / w.sum())
            cell = np.minimum(np.searchsorted(cdf, u[mask, j]), len(cdf) - 1)
            home_goals[mask, j], away_goals[mask, j] = hg.ravel()[cell], ag.ravel()[cell]
    return home_goals, away_goals


@dataclass
class SeasonSimulation:
    team_ids: list[int]
    rank_probs: pd.DataFrame
    summary: pd.DataFrame
    final_points: np.ndarray
    match_probs: pd.DataFrame


def simulate_season(
    a: Analysis,
    draws: EnsembleDraws,
    upto_gw: int | None = None,
    forced: dict[int, str | tuple[int, int]] | None = None,
    seed: int = 1,
    use_model: str | None = None,
    use_bonus: bool = True,
) -> SeasonSimulation:
    """Simule les matchs restants à partir des tirages de l'ensemble.

    `forced` fixe l'issue de certains matchs : index du match dans `draws.fixtures` → "H", "D", "A" ou un score
    exact (buts domicile, buts extérieur). Les autres matchs sont tirés selon les probabilités du modèle.
    """
    upto = a.league.last_gw if upto_gw is None else upto_gw
    rng = np.random.default_rng(seed)
    probs = draws.by_model[use_model] if use_model else draws.ensemble if use_bonus else draws.ensemble_raw
    n_sims, n_matches, _ = probs.shape
    cum = np.cumsum(probs, axis=2)
    outcome = (rng.random((n_sims, n_matches))[:, :, None] > cum[:, :, :2]).sum(axis=2)
    home_goals, away_goals = _sample_scores(draws.score_matrix, outcome, rng)

    for j, value in (forced or {}).items():
        if isinstance(value, tuple):
            h, g = value
            home_goals[:, j], away_goals[:, j] = h, g
            outcome[:, j] = 0 if h > g else 1 if h == g else 2
        else:
            k = OUTCOMES.index(value)
            if (outcome[:, j] != k).any():
                fixed = np.full((n_sims, 1), k)
                hg, ag = _sample_scores(draws.score_matrix[j : j + 1], fixed, rng)
                home_goals[:, j], away_goals[:, j] = hg[:, 0], ag[:, 0]
            outcome[:, j] = k

    team_ids = sorted(a.league.teams["team_id"].astype(int).tolist())
    idx = {t: i for i, t in enumerate(team_ids)}
    tm = a.team_match[a.team_match["gw"] <= upto]
    cur = tm.groupby("team_id").agg(pts=("pts", "sum"), bp=("bp", "sum"), bc=("bc", "sum")).reindex(team_ids).fillna(0)
    pts = np.tile(cur["pts"].to_numpy(float), (n_sims, 1))
    bp = np.tile(cur["bp"].to_numpy(float), (n_sims, 1))
    bc = np.tile(cur["bc"].to_numpy(float), (n_sims, 1))

    hi = draws.fixtures["home_team_id"].map(idx).to_numpy()
    ai = draws.fixtures["away_team_id"].map(idx).to_numpy()
    for j in range(n_matches):
        pts[:, hi[j]] += POINTS[0][outcome[:, j]]
        pts[:, ai[j]] += POINTS[1][outcome[:, j]]
        bp[:, hi[j]] += home_goals[:, j]
        bc[:, hi[j]] += away_goals[:, j]
        bp[:, ai[j]] += away_goals[:, j]
        bc[:, ai[j]] += home_goals[:, j]

    key = pts * 1e6 + (bp - bc + 1000) * 1e3 + bp + rng.random(pts.shape) * 1e-3
    order = np.argsort(-key, axis=1)
    ranks = np.empty_like(order)
    ranks[np.arange(n_sims)[:, None], order] = np.arange(1, len(team_ids) + 1)[None, :]

    n = len(team_ids)
    rank_probs = pd.DataFrame(
        [(ranks == r).mean(axis=0) for r in range(1, n + 1)], index=range(1, n + 1), columns=team_ids
    ).T
    summary = (
        pd.DataFrame(
            {
                "team_id": team_ids,
                "pts_actuels": cur["pts"].to_numpy(),
                "pts_moy": pts.mean(axis=0),
                "pts_p05": np.quantile(pts, 0.05, axis=0),
                "pts_p95": np.quantile(pts, 0.95, axis=0),
                "rang_moy": ranks.mean(axis=0),
                "p_titre": (ranks == 1).mean(axis=0),
                "p_podium": (ranks <= 3).mean(axis=0),
                "p_dernier": (ranks == n).mean(axis=0),
            }
        )
        .sort_values(["p_titre", "pts_moy"], ascending=False)
        .reset_index(drop=True)
    )

    p = probs.mean(axis=0)
    match_probs = draws.fixtures.assign(p_dom=p[:, 0], p_nul=p[:, 1], p_ext=p[:, 2])
    sm = draws.score_matrix
    best = sm.reshape(len(sm), -1).argmax(axis=1)
    match_probs["score_probable"] = [f"{b // sm.shape[2]}-{b % sm.shape[2]}" for b in best]
    return SeasonSimulation(
        team_ids=team_ids, rank_probs=rank_probs, summary=summary, final_points=pts, match_probs=match_probs
    )


def title_odds_history(a: Analysis, n_draws: int = 1500, seed: int = 0) -> pd.DataFrame:
    """Probabilités de titre, podium et dernière place recalculées après chaque journée (0 = avant la saison)."""
    rows = []
    for g in range(0, a.league.last_gw + 1):
        ctx = build_context(a, g)
        fx = fixtures_after(a, g)
        if fx.empty:
            continue
        sim = simulate_season(a, ensemble_draws(ctx, fx, n_draws=n_draws, seed=seed), upto_gw=g, seed=seed + 1)
        rows.append(sim.summary.assign(apres_journee=g))
    return pd.concat(rows, ignore_index=True)
