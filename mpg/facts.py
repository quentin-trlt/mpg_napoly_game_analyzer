import numpy as np
import pandas as pd

from mpg.loader import COACH_PICKS, ON_PITCH, League

POINTS = {"V": 3, "N": 1, "D": 0}
TARGETED_BONUS = {"Capitaine", "McDo+"}
OPPONENT_BONUS = {"Suarez"}
OPPONENT_FIELD_BONUS = {"Cheat Code 18-26"}
DEFENCE_BONUS = {"4 défenseurs", "5 défenseurs"}
TEAM_BONUS = {"Zahia"}


def team_fixtures(league: League) -> pd.DataFrame:
    """Une ligne par équipe et par match joué, vue de l'équipe (adversaire, domicile, score)."""
    played = league.played
    home = pd.DataFrame(
        {
            "match_id": played["match_id"],
            "gw": played["gw"],
            "date": played["date"],
            "team_id": played["home_team_id"],
            "opp_id": played["away_team_id"],
            "domicile": True,
            "bp": played["home_goals"],
            "bc": played["away_goals"],
            "formation": played["home_formation"],
            "formation_adv": played["away_formation"],
        }
    )
    away = pd.DataFrame(
        {
            "match_id": played["match_id"],
            "gw": played["gw"],
            "date": played["date"],
            "team_id": played["away_team_id"],
            "opp_id": played["home_team_id"],
            "domicile": False,
            "bp": played["away_goals"],
            "bc": played["home_goals"],
            "formation": played["away_formation"],
            "formation_adv": played["home_formation"],
        }
    )
    out = pd.concat([home, away], ignore_index=True)
    out[["team_id", "opp_id", "bp", "bc"]] = out[["team_id", "opp_id", "bp", "bc"]].astype(int)
    out["resultat"] = np.select([out["bp"] > out["bc"], out["bp"] == out["bc"]], ["V", "N"], "D")
    out["pts"] = out["resultat"].map(POINTS)
    return out.sort_values(["gw", "team_id"]).reset_index(drop=True)


def lineups_enriched(league: League) -> pd.DataFrame:
    """Compositions avec groupe de poste, adversaire, bonus attribué à chaque joueur et note brute estimée.

    La note brute retire les bonus nominatifs (Capitaine, McDo+), le Suarez subi, le Cheat Code subi (joueurs
    de champ adverses sur le terrain, Rotaldos exclus), les bonus défensifs (titulaires défenseurs) et Zahia
    (titulaires). Les bonus sans effet de note (Tonton Pat) sont ignorés.
    """
    lu = league.lineups.copy()
    opp = team_fixtures(league)[["match_id", "team_id", "opp_id"]]
    lu = lu.merge(opp, on=["match_id", "team_id"], how="left")
    groupe_joueur = league.players.set_index("player_key")["poste_groupe"]
    lu["poste_groupe"] = lu["poste_groupe"].fillna(lu["player_key"].map(groupe_joueur))
    lu["bonus_recu"] = 0.0

    on_pitch = lu["statut"].isin(ON_PITCH)
    for b in league.bonus.dropna(subset=["effet_pts"]).itertuples(index=False):
        same_match = lu["match_id"] == b.match_id
        own = same_match & (lu["team_id"] == b.team_id)
        if b.bonus in TARGETED_BONUS:
            mask = own & on_pitch & (lu["joueur_affiche"] == b.cible_affiche)
        elif b.bonus in OPPONENT_BONUS:
            mask = same_match & (lu["team_id"] != b.team_id) & on_pitch & (lu["joueur_affiche"] == b.cible_affiche)
        elif b.bonus in OPPONENT_FIELD_BONUS:
            field = (lu["statut"] != "rotaldo") & (lu["poste_groupe"] != "G")
            mask = same_match & (lu["team_id"] != b.team_id) & on_pitch & field
        elif b.bonus in DEFENCE_BONUS:
            mask = own & (lu["statut"] == "titulaire") & (lu["poste_groupe"] == "D")
        elif b.bonus in TEAM_BONUS:
            mask = own & (lu["statut"] == "titulaire")
        else:
            continue
        lu.loc[mask, "bonus_recu"] += b.effet_pts

    lu["note_brute"] = lu["note_avec_bonus"] - lu["bonus_recu"]
    lu["sur_terrain"] = on_pitch
    lu["choix_coach"] = lu["statut"].isin(COACH_PICKS)
    lu["a_joue_irl"] = lu["note_avec_bonus"].notna() & (lu["statut"] != "rotaldo")
    return lu


def _goal_counts(league: League) -> pd.DataFrame:
    goals = league.scored_goals
    g = goals.assign(type_but=goals["type_but"].replace({"rotaldo_csc": "csc"}))
    counts = g.groupby(["match_id", "team_id", "type_but"]).size().unstack(fill_value=0)
    for col in ("reel", "mpg", "csc"):
        if col not in counts:
            counts[col] = 0
    counts = counts[["reel", "mpg", "csc"]].add_prefix("bp_").reset_index()
    rotaldo = (
        (goals["type_but"] == "rotaldo_csc")
        .groupby([goals["match_id"], goals["team_id"]])
        .sum()
        .rename("bp_rotaldo_csc")
        .reset_index()
    )
    return counts.merge(rotaldo, on=["match_id", "team_id"], how="left")


def team_match(league: League) -> pd.DataFrame:
    """Table centrale : une ligne par équipe et par match joué, avec toutes les mesures de match."""
    tm = team_fixtures(league)
    lu = lineups_enriched(league)
    cote = league.players.set_index("player_key")["cote"]
    lu["cote"] = lu["player_key"].map(cote)
    taux_jeu = league.players.set_index("player_key")["taux_jeu"]
    lu["p_absence"] = 1 - lu["player_key"].map(taux_jeu).fillna(taux_jeu.median())

    keys = ["match_id", "team_id"]
    pitch = lu[lu["sur_terrain"]]
    agg_pitch = pitch.groupby(keys).agg(
        note_moy=("note_avec_bonus", "mean"),
        note_moy_brute=("note_brute", "mean"),
        note_mediane=("note_avec_bonus", "median"),
        note_ecart_type=("note_avec_bonus", "std"),
        bonus_total=("bonus_recu", "sum"),
        n_rotaldos=("statut", lambda s: int((s == "rotaldo").sum())),
        n_remplacants_entres=("statut", lambda s: int((s == "remplacant_entre").sum())),
    )
    picks = lu[lu["choix_coach"]]
    agg_picks = picks.groupby(keys).agg(
        cote_11_aligne=("cote", "sum"),
        absents_attendus=("p_absence", "sum"),
        n_absents=("statut", lambda s: int((s == "titulaire_absent").sum())),
        n_remplaces_tactique=("statut", lambda s: int((s == "titulaire_remplace_tactique").sum())),
    )
    bench = lu[lu["statut"] == "remplacant_non_entre"]
    agg_bench = bench.groupby(keys).agg(n_banc=("statut", "size"), cote_banc_aligne=("cote", "sum"))

    tm = tm.merge(agg_pitch, on=keys, how="left").merge(agg_picks, on=keys, how="left")
    tm = tm.merge(agg_bench, on=keys, how="left")

    gc = _goal_counts(league)
    tm = tm.merge(gc, on=keys, how="left")
    against = gc.rename(
        columns={"team_id": "opp_id", **{c: c.replace("bp_", "bc_") for c in gc.columns if c.startswith("bp_")}}
    )
    tm = tm.merge(against, on=["match_id", "opp_id"], how="left")
    goal_cols = [c for c in tm.columns if c.startswith(("bp_", "bc_"))]
    tm[goal_cols] = tm[goal_cols].fillna(0).astype(int)

    b = league.bonus
    played_bonus = b.dropna(subset=["effet_pts"])
    tm = tm.merge(
        played_bonus.groupby(keys).agg(
            bonus_poses=("bonus", lambda s: ", ".join(s)),
            n_bonus_hors_capitaine=("bonus", lambda s: int((s != "Capitaine").sum())),
        ),
        on=keys,
        how="left",
    )
    captain_on_pitch = lu[lu["sur_terrain"] & (lu["capitaine"] == 1)].set_index(keys).index
    tm["capitaine_manque"] = ~tm.set_index(keys).index.isin(captain_on_pitch)
    suarez = played_bonus[played_bonus["bonus"] == "Suarez"][keys].rename(columns={"team_id": "opp_id"})
    tm = tm.merge(
        suarez.groupby(["match_id", "opp_id"]).size().rename("suarez_subi").reset_index(),
        on=["match_id", "opp_id"],
        how="left",
    )
    tm["suarez_subi"] = tm["suarez_subi"].fillna(0).astype(int)
    tm["n_bonus_hors_capitaine"] = tm["n_bonus_hors_capitaine"].fillna(0).astype(int)
    tm["bonus_poses"] = tm["bonus_poses"].fillna("")

    opp_cols = tm[keys + ["note_moy", "note_moy_brute", "cote_11_aligne", "n_rotaldos"]].rename(
        columns={
            "team_id": "opp_id",
            "note_moy": "note_moy_adv",
            "note_moy_brute": "note_moy_brute_adv",
            "cote_11_aligne": "cote_11_aligne_adv",
            "n_rotaldos": "n_rotaldos_adv",
        }
    )
    tm = tm.merge(opp_cols, on=["match_id", "opp_id"], how="left")
    tm["ecart_note"] = tm["note_moy"] - tm["note_moy_adv"]
    tm["team_name"] = tm["team_id"].map(league.team_names)
    tm["opp_name"] = tm["opp_id"].map(league.team_names)
    return tm.sort_values(["gw", "team_id"]).reset_index(drop=True)


def line_ratings(lu: pd.DataFrame, note: str = "note_brute") -> pd.DataFrame:
    """Note moyenne par ligne (G, D, M, A) et globale des joueurs sur le terrain, Rotaldos inclus dans la globale.

    Renvoie une ligne par équipe : moyenne et effectif (n) par ligne, plus la médiane globale.
    """
    pitch = lu[lu["sur_terrain"]]
    by_line = pitch.dropna(subset=["poste_groupe"]).pivot_table(
        index="team_id", columns="poste_groupe", values=note, aggfunc=["mean", "size"]
    )
    out = pd.DataFrame(index=by_line.index)
    for g in ("G", "D", "M", "A"):
        out[g] = by_line[("mean", g)] if ("mean", g) in by_line else float("nan")
        out[f"n_{g}"] = by_line[("size", g)].fillna(0).astype(int) if ("size", g) in by_line else 0
    out["globale"] = pitch.groupby("team_id")[note].mean()
    out["globale_mediane"] = pitch.groupby("team_id")[note].median()
    return out.reset_index()
