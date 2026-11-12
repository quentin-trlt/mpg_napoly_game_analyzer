"""Recherche de la feuille de match qui maximise les points espérés contre une compo adverse donnée.

Toutes les compos sont évaluées sur les mêmes tirages (nombres aléatoires communs) : les écarts entre deux compos
sont bien plus précis que chaque espérance prise isolément. La recherche procède par étapes :
1. pour chaque formation, 11 de départ = meilleurs joueurs par poste selon leur contribution espérée, banc rempli
   par ordre de valeur (1 gardien, puis les joueurs de champ) ;
2. recherche locale sur les formations les plus prometteuses (échanges titulaire ↔ banc ou hors feuille,
   remplaçant ↔ hors feuille, ordre du banc) ;
3. capitaine, puis remplacements tactiques ajoutés un par un tant qu'ils rapportent.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from mpg.coach.rules import (
    BENCH_SIZE,
    FORMATION_424,
    FORMATIONS,
    MAX_TACTICS,
    ROTALDO_NOTE,
    Draws,
    Lineup,
    Tactic,
    simulate,
    slots_of,
)
from mpg.coaching import bonus_key
from mpg.forecast.bonus import F424, MCDO, MIROIR

THRESHOLDS = (4.0, 4.5, 5.0, 5.5, 6.0)
EPS = 0.002
TOP_FORMATIONS = 3
MCDO_CANDIDATES = 4


@dataclass
class Evaluator:
    """E[points] d'une compo contre `opponent`, avec cache. `home` : la compo évaluée joue à domicile."""

    draws: Draws
    opponent: Lineup
    home: bool
    cache: dict[Lineup, float] = field(default_factory=dict)

    def __call__(self, lineup: Lineup) -> float:
        if lineup not in self.cache:
            r = (
                simulate(lineup, self.opponent, self.draws)
                if self.home
                else simulate(self.opponent, lineup, self.draws)
            )
            self.cache[lineup] = r.expected_points(home_side=self.home)
        return self.cache[lineup]

    def against(self, opponent: Lineup) -> "Evaluator":
        return Evaluator(self.draws, opponent, self.home)

    def result(self, lineup: Lineup):
        return simulate(lineup, self.opponent, self.draws) if self.home else simulate(self.opponent, lineup, self.draws)


def contribution(draws: Draws) -> np.ndarray:
    """Note espérée apportée par chaque joueur s'il est titulaire : sa note s'il joue, un Rotaldo sinon."""
    return np.where(draws.plays, draws.note, ROTALDO_NOTE).mean(axis=1)


def _ranked(rows: list[int], draws: Draws, value: np.ndarray) -> dict[str, list[int]]:
    out = {g: [] for g in "GDMA"}
    for r in sorted(rows, key=lambda r: -value[r]):
        out[draws.line[r]].append(r)
    return out


def initial_lineup(rows: list[int], draws: Draws, formation: str, value: np.ndarray, bonus: str | None = None):
    """11 des meilleurs par poste, banc par ordre de valeur, capitaine = meilleur titulaire de champ. None si un
    poste ne peut pas être pourvu."""
    ranked = _ranked(rows, draws, value)
    slots = slots_of(formation)
    need = {g: slots.count(g) for g in "GDMA"}
    if any(len(ranked[g]) < n for g, n in need.items()):
        return None
    starters = [r for g in "GDMA" for r in ranked[g][: need[g]]]
    rest = {g: ranked[g][need[g] :] for g in "GDMA"}
    bench = rest["G"][:1]
    pool = sorted((r for g in "DMA" for r in rest[g]), key=lambda r: -value[r])
    bench += pool[: BENCH_SIZE - len(bench)]
    bench.sort(key=lambda r: ("GDMA".index(draws.line[r]), -value[r]))
    field_starters = [r for r in starters if draws.line[r] != "G"]
    captain = max(field_starters, key=lambda r: value[r])
    return Lineup(formation=formation, starters=tuple(starters), bench=tuple(bench), captain=captain, bonus=bonus)


def _neighbours(lu: Lineup, rows: list[int], draws: Draws) -> Iterator[Lineup]:
    starters, bench = list(lu.starters), list(lu.bench)
    on_sheet = set(starters) | set(bench)
    off = [r for r in rows if r not in on_sheet]
    tactic_players = {t.out for t in lu.tactics} | {t.inp for t in lu.tactics}
    for i, s in enumerate(starters):
        if s in tactic_players:
            continue
        for j, b in enumerate(bench):
            if draws.line[b] == draws.line[s] and b not in tactic_players:
                new_s, new_b = starters.copy(), bench.copy()
                new_s[i], new_b[j] = b, s
                cap = b if lu.captain == s else lu.captain
                yield lu.with_(starters=tuple(new_s), bench=tuple(new_b), captain=cap)
        for o in off:
            if draws.line[o] == draws.line[s]:
                new_s = starters.copy()
                new_s[i] = o
                cap = o if lu.captain == s else lu.captain
                yield lu.with_(starters=tuple(new_s), captain=cap)
    for j, b in enumerate(bench):
        if b in tactic_players:
            continue
        for o in off:
            if (draws.line[o] == "G") == (draws.line[b] == "G"):
                new_b = bench.copy()
                new_b[j] = o
                yield lu.with_(bench=tuple(new_b))
    for j in range(len(bench) - 1):
        if draws.line[bench[j]] == draws.line[bench[j + 1]]:
            new_b = bench.copy()
            new_b[j], new_b[j + 1] = new_b[j + 1], new_b[j]
            yield lu.with_(bench=tuple(new_b))
    if len(bench) < BENCH_SIZE:
        for o in off:
            if draws.line[o] != "G" or not any(draws.line[b] == "G" for b in bench):
                yield lu.with_(bench=tuple(bench + [o]))


def local_search(lu: Lineup, rows: list[int], ev: Evaluator, max_moves: int = 40) -> Lineup:
    best = ev(lu)
    for _ in range(max_moves):
        move = next((c for c in _neighbours(lu, rows, ev.draws) if ev(c) > best + EPS), None)
        if move is None:
            break
        lu, best = move, ev(move)
    return lu


def best_captain(lu: Lineup, draws: Draws, ev: Callable[[Lineup], float]) -> Lineup:
    cands = [r for r in lu.starters if draws.line[r] != "G" and r != lu.mcdo_target]
    return max((lu.with_(captain=c) for c in cands), key=ev)


def add_tactics(lu: Lineup, draws: Draws, ev: Callable[[Lineup], float]) -> Lineup:
    best = ev(lu)
    while len(lu.tactics) < MAX_TACTICS:
        used = {t.out for t in lu.tactics} | {t.inp for t in lu.tactics}
        cands = [
            lu.with_(tactics=lu.tactics + (Tactic(out=s, inp=b, threshold=th),))
            for s in lu.starters
            if draws.line[s] != "G" and s not in used
            for b in lu.bench
            if draws.line[b] == draws.line[s] and b not in used
            for th in THRESHOLDS
        ]
        if not cands:
            break
        top = max(cands, key=ev)
        if ev(top) <= best + EPS:
            break
        lu, best = top, ev(top)
    return lu


def prune_tactics(lu: Lineup, holdout: Evaluator) -> Lineup:
    """Retire un à un les remplacements tactiques qui ne rapportent rien sur des tirages indépendants : leur choix
    sur les tirages d'optimisation est biaisé vers le haut (meilleur de nombreux candidats)."""
    while lu.tactics:
        base = holdout(lu)
        weakest = max(
            (lu.with_(tactics=tuple(x for x in lu.tactics if x != t)) for t in lu.tactics),
            key=holdout,
        )
        if holdout(weakest) < base:
            break
        lu = weakest
    return lu


def optimise(
    rows: list[int],
    ev: Evaluator,
    bonus: str | None = None,
    tactics: bool = True,
    formations: tuple[str, ...] | None = None,
) -> list[Lineup]:
    """Compos optimisées des `TOP_FORMATIONS` formations les plus prometteuses au départ, par E[points] décroissant.

    Les autres formations ne sont pas renvoyées : non optimisées, elles paraîtraient à tort bien moins bonnes."""
    value = contribution(ev.draws)
    if formations is None:
        formations = (FORMATION_424,) if bonus == F424 else FORMATIONS
    starts = [lu for f in formations if (lu := initial_lineup(rows, ev.draws, f, value, bonus)) is not None]
    if not starts:
        raise ValueError("aucune formation ne peut être alignée avec cet effectif")
    starts.sort(key=ev, reverse=True)
    out = []
    for lu in starts[:TOP_FORMATIONS]:
        lu = local_search(lu, rows, ev)
        lu = best_captain(lu, ev.draws, ev)
        if tactics:
            lu = add_tactics(lu, ev.draws, ev)
        lu = local_search(lu, rows, ev)
        out.append(lu)
    return sorted(out, key=ev, reverse=True)


def with_mcdo(lu: Lineup, draws: Draws, ev: Callable[[Lineup], float]) -> Lineup:
    value = contribution(draws)
    cands = sorted((r for r in lu.starters if draws.line[r] != "G"), key=lambda r: -value[r])[: MCDO_CANDIDATES + 1]
    options = []
    for target in cands:
        trial = lu.with_(bonus=MCDO, mcdo_target=target)
        if trial.captain == target:
            trial = best_captain(trial, draws, ev)
        options.append(trial)
    return max(options, key=ev)


def opponent_bonus_probs(remaining: pd.DataFrame, team_id: int, matches_left: int) -> dict[str, float]:
    """P(l'adversaire pose chaque bonus à ce match) : ses bonus restants répartis au hasard sur ses matchs restants,
    au plus un par match (hypothèse de `bonus_shifts`). Le Miroir et le 424 sont exclus : leur effet sur moi
    dépend de ma propre décision."""
    if remaining is None or matches_left <= 0:
        return {}
    mine = remaining[(remaining["team_id"] == team_id) & (remaining["restants"] > 0)]
    stock = {bonus_key(b): int(q) for b, q in zip(mine["bonus"], mine["restants"])}
    total = sum(stock.values())
    if total == 0:
        return {}
    p_any = min(1.0, total / matches_left)
    return {k: p_any * q / total for k, q in stock.items() if k not in (MIROIR, F424)}


def opponent_variant(opp: Lineup, key: str, draws: Draws) -> Lineup:
    if key == MCDO:
        value = contribution(draws)
        target = max((r for r in opp.starters if draws.line[r] != "G" and r != opp.captain), key=lambda r: value[r])
        return opp.with_(bonus=MCDO, mcdo_target=target)
    return opp.with_(bonus=key)


def expected_vs_opponent_bonus(lu: Lineup, ev: Evaluator, probs: dict[str, float]) -> float:
    """E[points] moyenné sur les bonus que l'adversaire peut poser (sans bonus avec la probabilité restante)."""
    p_none = 1.0 - sum(probs.values())
    total = p_none * ev(lu)
    for key, p in probs.items():
        total += p * ev.against(opponent_variant(ev.opponent, key, ev.draws))(lu)
    return total


def mirror_gain(lu: Lineup, ev: Evaluator, probs: dict[str, float]) -> float:
    """Gain espéré du Miroir : il ne rapporte que si l'adversaire pose un bonus, qu'il renvoie alors contre lui."""
    gain = 0.0
    for key, p in probs.items():
        sub = ev.against(opponent_variant(ev.opponent, key, ev.draws))
        gain += p * (sub(lu.with_(bonus=MIROIR, mcdo_target=None)) - sub(lu.with_(bonus=None, mcdo_target=None)))
    return gain


def bonus_gains(
    lu: Lineup, rows: list[int], ev: Evaluator, stock: dict[str, int], probs: dict[str, float], full: bool = True
) -> dict[str, tuple[float, Lineup]]:
    """Gain en points espérés de chaque bonus disponible par rapport à `lu` sans bonus, avec la compo à poser."""
    base = lu.with_(bonus=None, mcdo_target=None)
    ref = ev(base)
    out = {}
    for key, qty in stock.items():
        if qty <= 0:
            continue
        if key == MCDO:
            trial = with_mcdo(base, ev.draws, ev)
        elif key == F424:
            found = optimise(rows, ev, bonus=F424, tactics=full) if full else None
            trial = found[0] if found else initial_lineup(rows, ev.draws, FORMATION_424, contribution(ev.draws), F424)
            if trial is None:
                continue
        elif key == MIROIR:
            out[key] = (mirror_gain(base, ev, probs), base.with_(bonus=MIROIR))
            continue
        else:
            trial = base.with_(bonus=key)
        out[key] = (ev(trial) - ref, trial)
    return out
