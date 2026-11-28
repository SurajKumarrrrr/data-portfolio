"""Model factory: every candidate becomes a full sklearn Pipeline (preprocessing + estimator)."""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from .config import Candidate
from .data import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def _preprocessor(model: str) -> ColumnTransformer:
    if model == "logistic_regression":
        return ColumnTransformer(
            [
                ("num", StandardScaler(), NUMERIC_FEATURES),
                ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ]
        )
    # Tree models don't need scaling; ordinal encoding keeps the feature space small.
    return ColumnTransformer(
        [
            ("num", "passthrough", NUMERIC_FEATURES),
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                CATEGORICAL_FEATURES,
            ),
        ]
    )


def build_pipeline(candidate: Candidate, seed: int) -> Pipeline:
    """Build an unfitted pipeline for a candidate; ``seed`` makes training deterministic."""
    params = dict(candidate.params)
    if candidate.model == "logistic_regression":
        estimator = LogisticRegression(max_iter=2000, random_state=seed, **params)
    elif candidate.model == "random_forest":
        estimator = RandomForestClassifier(random_state=seed, n_jobs=1, **params)
    elif candidate.model == "hist_gradient_boosting":
        n_cat = len(CATEGORICAL_FEATURES)
        cat_mask = [False] * len(NUMERIC_FEATURES) + [True] * n_cat
        estimator = HistGradientBoostingClassifier(
            random_state=seed, categorical_features=cat_mask, **params
        )
    else:
        raise ValueError(f"unknown model '{candidate.model}'")
    return Pipeline([("preprocess", _preprocessor(candidate.model)), ("model", estimator)])
