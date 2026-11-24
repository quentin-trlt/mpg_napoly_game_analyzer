"""Compo type d'une équipe : ses choix habituels de la saison, corrigés des absences prévues.

Chaque journée passée pèse 0,5^(âge / demi-vie), la dernière jouée pesant 1. Un joueur vaut sa part pondérée de
titularisations, plus `BENCH_WEIGHT` fois sa part de banc, multipliée par sa probabilité de jouer : un titulaire
habituel blessé passe derrière son remplaçant habituel. Les joueurs sans historique dans l'équipe ne servent qu'à
combler un poste, par ordre de contribution espérée. La formation est la plus utilisée (pondérée), le capitaine le
plus souvent désigné parmi les titulaires retenus. Pas de remplacement tactique : ceux de l'adversaire sont inconnus.
"""

from dataclasses import dataclass

import pandas as pd

from mpg.analysis import Analysis
from mpg.coach.optimizer import contribution, initial_lineup
from mpg.coach.rules import FORMATIONS, Draws, Lineup
from mpg.loader import COACH_PICKS

# experiments/backtest_opponent.py : la précision croît quand la demi-vie baisse ; 0,25 garde un peu des matchs
# précédents pour départager les remplaçants
HALF_LIFE = 0.25
BENCH_WEIGHT = 0.5
BENCH_STATUSES = ("remplacant_entre", "remplacant_non_entre")
TIE_BREAK = 1e-4


@dataclass(frozen=True)
class Usage:
    """Parts pondérées des journées passées (index `player_key` ; colonnes titulaire, banc, capitaine)."""

    share: pd.DataFrame
    formation: str | None


def usage(a: Analysis, team_id: int, gw: int, half_life: float = HALF_LIFE) -> Usage:
    """Habitudes de l'équipe sur ses matchs MPG des journées < `gw`."""
    tm = a.team_match
    tm = tm[(tm["team_id"] == team_id) & (tm["gw"] < gw)]
    empty = pd.DataFrame(columns=["titulaire", "banc", "capitaine"], dtype=float)
    if tm.empty:
        return Usage(empty, None)
    w = 0.5 ** ((gw - 1 - tm["gw"]) / half_life)
    by_formation = w.groupby(tm["formation"]).sum()
    by_formation = by_formation[by_formation.index.isin(FORMATIONS)]
    formation = str(by_formation.idxmax()) if len(by_formation) else None

    lu = a.lineups
    lu = lu[(lu["team_id"] == team_id) & (lu["gw"] < gw) & lu["player_key"].notna()]
    lu = lu.assign(w=lu["match_id"].map(dict(zip(tm["match_id"], w))).fillna(0.0))
    share = pd.DataFrame(
        {
            "titulaire": lu[lu["statut"].isin(COACH_PICKS)].groupby("player_key")["w"].sum(),
            "banc": lu[lu["statut"].isin(BENCH_STATUSES)].groupby("player_key")["w"].sum(),
            "capitaine": lu[lu["capitaine"] == 1].groupby("player_key")["w"].sum(),
        }
    )
    return Usage(share.fillna(0.0) / w.sum(), formation)


def typical_lineup(rows: list[int], draws: Draws, use: Usage) -> Lineup:
    """Compo type parmi les lignes `rows` de `draws` (joueurs de l'équipe)."""
    keys = [draws.keys[r] for r in rows]
    habit = use.share.reindex(keys).fillna(0.0)
    p_play = draws.plays[rows].mean(axis=1)
    value = TIE_BREAK * contribution(draws)
    value[rows] += p_play * (habit["titulaire"].to_numpy() + BENCH_WEIGHT * habit["banc"].to_numpy())

    lu = initial_lineup(rows, draws, use.formation, value) if use.formation else None
    if lu is None:
        starts = [x for f in FORMATIONS if (x := initial_lineup(rows, draws, f, value)) is not None]
        if not starts:
            raise ValueError("aucune formation ne peut être alignée avec cet effectif")
        lu = max(starts, key=lambda x: float(value[list(x.starters)].sum()))

    caps = habit["capitaine"].to_numpy()
    field = [i for i, r in enumerate(rows) if r in lu.starters and draws.line[r] != "G" and caps[i] > 0]
    if field:
        lu = lu.with_(captain=rows[max(field, key=lambda i: caps[i])])
    return lu
