import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from mpg.analysis import Analysis, run
from mpg.forecast.season import EnsembleDraws, SeasonSimulation, build_context, ensemble_draws, fixtures_after
from mpg.loader import DEFAULT_DATA_DIR

FROZEN_DIR = Path(os.environ.get("MPG_PRONOSTICS_DIR", Path(__file__).resolve().parents[2] / "content" / "pronostics"))
PROB_COLS = ["p_dom", "p_nul", "p_ext"]


def scores(p: np.ndarray, outcome: np.ndarray) -> pd.DataFrame:
    """Log-loss, Brier (somme sur les 3 issues) et RPS par match. p : (n, 3) dans l'ordre domicile, nul, extérieur."""
    p = np.clip(np.asarray(p, float), 1e-12, 1.0)
    o = np.eye(3)[np.asarray(outcome, int)]
    cum_p, cum_o = np.cumsum(p, axis=1)[:, :2], np.cumsum(o, axis=1)[:, :2]
    return pd.DataFrame(
        {
            "log_loss": -np.log(p[np.arange(len(p)), outcome]),
            "brier": ((p - o) ** 2).sum(axis=1),
            "rps": ((cum_p - cum_o) ** 2).sum(axis=1) / 2,
        }
    )


def _played_outcomes(fixtures: pd.DataFrame) -> np.ndarray:
    h, a = fixtures["home_goals"].to_numpy(), fixtures["away_goals"].to_numpy()
    return np.where(h > a, 0, np.where(h == a, 1, 2))


def backtest(a: Analysis, n_draws: int = 1500, seed: int = 0) -> pd.DataFrame:
    """Rejoue chaque journée jouée : modèles ajustés sur les journées précédentes, prédiction de la journée.

    Comme en prédiction réelle, les tirages portent sur tous les matchs restants : les bonus restants de chaque équipe
    sont répartis sur toute la fin de saison, pas concentrés sur la journée prédite.

    Avec player_match_notes.csv, chaque journée ne voit que les données joueurs connues avant elle
    (`build_context`). Sans ce fichier, les données joueurs sont celles du jour et les scores sont optimistes.
    """
    rows = []
    played = a.league.played
    keys = ["gw", "home_team_id", "away_team_id"]
    for g in sorted(played["gw"].unique()):
        ctx = build_context(a, int(g) - 1)
        remaining = fixtures_after(a, int(g) - 1)
        draws = ensemble_draws(ctx, remaining, n_draws=n_draws, seed=seed)
        sel = (remaining["gw"] == g).to_numpy()
        fx = remaining[sel][keys].merge(played[[*keys, "match_id", "home_goals", "away_goals"]], on=keys)
        outcome = _played_outcomes(fx)
        models = {name: d[:, sel].mean(axis=0) for name, d in draws.by_model.items()}
        models["Ensemble"] = draws.ensemble[:, sel].mean(axis=0)
        for name, p in models.items():
            s = scores(p, outcome)
            rows.append(
                s.assign(
                    modele=name,
                    gw=int(g),
                    match_id=fx["match_id"].to_numpy(),
                    issue=outcome,
                    p_dom=p[:, 0],
                    p_nul=p[:, 1],
                    p_ext=p[:, 2],
                )
            )
    return pd.concat(rows, ignore_index=True)


def season_dirs(current: Path = DEFAULT_DATA_DIR) -> dict[str, Path]:
    """Saisons passées (`history/<saison>_<ligue>/` avec un meta.json), de la plus ancienne à la plus récente, puis la
    saison en cours (`current`)."""
    history = sorted(d for d in (current / "history").glob("*") if (d / "meta.json").exists())
    return {**{d.name: d for d in history}, "en cours": current}


def backtest_seasons(dirs: dict[str, Path], n_draws: int = 1500, seed: int = 0) -> pd.DataFrame:
    """`backtest` de chaque saison, concaténé avec une colonne `saison`."""
    return pd.concat(
        [
            backtest(run(d, n_sim=50, seed=seed), n_draws=n_draws, seed=seed).assign(saison=name)
            for name, d in dirs.items()
        ],
        ignore_index=True,
    )


def paired_delta(
    bt: pd.DataFrame, model: str, ref: str, metric: str = "rps", n_boot: int = 10_000, level: float = 0.9, seed: int = 0
) -> tuple[float, float, float]:
    """Écart moyen de `metric` entre deux modèles sur les mêmes matchs, et son intervalle par bootstrap apparié.

    Les matchs sont rééchantillonnés à l'intérieur de chaque saison (colonne `saison` si présente) pour garder le
    poids de chaque saison.
    """
    cols = ["match_id", metric] + (["saison"] if "saison" in bt else [])
    m = bt.loc[bt["modele"] == model, cols].merge(
        bt.loc[bt["modele"] == ref, ["match_id", metric]], on="match_id", suffixes=("", "_ref")
    )
    m["d"] = m[metric] - m[f"{metric}_ref"]
    groups = [g["d"].to_numpy() for _, g in m.groupby("saison")] if "saison" in m else [m["d"].to_numpy()]
    rng = np.random.default_rng(seed)
    total = sum(len(g) for g in groups)
    boot = sum(rng.choice(g, (n_boot, len(g))).sum(axis=1) for g in groups) / total
    alpha = (1 - level) / 2
    return float(m["d"].mean()), float(np.quantile(boot, alpha)), float(np.quantile(boot, 1 - alpha))


def backtest_summary(bt: pd.DataFrame) -> pd.DataFrame:
    out = (
        bt.groupby("modele")
        .agg(matchs=("log_loss", "size"), log_loss=("log_loss", "mean"), brier=("brier", "mean"), rps=("rps", "mean"))
        .reset_index()
    )
    out["proba_issue_reelle"] = (
        bt.assign(p=np.choose(bt["issue"], bt[PROB_COLS].T.to_numpy()))
        .groupby("modele")["p"]
        .mean()
        .reindex(out["modele"])
        .to_numpy()
    )
    return out.sort_values("rps").reset_index(drop=True)


def frozen_path(gw: int) -> Path:
    return FROZEN_DIR / f"J{gw:02d}.csv"


def season_path(gw: int) -> Path:
    return FROZEN_DIR / f"saison_J{gw:02d}.csv"


def frozen_frames(a: Analysis, sim: SeasonSimulation, draws: EnsembleDraws) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pronostics de la prochaine journée (une ligne par match et par modèle) et instantané de fin de saison."""
    gw = int(draws.fixtures["gw"].min())
    meta = {"fige_apres_journee": a.league.last_gw, "fige_le": date.today().isoformat()}
    probs = draws.mean_probs()
    probs = probs[probs["gw"] == gw].merge(
        sim.match_probs[["gw", "home_team_id", "away_team_id", "score_probable"]],
        on=["gw", "home_team_id", "away_team_id"],
    )
    cols = ["gw", "home_team_id", "away_team_id", "home_team", "away_team", "modele", *PROB_COLS, "score_probable"]
    matches = probs[cols].assign(**meta)
    ranks = sim.rank_probs.add_prefix("p_rang_").reset_index(names="team_id")
    season = (
        sim.summary.merge(ranks, on="team_id")
        .assign(team_name=lambda d: d["team_id"].map(a.league.team_names))
        .assign(avant_journee=gw, **meta)
    )
    return matches, season


def freeze_next(a: Analysis, sim: SeasonSimulation, draws: EnsembleDraws) -> list[Path]:
    """Fige les pronostics de la prochaine journée (tous les modèles) et l'instantané de fin de saison.

    Chaque fichier n'est écrit que s'il n'existe pas encore : un pronostic figé n'est jamais modifié.
    """
    if draws.fixtures.empty:
        return []
    gw = int(draws.fixtures["gw"].min())
    matches, season = frozen_frames(a, sim, draws)
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for frame, path in ((matches, frozen_path(gw)), (season, season_path(gw))):
        if not path.exists():
            frame.to_csv(path, index=False)
            written.append(path)
    return written


def frozen_matches(a: Analysis) -> pd.DataFrame:
    """Tous les pronostics de match figés (une ligne par match et par modèle), avec le résultat s'il est connu."""
    files = sorted(FROZEN_DIR.glob("J*.csv")) if FROZEN_DIR.exists() else []
    if not files:
        return pd.DataFrame()
    frozen = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if "modele" not in frozen:
        frozen["modele"] = "Ensemble"
    frozen["modele"] = frozen["modele"].fillna("Ensemble")
    played = a.league.played[["gw", "home_team_id", "away_team_id", "home_goals", "away_goals"]]
    out = frozen.merge(played, on=["gw", "home_team_id", "away_team_id"], how="left")
    out["joue"] = out["home_goals"].notna()
    out["issue"] = np.nan
    for col in ("log_loss", "brier", "rps", "p_issue_reelle"):
        out[col] = np.nan
    done = out["joue"]
    if done.any():
        outcome = _played_outcomes(out[done])
        sc = scores(out.loc[done, PROB_COLS].to_numpy(), outcome)
        out.loc[done, "issue"] = outcome
        out.loc[done, ["log_loss", "brier", "rps"]] = sc.to_numpy()
        out.loc[done, "p_issue_reelle"] = out.loc[done, PROB_COLS].to_numpy()[np.arange(done.sum()), outcome]
    favourite = out[PROB_COLS].to_numpy().argmax(axis=1)
    out["favori"] = favourite
    out["favori_gagne"] = np.where(done, favourite == out["issue"], np.nan)
    return out


def scored_summary(fm: pd.DataFrame) -> pd.DataFrame:
    """Scores moyens des pronostics figés et joués, par modèle."""
    d = fm[fm["joue"]]
    if d.empty:
        return pd.DataFrame()
    return (
        d.groupby("modele")
        .agg(
            matchs=("rps", "size"),
            rps=("rps", "mean"),
            log_loss=("log_loss", "mean"),
            brier=("brier", "mean"),
            proba_issue_reelle=("p_issue_reelle", "mean"),
            favoris_gagnants=("favori_gagne", "mean"),
        )
        .reset_index()
        .sort_values("rps")
        .reset_index(drop=True)
    )


def rps_by_gameweek(fm: pd.DataFrame) -> pd.DataFrame:
    """RPS moyen par journée et RPS cumulé (moyenne sur toutes les journées jouées jusque-là), par modèle."""
    d = fm[fm["joue"]]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby(["modele", "gw"]).agg(rps=("rps", "mean"), matchs=("rps", "size")).reset_index()
    g["rps_cumule"] = g.groupby("modele", group_keys=False).apply(
        lambda x: (x["rps"] * x["matchs"]).cumsum() / x["matchs"].cumsum(), include_groups=False
    )
    return g


def calibration(fm: pd.DataFrame, model: str = "Ensemble", bins: int = 5) -> pd.DataFrame:
    """Probabilité annoncée contre fréquence observée, toutes issues confondues (3 lignes par match)."""
    d = fm[fm["joue"] & (fm["modele"] == model)]
    if d.empty:
        return pd.DataFrame()
    p = d[PROB_COLS].to_numpy().ravel()
    hit = (np.eye(3)[d["issue"].astype(int).to_numpy()]).ravel()
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    rows = [
        {
            "classe": f"{edges[b]:.0%}–{edges[b + 1]:.0%}",
            "p_annoncee": p[idx == b].mean(),
            "frequence_observee": hit[idx == b].mean(),
            "n": int((idx == b).sum()),
        }
        for b in range(bins)
        if (idx == b).any()
    ]
    return pd.DataFrame(rows)


def frozen_seasons() -> pd.DataFrame:
    """Instantanés de fin de saison figés, du plus ancien au plus récent."""
    files = sorted(FROZEN_DIR.glob("saison_J*.csv")) if FROZEN_DIR.exists() else []
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True).sort_values(["avant_journee", "team_id"])


def season_moves(snapshots: pd.DataFrame, tm: pd.DataFrame) -> pd.DataFrame:
    """Écart entre les deux derniers instantanés, avec les résultats joués entre les deux."""
    gws = sorted(snapshots["avant_journee"].unique())
    if len(gws) < 2:
        return pd.DataFrame()
    prev, last = snapshots[snapshots["avant_journee"] == gws[-2]], snapshots[snapshots["avant_journee"] == gws[-1]]
    cols = ["pts_moy", "rang_moy", "p_titre", "p_podium", "p_dernier"]
    m = last[["team_id", "team_name", *cols]].merge(prev[["team_id", *cols]], on="team_id", suffixes=("", "_avant"))
    for c in cols:
        m[f"delta_{c}"] = m[c] - m[f"{c}_avant"]
    played = tm[(tm["gw"] >= gws[-2]) & (tm["gw"] < gws[-1])]
    res = (
        played.sort_values("gw")
        .groupby("team_id")
        .apply(
            lambda d: ", ".join(f"{r.resultat} {r.bp}-{r.bc} vs {r.opp_name}" for r in d.itertuples()),
            include_groups=False,
        )
    )
    m["resultats"] = m["team_id"].map(res).fillna("")
    return m.sort_values("delta_p_titre", ascending=False).reset_index(drop=True)
