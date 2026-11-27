"""Bayesian analysis of conversion rates with a Beta-Binomial model."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class BayesResult:
    """Posterior summary for treatment vs control."""

    control_posterior_mean: float
    treatment_posterior_mean: float
    prob_treatment_better: float
    expected_loss_treatment: float
    expected_loss_control: float
    rel_lift_median: float
    rel_lift_ci_low: float
    rel_lift_ci_high: float

    def to_dict(self) -> dict:
        return asdict(self)


def beta_binomial(x_c: int, n_c: int, x_t: int, n_t: int, prior: tuple[float, float] = (1, 1),
                  draws: int = 200_000, cred: float = 0.95, seed: int = 0) -> BayesResult:
    """Posterior comparison of two conversion rates.

    With a Beta(a, b) prior the posterior is Beta(a + x, b + n - x). We sample both
    posteriors to get P(treatment > control), the expected loss of each decision
    (how much conversion we give up, in absolute points, if we pick it and are wrong)
    and a credible interval for the relative lift.
    """
    a, b = prior
    rng = np.random.default_rng(seed)
    pc = rng.beta(a + x_c, b + n_c - x_c, draws)
    pt = rng.beta(a + x_t, b + n_t - x_t, draws)
    lift = pt / pc - 1
    lo, med, hi = np.quantile(lift, [(1 - cred) / 2, 0.5, 1 - (1 - cred) / 2])
    return BayesResult(
        control_posterior_mean=(a + x_c) / (a + b + n_c),
        treatment_posterior_mean=(a + x_t) / (a + b + n_t),
        prob_treatment_better=float((pt > pc).mean()),
        expected_loss_treatment=float(np.maximum(pc - pt, 0).mean()),
        expected_loss_control=float(np.maximum(pt - pc, 0).mean()),
        rel_lift_median=float(med),
        rel_lift_ci_low=float(lo),
        rel_lift_ci_high=float(hi),
    )


def decide(result: BayesResult, loss_threshold: float = 0.0005) -> str:
    """Ship/stop rule based on expected loss (a common Bayesian stopping criterion)."""
    if result.expected_loss_treatment < loss_threshold:
        return "ship treatment"
    if result.expected_loss_control < loss_threshold:
        return "keep control"
    return "keep collecting data"
