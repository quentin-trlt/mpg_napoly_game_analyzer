import numpy as np
import pandas as pd
from scipy import stats as sps

from mpg.stats import bootstrap_ci, robust_z


def rule_points(diff: np.ndarray | pd.Series, band: float) -> np.ndarray:
    """Résultat « à la note » : victoire si l'écart de note moyenne dépasse `band`, nul sinon."""
    d = np.asarray(diff, dtype=float)
    return np.where(d > band, 3, np.where(d < -band, 0, 1))


def _gw_matrix(tm: pd.DataFrame, metric: str) -> pd.DataFrame:
    return tm.pivot_table(index="gw", columns="team_id", values=metric, aggfunc="first").sort_index()


def calibrate_draw_band(tm: pd.DataFrame, metric: str = "note_moy") -> float:
    """Choisit la bande de nul pour que le taux de nuls « all-play » égale le taux de nuls observé."""
    observed = (tm["resultat"] == "N").mean()
    mat = _gw_matrix(tm, metric).to_numpy()
    diffs = np.concatenate([(row[:, None] - row[None, :])[np.triu_indices(row.size, 1)] for row in mat])
    diffs = np.abs(diffs[~np.isnan(diffs)])
    if diffs.size == 0:
        return 0.0
    return float(np.quantile(diffs, observed))


def all_play(tm: pd.DataFrame, band: float, metric: str = "note_moy") -> pd.DataFrame:
    """Points attendus par journée si chaque équipe avait affronté les 9 autres (moyenne)."""
    mat = _gw_matrix(tm, metric)
    rows = []
    for gw, row in mat.iterrows():
        vals = row.to_numpy()
        for i, team_id in enumerate(mat.columns):
            if np.isnan(vals[i]):
                continue
            others = np.delete(vals, i)
            others = others[~np.isnan(others)]
            pts = rule_points(vals[i] - others, band)
            rows.append(
                {
                    "gw": gw,
                    "team_id": team_id,
                    "xpts_allplay": pts.mean(),
                    "v_allplay": int((pts == 3).sum()),
                    "n_allplay": int((pts == 1).sum()),
                    "d_allplay": int((pts == 0).sum()),
                }
            )
    ap = pd.DataFrame(rows)
    tmp = tm[["gw", "team_id", "pts", "ecart_note"]].assign(pts_regle=rule_points(tm["ecart_note"], band))
    return tmp.merge(ap, on=["gw", "team_id"], how="left")


def schedule_permutation(
    tm: pd.DataFrame, band: float, n_sim: int = 10_000, seed: int = 0, metric: str = "note_moy"
) -> tuple[pd.DataFrame, np.ndarray]:
    """Rejoue la saison sur `n_sim` calendriers aléatoires (appariements uniformes à chaque journée).

    Renvoie un résumé par équipe et la matrice (n_sim × équipes) des points simulés.
    """
    mat = _gw_matrix(tm, metric)
    teams = mat.columns.to_numpy()
    n = teams.size
    if n % 2:
        raise ValueError("nombre d'équipes impair : appariement impossible")
    rng = np.random.default_rng(seed)
    totals = np.zeros((n_sim, n))
    idx = np.arange(n_sim)[:, None]
    for _, row in mat.iterrows():
        notes = row.to_numpy()
        perm = np.argsort(rng.random((n_sim, n)), axis=1)
        partner = np.empty_like(perm)
        partner[idx, perm[:, 0::2]] = perm[:, 1::2]
        partner[idx, perm[:, 1::2]] = perm[:, 0::2]
        diff = notes[None, :] - notes[partner]
        totals += rule_points(diff, band)

    ap = all_play(tm, band, metric)
    real_rule = ap.groupby("team_id")["pts_regle"].sum().reindex(teams).to_numpy()
    real_pts = ap.groupby("team_id")["pts"].sum().reindex(teams).to_numpy()
    summary = pd.DataFrame(
        {
            "team_id": teams,
            "pts_sim_moy": totals.mean(axis=0),
            "pts_sim_p05": np.quantile(totals, 0.05, axis=0),
            "pts_sim_p95": np.quantile(totals, 0.95, axis=0),
            "percentile_calendrier": ((totals < real_rule).mean(axis=0) + 0.5 * (totals == real_rule).mean(axis=0))
            * 100,
            "percentile_pts_reels": ((totals < real_pts).mean(axis=0) + 0.5 * (totals == real_pts).mean(axis=0)) * 100,
        }
    )
    return summary, totals


def pythagorean_poisson(tm: pd.DataFrame, prior_matches: float = 1.0) -> pd.DataFrame:
    """Points attendus d'après les buts marqués/encaissés (Poisson indépendants, différence de Skellam).

    Les taux sont rétrécis vers la moyenne de la ligue avec `prior_matches` matchs fictifs
    (modèle Poisson-Gamma), ce qui évite un taux nul après quelques matchs sans marquer.
    """
    league_rate = tm["bp"].mean()
    g = tm.groupby("team_id").agg(j=("match_id", "size"), bp=("bp", "sum"), bc=("bc", "sum"), pts=("pts", "sum"))
    lam_for = (g["bp"] + prior_matches * league_rate) / (g["j"] + prior_matches)
    lam_against = (g["bc"] + prior_matches * league_rate) / (g["j"] + prior_matches)
    p_win = sps.skellam.sf(0, lam_for, lam_against)
    p_draw = sps.skellam.pmf(0, lam_for, lam_against)
    g["lambda_pour"] = lam_for
    g["lambda_contre"] = lam_against
    g["xpts_pythagore"] = g["j"] * (3 * p_win + p_draw)
    g["chance_pythagore"] = g["pts"] - g["xpts_pythagore"]
    return g.reset_index()


def opponent_overperformance(tm: pd.DataFrame) -> pd.DataFrame:
    """Note de l'adversaire face à l'équipe moins sa note moyenne sur ses autres matchs (leave-one-out)."""
    totals = tm.groupby("team_id")["note_moy"].agg(["sum", "count"])
    t = tm[["match_id", "team_id", "opp_id", "note_moy_adv"]].copy()
    s = t["opp_id"].map(totals["sum"])
    c = t["opp_id"].map(totals["count"])
    t["note_adv_habituelle"] = (s - t["note_moy_adv"]) / (c - 1).replace(0, np.nan)
    t["sur_regime_adv"] = t["note_moy_adv"] - t["note_adv_habituelle"]
    return (
        t.groupby("team_id")
        .agg(
            note_adv_moy=("note_moy_adv", "mean"),
            sur_regime_adv_moy=("sur_regime_adv", "mean"),
        )
        .reset_index()
    )


def luck_components(tm: pd.DataFrame) -> pd.DataFrame:
    tm = tm.assign(
        v_1but=(tm["bp"] - tm["bc"] == 1).astype(int),
        d_1but=(tm["bc"] - tm["bp"] == 1).astype(int),
    )
    return (
        tm.groupby("team_id")
        .agg(
            buts_mpg_pour=("bp_mpg", "sum"),
            buts_mpg_contre=("bc_mpg", "sum"),
            csc_pour=("bp_csc", "sum"),
            csc_rotaldo_pour=("bp_rotaldo_csc", "sum"),
            rotaldos_adverses=("n_rotaldos_adv", "sum"),
            suarez_subis=("suarez_subi", "sum"),
            victoires_1but=("v_1but", "sum"),
            defaites_1but=("d_1but", "sum"),
        )
        .reset_index()
    )


def luck_table(
    tm: pd.DataFrame, strength: pd.DataFrame | None = None, n_sim: int = 10_000, seed: int = 0
) -> pd.DataFrame:
    band = calibrate_draw_band(tm)
    ap = all_play(tm, band)
    per_team = (
        ap.groupby("team_id")
        .agg(
            pts=("pts", "sum"),
            xpts_allplay=("xpts_allplay", "sum"),
            pts_regle=("pts_regle", "sum"),
            v_allplay=("v_allplay", "sum"),
            n_allplay=("n_allplay", "sum"),
            d_allplay=("d_allplay", "sum"),
        )
        .reset_index()
    )
    per_team["chance_totale"] = per_team["pts"] - per_team["xpts_allplay"]
    per_team["chance_conversion"] = per_team["pts"] - per_team["pts_regle"]
    per_team["chance_calendrier"] = per_team["pts_regle"] - per_team["xpts_allplay"]

    ap["ecart_gw"] = ap["pts"] - ap["xpts_allplay"]
    ci = ap.groupby("team_id")["ecart_gw"].apply(lambda s: bootstrap_ci(s.to_numpy(), np.sum, seed=seed))
    per_team["chance_ic90_bas"] = per_team["team_id"].map(ci.str[0])
    per_team["chance_ic90_haut"] = per_team["team_id"].map(ci.str[1])

    perm, _ = schedule_permutation(tm, band, n_sim=n_sim, seed=seed)
    out = per_team.merge(perm, on="team_id")
    out = out.merge(pythagorean_poisson(tm)[["team_id", "xpts_pythagore", "chance_pythagore"]], on="team_id")
    out = out.merge(opponent_overperformance(tm), on="team_id")
    out = out.merge(luck_components(tm), on="team_id")
    if strength is not None:
        opp_strength = tm[["team_id", "opp_id"]].merge(
            strength[["team_id", "indice_force"]].rename(columns={"team_id": "opp_id"}), on="opp_id"
        )
        out = out.merge(
            opp_strength.groupby("team_id")["indice_force"].mean().rename("force_adv_moy").reset_index(), on="team_id"
        )

    out["indice_chance"] = (
        robust_z(out["chance_totale"]) + robust_z(out["chance_pythagore"]) - robust_z(out["sur_regime_adv_moy"])
    ) / 3
    out.attrs["bande_nul"] = band
    out.attrs["concordance"] = float((ap["pts_regle"] == ap["pts"]).mean())
    return out.sort_values("indice_chance", ascending=False).reset_index(drop=True)
