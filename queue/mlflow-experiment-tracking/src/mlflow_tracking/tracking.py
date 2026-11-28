"""Tracking-server setup helpers (local SQLite backend + file artifact store by default)."""

from __future__ import annotations

from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

DEFAULT_TRACKING_URI = "sqlite:///mlflow.db"
DEFAULT_ARTIFACT_ROOT = "mlartifacts"


def setup_experiment(
    experiment_name: str,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
) -> str:
    """Point MLflow at the backend store and create the experiment if needed.

    A database backend (SQLite here, PostgreSQL in production) is required for the
    model registry; the plain ``./mlruns`` file store does not support it.
    """
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    existing = client.get_experiment_by_name(experiment_name)
    if existing is not None:
        experiment_id = existing.experiment_id
    else:
        location = Path(artifact_root).resolve().as_uri()
        experiment_id = client.create_experiment(experiment_name, artifact_location=location)
    mlflow.set_experiment(experiment_name)
    return experiment_id
