import pandas as pd

from mpg.stats import estimate_shrinkage_k, shrink

MIN_NOTES_CLASSEMENT = 2


def player_appearances(lu: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par joueur et par match où il a été noté en vrai (titulaire, entré ou resté sur le banc MPG)."""
    return lu[lu["a_joue_irl"] & lu["player_key"].notna()][
        ["match_id", "gw", "team_id", "player_key", "statut", "sur_terrain", "note_brute", "note_avec_bonus"]
    ]


def player_stats(league, lu: pd.DataFrame) -> pd.DataFrame:
    players = league.players.copy()
    app = player_appearances(lu)

    notes = app.groupby("player_key")["note_brute"].agg(
        n_notes="size", note_moy="mean", note_ecart_type="std", note_min="min", note_max="max"
    )
    usage = (
        lu[lu["player_key"].notna()]
        .groupby("player_key")
        .agg(
            feuilles_de_match=("statut", "size"),
            choisi_titulaire=("choix_coach", "sum"),
            sur_terrain=("sur_terrain", "sum"),
            absent_titulaire=("statut", lambda s: int((s == "titulaire_absent").sum())),
            capitanats=("capitaine", "sum"),
        )
    )
    g = league.goals[league.goals["type_but"].isin(["reel", "mpg"]) & league.goals["player_key"].notna()]
    goals = (
        g.groupby(["player_key", "type_but"])
        .size()
        .unstack(fill_value=0)
        .rename(columns={"reel": "buts_reels", "mpg": "buts_mpg"})
    )
    best = league.best_players.groupby("joueur").agg(
        top3_match=("rang", "size"), mvp_match=("rang", lambda s: int((s == 1).sum()))
    )

    out = players.merge(notes, left_on="player_key", right_index=True, how="left")
    out = out.merge(usage, left_on="player_key", right_index=True, how="left")
    out = out.merge(goals, left_on="player_key", right_index=True, how="left")
    out = out.merge(best, left_on="joueur", right_index=True, how="left")
    count_cols = [
        "n_notes",
        "feuilles_de_match",
        "choisi_titulaire",
        "sur_terrain",
        "absent_titulaire",
        "capitanats",
        "buts_reels",
        "buts_mpg",
        "top3_match",
        "mvp_match",
    ]
    for c in count_cols:
        if c not in out:
            out[c] = 0
    out[count_cols] = out[count_cols].fillna(0).astype(int)
    out["buts_total"] = out["buts_reels"] + out["buts_mpg"]

    poste_prior = out.groupby("poste_groupe")["note_moy_reelle"].transform("median")
    out["note_prior"] = out["note_moy_reelle"].fillna(poste_prior)
    k = estimate_shrinkage_k(app["note_brute"], app["player_key"])
    out["note_retrecie"] = shrink(out["note_moy"], out["n_notes"], out["note_prior"], k)
    out["team_name"] = out["team_id"].map(league.team_names)
    out.attrs["k_shrinkage"] = k
    return out


def top_players(
    stats: pd.DataFrame,
    by: str = "note_retrecie",
    poste: str | None = None,
    n: int = 10,
    ascending: bool = False,
    min_notes: int = MIN_NOTES_CLASSEMENT,
) -> pd.DataFrame:
    df = stats[stats["n_notes"] >= min_notes]
    if poste:
        df = df[df["poste_groupe"] == poste]
    return df.sort_values(by, ascending=ascending).head(n)
