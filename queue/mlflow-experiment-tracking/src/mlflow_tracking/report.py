"""Markdown comparison report built from the MLflow tracking store (not from local state)."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from mlflow.tracking import MlflowClient

from .registry import PromotionDecision

REPORT_COLUMNS = {
    "tags.candidate": "candidate",
    "params.model": "model",
    "metrics.cv_roc_auc_mean": "cv_auc",
    "metrics.cv_roc_auc_std": "cv_auc_std",
    "metrics.test_roc_auc": "test_auc",
    "metrics.test_pr_auc": "test_pr_auc",
    "metrics.test_f1": "test_f1",
    "metrics.test_brier": "test_brier",
    "metrics.overfit_gap_roc_auc": "overfit_gap",
    "metrics.fit_seconds": "fit_s",
}


def sweep_runs(experiment_id: str, sweep_id: str, metric: str) -> pd.DataFrame:
    """Fetch the child runs of a sweep as a tidy DataFrame sorted by the primary metric."""
    client = MlflowClient()
    runs = client.search_runs(
        [experiment_id],
        filter_string=f"tags.sweep_id = '{sweep_id}'",
        order_by=[f"metrics.{metric} DESC"],
    )
    rows = []
    for r in runs:
        flat = {f"tags.{k}": v for k, v in r.data.tags.items()}
        flat.update({f"params.{k}": v for k, v in r.data.params.items()})
        flat.update({f"metrics.{k}": v for k, v in r.data.metrics.items()})
        flat["run_id"] = r.info.run_id
        rows.append(flat)
    df = pd.DataFrame(rows)
    keep = [c for c in REPORT_COLUMNS if c in df.columns]
    return df[keep + ["run_id"]].rename(columns=REPORT_COLUMNS)


def _md_table(df: pd.DataFrame) -> str:
    header = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join(["---"] * len(df.columns)) + "|"
    lines = [header, sep]
    for _, row in df.iterrows():
        cells = [f"{v:.4f}" if isinstance(v, float) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(
    experiment_name: str,
    experiment_id: str,
    sweep_id: str,
    metric: str,
    decision: PromotionDecision | None,
    data_fingerprint: str,
    config_fingerprint: str,
) -> str:
    runs = sweep_runs(experiment_id, sweep_id, metric)
    table = runs.drop(columns=["run_id"]).copy()
    table["fit_s"] = table["fit_s"].map(lambda s: f"{s:.2f}")
    lines = [
        f"# Experiment report: {experiment_name}",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from the MLflow tracking store.",
        "",
        f"- Sweep run: `{sweep_id}`",
        f"- Config fingerprint: `{config_fingerprint}`",
        f"- Data fingerprint: `{data_fingerprint}` (synthetic data, fixed seed)",
        f"- Primary metric: `{metric}`",
        "",
        "## Candidates (sorted by primary metric)",
        "",
        _md_table(table),
        "",
    ]
    if decision is not None:
        champ = (
            "none"
            if decision.champion_score is None
            else f"v{decision.previous_champion_version} ({decision.champion_score:.4f})"
        )
        verdict = "PROMOTED to @champion" if decision.promoted else "kept as @challenger only"
        lines += [
            "## Model registry",
            "",
            f"- Registered `{decision.model_name}` version **{decision.version}** "
            f"from run `{decision.run_id}`",
            f"- Challenger {metric}: {decision.challenger_score:.4f}; previous champion: {champ}",
            f"- Decision: **{verdict}** - {decision.reason}",
            "",
        ]
    return "\n".join(lines)
