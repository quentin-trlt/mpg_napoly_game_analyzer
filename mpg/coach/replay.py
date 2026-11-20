"""Rejeu des matchs joués : feuille de match réelle, puis feuille avec le meilleur 11 a posteriori."""

import logging

import numpy as np
import pandas as pd

from mpg.coach.rules import Sheet, score_sheets
from mpg.coaching import KEYS, best_by_line
from mpg.facts import OPPONENT_BONUS, OPPONENT_FIELD_BONUS
from mpg.loader import ON_PITCH, League
from mpg.premier_league import pl_gw_for

logger = logging.getLogger(__name__)

FIELD_LINE = {0: "G", 1: "D", 2: "M", 3: "M", 4: "A"}
REAL_GOALS = ("reel", "bloque")
POINTS = {1: 3, 0: 1, -1: 0}


def slot_lines(rows: pd.DataFrame) -> pd.Series:
    """Poste de chaque place du terrain. `ligne_terrain` est la rangée à l'écran : la plus haute est l'attaque
    (rangée 3 en 4-2-4, 4 sinon)."""
    level = rows["ligne_terrain"].astype(int)
    top = level.max()
    return level.map(lambda r: "A" if r == top and r >= 3 else FIELD_LINE[r])


def sheet_from_rows(rows: pd.DataFrame, goals: dict[str, int], own_goals: int) -> Sheet:
    rows = rows.sort_values("ligne_terrain")
    return Sheet(
        line=tuple(slot_lines(rows)),
        note=rows["note_avec_bonus"].to_numpy(float)[:, None],
        goals=np.array([goals.get(k, 0) if isinstance(k, str) else 0 for k in rows["player_key"]])[:, None],
        rotaldo=(rows["statut"] == "rotaldo").to_numpy()[:, None],
        own_goals=np.array([own_goals]),
    )


def play_match(fx, rows: dict[int, pd.DataFrame], goals: pd.DataFrame, bonus: pd.DataFrame) -> tuple[int, int]:
    """Score d'un match joué (`fx` : ligne de `league.played`) à partir des joueurs sur le terrain de chaque équipe.

    Les buts réels sont rattachés aux joueurs par leur clé : un joueur absent de `rows` perd ses buts. La colonne
    facultative `buts_banc` donne les buts réels d'un joueur qui n'était pas sur le terrain.
    """
    goals = goals[goals["match_id"] == fx.match_id]
    csc = goals[goals["type_but"] == "csc"]
    real = goals[goals["type_but"].isin(REAL_GOALS)]
    sheets = {}
    for team, opp in ((fx.home_team_id, fx.away_team_id), (fx.away_team_id, fx.home_team_id)):
        mine = real.loc[real["team_id"] == team, "player_key"].value_counts().to_dict()
        if "buts_banc" in rows[team]:
            mine.update(rows[team].set_index("player_key")["buts_banc"].loc[lambda b: b > 0].to_dict())
        sheets[team] = sheet_from_rows(rows[team], mine, int((csc["team_id"] == opp).sum()))
    posed = bonus[
        (bonus["match_id"] == fx.match_id) & bonus["bonus"].str.contains("valise", case=False) & bonus["effet"].notna()
    ]["team_id"]
    hg, ag = score_sheets(
        sheets[fx.home_team_id],
        sheets[fx.away_team_id],
        valise_home=fx.home_team_id in set(posed),
        valise_away=fx.away_team_id in set(posed),
    )
    return int(hg[0]), int(ag[0])


def _entrant_bonus(player: pd.Series, opp_bonus: pd.DataFrame) -> float:
    """Bonus ou malus subis par un joueur qui entre sur le terrain : ceux de l'adversaire. Les bonus de l'équipe
    (défense, Zahia) ne vont qu'aux titulaires, et capitaine et McDo+ restent sur leur cible."""
    total = 0.0
    for b in opp_bonus.itertuples():
        if b.bonus in OPPONENT_FIELD_BONUS and player["poste_groupe"] != "G":
            total += b.effet_pts
        elif b.bonus in OPPONENT_BONUS and b.cible_affiche == player["joueur_affiche"]:
            total += b.effet_pts
    return total


def bench_goals(league: League, gw: int) -> pd.Series | None:
    """Buts réels de chaque joueur de PL dans la journée de PL qui correspond à la journée MPG `gw`."""
    notes = league.player_match_notes
    if notes is None or league.club_results is None:
        return None
    played = notes[(notes["pl_gw"] == pl_gw_for(league, gw)) & (notes["a_joue"] == 1)]
    return played.groupby("player_key")["buts"].sum()


def with_best_eleven(
    sheet: pd.DataFrame, formation: str, bonus: pd.DataFrame, goals: pd.Series | None = None
) -> pd.DataFrame | None:
    """Joueurs sur le terrain une fois les meilleurs du banc à la place des titulaires moins bien notés du même poste.

    L'entrant prend la place du sortant, avec sa note brute et les bonus de l'adversaire. Le capitaine et la cible
    de McDo+ ne sortent jamais. Les places de Rotaldo sortent en premier. `goals` (voir `bench_goals`) donne les buts réels des entrants, colonne `buts_banc`
    (zéro si inconnus ; `attrs["buts_inconnus"]` compte ces entrants). Renvoie None si un entrant n'a aucune
    place à prendre à son poste.
    """
    match_id, team_id = sheet["match_id"].iloc[0], sheet["team_id"].iloc[0]
    pitch = sheet[sheet["sur_terrain"]].copy()
    pitch["ligne"] = slot_lines(pitch)
    pitch["buts_banc"] = 0
    unknown = 0
    in_match = bonus[bonus["match_id"] == match_id]
    mcdo_targets = in_match.loc[(in_match["bonus"] == "McDo+") & (in_match["team_id"] == team_id), "cible_affiche"]
    protected = (pitch["capitaine"] == 1) | pitch["joueur_affiche"].isin(mcdo_targets)
    opp = in_match[(in_match["team_id"] != team_id) & in_match["effet_pts"].notna()]
    for g, _, chosen in best_by_line(sheet, formation):
        entrants = chosen[~chosen["sur_terrain"]]
        if entrants.empty:
            continue
        leaving = pitch[(pitch["ligne"] == g) & ~pitch.index.isin(chosen.index) & ~protected]
        leaving = leaving.assign(_r=leaving["statut"] != "rotaldo").sort_values(["_r", "note_brute"])
        if len(leaving) < len(entrants):
            return None
        for slot, (_, new) in zip(leaving.index, entrants.iterrows()):
            pitch.loc[slot, ["player_key", "joueur_affiche", "statut"]] = [
                new["player_key"],
                new["joueur_affiche"],
                "remplacant_entre",
            ]
            pitch.loc[slot, "note_avec_bonus"] = new["note_brute"] + _entrant_bonus(new, opp)
            if goals is not None and new["player_key"] in goals.index:
                pitch.loc[slot, "buts_banc"] = int(goals[new["player_key"]])
            else:
                unknown += 1
    pitch = pitch.drop(columns="ligne")
    pitch.attrs["buts_inconnus"] = unknown
    return pitch


def optimal_replay(league: League, lu: pd.DataFrame, tm: pd.DataFrame, optimal: pd.DataFrame) -> pd.DataFrame:
    """Score de chaque équipe à chaque match joué si elle avait aligné le meilleur 11 de sa feuille de match.

    `optimal` est la sortie de `coaching.optimal_lineups` : sans regret, rien n'est échangé. Même formation, même capitaine, mêmes bonus, adversaire inchangé : remplacements tactiques non rejoués, et les
    buts réels d'un joueur resté sur le banc viennent de `player_match_notes`. Un match dont un échange est
    impossible n'est pas rejoué ; leur nombre est dans `attrs["exclus"]`.
    `attrs["buts_entrants"]` compte les buts réels pris en compte pour les joueurs du banc, `attrs["buts_inconnus"]` les entrants dont
    les buts sont inconnus (comptés pour zéro).
    """
    formations = tm.set_index(KEYS)["formation"]
    no_regret = set(optimal.loc[optimal["regret"] <= 0, KEYS].itertuples(index=False, name=None))
    sheets = dict(iter(lu.groupby(KEYS)))
    real = {key: s[s["statut"].isin(ON_PITCH)] for key, s in sheets.items()}
    out, excluded, unknown, entrant_goals = [], 0, 0, 0
    bench = {gw: bench_goals(league, gw) for gw in league.played["gw"].unique()}
    for fx in league.played.itertuples():
        for team, home in ((fx.home_team_id, True), (fx.away_team_id, False)):
            key = (fx.match_id, team)
            rows = {t: real[(fx.match_id, t)] for t in (fx.home_team_id, fx.away_team_id)}
            swapped = (
                real[key]
                if key in no_regret
                else with_best_eleven(sheets[key], formations[key], league.bonus, bench[fx.gw])
            )
            if swapped is None:
                excluded += 1
                continue
            rows[team] = swapped
            unknown += swapped.attrs.get("buts_inconnus", 0)
            entrant_goals += int(swapped["buts_banc"].sum()) if "buts_banc" in swapped else 0
            hg, ag = play_match(fx, rows, league.goals, league.bonus)
            bp, bc = (fx.home_goals, fx.away_goals) if home else (fx.away_goals, fx.home_goals)
            bp_opt, bc_opt = (hg, ag) if home else (ag, hg)
            out.append(
                {
                    "match_id": fx.match_id,
                    "team_id": team,
                    "bp": int(bp),
                    "bc": int(bc),
                    "bp_opt": bp_opt,
                    "bc_opt": bc_opt,
                    "pts": POINTS[int(np.sign(bp - bc))],
                    "pts_opt": POINTS[int(np.sign(bp_opt - bc_opt))],
                }
            )
    result = pd.DataFrame(out)
    result.attrs.update(exclus=excluded, buts_inconnus=unknown, buts_entrants=entrant_goals)
    if excluded:
        logger.info("%d feuilles de match non rejouées (échange impossible)", excluded)
    return result
