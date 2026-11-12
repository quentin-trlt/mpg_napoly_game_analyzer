"""Moteur de match MPG (mode remplacements tactiques), vectorisé sur les tirages.

Règles : https://ligue1.com/fr/articles/l1_article_443-mpg-toutes-les-regles-a-connaitre-1. Le calcul des buts
MPG (`score_sheets`) retrouve exactement les buts MPG de toutes les journées jouées de la ligue.

Un match se joue en trois temps :
1. remplacements (`_substitute`) : tactiques d'abord, puis automatiques (même poste, sinon poste inférieur avec
   −1 par poste sauté), sinon Rotaldo à 2,5 ;
2. bonus de note (`_sheet`) : défense à 4 ou 5, capitaine, McDo+, Zahia, Suarez et Cheat Code subis ;
3. score (`score_sheets`) : buts réels, arrêt MPG du gardien noté ≥ 8, buts MPG, CSC réels, CSC de Rotaldo,
   Valise à Nanard.
"""

from dataclasses import dataclass, field, replace

import numpy as np

from mpg.forecast.bonus import CHEAT, F424, MCDO, MIROIR, SUAREZ, TONTON, VALISE, ZAHIA

LINES = ("G", "D", "M", "A")
LOWER = {"G": (), "D": (), "M": ("D",), "A": ("M", "D")}
PATHS = {"D": ("A", "M", "D"), "M": ("M", "D"), "A": ("D",)}
FORMATIONS = ("3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1")
FORMATION_424 = "4-2-4"
DEFENCE_BONUS = {4: 0.5, 5: 1.0}
ROTALDO = -1
ROTALDO_NOTE = 2.5
MPG_GOAL_MIN_NOTE = 5.0
SAVE_NOTE = 8.0
CAPTAIN_BONUS = 0.5
BENCH_SIZE = 7
MAX_TACTICS = 6
POINTS = np.array([3.0, 1.0, 0.0])


def slots_of(formation: str) -> tuple[str, ...]:
    try:
        d, m, a = (int(x) for x in formation.split("-"))
    except ValueError as exc:
        raise ValueError(f"formation invalide : {formation!r}") from exc
    if d + m + a != 10:
        raise ValueError(f"formation invalide (pas 10 joueurs de champ) : {formation!r}")
    return ("G",) + ("D",) * d + ("M",) * m + ("A",) * a


@dataclass(frozen=True)
class Tactic:
    """Remplacement tactique : `inp` remplace `out` si la note de `out` est sous `threshold` (ou s'il n'a pas joué)."""

    out: int
    inp: int
    threshold: float


@dataclass(frozen=True)
class Lineup:
    """Feuille de match. Les joueurs sont des indices de ligne dans `Draws` ; `starters` suit l'ordre des postes
    de `slots_of(formation)` (G, puis D, M, A)."""

    formation: str
    starters: tuple[int, ...]
    bench: tuple[int, ...] = ()
    tactics: tuple[Tactic, ...] = ()
    captain: int | None = None
    bonus: str | None = None
    mcdo_target: int | None = None

    def with_(self, **changes) -> "Lineup":
        return replace(self, **changes)

    def validate(self, lines: np.ndarray) -> None:
        slots = slots_of(self.formation)
        if self.formation == FORMATION_424 and self.bonus != F424:
            raise ValueError("le 4-2-4 n'est possible qu'avec le bonus 424")
        if len(self.starters) != len(slots):
            raise ValueError(f"{len(self.starters)} titulaires pour {len(slots)} postes")
        wrong = [p for p, s in zip(self.starters, slots) if lines[p] != s]
        if wrong:
            raise ValueError(f"titulaires hors de leur poste : {wrong}")
        everyone = list(self.starters) + list(self.bench)
        if len(set(everyone)) != len(everyone):
            raise ValueError("un joueur figure deux fois sur la feuille")
        if len(self.bench) > BENCH_SIZE or sum(lines[p] == "G" for p in self.bench) > 1:
            raise ValueError("banc de 7 joueurs au plus, dont 1 gardien au plus")
        if len(self.tactics) > MAX_TACTICS:
            raise ValueError(f"{MAX_TACTICS} remplacements tactiques au plus")
        for t in self.tactics:
            if t.out not in self.starters or t.inp not in self.bench or lines[t.out] == "G":
                raise ValueError(f"remplacement tactique invalide : {t}")
        if self.captain is not None and (self.captain not in self.starters or lines[self.captain] == "G"):
            raise ValueError("le capitaine doit être un titulaire de champ")
        if self.bonus == MCDO and (self.mcdo_target not in self.starters or lines[self.mcdo_target] == "G"):
            raise ValueError("McDo+ doit cibler un titulaire de champ")


@dataclass
class Draws:
    """Tirages par joueur : a joué (P, N), note brute arrondie à 0,5, buts réels, CSC réels."""

    keys: list[str]
    line: np.ndarray
    plays: np.ndarray
    note: np.ndarray
    goals: np.ndarray
    own_goals: np.ndarray
    _index: dict[str, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._index = {k: i for i, k in enumerate(self.keys)}

    @property
    def n(self) -> int:
        return self.plays.shape[1]

    def row(self, key: str) -> int:
        return self._index[key]


@dataclass
class Sheet:
    """Équipe sur le terrain après remplacements et bonus : 11 postes × N tirages."""

    line: tuple[str, ...]
    note: np.ndarray
    goals: np.ndarray
    rotaldo: np.ndarray
    own_goals: np.ndarray

    def line_mean(self, line: str) -> np.ndarray:
        idx = [i for i, g in enumerate(self.line) if g == line]
        return self.note[idx].mean(axis=0)

    @property
    def keeper(self) -> np.ndarray:
        return self.note[self.line.index("G")]


@dataclass
class _Pitch:
    occ: np.ndarray
    note: np.ndarray
    original: np.ndarray


def _substitute(lineup: Lineup, draws: Draws, cancel_tactics: bool) -> _Pitch:
    slots = slots_of(lineup.formation)
    starters = np.array(lineup.starters)
    n = draws.n
    occ = np.repeat(starters[:, None], n, axis=1)
    on = draws.plays[starters].copy()
    note = np.where(on, draws.note[starters], np.nan)
    original = on.copy()
    bench = list(lineup.bench)
    used = np.zeros((len(bench), n), dtype=bool)
    slot_of = {p: i for i, p in enumerate(lineup.starters)}
    bench_of = {p: i for i, p in enumerate(bench)}

    if not cancel_tactics:
        for t in lineup.tactics:
            s, b = slot_of[t.out], bench_of[t.inp]
            low = ~on[s] | (np.nan_to_num(note[s], nan=0.0) < t.threshold)
            fire = draws.plays[t.inp] & ~used[b] & (occ[s] == t.out) & low
            occ[s] = np.where(fire, t.inp, occ[s])
            note[s] = np.where(fire, draws.note[t.inp], note[s])
            on[s] |= fire
            original[s] &= ~fire
            used[b] |= fire

    def fill(s: int, line: str, malus: float) -> None:
        need = ~on[s]
        for b, p in enumerate(bench):
            if draws.line[p] != line or not need.any():
                continue
            take = need & draws.plays[p] & ~used[b]
            occ[s] = np.where(take, p, occ[s])
            note[s] = np.where(take, draws.note[p] - malus, note[s])
            on[s] |= take
            used[b] |= take
            need &= ~take

    for s, line in enumerate(slots):
        fill(s, line, 0.0)
    for s, line in enumerate(slots):
        for depth, lower in enumerate(LOWER[line], start=1):
            fill(s, lower, float(depth))

    occ = np.where(on, occ, ROTALDO)
    note = np.where(on, note, ROTALDO_NOTE)
    return _Pitch(occ=occ, note=note, original=original)


@dataclass(frozen=True)
class Effects:
    """Bonus effectivement actifs pour une équipe, après résolution du Miroir."""

    own: str | None = None
    mirrored: bool = False
    defence_bonus_lost: bool = False
    extra_defence_bonus: float = 0.0


def resolve_bonuses(home: str | None, away: str | None) -> tuple[Effects, Effects]:
    """Le Miroir renvoie le bonus adverse au profit de celui qui l'a posé ; contre un 424, il récupère le bonus
    défensif de +0,5 de l'adversaire. Deux Miroirs, ou un Miroir face à aucun bonus, n'ont aucun effet."""

    def one_side(mine: str | None, theirs: str | None) -> Effects:
        if mine == MIROIR:
            if theirs == F424:
                return Effects(extra_defence_bonus=DEFENCE_BONUS[4])
            if theirs in (None, MIROIR):
                return Effects()
            return Effects(own=theirs, mirrored=True)
        if theirs == MIROIR and mine is not None:
            return Effects(defence_bonus_lost=mine == F424)
        return Effects(own=mine)

    return one_side(home, away), one_side(away, home)


def _sheet(lineup: Lineup, draws: Draws, mine: Effects, theirs: Effects) -> Sheet:
    slots = slots_of(lineup.formation)
    pitch = _substitute(lineup, draws, cancel_tactics=theirs.own == TONTON)
    note = pitch.note.copy()
    occ, original = pitch.occ, pitch.original
    is_def = np.array([s == "D" for s in slots])
    is_field = np.array([s != "G" for s in slots])

    n_def = int(is_def.sum())
    defence = 0.0 if mine.defence_bonus_lost else DEFENCE_BONUS.get(n_def, 0.0)
    note += (defence + mine.extra_defence_bonus) * (is_def[:, None] & original)

    mcdo_slot = None
    if mine.own == MCDO:
        if mine.mirrored:
            field_notes = np.where(is_field[:, None] & original, note, -np.inf)
            best = field_notes.argmax(axis=0)
            note[best, np.arange(draws.n)] += np.where(np.isfinite(field_notes.max(axis=0)), 1.0, 0.0)
        else:
            mcdo_slot = lineup.starters.index(lineup.mcdo_target)
            note[mcdo_slot] += 1.0 * original[mcdo_slot]
    if lineup.captain is not None:
        c = lineup.starters.index(lineup.captain)
        if c != mcdo_slot:
            note[c] += CAPTAIN_BONUS * original[c]
    if mine.own == ZAHIA:
        note += 0.5 * original
    if theirs.own == SUAREZ:
        note[0] -= 1.0
    if theirs.own == CHEAT:
        note -= 0.5 * is_field[:, None]

    rotaldo = occ == ROTALDO
    safe = np.where(rotaldo, 0, occ)
    cols = np.arange(draws.n)[None, :]
    goals = np.where(rotaldo, 0, draws.goals[safe, cols])
    own = np.where(rotaldo, 0, draws.own_goals[safe, cols]).sum(axis=0)
    return Sheet(line=slots, note=note, goals=goals, rotaldo=rotaldo, own_goals=own)


def _real_goals(att: Sheet, dfn: Sheet) -> np.ndarray:
    return np.maximum(att.goals.sum(axis=0) - (dfn.keeper >= SAVE_NOTE), 0)


def mpg_goals(att: Sheet, dfn: Sheet, att_home: bool) -> np.ndarray:
    """Buts MPG : joueur de champ noté ≥ 5, sans but réel, qui franchit chaque ligne adverse de son parcours
    (note > moyenne de la ligne, −1 après la première ligne franchie, −0,5 après les suivantes) puis bat le
    gardien. À égalité, l'équipe à domicile gagne le duel."""
    means = {line: dfn.line_mean(line) for line in ("D", "M", "A")}
    keeper = dfn.keeper

    def beats(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return (x > y) | (att_home & (x == y))

    total = np.zeros(att.note.shape[1], dtype=int)
    for s, line in enumerate(att.line):
        if line == "G":
            continue
        note = att.note[s].copy()
        ok = ~att.rotaldo[s] & (note >= MPG_GOAL_MIN_NOTE) & (att.goals[s] == 0)
        for i, crossed in enumerate(PATHS[line]):
            ok &= beats(note, means[crossed])
            note -= 1.0 if i == 0 else 0.5
        ok &= beats(note, keeper)
        total += ok
    return total


def rotaldo_own_goals(sheet: Sheet) -> np.ndarray:
    return np.minimum(sheet.rotaldo.sum(axis=0) // 3, 3)


def score_sheets(
    home: Sheet, away: Sheet, valise_home: bool = False, valise_away: bool = False
) -> tuple[np.ndarray, np.ndarray]:
    """Score final. La Valise posée par une équipe annule un but adverse réel ou MPG, jamais un CSC."""
    scored_home = _real_goals(home, away) + mpg_goals(home, away, att_home=True)
    scored_away = _real_goals(away, home) + mpg_goals(away, home, att_home=False)
    scored_home = scored_home - (valise_away & (scored_home > 0))
    scored_away = scored_away - (valise_home & (scored_away > 0))
    home_goals = scored_home + away.own_goals + rotaldo_own_goals(away)
    away_goals = scored_away + home.own_goals + rotaldo_own_goals(home)
    return home_goals, away_goals


@dataclass
class MatchResult:
    home_goals: np.ndarray
    away_goals: np.ndarray

    def outcome_probs(self, home_side: bool = True) -> np.ndarray:
        """P(victoire, nul, défaite) du point de vue de l'équipe à domicile (ou de l'extérieur)."""
        diff = self.home_goals - self.away_goals
        if not home_side:
            diff = -diff
        return np.array([(diff > 0).mean(), (diff == 0).mean(), (diff < 0).mean()])

    def points(self, home_side: bool = True) -> np.ndarray:
        diff = self.home_goals - self.away_goals
        if not home_side:
            diff = -diff
        return np.where(diff > 0, 3.0, np.where(diff == 0, 1.0, 0.0))

    def expected_points(self, home_side: bool = True) -> float:
        return float(self.points(home_side).mean())

    def stderr(self, home_side: bool = True) -> float:
        p = self.points(home_side)
        return float(p.std(ddof=1) / np.sqrt(len(p)))


def simulate(home: Lineup, away: Lineup, draws: Draws) -> MatchResult:
    home_fx, away_fx = resolve_bonuses(home.bonus, away.bonus)
    h = _sheet(home, draws, home_fx, away_fx)
    a = _sheet(away, draws, away_fx, home_fx)
    hg, ag = score_sheets(h, a, valise_home=home_fx.own == VALISE, valise_away=away_fx.own == VALISE)
    return MatchResult(home_goals=hg, away_goals=ag)
