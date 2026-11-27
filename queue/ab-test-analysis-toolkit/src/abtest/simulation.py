"""Monte-Carlo checks: does the test keep its promised error rates?"""

from __future__ import annotations

import numpy as np
from scipy import stats


def _z_pvalues(x_c: np.ndarray, x_t: np.ndarray, n_c: np.ndarray, n_t: np.ndarray) -> np.ndarray:
    """Vectorised pooled two-proportion z-test p-values."""
    p_pool = (x_c + x_t) / (n_c + n_t)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(se > 0, (x_t / n_t - x_c / n_c) / se, 0.0)
    return 2 * stats.norm.sf(np.abs(z))


def simulate_power(p_control: float, p_treatment: float, n_per_group: int, n_sims: int = 2000,
                   alpha: float = 0.05, seed: int = 0) -> float:
    """Share of simulated experiments that reach significance (empirical power / FPR)."""
    rng = np.random.default_rng(seed)
    x_c = rng.binomial(n_per_group, p_control, n_sims)
    x_t = rng.binomial(n_per_group, p_treatment, n_sims)
    n = np.full(n_sims, n_per_group)
    return float((_z_pvalues(x_c, x_t, n, n) < alpha).mean())


def simulate_peeking(p: float, n_per_group: int, n_looks: int = 20, n_sims: int = 2000,
                     alpha: float = 0.05, seed: int = 0) -> dict:
    """A/A simulation of 'peeking': checking the p-value after every batch of traffic.

    Both groups share the same true rate, so every significant result is a false
    positive. Stopping at the first p < alpha inflates the false-positive rate far
    above the nominal alpha; testing only once at the planned horizon does not.
    """
    rng = np.random.default_rng(seed)
    step = n_per_group // n_looks
    inc = rng.binomial(step, p, size=(2, n_sims, n_looks))
    x = inc.cumsum(axis=2)
    n = step * np.arange(1, n_looks + 1)
    pvals = _z_pvalues(x[0], x[1], n, n)
    significant = pvals < alpha
    first_hit = np.where(significant.any(axis=1), significant.argmax(axis=1) + 1, 0)
    return {
        "n_looks": n_looks,
        "fixed_horizon_fpr": float(significant[:, -1].mean()),
        "peeking_fpr": float(significant.any(axis=1).mean()),
        "bonferroni_peeking_fpr": float((pvals < alpha / n_looks).any(axis=1).mean()),
        "median_stop_look": float(np.median(first_hit[first_hit > 0])) if first_hit.any() else 0.0,
    }
