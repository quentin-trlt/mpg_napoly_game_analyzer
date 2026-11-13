"""Backtest des modèles de prédiction sur toutes les saisons disponibles (data/history/ et la saison en cours).

Chaque journée de chaque saison est prédite avec ce qui était connu avant elle (`mpg.forecast.evaluation.backtest`).
Limites propres aux saisons passées : pas de cote MPG (indice de force calculé sur les enchères), pas d'instantané
FPL (probabilité de jouer = taux de jeu PL d'avant la journée), effectif de fin de saison (les joueurs partis de PL
en cours de saison manquent au 11 probable). En 2024-2025, les notes PL ne commencent qu'à la journée MPG 1.

Les combinaisons ajoutées sont des moyennes à poids égaux des probabilités des modèles, sans l'ajustement des bonus
restants ; « Poids égaux sans bonus » est l'ancien ensemble avant cet ajustement. « Ensemble » est l'ensemble de l'app
(structurel seul pour les journées 1 à 3, puis poids égaux, ajusté des bonus).

Usage : uv run python -m experiments.backtest_seasons
"""

import logging
import warnings

import numpy as np
import pandas as pd

from mpg.forecast.evaluation import PROB_COLS, backtest_seasons, paired_delta, scores, season_dirs

N_DRAWS = 1500
STRUCT, ELO, POISSON, ENS = "Structurel (joueurs)", "Elo", "Poisson bayésien", "Ensemble"
COMBOS = {
    "Poids égaux sans bonus": [STRUCT, ELO, POISSON],
    "Structurel + Elo": [STRUCT, ELO],
    "Structurel + Poisson": [STRUCT, POISSON],
}


def add_combos(bt: pd.DataFrame) -> pd.DataFrame:
    base = bt[bt["modele"] == STRUCT][["saison", "gw", "match_id", "issue"]].reset_index(drop=True)
    rows = [bt]
    for name, parts in COMBOS.items():
        p = np.mean([bt[bt["modele"] == m][PROB_COLS].to_numpy() for m in parts], axis=0)
        s = scores(p, base["issue"].to_numpy())
        rows.append(pd.concat([base, s], axis=1).assign(modele=name, p_dom=p[:, 0], p_nul=p[:, 1], p_ext=p[:, 2]))
    return pd.concat(rows, ignore_index=True)


def summary(bt: pd.DataFrame) -> pd.DataFrame:
    by_season = bt.pivot_table(index="modele", columns="saison", values="rps", aggfunc="mean")
    by_season = by_season[[c for c in bt["saison"].unique()]]
    pooled = bt.groupby("modele").agg(
        rps=("rps", "mean"), log_loss=("log_loss", "mean"), brier=("brier", "mean"), p_nul=("p_nul", "mean")
    )
    return by_season.add_prefix("RPS ").join(pooled).sort_values("rps")


def deltas(bt: pd.DataFrame, ref: str) -> pd.DataFrame:
    rows = []
    for m in bt["modele"].unique():
        if m == ref:
            continue
        row = {"modèle": m}
        for season, part in [("toutes", bt), *bt.groupby("saison", sort=False)]:
            d, lo, hi = paired_delta(part, m, ref)
            row[season] = f"{d:+.3f} [{lo:+.3f} ; {hi:+.3f}]"
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    warnings.simplefilter("ignore", RuntimeWarning)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    dirs = season_dirs()
    bt = add_combos(backtest_seasons(dirs, n_draws=N_DRAWS))
    counts = bt[bt["modele"] == STRUCT].groupby("saison", sort=False).size()
    draws = bt[bt["modele"] == STRUCT].assign(nul=lambda d: d["issue"] == 1).groupby("saison", sort=False)["nul"].mean()
    print("=== Matchs par saison ===")
    print(pd.DataFrame({"matchs": counts, "nuls observés": draws.round(3)}).to_string())

    print("\n=== Scores moyens (RPS par saison, puis toutes saisons) ===")
    print(summary(bt).round(4).to_string())

    for ref in (ENS, STRUCT):
        print(f"\n=== Δ RPS face à « {ref} » [IC 90 %, bootstrap apparié par saison] ===")
        print(deltas(bt, ref).to_string(index=False))

    early = bt.assign(phase=np.where(bt["gw"] <= 3, "J1-J3", "J4+"))
    print("\n=== RPS selon l'avancement de la saison ===")
    print(early.pivot_table(index="modele", columns="phase", values="rps", aggfunc="mean").round(4).to_string())


if __name__ == "__main__":
    main()
