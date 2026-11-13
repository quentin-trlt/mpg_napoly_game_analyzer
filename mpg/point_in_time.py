"""Données joueurs telles qu'on les connaissait avant une journée MPG, reconstruites depuis player_match_notes.csv.

Une journée MPG g se joue sur la journée de PL r = `pl_gw_for(g)`. Avant g, on connaît les notes des matchs de PL
commencés avant le premier coup d'envoi de r. Les colonnes de saison PL de players.csv (note moyenne, matchs joués,
titularisations, buts, passes) sont recalculées sur ces seuls matchs, et player_match_notes est tronqué à ces
matchs (loi des notes de `mpg.notes`). Le statut du jour (blessé, suspendu,
incertain) n'est pas archivé : il vaut « ok ». La cote MPG et `points_mpg_moy` restent celles du jour.
"""

import dataclasses

import pandas as pd

from mpg.loader import League, derive_player_columns
from mpg.premier_league import pl_gw_for

COUNT_COLUMNS = ["matchs_club", "matchs_joues", "matchs_titulaire", "buts_reels_saison", "passes_decisives_saison"]


def pl_kickoff(league: League, mpg_gw: int) -> pd.Timestamp:
    """Premier coup d'envoi de la journée de PL sur laquelle se joue la journée MPG `mpg_gw`."""
    r = pl_gw_for(league, mpg_gw)
    return league.club_results.loc[league.club_results["pl_gw"] == r, "date"].min()


def notes_before(league: League, mpg_gw: int) -> pd.DataFrame | None:
    """Lignes de player_match_notes des matchs de PL commencés avant la journée MPG `mpg_gw`.

    None sans player_match_notes.csv ou sans club_results.csv.
    """
    notes = league.player_match_notes
    if notes is None or league.club_results is None:
        return None
    return notes[notes["date"] < pl_kickoff(league, mpg_gw)]


def season_totals(notes: pd.DataFrame) -> pd.DataFrame:
    """Colonnes de saison PL de players.csv recalculées sur `notes`, indexées par player_key."""
    g = notes[notes["pl_match_id"].notna()].groupby("player_key")
    return pd.DataFrame(
        {
            "note_moy_reelle": g["note"].mean(),
            "matchs_club": g.size(),
            "matchs_joues": g["a_joue"].sum(),
            "matchs_titulaire": g["titulaire"].sum(),
            "buts_reels_saison": g["buts"].sum(),
            "passes_decisives_saison": g["passes_decisives"].sum(),
        }
    )


def players_before(league: League, mpg_gw: int) -> pd.DataFrame | None:
    """players.csv tel qu'on l'aurait exporté juste avant la journée MPG `mpg_gw` (None sans notes par match)."""
    notes = notes_before(league, mpg_gw)
    if notes is None:
        return None
    totals = season_totals(notes)
    p = league.players.copy()
    keys = p["player_key"]
    p["note_moy_reelle"] = keys.map(totals["note_moy_reelle"])
    for col in COUNT_COLUMNS:
        p[col] = keys.map(totals[col]).fillna(0).astype(int)
    p["statut_performance"] = "ok"
    return derive_player_columns(p)


def league_before(league: League, mpg_gw: int) -> League | None:
    """Ligue vue avant la journée MPG `mpg_gw` : joueurs recalculés, notes de PL antérieures, buts et meilleurs
    joueurs des journées < `mpg_gw`.

    Calendrier, compos et résultats ne sont pas tronqués : l'appelant filtre déjà ses tables par journée.
    """
    players = players_before(league, mpg_gw)
    if players is None:
        return None
    return dataclasses.replace(
        league,
        players=players,
        player_match_notes=notes_before(league, mpg_gw),
        goals=league.goals[league.goals["gw"] < mpg_gw],
        best_players=league.best_players[league.best_players["gw"] < mpg_gw],
    )
