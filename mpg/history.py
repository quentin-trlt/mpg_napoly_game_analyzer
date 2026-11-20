"""Mémoire de la ligue : les saisons mises bout à bout, par coach (pseudo canonique de `mpg.seasons`)."""

import numpy as np
import pandas as pd

from mpg.analysis import Analysis
from mpg.seasons import Season, coach_by_team

CAREER_COLUMNS = [
    "saison",
    "en_cours",
    "coach",
    "equipe",
    "team_id",
    "rang",
    "n_equipes",
    "j",
    "pts",
    "g",
    "n",
    "p",
    "diff",
    "xpts",
    "chance",
    "regret_moy",
]
MATCH_COLUMNS = ["saison", "gw", "adversaire", "opp_name", "domicile", "bp", "bc", "resultat"]
HONOURS_COLUMNS = [
    "coach",
    "saisons",
    "matchs",
    "pts",
    "ppm",
    "xppm",
    "chance",
    "titres",
    "meilleur_rang",
    "meilleure_saison",
    "meilleure_equipe",
]


def _require(seasons: list[tuple[Season, Analysis]]) -> None:
    if not seasons:
        raise ValueError("Aucune saison fournie : impossible de construire l'historique.")


def career(seasons: list[tuple[Season, Analysis]]) -> pd.DataFrame:
    """Une ligne par coach et par saison : rang, bilan, points mérités, chance et regret moyen du banc."""
    _require(seasons)
    rows = []
    for season, a in seasons:
        by_team = coach_by_team(a.league)
        table = a.standings.merge(a.luck[["team_id", "xpts_allplay", "chance_totale"]], on="team_id").merge(
            a.coaching[["team_id", "regret_moy"]], on="team_id"
        )
        rows += [
            {
                "saison": season.key,
                "en_cours": season.current,
                "coach": by_team[int(r.team_id)],
                "equipe": r.team_name,
                "team_id": int(r.team_id),
                "rang": int(r.rang),
                "n_equipes": len(table),
                "j": int(r.j),
                "pts": int(r.pts),
                "g": int(r.g),
                "n": int(r.n),
                "p": int(r.p),
                "diff": int(r.diff),
                "xpts": float(r.xpts_allplay),
                "chance": float(r.chance_totale),
                "regret_moy": float(r.regret_moy),
            }
            for r in table.itertuples()
        ]
    return pd.DataFrame(rows, columns=CAREER_COLUMNS)


def head_to_head(seasons: list[tuple[Season, Analysis]], coach: str) -> pd.DataFrame:
    """Tous les matchs joués par un coach, toutes saisons confondues, avec le coach adverse (pseudo canonique)."""
    _require(seasons)
    by_team_season = [coach_by_team(a.league) for _, a in seasons]
    known = {c for by_team in by_team_season for c in by_team.values()}
    if coach not in known:
        raise ValueError(
            f"Coach inconnu : {coach!r} n'a joué dans aucune saison (coachs connus : "
            f"{', '.join(sorted(known, key=str.lower))})."
        )
    frames = []
    for (season, a), by_team in zip(seasons, by_team_season):
        tm = a.team_match
        mine = tm[tm["team_id"].map(by_team) == coach]
        frames.append(mine.assign(saison=season.key, adversaire=mine["opp_id"].map(by_team))[MATCH_COLUMNS])
    return pd.concat(frames, ignore_index=True)


def honours(seasons: list[tuple[Season, Analysis]]) -> pd.DataFrame:
    """Palmarès par coach, trié par points par match : cumuls, titres (saisons terminées) et meilleur rang."""
    car = career(seasons)
    grouped = car.groupby("coach")
    totals = grouped.agg(
        saisons=("saison", "nunique"),
        matchs=("j", "sum"),
        pts=("pts", "sum"),
        xpts=("xpts", "sum"),
        chance=("chance", "sum"),
    )
    matchs = totals["matchs"].replace(0, np.nan)
    totals["ppm"] = totals["pts"] / matchs
    totals["xppm"] = totals["xpts"] / matchs
    totals["titres"] = (
        car[(car["rang"] == 1) & ~car["en_cours"]].groupby("coach").size().reindex(totals.index, fill_value=0)
    )
    best = car.sort_values(["rang", "saison"]).groupby("coach").first()
    totals["meilleur_rang"] = best["rang"]
    totals["meilleure_saison"] = best["saison"]
    totals["meilleure_equipe"] = best["equipe"]
    return totals.sort_values("ppm", ascending=False, na_position="last").reset_index()[HONOURS_COLUMNS]
