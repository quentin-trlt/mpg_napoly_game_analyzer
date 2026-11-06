import numpy as np
import pandas as pd

from mpg.stats import bootstrap_ci, estimate_shrinkage_k, gini, hhi, robust_z, shrink, spearman, trimmed_mean


def test_robust_z_invariant_to_affine_transform():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 10.0, 50.0])
    assert np.allclose(robust_z(x), robust_z(3 * x + 7))


def test_robust_z_resists_outlier():
    base = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    with_outlier = pd.concat([base, pd.Series([1000.0])], ignore_index=True)
    assert abs(robust_z(with_outlier).iloc[2] - robust_z(base).iloc[2]) < 0.5


def test_robust_z_constant_series():
    assert (robust_z(pd.Series([2.0, 2.0, 2.0])) == 0).all()


def test_gini_bounds():
    assert gini([5, 5, 5, 5]) == 0
    assert 0 < gini([1, 1, 1, 100]) < 1
    assert gini([0, 0, 0, 10]) == 0.75


def test_hhi():
    assert np.isclose(hhi([1, 1, 1, 1]), 0.25)
    assert np.isclose(hhi([0, 0, 10]), 1.0)


def test_shrink_between_mean_and_prior():
    mean, n, prior = pd.Series([7.0, 3.0, np.nan]), pd.Series([2, 4, 0]), pd.Series([5.0, 5.0, 5.5])
    s = shrink(mean, n, prior, k=3)
    assert 5 < s[0] < 7 and 3 < s[1] < 5 and s[2] == 5.5


def test_shrinkage_k_large_when_no_between_variance():
    rng = np.random.default_rng(0)
    values = pd.Series(rng.normal(5, 1, 200))
    groups = pd.Series(np.repeat(np.arange(50), 4))
    assert estimate_shrinkage_k(values, groups) >= 5


def test_trimmed_mean_ignores_extremes():
    assert trimmed_mean([1, 2, 3, 4, 5, 6, 7, 8, 9, 1000]) < 10


def test_bootstrap_ci_contains_point_estimate():
    lo, hi = bootstrap_ci(np.array([1.0, 2.0, 3.0, 4.0]), np.mean)
    assert lo <= 2.5 <= hi


def test_spearman_perfect_rank():
    c = spearman(pd.Series([1, 2, 3, 4]), pd.Series([10, 20, 30, 1000]))
    assert np.isclose(c.rho, 1.0) and c.n == 4
