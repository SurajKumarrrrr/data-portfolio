"""Deterministic synthetic experiment data (a checkout-page redesign in a DACH web shop).

Everything here is simulated with a fixed seed; the numbers are not real-world facts.
Known ground truth lets us check that the analysis recovers the effects it should.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

TRUE_EFFECTS = {
    "conversion_log_odds": 0.07,  # ~ +6-7% relative conversion uplift
    "add_to_cart_log_odds": 0.03,
    "basket_value_multiplier": 1.00,  # no effect on order value
}


def assign_variant(user_id: str, salt: str = "checkout-v2", treatment_share: float = 0.5) -> str:
    """Deterministic hash-based assignment: same user + salt -> same variant, always."""
    h = int(hashlib.md5(f"{salt}:{user_id}".encode()).hexdigest()[:8], 16)
    return "treatment" if h / 0xFFFFFFFF < treatment_share else "control"


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-z))


def generate_experiment(n_users: int = 60_000, seed: int = 42,
                        effects: dict | None = None) -> pd.DataFrame:
    """One row per user with variant, segments, a pre-period covariate and outcomes."""
    eff = {**TRUE_EFFECTS, **(effects or {})}
    rng = np.random.default_rng(seed)
    user_id = np.array([f"u{i:07d}" for i in range(n_users)])
    variant = np.array([assign_variant(u) for u in user_id])
    treat = (variant == "treatment").astype(float)

    device = rng.choice(["mobile", "desktop"], n_users, p=[0.62, 0.38])
    country = rng.choice(["DE", "AT", "CH"], n_users, p=[0.78, 0.12, 0.10])
    is_mobile = (device == "mobile").astype(float)
    is_ch = (country == "CH").astype(float)

    # Latent shopping propensity drives both past and current behaviour.
    propensity = rng.normal(0, 1, n_users)

    # Pre-period (4 weeks before the test): spend is a sum of Poisson orders.
    pre_orders = rng.poisson(np.exp(-0.7 + 1.1 * propensity))
    pre_revenue = np.array([rng.lognormal(3.7, 0.5, k).sum() for k in pre_orders])

    atc_logit = -1.1 + 0.8 * propensity - 0.2 * is_mobile + eff["add_to_cart_log_odds"] * treat
    add_to_cart = rng.random(n_users) < _sigmoid(atc_logit)

    conv_logit = (-3.1 + 1.2 * propensity - 0.35 * is_mobile
                  + eff["conversion_log_odds"] * treat + 0.6 * add_to_cart)
    converted = rng.random(n_users) < _sigmoid(conv_logit)
    basket = rng.lognormal(3.7 + 0.25 * propensity + 0.2 * is_ch, 0.55, n_users)
    revenue = np.where(converted, basket * eff["basket_value_multiplier"], 0.0)

    return pd.DataFrame({
        "user_id": user_id,
        "variant": variant,
        "device": device,
        "country": country,
        "pre_revenue": pre_revenue.round(2),
        "add_to_cart": add_to_cart.astype(int),
        "converted": converted.astype(int),
        "revenue": revenue.round(2),
    })
