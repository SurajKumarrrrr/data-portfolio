"""Train every candidate of an experiment config and log everything to MLflow."""

from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import dataclass

import mlflow
import numpy as np
import pandas as pd
import sklearn
from mlflow.models import infer_signature
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline

from .config import Candidate, ExperimentConfig
from .data import TARGET, dataset_fingerprint, generate_credit_data
from .models import build_pipeline


@dataclass(frozen=True)
class Splits:
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series


@dataclass(frozen=True)
class RunResult:
    run_id: str
    candidate: str
    metrics: dict[str, float]


def make_splits(df: pd.DataFrame, test_size: float, seed: int) -> Splits:
    X = df.drop(columns=[TARGET])
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )
    return Splits(X_train, X_test, y_train, y_test)


def evaluate(pipeline: Pipeline, X: pd.DataFrame, y: pd.Series, prefix: str = "test") -> dict:
    """Threshold-free and threshold-0.5 metrics for a fitted binary classifier."""
    proba = pipeline.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        f"{prefix}_roc_auc": float(roc_auc_score(y, proba)),
        f"{prefix}_pr_auc": float(average_precision_score(y, proba)),
        f"{prefix}_f1": float(f1_score(y, pred)),
        f"{prefix}_accuracy": float(accuracy_score(y, pred)),
        f"{prefix}_brier": float(brier_score_loss(y, proba)),
        f"{prefix}_log_loss": float(log_loss(y, proba)),
    }


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def train_candidate(
    cfg: ExperimentConfig,
    candidate: Candidate,
    splits: Splits,
    data_fp: str,
    sweep_id: str,
) -> RunResult:
    """Fit one candidate inside a nested MLflow run and log params, metrics and artifacts."""
    pipeline = build_pipeline(candidate, cfg.seed)
    with mlflow.start_run(run_name=candidate.name, nested=True) as run:
        mlflow.set_tags(
            {
                "candidate": candidate.name,
                "model_family": candidate.model,
                "sweep_id": sweep_id,
                "config_fingerprint": cfg.fingerprint(),
                "data_fingerprint": data_fp,
                "git_commit": _git_commit(),
                "sklearn_version": sklearn.__version__,
                "python_version": platform.python_version(),
            }
        )
        mlflow.log_params(
            {
                "model": candidate.model,
                "seed": cfg.seed,
                "n_train": len(splits.X_train),
                "n_test": len(splits.X_test),
                **{f"model__{k}": v for k, v in candidate.params.items()},
            }
        )

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=cfg.seed)
        cv_scores = cross_val_score(
            pipeline, splits.X_train, splits.y_train, cv=cv, scoring="roc_auc"
        )

        start = time.perf_counter()
        pipeline.fit(splits.X_train, splits.y_train)
        fit_seconds = time.perf_counter() - start

        metrics = {
            "cv_roc_auc_mean": float(np.mean(cv_scores)),
            "cv_roc_auc_std": float(np.std(cv_scores)),
            "fit_seconds": fit_seconds,
            **evaluate(pipeline, splits.X_test, splits.y_test, "test"),
            **evaluate(pipeline, splits.X_train, splits.y_train, "train"),
        }
        metrics["overfit_gap_roc_auc"] = metrics["train_roc_auc"] - metrics["test_roc_auc"]
        mlflow.log_metrics(metrics)
        for fold, score in enumerate(cv_scores):
            mlflow.log_metric("cv_fold_roc_auc", float(score), step=fold)

        pred = pipeline.predict(splits.X_test)
        tn, fp, fn, tp = confusion_matrix(splits.y_test, pred).ravel()
        mlflow.log_dict(
            {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "evaluation/confusion_matrix.json",
        )

        importance = permutation_importance(
            pipeline,
            splits.X_test,
            splits.y_test,
            scoring="roc_auc",
            n_repeats=5,
            random_state=cfg.seed,
        )
        ranked = sorted(
            zip(splits.X_test.columns, importance.importances_mean, strict=True),
            key=lambda kv: kv[1],
            reverse=True,
        )
        mlflow.log_dict(
            {name: round(float(v), 5) for name, v in ranked},
            "evaluation/permutation_importance.json",
        )
        mlflow.log_text(json.dumps(candidate.params, indent=2), "config/candidate_params.json")

        example = splits.X_test.head(5)
        signature = infer_signature(example, pipeline.predict_proba(example)[:, 1])
        mlflow.sklearn.log_model(
            pipeline, artifact_path="model", signature=signature, input_example=example
        )
    return RunResult(run.info.run_id, candidate.name, metrics)


def run_experiment(cfg: ExperimentConfig) -> tuple[str, list[RunResult]]:
    """Train all candidates under one parent 'sweep' run. Assumes tracking is configured."""
    df = generate_credit_data(cfg.data.n_samples, cfg.seed)
    data_fp = dataset_fingerprint(df)
    splits = make_splits(df, cfg.data.test_size, cfg.seed)
    results: list[RunResult] = []
    with mlflow.start_run(run_name=f"sweep-{cfg.fingerprint()}") as parent:
        sweep_id = parent.info.run_id
        mlflow.set_tags(
            {
                "run_type": "sweep",
                "config_fingerprint": cfg.fingerprint(),
                "data_fingerprint": data_fp,
            }
        )
        mlflow.log_params(
            {
                "n_candidates": len(cfg.candidates),
                "n_samples": cfg.data.n_samples,
                "positive_rate": round(float(df[TARGET].mean()), 4),
                "primary_metric": cfg.primary_metric,
            }
        )
        for candidate in cfg.candidates:
            results.append(train_candidate(cfg, candidate, splits, data_fp, sweep_id))
        best = max(results, key=lambda r: r.metrics[cfg.primary_metric])
        mlflow.set_tag("best_candidate", best.candidate)
        mlflow.log_metric(f"best_{cfg.primary_metric}", best.metrics[cfg.primary_metric])
    return sweep_id, results
