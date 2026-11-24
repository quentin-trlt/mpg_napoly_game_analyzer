"""Banc d'essai : les gains des bonus sur les matchs futurs doivent-ils être calculés avec ma compo optimisée ?

Le coach (`bonus_plan.future_gains`) estime le gain de chaque bonus sur chaque match après le prochain avec une compo
projetée : meilleure formation de départ, capitaine optimisé, sans recherche locale ni remplacements tactiques. La
variante « optimisée » prend la compo que le coach poserait vraiment (`optimise` complet contre la compo type
adverse, 424 réoptimisé).

Chaque équipe de chaque saison est rejouée journée après journée avec ce qui était connu avant (`snapshot`) : plan
de bonus avec chacune des deux méthodes, bonus posé maintenant selon ce plan, stock mis à jour (un stock par
méthode). Le prochain match est traité comme dans le coach, de la même façon pour les deux méthodes. Deux mesures
de la valeur des bonus posés :
- espérée : gain du bonus posé, estimé au moment de le poser sur des tirages indépendants ;
- réelle : écart de points entre ma compo avec et sans ce bonus, jouées par le moteur sur les vraies notes de la
  journée (un « tirage » égal à la réalité) contre la vraie compo adverse et son vrai bonus.

Usage :
  uv run python -m experiments.backtest_bonus_plan <dossier> <saison>   (une saison, écrit <dossier>/<saison>.csv)
  uv run python -m experiments.backtest_bonus_plan <dossier>            (résumé des CSV du dossier)
"""

import dataclasses
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.backtest_engine import actual_lineup, snapshot
from mpg.analysis import run
from mpg.coach import optimizer as op
from mpg.coach.bonus_plan import FUTURE_DRAWS, _projected_lineup, assign, remaining_matches
from mpg.coach.projection import project_players, sample_draws
from mpg.coach.rules import Draws, simulate
from mpg.coach.typical import typical_lineup, usage
from mpg.coaching import bonus_key, remaining_bonuses
from mpg.forecast.bonus import F424, KNOWN, MCDO, MIROIR
from mpg.forecast.evaluation import season_dirs
from mpg.playing_time import split_history
from mpg.premier_league import pl_gw_for

N_NEXT = 2000
N_BOOT = 10_000
METHODS = ("projetée (actuel)", "optimisée")

log = logging.getLogger(__name__)


def real_draws(notes: pd.DataFrame, proj: pd.DataFrame, r: int, line: np.ndarray) -> Draws:
    """Un seul tirage : ce qui s'est passé pendant la journée de PL r."""
    cur = (
        notes[notes["pl_gw"] == r]
        .groupby("player_key")
        .agg(a_joue=("a_joue", "max"), note=("note", "mean"), buts=("buts", "sum"), csc=("csc", "sum"))
        .reindex(proj["player_key"])
    )
    plays = (cur["a_joue"].fillna(0).to_numpy() > 0) & cur["note"].notna().to_numpy()
    return Draws(
        keys=list(proj["player_key"]),
        line=line,
        plays=plays[:, None],
        note=cur["note"].fillna(0.0).to_numpy(float)[:, None],
        goals=cur["buts"].fillna(0).astype(int).to_numpy()[:, None],
        own_goals=cur["csc"].fillna(0).astype(int).to_numpy()[:, None],
    )


def with_real_bonus(lu, a, match_id: str, team: int, d: Draws, index: dict[str, int]):
    """`lu` avec le bonus réellement posé par l'équipe à ce match (cible du McDo+ comprise)."""
    bonus = a.league.bonus
    rows = bonus[(bonus["match_id"] == match_id) & (bonus["team_id"] == team)]
    rows = rows[rows["bonus"].map(bonus_key).isin(KNOWN)]
    if rows.empty:
        return lu
    key = bonus_key(rows["bonus"].iloc[0])
    if key != MCDO:
        return lu.with_(bonus=key)
    sheet = a.lineups[(a.lineups["match_id"] == match_id) & (a.lineups["team_id"] == team)]
    target = sheet.loc[sheet["joueur_affiche"] == rows["cible_affiche"].iloc[0], "player_key"]
    row = index.get(target.iloc[0]) if len(target) else None
    if row in lu.starters and row != lu.captain:
        return lu.with_(bonus=MCDO, mcdo_target=row)
    return op.opponent_variant(lu, MCDO, d)


def gains(lu, rows: list[int], ev, stock: dict[str, int], probs: dict[str, float], full: bool) -> dict:
    """`bonus_gains`, sans le 424 quand l'effectif ne peut pas jouer en 4-2-4."""
    try:
        return op.bonus_gains(lu, rows, ev, stock, probs, full=full)
    except ValueError:
        return op.bonus_gains(lu, rows, ev, {k: q for k, q in stock.items() if k != F424}, probs, full=full)


def future_tables(sub, team: int, g: int, snap, stocks: dict[str, dict[str, int]]) -> dict[str, pd.DataFrame]:
    """Gains de chaque bonus sur chaque match après g, pour chaque méthode (mêmes tirages pour les deux)."""
    rows_out = {k: [] for k in METHODS}
    future = remaining_matches(sub, team, g)
    n_left = len(future) + 1
    for i, m in enumerate(future.itertuples()):
        opp = int(m.adversaire_id)
        proj = project_players(
            sub,
            [team, opp],
            pl_gw_for(sub.league, int(m.gw)),
            snap.model,
            snap.strength,
            snap.fpl_players,
            snap.history,
            horizon=int(m.gw) - g + 1,
            play_model=snap.play_model,
            history_until=snap.pl_gw,
        )
        d = sample_draws(proj, snap.model, FUTURE_DRAWS, seed=int(m.gw))
        mine = [d.row(k) for k in proj.loc[proj["team_id"] == team, "player_key"]]
        theirs = [d.row(k) for k in proj.loc[proj["team_id"] == opp, "player_key"]]
        try:
            ev = op.Evaluator(d, typical_lineup(theirs, d, usage(sub, opp, g)), home=bool(m.domicile))
            lineups = {METHODS[0]: _projected_lineup(mine, ev), METHODS[1]: op.optimise(mine, ev)[0]}
        except ValueError:
            continue
        probs = op.opponent_bonus_probs(sub.bonus_remaining, opp, n_left - i - 1)
        for method, lu in lineups.items():
            full = method == METHODS[1]
            for key, (gain, _) in gains(lu, mine, ev, stocks[method], probs, full=full).items():
                rows_out[method].append({"gw": int(m.gw), "bonus": key, "gain": gain})
    return {k: pd.DataFrame(v, columns=["gw", "bonus", "gain"]) for k, v in rows_out.items()}


def season_cases(name: str, path) -> pd.DataFrame:
    a = run(path, n_sim=50)
    lg = a.league
    mapping, hist = None, {}
    if lg.fpl_players is not None and lg.fpl_history is not None:
        mapping, hist = lg.fpl_players[["player_key", "element_id"]], split_history(lg.fpl_history)
    teams = sorted(lg.team_names)
    stock0 = {bonus_key(b): int(q) for b, q in zip(lg.bonus_stock["bonus"], lg.bonus_stock["quantite"]) if int(q) > 0}
    stocks = {(t, k): dict(stock0) for t in teams for k in METHODS}
    played = lg.played.sort_values(["gw", "match_id"])
    out, n_check, n_exact = [], 0, 0
    for g in sorted(played["gw"].unique()):
        t0 = time.perf_counter()
        g = int(g)
        snap = snapshot(a, g, mapping, hist)
        fixtures = lg.fixtures.copy()
        fixtures.loc[fixtures["gw"] >= g, "statut"] = "a_venir"
        rem = remaining_bonuses(lg.bonus[lg.bonus["gw"] < g], lg.bonus_stock, teams)
        sub = dataclasses.replace(
            snap.a, league=dataclasses.replace(snap.a.league, fixtures=fixtures), bonus_remaining=rem
        )
        proj = snap.proj
        d = sample_draws(proj, snap.model, N_NEXT, seed=g)
        hold = sample_draws(proj, snap.model, N_NEXT, seed=10_000 + g)
        index = {k: j for j, k in enumerate(proj["player_key"])}
        rows = {t: [index[k] for k in proj.loc[proj["team_id"] == t, "player_key"]] for t in teams}
        reality = real_draws(lg.player_match_notes, proj, snap.pl_gw, d.line)

        for m in played[played["gw"] == g].itertuples():
            h, w = int(m.home_team_id), int(m.away_team_id)
            forms = {h: m.home_formation, w: m.away_formation}
            real = {t: actual_lineup(a, m.match_id, t, forms[t], d, index) for t in (h, w)}
            if all(v is not None for v in real.values()):
                lus = {t: with_real_bonus(real[t], a, m.match_id, t, d, index) for t in (h, w)}
                res = simulate(lus[h], lus[w], reality)
                n_check += 1
                n_exact += int(res.home_goals[0] == m.home_goals and res.away_goals[0] == m.away_goals)
            for t, opp in ((h, w), (w, h)):
                home = t == h
                try:
                    typ = typical_lineup(rows[opp], d, usage(sub, opp, g))
                    ev, ev_h = op.Evaluator(d, typ, home=home), op.Evaluator(hold, typ, home=home)
                    mine = op.prune_tactics(op.optimise(rows[t], ev)[0], ev_h)
                except ValueError as exc:
                    log.warning("%s J%d équipe %d écartée : %s", name, g, t, exc)
                    continue
                n_left = int(
                    (
                        (fixtures["statut"] == "a_venir")
                        & fixtures[["home_team_id", "away_team_id"]].eq(opp).any(axis=1)
                    ).sum()
                )
                probs = op.opponent_bonus_probs(rem, opp, n_left)
                opp_real = with_real_bonus(real[opp] or typ, a, m.match_id, opp, d, index)

                def points(lu, opp_real=opp_real, home=home) -> float:
                    res = simulate(lu, opp_real, reality) if home else simulate(opp_real, lu, reality)
                    return float(res.points(home)[0])

                tables = future_tables(sub, t, g, snap, {k: stocks[t, k] for k in METHODS})
                for method in METHODS:
                    stock = stocks[t, method]
                    key, expected, realised = None, 0.0, 0.0
                    if stock:
                        now = {}
                        for k, (_, trial) in gains(mine, rows[t], ev, stock, probs, full=True).items():
                            trial = op.prune_tactics(trial, ev_h)
                            gain = op.mirror_gain(mine, ev_h, probs) if k == MIROIR else ev_h(trial) - ev_h(mine)
                            now[k] = (gain, trial)
                        table = pd.concat(
                            [
                                pd.DataFrame([{"gw": g, "bonus": k, "gain": v[0]} for k, v in now.items()]),
                                tables[method],
                            ],
                            ignore_index=True,
                        )
                        plan = assign(table, stock)
                        key = plan.loc[plan["gw"] == g, "bonus"].iloc[0]
                        if isinstance(key, str):
                            expected = now[key][0]
                            realised = points(now[key][1]) - points(mine)
                            stock[key] -= 1
                            if stock[key] == 0:
                                del stock[key]
                        else:
                            key = None
                    out.append(
                        {
                            "saison": name,
                            "gw": g,
                            "team_id": t,
                            "methode": method,
                            "bonus": key,
                            "attendu": expected,
                            "reel": realised,
                            "compo_adverse_reelle": real[opp] is not None,
                        }
                    )
        log.warning("%s J%d : %.0f s", name, g, time.perf_counter() - t0)
    log.warning("%s : moteur sur la réalité, score exact %d/%d matchs", name, n_exact, n_check)
    return pd.DataFrame(out)


def summary(cases: pd.DataFrame) -> None:
    pd.set_option("display.width", 200)
    per_team = cases.groupby(["saison", "team_id", "methode"])[["attendu", "reel"]].sum().unstack("methode")
    print(f"\n=== {len(per_team)} équipes-saisons, {cases['gw'].nunique()} journées max ===")
    print("Valeur des bonus posés sur la saison, moyenne par équipe :")
    print(per_team.mean().unstack(0).round(3).to_string())
    rng = np.random.default_rng(0)
    for metric in ("attendu", "reel"):
        diff = (per_team[(metric, METHODS[1])] - per_team[(metric, METHODS[0])]).to_numpy()
        boot = rng.choice(diff, (N_BOOT, len(diff))).mean(axis=1)
        print(
            f"Δ {metric:8s} optimisée − actuelle : {diff.mean():+.3f} pt par équipe-saison "
            f"[IC 90 % {np.quantile(boot, 0.05):+.3f} ; {np.quantile(boot, 0.95):+.3f}]"
        )
    wide = cases.pivot_table(index=["saison", "gw", "team_id"], columns="methode", values="bonus", aggfunc="first")
    differ = (wide[METHODS[0]].fillna("—") != wide[METHODS[1]].fillna("—")).mean()
    print(f"Décisions différentes entre les deux méthodes : {differ:.0%}")
    print("\nBonus posés par méthode :")
    print(cases.groupby(["methode", "bonus"]).size().unstack(0).fillna(0).astype(int).to_string())


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    out_dir = Path(sys.argv[1])
    if len(sys.argv) > 2:
        name = sys.argv[2]
        season_cases(name, season_dirs()[name]).to_csv(out_dir / f"{name}.csv", index=False)
        return
    summary(pd.concat([pd.read_csv(p) for p in sorted(out_dir.glob("*.csv"))], ignore_index=True))


if __name__ == "__main__":
    main()
