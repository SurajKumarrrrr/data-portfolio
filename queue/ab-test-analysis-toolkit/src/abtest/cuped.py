"""CUPED variance reduction (Deng et al., 2013).

Y_adj = Y - theta * (X - mean(X)) with theta = cov(X, Y) / var(X), where X is a
pre-experiment covariate unaffected by treatment. Same expected treatment effect,
lower variance -> narrower CIs / smaller required samples.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CupedResult:
    adjusted: np.ndarray
    theta: float
    variance_reduction: float
    correlation: float


def cuped_adjust(y: np.ndarray, x: np.ndarray) -> CupedResult:
    """Return CUPED-adjusted outcomes. theta is estimated on the pooled sample."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    if y.shape != x.shape:
        raise ValueError("y and x must have the same shape")
    var_x = x.var(ddof=1)
    if var_x == 0:
        return CupedResult(y.copy(), 0.0, 0.0, 0.0)
    theta = float(np.cov(x, y, ddof=1)[0, 1] / var_x)
    adjusted = y - theta * (x - x.mean())
    reduction = 1 - adjusted.var(ddof=1) / y.var(ddof=1)
    corr = float(np.corrcoef(x, y)[0, 1])
    return CupedResult(adjusted, theta, float(reduction), corr)
