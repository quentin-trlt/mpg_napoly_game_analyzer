import numpy as np
import pandas as pd

from mpg.loader import GROUPES
from mpg.stats import gini, hhi, robust_z, robust_z_by, theil_sen, trimmed_mean

MIN_NOTES_RENDEMENT = 1

DEFAULT_WEIGHTS = {
    "rendement": 0.30,
    "prix": 0.20,
    "fiabilite": 0.15,
    "profondeur": 0.15,
    "risque": 0.10,
    "equilibre": 0.10,
}
ALT_WEIGHTS = {
    "par défaut": DEFAULT_WEIGHTS,
    "poids égaux": dict.fromkeys(DEFAULT_WEIGHTS, 1 / 6),
    "rendement d'abord": {
        "rendement": 0.6,
        "prix": 0.15,
        "fiabilite": 0.1,
        "profondeur": 0.05,
        "risque": 0.05,
        "equilibre": 0.05,
    },
    "gestion du budget": {
        "rendement": 0.1,
        "prix": 0.3,
        "fiabilite": 0.15,
        "profondeur": 0.2,
        "risque": 0.15,
        "equilibre": 0.1,
    },
    "joueurs qui jouent": {
        "rendement": 0.2,
        "prix": 0.1,
        "fiabilite": 0.5,
        "profondeur": 0.1,
        "risque": 0.05,
        "equilibre": 0.05,
    },
}
COMPONENT_LABELS = {
    "rendement": "Rendement vs prix",
    "prix": "Prix payé vs cote",
    "fiabilite": "Temps de jeu des joueurs achetés",
    "profondeur": "Profondeur de banc",
    "risque": "Diversification du budget",
    "equilibre": "Équilibre par ligne",
}


def player_value(pstats: pd.DataFrame) -> pd.DataFrame:
    """Mesures de valeur par joueur : surpaiement, prix relatif au poste, rendement par rapport au prix."""
    p = pstats.copy()
    p["log_enchere"] = np.log(p["enchere"])
    p["surpaiement_log"] = np.log(p["enchere"] / p["cote"])
    p["surpaiement_x"] = p["enchere"] / p["cote"]
    p["z_prix_poste"] = robust_z_by(p, "log_enchere", "poste_groupe")
    p["note_attendue"] = np.nan
    for g, grp in p.groupby("poste_groupe"):
        fit = grp[grp["n_notes"] >= MIN_NOTES_RENDEMENT]
        slope, intercept = theil_sen(fit["log_enchere"], fit["note_retrecie"])
        p.loc[grp.index, "note_attendue"] = intercept + slope * grp["log_enchere"]
        p.loc[grp.index, "pente_prix_note"] = slope
    p["residu_valeur"] = np.where(p["n_notes"] >= MIN_NOTES_RENDEMENT, p["note_retrecie"] - p["note_attendue"], np.nan)
    p["cout_par_but"] = np.where(p["buts_total"] > 0, p["enchere"] / p["buts_total"].replace(0, np.nan), np.nan)
    p["cout_par_ga_saison"] = p["enchere"] / p["ga_saison"].where(p["ga_saison"] > 0)
    return p


def team_components(pv: pd.DataFrame) -> pd.DataFrame:
    rows = []
    league_share = (
        (pv.groupby(["team_id", "poste_groupe"])["enchere"].sum() / pv.groupby("team_id")["enchere"].sum())
        .unstack()
        .reindex(columns=GROUPES)
        .fillna(0)
    )
    ref_share = league_share.median()
    for team_id, r in pv.groupby("team_id"):
        e = r["enchere"].sort_values(ascending=False)
        total = e.sum()
        known = r["taux_jeu"].notna()
        xi_mask = r["choisi_titulaire"] > 0
        share = league_share.loc[team_id]
        rows.append(
            {
                "team_id": team_id,
                "nb_joueurs": len(r),
                "enchere_totale": total,
                "enchere_mediane": e.median(),
                "enchere_moyenne": e.mean(),
                "enchere_moy_tronquee": trimmed_mean(e),
                "enchere_ecart_type": e.std(ddof=1),
                "enchere_iqr": e.quantile(0.75) - e.quantile(0.25),
                "enchere_max": e.max(),
                "joueur_plus_cher": r.loc[r["enchere"].idxmax(), "joueur"],
                "part_top1": e.iloc[0] / total,
                "part_top3": e.head(3).sum() / total,
                "gini_enchere": gini(e),
                "hhi_enchere": hhi(e),
                "surpaiement_global_x": total / r["cote"].sum(min_count=1),
                "surpaiement_median_x": float(np.exp(r["surpaiement_log"].median())),
                "surpaiement_log_median": r["surpaiement_log"].median(),
                "residu_moy_tronque": trimmed_mean(r["residu_valeur"]),
                "residu_median": r["residu_valeur"].median(),
                "residu_titulaires": trimmed_mean(r.loc[xi_mask, "residu_valeur"]) if xi_mask.any() else np.nan,
                "joueurs_notes": int((r["n_notes"] > 0).sum()),
                "budget_titulaires": r.loc[xi_mask, "enchere"].sum() / total,
                "ecart_repartition": float((share - ref_share).abs().sum()),
                "flags_incertains": int(r["flag_point_interrogation"].sum()),
                "disponibilite_ponderee": (r.loc[known, "enchere"] * r.loc[known, "taux_jeu"]).sum()
                / r.loc[known, "enchere"].sum()
                if known.any()
                else np.nan,
                "part_budget_titulaires_pl": r.loc[r["taux_titu"] >= 0.5, "enchere"].sum() / total,
                "part_budget_indisponible": r.loc[r["indisponible"], "enchere"].sum() / total,
                "nb_indisponibles": int(r["indisponible"].sum()),
                "nb_incertains_pl": int((r["statut_performance"] == "incertain").sum()),
                "ga_saison": r["ga_saison"].sum(),
                "buts_saison": r["buts_reels_saison"].sum(),
                "passes_saison": r["passes_decisives_saison"].sum(),
                "cartons_jaunes": r["cartons_jaunes"].sum(),
                "cartons_rouges": r["cartons_rouges"].sum(),
                "cout_median_par_ga": r["cout_par_ga_saison"].median(),
                **{f"part_{g}": share[g] for g in GROUPES},
                **{f"nb_{g}": int((r["poste_groupe"] == g).sum()) for g in GROUPES},
            }
        )
    return pd.DataFrame(rows)


def score_mercato(teams: pd.DataFrame, depth: pd.Series, weights: dict[str, float]) -> pd.DataFrame:
    comp = pd.DataFrame(
        {
            "team_id": teams["team_id"],
            "rendement": robust_z(teams["residu_moy_tronque"]),
            "prix": -robust_z(teams["surpaiement_log_median"]),
            "fiabilite": robust_z(teams["disponibilite_ponderee"]),
            "profondeur": robust_z(teams["team_id"].map(depth)),
            "risque": -robust_z(teams["gini_enchere"]),
            "equilibre": -robust_z(teams["ecart_repartition"]),
        }
    )
    weights = {k: w for k, w in weights.items() if w > 0}
    if not weights:
        raise ValueError("au moins un poids strictement positif est requis")
    total = sum(weights.values())
    comp["score"] = sum(w / total * comp[c] for c, w in weights.items())
    comp["rang"] = comp["score"].rank(ascending=False, method="min").astype(int)
    return comp


def mercato_ranking(
    pv: pd.DataFrame, depth: pd.Series, weights: dict[str, float] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classement composite des mercatos et analyse de sensibilité.

    `depth` : cote du banc par team_id (cote totale − cote du meilleur 11).
    `weights` : pondération principale (par défaut DEFAULT_WEIGHTS), également utilisée pour le leave-one-out.
    Renvoie (tableau équipe avec composantes et score, tableau des rangs par scénario).
    """
    weights = weights or DEFAULT_WEIGHTS
    teams = team_components(pv)
    base = score_mercato(teams, depth, weights)
    alt = dict(ALT_WEIGHTS)
    if weights != DEFAULT_WEIGHTS:
        alt["personnalisé"] = weights
    scenarios = {name: score_mercato(teams, depth, w).set_index("team_id")["rang"] for name, w in alt.items()}

    loo_pv = pv.drop(pv.groupby("team_id")["enchere"].idxmax())
    scenarios["sans le plus gros achat"] = score_mercato(team_components(loo_pv), depth, weights).set_index("team_id")[
        "rang"
    ]

    ranks = pd.DataFrame(scenarios)
    out = teams.merge(base, on="team_id")
    out["rang_min"] = out["team_id"].map(ranks.min(axis=1))
    out["rang_max"] = out["team_id"].map(ranks.max(axis=1))
    return out.sort_values("rang").reset_index(drop=True), ranks.reset_index(names="team_id")


def club_exposure(players: pd.DataFrame) -> pd.DataFrame:
    return (
        players.groupby(["team_id", "club"])
        .agg(n=("player_key", "size"), enchere=("enchere", "sum"))
        .reset_index()
        .sort_values(["team_id", "n"], ascending=[True, False])
    )
