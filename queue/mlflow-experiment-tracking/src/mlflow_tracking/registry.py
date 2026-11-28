"""Model registry: register the sweep winner and promote it only if it beats the champion."""

from __future__ import annotations

from dataclasses import dataclass

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

CHAMPION = "champion"
CHALLENGER = "challenger"


@dataclass(frozen=True)
class PromotionDecision:
    model_name: str
    version: str
    run_id: str
    metric: str
    challenger_score: float
    champion_score: float | None
    previous_champion_version: str | None
    promoted: bool
    reason: str


def should_promote(
    challenger_score: float, champion_score: float | None, min_improvement: float
) -> tuple[bool, str]:
    """Champion/challenger gate. Higher metric values are assumed to be better."""
    if champion_score is None:
        return True, "no champion yet"
    delta = challenger_score - champion_score
    if delta >= min_improvement:
        return True, f"beats champion by {delta:+.4f} (>= {min_improvement})"
    return False, f"delta {delta:+.4f} below required {min_improvement}"


def best_run_in_sweep(client: MlflowClient, experiment_id: str, sweep_id: str, metric: str):
    runs = client.search_runs(
        [experiment_id],
        filter_string=f"tags.sweep_id = '{sweep_id}'",
        order_by=[f"metrics.{metric} DESC"],
        max_results=1,
    )
    if not runs:
        raise LookupError(f"no runs found for sweep {sweep_id}")
    return runs[0]


def current_champion(client: MlflowClient, model_name: str):
    try:
        return client.get_model_version_by_alias(model_name, CHAMPION)
    except MlflowException:
        return None


def register_and_maybe_promote(
    experiment_id: str,
    sweep_id: str,
    model_name: str,
    metric: str,
    min_improvement: float,
) -> PromotionDecision:
    """Register the best run of a sweep as a new version and gate it against the champion."""
    client = MlflowClient()
    best = best_run_in_sweep(client, experiment_id, sweep_id, metric)
    challenger_score = float(best.data.metrics[metric])

    champion = current_champion(client, model_name)
    champion_score = None
    if champion is not None:
        champion_score = float(client.get_run(champion.run_id).data.metrics[metric])

    version = mlflow.register_model(f"runs:/{best.info.run_id}/model", model_name).version
    promoted, reason = should_promote(challenger_score, champion_score, min_improvement)

    client.set_model_version_tag(model_name, version, "candidate", best.data.tags["candidate"])
    client.set_model_version_tag(model_name, version, metric, f"{challenger_score:.4f}")
    client.set_model_version_tag(model_name, version, "gate_decision", reason)
    client.set_registered_model_alias(model_name, CHALLENGER, version)
    if promoted:
        client.set_registered_model_alias(model_name, CHAMPION, version)

    return PromotionDecision(
        model_name=model_name,
        version=str(version),
        run_id=best.info.run_id,
        metric=metric,
        challenger_score=challenger_score,
        champion_score=champion_score,
        previous_champion_version=None if champion is None else str(champion.version),
        promoted=promoted,
        reason=reason,
    )


def load_champion(model_name: str):
    """Load the current champion sklearn pipeline via its registry alias."""
    return mlflow.sklearn.load_model(f"models:/{model_name}@{CHAMPION}")
