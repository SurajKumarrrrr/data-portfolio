from __future__ import annotations

import copy

import mlflow
import pytest

from mlflow_tracking.config import parse_config
from mlflow_tracking.tracking import setup_experiment

SMALL_RAW = {
    "experiment_name": "test-exp",
    "registered_model_name": "test-model",
    "seed": 7,
    "primary_metric": "cv_roc_auc_mean",
    "min_improvement": 0.002,
    "data": {"n_samples": 900, "test_size": 0.25},
    "candidates": [
        {"name": "lr", "model": "logistic_regression", "params": {"C": 1.0}},
        {"name": "rf", "model": "random_forest", "params": {"n_estimators": 20, "max_depth": 4}},
    ],
}


@pytest.fixture
def small_raw() -> dict:
    return copy.deepcopy(SMALL_RAW)


@pytest.fixture
def small_cfg(small_raw):
    return parse_config(small_raw)


@pytest.fixture
def tracking(tmp_path, small_cfg):
    """Isolated SQLite tracking store + artifact root per test."""
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    experiment_id = setup_experiment(small_cfg.experiment_name, uri, tmp_path / "artifacts")
    yield experiment_id
    while mlflow.active_run() is not None:
        mlflow.end_run()
