from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

MAD_TO_SIGMA = 1.4826


def mad(x: pd.Series | np.ndarray) -> float:
    arr = np.asarray(x, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return float("nan")
    return float(np.median(np.abs(arr - np.median(arr))))


def robust_z(x: pd.Series) -> pd.Series:
    """(x - médiane) / (1.4826 * MAD), avec repli sur l'écart-type si la MAD est nulle."""
    x = x.astype(float)
    scale = MAD_TO_SIGMA * mad(x)
    if not np.isfinite(scale) or scale == 0:
        scale = x.std(ddof=0)
    if not np.isfinite(scale) or scale == 0:
        return pd.Series(0.0, index=x.index)
    return (x - x.median()) / scale


def robust_z_by(df: pd.DataFrame, col: str, by: str) -> pd.Series:
    return df.groupby(by, group_keys=False)[col].apply(robust_z).reindex(df.index)


def trimmed_mean(x: pd.Series | np.ndarray, proportion: float = 0.1) -> float:
    arr = np.asarray(x, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return float("nan")
    return float(sps.trim_mean(arr, proportion))


def describe_robust(x: pd.Series) -> dict[str, float]:
    x = x.dropna().astype(float)
    if x.empty:
        return {
            k: float("nan")
            for k in ("n", "moyenne", "mediane", "moy_tronquee", "ecart_type", "iqr", "mad", "min", "max")
        }
    return {
        "n": float(x.size),
        "moyenne": float(x.mean()),
        "mediane": float(x.median()),
        "moy_tronquee": trimmed_mean(x),
        "ecart_type": float(x.std(ddof=1)) if x.size > 1 else 0.0,
        "iqr": float(x.quantile(0.75) - x.quantile(0.25)),
        "mad": mad(x),
        "min": float(x.min()),
        "max": float(x.max()),
    }


def gini(x: pd.Series | np.ndarray) -> float:
    arr = np.sort(np.asarray(x, dtype=float))
    arr = arr[~np.isnan(arr)]
    if arr.size == 0 or arr.sum() == 0:
        return 0.0
    if (arr < 0).any():
        raise ValueError("gini requires non-negative values")
    n = arr.size
    ranks = np.arange(1, n + 1)
    return float((2 * (ranks * arr).sum()) / (n * arr.sum()) - (n + 1) / n)


def hhi(x: pd.Series | np.ndarray) -> float:
    arr = np.asarray(x, dtype=float)
    total = np.nansum(arr)
    if total == 0:
        return 0.0
    shares = arr / total
    return float(np.nansum(shares**2))


def estimate_shrinkage_k(values: pd.Series, groups: pd.Series, min_obs: int = 2) -> float:
    """k = variance intra-joueur / variance inter-joueurs (méthode des moments, modèle à effets aléatoires).

    k s'interprète comme le nombre de matchs « fictifs » à la moyenne a priori ajoutés à chaque joueur.
    """
    df = pd.DataFrame({"v": values.astype(float), "g": groups}).dropna()
    counts = df.groupby("g")["v"].transform("size")
    df = df[counts >= min_obs]
    if df["g"].nunique() < 3:
        return 3.0
    within = df.groupby("g")["v"].var(ddof=1).mean()
    means = df.groupby("g")["v"].mean()
    n_bar = df.groupby("g").size().mean()
    between = means.var(ddof=1) - within / n_bar
    if not np.isfinite(between) or between <= 0:
        return 10.0
    return float(np.clip(within / between, 1.0, 10.0))


def shrink(mean: pd.Series, n: pd.Series, prior: pd.Series, k: float) -> pd.Series:
    """(n·x̄ + k·prior) / (n + k) ; vaut prior quand n = 0."""
    m = mean.fillna(0.0)
    return (n * m + k * prior) / (n + k)


def bootstrap_ci(
    values: np.ndarray | pd.Series,
    statistic: Callable[[np.ndarray], float] = np.sum,
    n_boot: int = 5000,
    level: float = 0.9,
    seed: int = 0,
) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    samples = rng.choice(arr, size=(n_boot, arr.size), replace=True)
    boot = np.apply_along_axis(statistic, 1, samples)
    alpha = (1 - level) / 2
    return float(np.quantile(boot, alpha)), float(np.quantile(boot, 1 - alpha))


@dataclass(frozen=True)
class Correlation:
    rho: float
    p_value: float
    n: int

    def __str__(self) -> str:
        return f"ρ = {self.rho:+.2f} (p = {self.p_value:.3f}, n = {self.n})"


def spearman(x: pd.Series, y: pd.Series) -> Correlation:
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 3 or df["x"].nunique() < 2 or df["y"].nunique() < 2:
        return Correlation(float("nan"), float("nan"), len(df))
    res = sps.spearmanr(df["x"], df["y"])
    return Correlation(float(res.statistic), float(res.pvalue), len(df))


def theil_sen(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """Pente et ordonnée de Theil–Sen (médiane des pentes deux à deux), robuste à ~29 % d'outliers."""
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 3 or df["x"].nunique() < 2:
        return 0.0, float(df["y"].median()) if len(df) else float("nan")
    res = sps.theilslopes(df["y"], df["x"])
    return float(res.slope), float(res.intercept)
