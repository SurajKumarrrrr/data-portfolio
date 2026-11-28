"""Deterministic synthetic credit-default dataset.

The data is SYNTHETIC: generated from a hand-written logistic model with noise,
non-linear effects and interactions so that tree models have something to find.
It is not real customer data and results must not be read as real-world facts.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

NUMERIC_FEATURES = [
    "age",
    "income_k_eur",
    "loan_amount_k_eur",
    "loan_term_months",
    "credit_history_years",
    "num_open_credit_lines",
    "late_payments_12m",
    "debt_to_income",
]
CATEGORICAL_FEATURES = ["employment_type", "housing", "loan_purpose"]
TARGET = "default"


def generate_credit_data(n_samples: int = 6000, seed: int = 42) -> pd.DataFrame:
    """Generate a reproducible tabular dataset with a binary ``default`` target."""
    rng = np.random.default_rng(seed)
    age = rng.integers(19, 71, n_samples)
    employment = rng.choice(
        ["permanent", "temporary", "self_employed", "student", "unemployed"],
        n_samples,
        p=[0.55, 0.15, 0.12, 0.10, 0.08],
    )
    base_income = {
        "permanent": 52,
        "temporary": 36,
        "self_employed": 58,
        "student": 14,
        "unemployed": 11,
    }
    income = np.array([base_income[e] for e in employment]) * rng.lognormal(0, 0.35, n_samples)
    income = np.round(income + (age - 19) * 0.25, 1)
    housing = rng.choice(["rent", "own", "with_parents"], n_samples, p=[0.58, 0.30, 0.12])
    purpose = rng.choice(
        ["car", "home_improvement", "consumer", "education", "debt_consolidation"],
        n_samples,
        p=[0.25, 0.20, 0.30, 0.10, 0.15],
    )
    loan = np.round(rng.gamma(2.2, 6.0, n_samples) + (purpose == "home_improvement") * 8, 1)
    term = rng.choice([12, 24, 36, 48, 60, 84], n_samples)
    history = np.clip(age - 18 - rng.integers(0, 6, n_samples), 0, None)
    open_lines = rng.poisson(2.5, n_samples)
    late = rng.poisson(0.4 + (employment == "unemployed") * 0.8, n_samples)
    dti = np.round(np.clip(loan / np.maximum(income, 5) + rng.normal(0, 0.08, n_samples), 0, 3), 3)

    logit = (
        -1.5
        + 1.9 * np.tanh(dti - 0.6)                  # non-linear affordability effect
        + 0.55 * late
        - 0.035 * history
        + 0.12 * np.maximum(open_lines - 4, 0)
        + 0.010 * (term - 36)
        + 0.9 * (employment == "unemployed")
        + 0.4 * (employment == "temporary")
        - 0.35 * (housing == "own")
        + 0.3 * (purpose == "debt_consolidation")
        + 0.6 * ((age < 25) & (housing == "rent"))   # interaction
        + rng.normal(0, 0.6, n_samples)
    )
    prob = 1 / (1 + np.exp(-logit))
    target = (rng.random(n_samples) < prob).astype(int)

    return pd.DataFrame(
        {
            "age": age,
            "income_k_eur": income,
            "loan_amount_k_eur": loan,
            "loan_term_months": term,
            "credit_history_years": history,
            "num_open_credit_lines": open_lines,
            "late_payments_12m": late,
            "debt_to_income": dti,
            "employment_type": employment,
            "housing": housing,
            "loan_purpose": purpose,
            TARGET: target,
        }
    )


def dataset_fingerprint(df: pd.DataFrame) -> str:
    """Content hash of a DataFrame, logged with every run to prove which data was used."""
    row_hashes = pd.util.hash_pandas_object(df, index=True).values
    return hashlib.sha256(row_hashes.tobytes()).hexdigest()[:16]
