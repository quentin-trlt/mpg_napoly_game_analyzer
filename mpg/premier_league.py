import numpy as np
import pandas as pd

from mpg.loader import PL_COUNTED


def club_view(results: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par club et par match de Premier League, vue du club (adversaire, lieu, score, résultat)."""
    sides = []
    for side, opp, own_score, opp_score, home in (
        ("home", "away", "home_score", "away_score", True),
        ("away", "home", "away_score", "home_score", False),
    ):
        sides.append(
            pd.DataFrame(
                {
                    "pl_match_id": results["pl_match_id"],
                    "pl_gw": results["pl_gw"],
                    "date": results["date"],
                    "club": results[f"{side}_club"],
                    "adversaire": results[f"{opp}_club"],
                    "adversaire_short": results[f"{opp}_club_short"],
                    "domicile": home,
                    "bp": results[own_score],
                    "bc": results[opp_score],
                    "statut": results["statut"],
                }
            )
        )
    out = pd.concat(sides, ignore_index=True)
    played = out["statut"] == "joue"
    win = (out["bp"] > out["bc"]).fillna(False).to_numpy(bool)
    draw = (out["bp"] == out["bc"]).fillna(False).to_numpy(bool)
    res = np.select([win, draw], ["V", "N"], "D")
    out["resultat"] = pd.Series(res, index=out.index).where(played)
    return out.sort_values(["club", "date"]).reset_index(drop=True)


def last_results(results: pd.DataFrame, club: str, n: int | None = None) -> pd.DataFrame:
    """Matchs joués d'un club, du plus récent au plus ancien (`n` derniers si précisé)."""
    v = club_view(results)
    done = v[(v["club"] == club) & (v["statut"] == "joue")].sort_values("date", ascending=False)
    return done if n is None else done.head(n)


def next_match(results: pd.DataFrame, club: str) -> pd.Series | None:
    """Prochain match à venir d'un club, None s'il n'en reste aucun."""
    v = club_view(results)
    todo = v[(v["club"] == club) & (v["statut"] == "a_venir")].sort_values("date")
    return None if todo.empty else todo.iloc[0]


def club_form(results: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Par club : `n` derniers résultats (ordre chronologique) et prochain adversaire avec sa date."""
    v = club_view(results)
    done = v[v["statut"] == "joue"].sort_values("date")
    forme = done.groupby("club")["resultat"].apply(lambda s: "".join(s.tail(n))).rename("forme_club")
    todo = v[v["statut"] == "a_venir"].sort_values("date").groupby("club").head(1).set_index("club")
    nxt = todo[["adversaire", "adversaire_short", "domicile", "date"]].add_prefix("prochain_")
    return pd.concat([forme, nxt], axis=1).rename_axis("club").reset_index()


def player_totals(pl_goals: pd.DataFrame) -> pd.DataFrame:
    """Buts et passes décisives de Premier League par player_key (buts et penalties, hors csc et annule_var)."""
    counted = pl_goals[pl_goals["type_but"].isin(PL_COUNTED)]
    buts = counted.dropna(subset=["buteur_player_key"]).groupby("buteur_player_key").size().rename("buts_pl")
    passes = counted.dropna(subset=["passeur_player_key"]).groupby("passeur_player_key").size().rename("passes_pl")
    out = pd.concat([buts, passes], axis=1).fillna(0).astype(int)
    return out.rename_axis("player_key").reset_index()
