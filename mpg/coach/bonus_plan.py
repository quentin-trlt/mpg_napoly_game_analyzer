"""Quand poser chaque bonus : affectation des bonus restants aux matchs restants qui maximise le gain total.

Pour chaque match restant et chaque bonus, le gain est la hausse des points espérés qu'il apporte. Le match à venir
utilise la compo optimisée ; les suivants une compo projetée (meilleure formation de départ, capitaine optimisé,
sans remplacements tactiques) et des disponibilités génériques, puisque les blessures au-delà de deux journées
sont inconnues. L'affectation (un bonus par match, dans la limite du stock) est un problème d'affectation linéaire.
Le bonus recommandé pour le prochain match est celui que l'affectation lui attribue : un bonus n'est posé
maintenant que si ce match fait partie de ses meilleures occasions.
"""

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from mpg.analysis import Analysis
from mpg.coach import optimizer as op
from mpg.coach.projection import ClubStrength, NoteModel, project_players, sample_draws
from mpg.coach.rules import FORMATIONS
from mpg.coaching import bonus_key
from mpg.playing_time import PlayModel
from mpg.premier_league import pl_gw_for

FUTURE_DRAWS = 1500
UNAVAILABLE_GAIN = -1e6


def team_stock(remaining: pd.DataFrame | None, team_id: int) -> tuple[dict[str, int], dict[str, str]]:
    """Bonus restants d'une équipe (clé normalisée → quantité) et nom affiché de chaque clé."""
    if remaining is None:
        return {}, {}
    mine = remaining[remaining["team_id"] == team_id]
    stock = {bonus_key(b): max(int(q), 0) for b, q in zip(mine["bonus"], mine["restants"])}
    names = {bonus_key(b): b for b in mine["bonus"]}
    return {k: q for k, q in stock.items() if q > 0}, names


def remaining_matches(a: Analysis, team_id: int, after_gw: int) -> pd.DataFrame:
    fx = a.league.fixtures
    mine = fx[(fx["statut"] == "a_venir") & ((fx["home_team_id"] == team_id) | (fx["away_team_id"] == team_id))]
    mine = mine[mine["gw"] > after_gw].sort_values("gw")
    home = mine["home_team_id"] == team_id
    return pd.DataFrame(
        {
            "gw": mine["gw"].to_numpy(),
            "domicile": home.to_numpy(),
            "adversaire_id": np.where(home, mine["away_team_id"], mine["home_team_id"]).astype(int),
        }
    )


def _projected_lineup(rows: list[int], ev: op.Evaluator) -> op.Lineup:
    value = op.contribution(ev.draws)
    starts = [lu for f in FORMATIONS if (lu := op.initial_lineup(rows, ev.draws, f, value)) is not None]
    return op.best_captain(max(starts, key=ev), ev.draws, ev)


def future_gains(
    a: Analysis,
    team_id: int,
    next_gw: int,
    model: NoteModel,
    strength: ClubStrength,
    fpl_players: pd.DataFrame | None,
    stock: dict[str, int],
    fpl_history: dict[int, pd.DataFrame] | None = None,
    play_model: PlayModel | None = None,
    seed: int = 0,
    n_draws: int = FUTURE_DRAWS,
) -> pd.DataFrame:
    """Gain de chaque bonus sur chaque match après `next_gw` (une ligne par match et par bonus)."""
    rows_out = []
    remaining = a.bonus_remaining
    future = remaining_matches(a, team_id, next_gw)
    n_left = len(future) + 1
    known_until = pl_gw_for(a.league, next_gw)
    for i, m in enumerate(future.itertuples()):
        opp = int(m.adversaire_id)
        pl_gw = pl_gw_for(a.league, int(m.gw))
        proj = project_players(
            a,
            [team_id, opp],
            pl_gw,
            model,
            strength,
            fpl_players,
            fpl_history,
            horizon=int(m.gw) - next_gw + 1,
            play_model=play_model,
            history_until=known_until,
        )
        d = sample_draws(proj, model, n_draws, seed=seed + int(m.gw))
        mine = [d.row(k) for k in proj.loc[proj["team_id"] == team_id, "player_key"]]
        theirs = [d.row(k) for k in proj.loc[proj["team_id"] == opp, "player_key"]]
        value = op.contribution(d)
        my_naive = max(
            (lu for f in FORMATIONS if (lu := op.initial_lineup(mine, d, f, value)) is not None),
            key=lambda lu: sum(value[r] for r in lu.starters),
        )
        opp_lu = _projected_lineup(theirs, op.Evaluator(d, my_naive, home=not m.domicile))
        ev = op.Evaluator(d, opp_lu, home=bool(m.domicile))
        my_lu = _projected_lineup(mine, ev)
        probs = op.opponent_bonus_probs(remaining, opp, n_left - i - 1)
        gains = op.bonus_gains(my_lu, mine, ev, stock, probs, full=False)
        for key, (gain, _) in gains.items():
            rows_out.append(
                {"gw": int(m.gw), "adversaire_id": opp, "domicile": bool(m.domicile), "bonus": key, "gain": gain}
            )
    return pd.DataFrame(rows_out, columns=["gw", "adversaire_id", "domicile", "bonus", "gain"])


def assign(gains: pd.DataFrame, stock: dict[str, int]) -> pd.DataFrame:
    """Affectation optimale : chaque match reçoit au plus un bonus, chaque bonus au plus sa quantité restante.

    `gains` : colonnes gw, bonus, gain. Renvoie une ligne par match avec le bonus affecté (None) et son gain.
    """
    matches = sorted(gains["gw"].unique())
    units = [k for k, q in stock.items() for _ in range(q)]
    table = gains.pivot_table(index="gw", columns="bonus", values="gain").reindex(index=matches)
    value = np.zeros((len(matches), len(units) + len(matches)))
    for j, key in enumerate(units):
        value[:, j] = table[key].fillna(UNAVAILABLE_GAIN).to_numpy() if key in table else UNAVAILABLE_GAIN
    rows, cols = linear_sum_assignment(-value)
    out = []
    for r, c in zip(rows, cols):
        key = units[c] if c < len(units) and value[r, c] > 0 else None
        out.append({"gw": int(matches[r]), "bonus": key, "gain": float(value[r, c]) if key else 0.0})
    plan = pd.DataFrame(out, columns=["gw", "bonus", "gain"]).sort_values("gw").reset_index(drop=True)
    plan["bonus"] = plan["bonus"].astype(object).where(plan["bonus"].notna(), None)
    return plan
