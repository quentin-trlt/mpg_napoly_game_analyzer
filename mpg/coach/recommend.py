"""Recommandation complète pour le prochain match d'une équipe : compo, banc, tactiques, capitaine, bonus.

Les compos sont choisies sur un premier jeu de tirages et toutes les valeurs affichées (points espérés, gains des
bonus, probabilités) sont recalculées sur un second jeu indépendant, pour ne pas surestimer le gain des choix
retenus parmi beaucoup de candidats.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mpg.analysis import Analysis
from mpg.coach import optimizer as op
from mpg.coach.bonus_plan import FUTURE_DRAWS, assign, future_gains, team_stock
from mpg.coach.projection import (
    ClubStrength,
    NoteModel,
    deadline,
    fit_club_strength,
    fit_note_model,
    project_players,
    sample_draws,
)
from mpg.coach.rules import Draws, Lineup, slots_of
from mpg.forecast.bonus import MCDO, MIROIR
from mpg.playing_time import PlayModel, fit_play_model
from mpg.premier_league import pl_gw_for

N_DRAWS = 4000
TOP_LINEUPS = 5


def next_match(a: Analysis, team_id: int) -> tuple[int, int, bool]:
    """(journée, adversaire, à domicile) du prochain match MPG de l'équipe."""
    fx = a.league.fixtures
    todo = fx[(fx["statut"] == "a_venir") & ((fx["home_team_id"] == team_id) | (fx["away_team_id"] == team_id))]
    if todo.empty:
        raise ValueError(f"l'équipe {team_id} n'a plus de match à jouer")
    m = todo.sort_values("gw").iloc[0]
    home = int(m["home_team_id"]) == team_id
    return int(m["gw"]), int(m["away_team_id"] if home else m["home_team_id"]), home


@dataclass
class Recommendation:
    team_id: int
    opp_id: int
    home: bool
    gw: int
    pl_gw: int
    deadline: pd.Timestamp
    proj: pd.DataFrame
    draws: Draws
    holdout: Draws
    lineups: list[Lineup]
    opponent: Lineup
    ev: op.Evaluator
    ev_holdout: op.Evaluator
    opp_probs: dict[str, float]
    gains_now: pd.DataFrame
    plan: pd.DataFrame
    stock: dict[str, int]
    bonus_names: dict[str, str]
    model: NoteModel
    strength: ClubStrength
    play_model: PlayModel | None

    @property
    def bonus(self) -> str | None:
        row = self.plan[self.plan["gw"] == self.gw]
        return None if row.empty or row["bonus"].isna().all() else row["bonus"].iloc[0]

    @property
    def best(self) -> Lineup:
        """Compo à poser : la meilleure sans bonus, ou sa variante avec le bonus que le plan affecte à ce match."""
        key = self.bonus
        if key is None:
            return self.lineups[0]
        row = self.gains_now[self.gains_now["bonus"] == key]
        return row["lineup"].iloc[0] if not row.empty else self.lineups[0]

    def summary(self, lu: Lineup) -> dict[str, float]:
        r = self.ev_holdout.result(lu)
        p = r.outcome_probs(self.home)
        return {
            "e_pts": r.expected_points(self.home),
            "se": r.stderr(self.home),
            "p_v": p[0],
            "p_n": p[1],
            "p_d": p[2],
            "e_pts_bonus_adverses": op.expected_vs_opponent_bonus(lu, self.ev_holdout, self.opp_probs),
        }

    def name(self, row: int) -> str:
        return str(self.proj.at[row, "joueur"])

    def sheet(self, lu: Lineup) -> pd.DataFrame:
        """Feuille de match lisible : titulaires dans l'ordre des postes puis banc dans l'ordre d'entrée."""
        cols = ["joueur", "club", "poste_groupe", "p_joue", "note_attendue", "lambda_buts", "adversaire_pl", "news"]
        slots = slots_of(lu.formation)
        rows = []
        for i, (r, slot) in enumerate(zip(lu.starters, slots)):
            rows.append({"role": "Titulaire", "ordre": i + 1, "poste": slot, **self.proj.loc[r, cols].to_dict()})
        for i, r in enumerate(lu.bench):
            rows.append(
                {
                    "role": "Banc",
                    "ordre": i + 1,
                    "poste": self.proj.at[r, "poste_groupe"],
                    **self.proj.loc[r, cols].to_dict(),
                }
            )
        out = pd.DataFrame(rows)
        out["capitaine"] = [r == lu.captain for r in list(lu.starters) + list(lu.bench)]
        out["mcdo"] = [r == lu.mcdo_target and lu.bonus == MCDO for r in list(lu.starters) + list(lu.bench)]
        return out

    def tactics_table(self, lu: Lineup) -> pd.DataFrame:
        return pd.DataFrame(
            [{"sort": self.name(t.out), "entre": self.name(t.inp), "seuil": t.threshold} for t in lu.tactics],
            columns=["sort", "entre", "seuil"],
        )


def _distinct(lineups: list[Lineup]) -> list[Lineup]:
    seen, out = set(), []
    for lu in lineups:
        sig = (lu.formation, frozenset(lu.starters))
        if sig not in seen:
            seen.add(sig)
            out.append(lu)
    return out


def recommend(
    a: Analysis,
    team_id: int,
    fpl_players: pd.DataFrame | None = None,
    fpl_history: dict[int, pd.DataFrame] | None = None,
    overrides: dict[str, float] | None = None,
    n_draws: int = N_DRAWS,
    seed: int = 0,
    future_draws: int = FUTURE_DRAWS,
    with_plan: bool = True,
) -> Recommendation:
    league = a.league
    gw, opp, home = next_match(a, team_id)
    pl_gw = pl_gw_for(league, gw)
    model = fit_note_model(a)
    strength = fit_club_strength(league.club_results)
    play_model = None
    if fpl_players is not None and fpl_history:
        play_model = fit_play_model(fpl_players, fpl_history, league.players.set_index("player_key")["taux_jeu"], pl_gw)
    proj = project_players(
        a, [team_id, opp], pl_gw, model, strength, fpl_players, fpl_history, overrides, play_model=play_model
    )
    draws = sample_draws(proj, model, n_draws, seed=seed)
    holdout = sample_draws(proj, model, n_draws, seed=seed + 10_000)
    mine = [draws.row(k) for k in proj.loc[proj["team_id"] == team_id, "player_key"]]
    theirs = [draws.row(k) for k in proj.loc[proj["team_id"] == opp, "player_key"]]

    value = op.contribution(draws)
    naive = max(
        (lu for f in op.FORMATIONS if (lu := op.initial_lineup(mine, draws, f, value)) is not None),
        key=lambda lu: sum(value[r] for r in lu.starters),
    )
    opp_lu = op.optimise(theirs, op.Evaluator(draws, naive, home=not home))[0]
    opp_lu = op.prune_tactics(opp_lu, op.Evaluator(holdout, naive, home=not home))

    ev = op.Evaluator(draws, opp_lu, home=home)
    ev_h = op.Evaluator(holdout, opp_lu, home=home)
    found = [op.prune_tactics(lu, ev_h) for lu in op.optimise(mine, ev)]
    lineups = sorted(_distinct(found), key=ev_h, reverse=True)[:TOP_LINEUPS]
    best = lineups[0]

    stock, names = team_stock(a.bonus_remaining, team_id)
    fx = league.fixtures
    opp_left = int(((fx["statut"] == "a_venir") & ((fx["home_team_id"] == opp) | (fx["away_team_id"] == opp))).sum())
    probs = op.opponent_bonus_probs(a.bonus_remaining, opp, opp_left)
    raw = op.bonus_gains(best, mine, ev, stock, probs, full=True)
    rows = []
    for key, (_, trial) in raw.items():
        trial = op.prune_tactics(trial, ev_h)
        gain = op.mirror_gain(best, ev_h, probs) if key == MIROIR else ev_h(trial) - ev_h(best)
        rows.append({"gw": gw, "bonus": key, "gain": gain, "lineup": trial})
    gains_now = pd.DataFrame(rows, columns=["gw", "bonus", "gain", "lineup"])

    if with_plan and stock:
        future = future_gains(
            a, team_id, gw, model, strength, fpl_players, stock, fpl_history, play_model, seed, future_draws
        )
        table = pd.concat([gains_now[["gw", "bonus", "gain"]], future[["gw", "bonus", "gain"]]], ignore_index=True)
        by_bonus = table.pivot_table(index="gw", columns="bonus", values="gain")
        plan = assign(table, stock).merge(by_bonus, left_on="gw", right_index=True, how="left")
        plan["adversaire_id"] = plan["gw"].map(dict(zip(future["gw"], future["adversaire_id"])) | {gw: opp})
    else:
        best_now = gains_now.sort_values("gain", ascending=False).head(1)
        key = best_now["bonus"].iloc[0] if not best_now.empty and best_now["gain"].iloc[0] > 0 else None
        plan = pd.DataFrame([{"gw": gw, "bonus": key, "gain": 0.0 if key is None else best_now["gain"].iloc[0]}])
        plan["adversaire_id"] = opp

    return Recommendation(
        team_id=team_id,
        opp_id=opp,
        home=home,
        gw=gw,
        pl_gw=pl_gw,
        deadline=deadline(league, pl_gw),
        proj=proj,
        draws=draws,
        holdout=holdout,
        lineups=lineups,
        opponent=opp_lu,
        ev=ev,
        ev_holdout=ev_h,
        opp_probs=probs,
        gains_now=gains_now,
        plan=plan,
        stock=stock,
        bonus_names=names,
        model=model,
        strength=strength,
        play_model=play_model,
    )


def naive_lineup(rec: Recommendation) -> Lineup:
    """11 de référence : meilleure formation par contribution espérée, sans recherche ni tactiques."""
    rows = [rec.draws.row(k) for k in rec.proj.loc[rec.proj["team_id"] == rec.team_id, "player_key"]]
    value = op.contribution(rec.draws)
    return max(
        (lu for f in op.FORMATIONS if (lu := op.initial_lineup(rows, rec.draws, f, value)) is not None),
        key=lambda lu: float(np.sum(value[list(lu.starters)])),
    )
