import pandas as pd

from mpg.loader import GROUPES, League
from mpg.stats import robust_z, spearman

FORMATIONS = ["3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"]

DEFAULT_WEIGHTS = {
    "cote_11_max": 0.45,
    "note_reelle_11": 0.30,
    "cote_banc": 0.15,
    "nb_joueurs": 0.10,
}

FEATURE_LABELS = {
    "valeur_effectif_meur": "Valeur de l'effectif (cotes + budget restant)",
    "total_cote": "Somme des cotes",
    "cote_11_max": "Cote du meilleur 11 possible",
    "cote_11_type": "Cote du 11 type MPG",
    "cote_banc": "Cote du banc (hors meilleur 11)",
    "note_reelle_11": "Note réelle PL du meilleur 11",
    "note_reelle_effectif_mediane": "Note réelle PL médiane de l'effectif",
    "nb_joueurs": "Nombre de joueurs",
    "taux_titu_11": "Taux de titularisation PL du meilleur 11",
    "disponibilite_effectif": "Taux de jeu PL moyen de l'effectif",
    "ga_saison": "Buts + passes décisives PL de l'effectif",
    "points_mpg_11": "Points MPG moyens du meilleur 11",
    "cote_G": "Cote des gardiens",
    "cote_D": "Cote des défenseurs",
    "cote_M": "Cote des milieux",
    "cote_A": "Cote des attaquants",
}

SCENARIOS = {
    "par défaut": DEFAULT_WEIGHTS,
    "valeur de l'effectif seule": {"valeur_effectif_meur": 1.0},
    "11 titulaire seul": {"cote_11_max": 1.0},
    "profondeur d'abord": {"cote_banc": 0.5, "nb_joueurs": 0.2, "cote_11_max": 0.3},
    "niveau réel PL": {"note_reelle_11": 0.7, "note_reelle_effectif_mediane": 0.3},
    "poids égaux": dict.fromkeys(["cote_11_max", "note_reelle_11", "cote_banc", "nb_joueurs"], 0.25),
    "joueurs qui jouent": {"taux_titu_11": 0.4, "disponibilite_effectif": 0.3, "cote_11_max": 0.3},
    "production offensive": {"ga_saison": 0.6, "cote_A": 0.2, "cote_M": 0.2},
}


def _parse_formation(f: str) -> dict[str, int]:
    d, m, a = (int(x) for x in f.split("-"))
    return {"G": 1, "D": d, "M": m, "A": a}


def best_xi(roster: pd.DataFrame, value: str, formations: list[str] = FORMATIONS) -> tuple[str, pd.DataFrame]:
    """Meilleur 11 possible selon `value`, en testant toutes les formations MPG autorisées."""
    best_f, best_xi_df, best_total = None, roster.iloc[0:0], float("-inf")
    ranked = {g: roster[roster["poste_groupe"] == g].sort_values(value, ascending=False) for g in GROUPES}
    for f in formations:
        slots = _parse_formation(f)
        if any(len(ranked[g]) < n for g, n in slots.items()):
            continue
        xi = pd.concat([ranked[g].head(n) for g, n in slots.items()])
        total = xi[value].sum()
        if total > best_total:
            best_f, best_xi_df, best_total = f, xi, total
    return best_f, best_xi_df


def squad_features(league: League) -> pd.DataFrame:
    players = league.players.copy()
    players["note_reelle_imp"] = players["note_moy_reelle"].fillna(
        players.groupby("poste_groupe")["note_moy_reelle"].transform("median")
    )
    xi_type = league.typical_xi.merge(players[["player_key", "cote"]], on="player_key", how="left")
    rows = []
    for team_id, roster in players.groupby("team_id"):
        formation, xi = best_xi(roster, "cote")
        _, xi_note = best_xi(roster, "note_reelle_imp")
        row = {
            "team_id": team_id,
            "nb_joueurs": len(roster),
            "total_cote": roster["cote"].sum(),
            "total_enchere": roster["enchere"].sum(),
            "cote_mediane": roster["cote"].median(),
            "cote_11_max": xi["cote"].sum(),
            "formation_11_max": formation,
            "cote_11_type": xi_type.loc[xi_type["team_id"] == team_id, "cote"].sum(),
            "note_reelle_11": xi_note["note_reelle_imp"].mean(),
            "note_reelle_effectif_mediane": roster["note_moy_reelle"].median(),
            "taux_titu_11": xi["taux_titu"].mean(),
            "disponibilite_effectif": roster["taux_jeu"].mean(),
            "ga_saison": roster["ga_saison"].sum(),
            "points_mpg_11": xi_note["points_mpg_moy"].mean(),
            "nb_indisponibles": int(roster["indisponible"].sum()),
        }
        row["cote_banc"] = row["total_cote"] - row["cote_11_max"]
        for g in GROUPES:
            row[f"cote_{g}"] = roster.loc[roster["poste_groupe"] == g, "cote"].sum()
            row[f"nb_{g}"] = int((roster["poste_groupe"] == g).sum())
        rows.append(row)
    feats = pd.DataFrame(rows)
    feats = feats.merge(league.teams[["team_id", "team_name", "valeur_effectif_meur", "budget_restant"]], on="team_id")
    return feats


def strength_index(feats: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Indice de force a priori = moyenne pondérée des z-scores robustes des caractéristiques d'effectif."""
    weights = {k: w for k, w in (weights or DEFAULT_WEIGHTS).items() if w > 0}
    if not weights:
        raise ValueError("au moins un poids strictement positif est requis")
    unknown = set(weights) - set(feats.columns)
    if unknown:
        raise ValueError(f"caractéristiques inconnues : {sorted(unknown)}")
    total_w = sum(weights.values())
    out = feats.copy()
    out["indice_force"] = 0.0
    for col, w in weights.items():
        out[f"z_{col}"] = robust_z(out[col])
        out["indice_force"] += w / total_w * out[f"z_{col}"]
    out["rang_attendu"] = out["indice_force"].rank(ascending=False, method="min").astype(int)
    return out


def strength_scenarios(
    feats: pd.DataFrame, pts: pd.Series, scenarios: dict[str, dict[str, float]] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rang attendu de chaque équipe sous plusieurs pondérations, et corrélation de Spearman de chaque scénario
    avec les points réels. `pts` est indexé par team_id.

    Avec 10 équipes, choisir le scénario le mieux corrélé revient à sur-ajuster : ces corrélations servent à
    juger de la sensibilité, pas à sélectionner une pondération.
    """
    scenarios = scenarios or SCENARIOS
    ranks, fit = {}, []
    for name, w in scenarios.items():
        idx = strength_index(feats, w).set_index("team_id")
        ranks[name] = idx["rang_attendu"]
        c = spearman(idx["indice_force"], pts.reindex(idx.index))
        fit.append({"scenario": name, "rho": c.rho, "p_value": c.p_value, "n": c.n})
    return pd.DataFrame(ranks).reset_index(names="team_id"), pd.DataFrame(fit)


def favourites_vs_reality(
    league: League, tm: pd.DataFrame, standings: pd.DataFrame, weights: dict[str, float] | None = None
) -> pd.DataFrame:
    idx = strength_index(squad_features(league), weights)
    aligned = (
        tm.groupby("team_id")
        .agg(
            cote_11_aligne_moy=("cote_11_aligne", "mean"),
            cote_11_aligne_min=("cote_11_aligne", "min"),
            cote_11_aligne_max=("cote_11_aligne", "max"),
        )
        .reset_index()
    )
    out = idx.merge(aligned, on="team_id", how="left")
    out = out.merge(standings[["team_id", "rang", "pts", "diff"]], on="team_id", how="left")
    out["ecart_rang"] = out["rang_attendu"] - out["rang"]
    out["taux_utilisation_11"] = out["cote_11_aligne_moy"] / out["cote_11_max"]
    ranks, _ = strength_scenarios(idx, out.set_index("team_id")["pts"])
    ranks = ranks.set_index("team_id")
    out["rang_attendu_min"] = out["team_id"].map(ranks.min(axis=1))
    out["rang_attendu_max"] = out["team_id"].map(ranks.max(axis=1))
    return out.sort_values("rang_attendu").reset_index(drop=True)


def strength_correlations(fav: pd.DataFrame) -> dict[str, object]:
    cols = [
        "indice_force",
        "valeur_effectif_meur",
        "cote_11_max",
        "cote_11_aligne_moy",
        "note_reelle_11",
        "cote_banc",
        "taux_titu_11",
        "disponibilite_effectif",
        "ga_saison",
    ]
    return {c: spearman(fav[c], fav["pts"]) for c in cols}


def remaining_schedule(league: League, fav: pd.DataFrame) -> pd.DataFrame:
    """Force moyenne (indice a priori) des adversaires restants, par équipe."""
    todo = league.fixtures[league.fixtures["statut"] != "joue"]
    pairs = pd.concat(
        [
            todo[["gw", "home_team_id", "away_team_id"]].set_axis(["gw", "team_id", "opp_id"], axis=1),
            todo[["gw", "away_team_id", "home_team_id"]].set_axis(["gw", "team_id", "opp_id"], axis=1),
        ]
    )
    force = fav.set_index("team_id")["indice_force"]
    pairs["force_adv"] = pairs["opp_id"].map(force)
    return (
        pairs.groupby("team_id")
        .agg(matchs_restants=("gw", "size"), force_adv_restante=("force_adv", "mean"))
        .reset_index()
        .sort_values("force_adv_restante", ascending=False)
    )
