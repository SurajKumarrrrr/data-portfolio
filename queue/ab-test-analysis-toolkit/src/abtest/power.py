"""Experiment planning: sample size, power and minimum detectable effect.

All formulas use the normal approximation that most experimentation platforms use.
`ratio` is n_treatment / n_control.
"""

from __future__ import annotations

import math

from scipy.optimize import brentq
from scipy.stats import norm


def _z_alpha(alpha: float, two_sided: bool) -> float:
    return float(norm.ppf(1 - alpha / 2 if two_sided else 1 - alpha))


def _target_rate(baseline: float, mde: float, relative: bool) -> float:
    p2 = baseline * (1 + mde) if relative else baseline + mde
    if not 0 < baseline < 1 or not 0 < p2 < 1:
        raise ValueError("baseline and baseline+effect must lie strictly between 0 and 1")
    if p2 == baseline:
        raise ValueError("mde must be non-zero")
    return p2


def sample_size_proportions(
    baseline: float,
    mde: float,
    alpha: float = 0.05,
    power: float = 0.8,
    relative: bool = True,
    ratio: float = 1.0,
    two_sided: bool = True,
) -> int:
    """Control-group sample size to detect a change in a conversion rate.

    Uses the pooled variance under H0 and unpooled variance under H1
    (Fleiss' formula without continuity correction).
    """
    p1 = baseline
    p2 = _target_rate(baseline, mde, relative)
    z_a, z_b = _z_alpha(alpha, two_sided), float(norm.ppf(power))
    p_bar = (p1 + ratio * p2) / (1 + ratio)
    term_h0 = z_a * math.sqrt(p_bar * (1 - p_bar) * (1 + 1 / ratio))
    term_h1 = z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2) / ratio)
    return math.ceil((term_h0 + term_h1) ** 2 / (p2 - p1) ** 2)


def sample_size_means(
    std: float,
    mde: float,
    alpha: float = 0.05,
    power: float = 0.8,
    ratio: float = 1.0,
    two_sided: bool = True,
) -> int:
    """Control-group sample size to detect an absolute difference `mde` in a mean."""
    if std <= 0 or mde == 0:
        raise ValueError("std must be positive and mde non-zero")
    z_a, z_b = _z_alpha(alpha, two_sided), float(norm.ppf(power))
    return math.ceil((z_a + z_b) ** 2 * std**2 * (1 + 1 / ratio) / mde**2)


def power_proportions(
    baseline: float,
    mde: float,
    n_control: int,
    alpha: float = 0.05,
    relative: bool = True,
    ratio: float = 1.0,
    two_sided: bool = True,
) -> float:
    """Power of a two-proportion z-test for a given control-group size."""
    p1 = baseline
    p2 = _target_rate(baseline, mde, relative)
    n_t = n_control * ratio
    p_bar = (p1 * n_control + p2 * n_t) / (n_control + n_t)
    se0 = math.sqrt(p_bar * (1 - p_bar) * (1 / n_control + 1 / n_t))
    se1 = math.sqrt(p1 * (1 - p1) / n_control + p2 * (1 - p2) / n_t)
    z_a = _z_alpha(alpha, two_sided)
    return float(norm.cdf((abs(p2 - p1) - z_a * se0) / se1))


def mde_proportions(
    baseline: float,
    n_control: int,
    alpha: float = 0.05,
    power: float = 0.8,
    ratio: float = 1.0,
    two_sided: bool = True,
) -> float:
    """Smallest positive relative lift detectable with the given power."""
    upper = (1 - baseline) / baseline - 1e-9

    def gap(m: float) -> float:
        return power_proportions(baseline, m, n_control, alpha, True, ratio, two_sided) - power

    if gap(upper) < 0:
        raise ValueError("sample too small: no achievable lift reaches the requested power")
    return float(brentq(gap, 1e-9, upper, xtol=1e-10))


def duration_days(n_control: int, daily_traffic: int, traffic_share: float = 1.0,
                  ratio: float = 1.0) -> int:
    """Days needed to collect both groups given daily eligible traffic."""
    total = n_control * (1 + ratio)
    return math.ceil(total / (daily_traffic * traffic_share))
