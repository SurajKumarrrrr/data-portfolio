"""Frequentist tests: two-proportion z-test, Welch t-test, bootstrap, SRM, p-value adjustment."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class TestResult:
    """Outcome of comparing treatment against control on one metric."""

    __test__ = False  # stop pytest from collecting this class

    metric: str
    method: str
    control_mean: float
    treatment_mean: float
    abs_diff: float
    ci_low: float
    ci_high: float
    rel_lift: float
    rel_ci_low: float
    rel_ci_high: float
    statistic: float
    p_value: float

    def to_dict(self) -> dict:
        return asdict(self)


def _relative_ci(m_c: float, m_t: float, var_c: float, var_t: float,
                 z: float) -> tuple[float, float, float]:
    """Delta-method CI for the relative lift m_t / m_c - 1.

    var_c and var_t are the variances of the two *sample means*.
    """
    lift = m_t / m_c - 1
    se = np.sqrt(var_t / m_c**2 + m_t**2 * var_c / m_c**4)
    return lift, lift - z * se, lift + z * se


def two_proportion_ztest(x_c: int, n_c: int, x_t: int, n_t: int, alpha: float = 0.05,
                         metric: str = "conversion") -> TestResult:
    """Two-sided z-test for a difference in proportions.

    The test statistic uses the pooled variance (correct under H0); the confidence
    interval uses the unpooled variance (correct under H1).
    """
    if min(n_c, n_t) <= 0 or not (0 <= x_c <= n_c and 0 <= x_t <= n_t):
        raise ValueError("invalid counts")
    p_c, p_t = x_c / n_c, x_t / n_t
    p_pool = (x_c + x_t) / (n_c + n_t)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z_stat = (p_t - p_c) / se_pool if se_pool > 0 else 0.0
    p_value = float(2 * stats.norm.sf(abs(z_stat)))
    var_c, var_t = p_c * (1 - p_c) / n_c, p_t * (1 - p_t) / n_t
    z = float(stats.norm.ppf(1 - alpha / 2))
    se = np.sqrt(var_c + var_t)
    lift, r_lo, r_hi = _relative_ci(p_c, p_t, var_c, var_t, z)
    return TestResult(metric, "two-proportion z-test", p_c, p_t, p_t - p_c,
                      p_t - p_c - z * se, p_t - p_c + z * se, lift, r_lo, r_hi,
                      float(z_stat), p_value)


def welch_ttest(control: np.ndarray, treatment: np.ndarray, alpha: float = 0.05,
                metric: str = "mean") -> TestResult:
    """Welch's unequal-variance t-test with a CI on the absolute and relative difference."""
    c = np.asarray(control, dtype=float)
    t = np.asarray(treatment, dtype=float)
    if len(c) < 2 or len(t) < 2:
        raise ValueError("need at least two observations per group")
    m_c, m_t = c.mean(), t.mean()
    var_c, var_t = c.var(ddof=1) / len(c), t.var(ddof=1) / len(t)
    se = np.sqrt(var_c + var_t)
    df = (var_c + var_t) ** 2 / (var_c**2 / (len(c) - 1) + var_t**2 / (len(t) - 1))
    t_stat = (m_t - m_c) / se
    p_value = float(2 * stats.t.sf(abs(t_stat), df))
    q = float(stats.t.ppf(1 - alpha / 2, df))
    lift, r_lo, r_hi = _relative_ci(m_c, m_t, var_c, var_t, q)
    return TestResult(metric, "Welch t-test", float(m_c), float(m_t), float(m_t - m_c),
                      float(m_t - m_c - q * se), float(m_t - m_c + q * se),
                      float(lift), float(r_lo), float(r_hi), float(t_stat), p_value)


def bootstrap_diff_ci(control: np.ndarray, treatment: np.ndarray, n_boot: int = 2000,
                      alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI for the difference in means (robust to heavy tails)."""
    rng = np.random.default_rng(seed)
    c = np.asarray(control, dtype=float)
    t = np.asarray(treatment, dtype=float)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        diffs[i] = rng.choice(t, len(t)).mean() - rng.choice(c, len(c)).mean()
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def srm_check(observed: Sequence[int], expected_ratios: Sequence[float],
              threshold: float = 0.001) -> dict:
    """Sample-ratio-mismatch check with a chi-square goodness-of-fit test.

    A tiny p-value means the split is broken (bugged assignment, bot filtering, ...)
    and the experiment results should not be trusted. 0.001 is the usual threshold.
    """
    obs = np.asarray(observed, dtype=float)
    ratios = np.asarray(expected_ratios, dtype=float)
    expected = obs.sum() * ratios / ratios.sum()
    chi2, p = stats.chisquare(obs, expected)
    return {"chi2": float(chi2), "p_value": float(p), "srm_detected": bool(p < threshold),
            "observed": [int(o) for o in obs], "expected": [float(e) for e in expected]}


def adjust_pvalues(p_values: Sequence[float], method: str = "holm") -> list[float]:
    """Multiple-testing correction: Holm (FWER) or Benjamini-Hochberg (FDR)."""
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order]
    if method == "holm":
        adj = np.maximum.accumulate((m - np.arange(m)) * ranked)
    elif method == "bh":
        adj = np.minimum.accumulate(m / np.arange(m, 0, -1) * ranked[::-1])[::-1]
    else:
        raise ValueError("method must be 'holm' or 'bh'")
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    return out.tolist()
