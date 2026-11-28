"""Integration tests against a real (temporary) MLflow SQLite store."""

from pathlib import Path

import yaml
from mlflow.tracking import MlflowClient

from mlflow_tracking.cli import main
from mlflow_tracking.data import TARGET, generate_credit_data
from mlflow_tracking.registry import CHALLENGER, CHAMPION, load_champion, register_and_maybe_promote
from mlflow_tracking.report import build_report
from mlflow_tracking.train import run_experiment


def _register(cfg, experiment_id, sweep_id):
    return register_and_maybe_promote(
        experiment_id, sweep_id, cfg.registered_model_name, cfg.primary_metric, cfg.min_improvement
    )


def test_sweep_logs_runs_params_metrics_artifacts(small_cfg, tracking):
    sweep_id, results = run_experiment(small_cfg)
    assert {r.candidate for r in results} == {"lr", "rf"}
    client = MlflowClient()
    children = client.search_runs([tracking], filter_string=f"tags.sweep_id = '{sweep_id}'")
    assert len(children) == 2
    run = children[0]
    assert run.data.tags["data_fingerprint"]
    assert run.data.tags["config_fingerprint"] == small_cfg.fingerprint()
    assert run.data.params["seed"] == "7"
    for metric in ("cv_roc_auc_mean", "test_roc_auc", "test_pr_auc", "overfit_gap_roc_auc"):
        assert metric in run.data.metrics
    assert 0.5 < run.data.metrics["test_roc_auc"] <= 1.0
    artifacts = {a.path for a in client.list_artifacts(run.info.run_id)}
    assert {"model", "evaluation", "config"} <= artifacts
    history = client.get_metric_history(run.info.run_id, "cv_fold_roc_auc")
    assert len(history) == 5
    parent = client.get_run(sweep_id)
    assert parent.data.tags["best_candidate"] in {"lr", "rf"}


def test_training_is_reproducible(small_cfg, tracking):
    _, first = run_experiment(small_cfg)
    _, second = run_experiment(small_cfg)
    for a, b in zip(first, second, strict=True):
        assert a.metrics["test_roc_auc"] == b.metrics["test_roc_auc"]
        assert a.metrics["cv_roc_auc_mean"] == b.metrics["cv_roc_auc_mean"]


def test_champion_challenger_flow(small_cfg, tracking):
    sweep1, _ = run_experiment(small_cfg)
    d1 = _register(small_cfg, tracking, sweep1)
    assert d1.promoted and d1.version == "1"

    # Identical retrain cannot beat the champion by min_improvement -> not promoted.
    sweep2, _ = run_experiment(small_cfg)
    d2 = _register(small_cfg, tracking, sweep2)
    assert not d2.promoted
    assert d2.champion_score == d1.challenger_score
    client = MlflowClient()
    assert str(client.get_model_version_by_alias("test-model", CHAMPION).version) == "1"
    assert str(client.get_model_version_by_alias("test-model", CHALLENGER).version) == "2"
    tags = client.get_model_version("test-model", "2").tags
    assert "below required" in tags["gate_decision"]

    model = load_champion("test-model")
    rows = generate_credit_data(10, seed=99).drop(columns=[TARGET])
    assert model.predict_proba(rows).shape == (10, 2)


def test_report_contains_all_candidates(small_cfg, tracking):
    sweep_id, _ = run_experiment(small_cfg)
    decision = _register(small_cfg, tracking, sweep_id)
    md = build_report(
        "test-exp", tracking, sweep_id, small_cfg.primary_metric, decision, "abc", "def"
    )
    assert "| lr |" in md and "| rf |" in md
    assert "PROMOTED to @champion" in md


def test_cli_train_and_predict(tmp_path, small_raw, capsys):
    cfg_path = tmp_path / "exp.yaml"
    cfg_path.write_text(yaml.safe_dump(small_raw))
    report = tmp_path / "report.md"
    common = ["--tracking-uri", f"sqlite:///{tmp_path / 'cli.db'}",
              "--artifact-root", str(tmp_path / "art")]
    main([*common, "all", "--config", str(cfg_path), "--report", str(report), "-n", "3"])
    out = capsys.readouterr().out
    assert "promoted to @champion" in out
    assert "applicant 2" in out
    assert Path(report).read_text().startswith("# Experiment report")
