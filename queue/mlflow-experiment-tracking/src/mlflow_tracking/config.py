"""Typed experiment configuration loaded from YAML."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

SUPPORTED_MODELS = {"logistic_regression", "random_forest", "hist_gradient_boosting"}


@dataclass(frozen=True)
class Candidate:
    """One model configuration to train and track as an MLflow run."""

    name: str
    model: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DataConfig:
    n_samples: int = 6000
    test_size: float = 0.25


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_name: str
    registered_model_name: str
    candidates: list[Candidate]
    seed: int = 42
    primary_metric: str = "test_roc_auc"
    min_improvement: float = 0.0
    data: DataConfig = field(default_factory=DataConfig)

    def fingerprint(self) -> str:
        """Stable short hash of the full config, logged as a tag for traceability."""
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


def parse_config(raw: dict) -> ExperimentConfig:
    """Validate a raw dict (e.g. parsed YAML) and build an ExperimentConfig."""
    for key in ("experiment_name", "registered_model_name", "candidates"):
        if key not in raw:
            raise ValueError(f"config is missing required key '{key}'")
    candidates = [Candidate(**c) for c in raw["candidates"]]
    if not candidates:
        raise ValueError("config must define at least one candidate")
    names = [c.name for c in candidates]
    if len(names) != len(set(names)):
        raise ValueError("candidate names must be unique")
    for c in candidates:
        if c.model not in SUPPORTED_MODELS:
            raise ValueError(f"unknown model '{c.model}' for candidate '{c.name}'")
    data = DataConfig(**raw.get("data", {}))
    if not 0.05 <= data.test_size <= 0.5:
        raise ValueError("data.test_size must be between 0.05 and 0.5")
    return ExperimentConfig(
        experiment_name=raw["experiment_name"],
        registered_model_name=raw["registered_model_name"],
        candidates=candidates,
        seed=int(raw.get("seed", 42)),
        primary_metric=raw.get("primary_metric", "test_roc_auc"),
        min_improvement=float(raw.get("min_improvement", 0.0)),
        data=data,
    )


def load_config(path: str | Path) -> ExperimentConfig:
    with open(path, encoding="utf-8") as fh:
        return parse_config(yaml.safe_load(fh))
