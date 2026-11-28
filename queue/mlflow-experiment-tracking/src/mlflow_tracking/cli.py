"""Command line entry point: ``python -m mlflow_tracking.cli {train,predict,all}``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .data import TARGET, dataset_fingerprint, generate_credit_data
from .registry import load_champion, register_and_maybe_promote
from .report import build_report
from .tracking import DEFAULT_ARTIFACT_ROOT, DEFAULT_TRACKING_URI, setup_experiment
from .train import run_experiment


def cmd_train(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    experiment_id = setup_experiment(cfg.experiment_name, args.tracking_uri, args.artifact_root)
    sweep_id, results = run_experiment(cfg)
    print(f"Sweep {sweep_id}: trained {len(results)} candidates")
    for r in sorted(results, key=lambda r: -r.metrics[cfg.primary_metric]):
        print(f"  {r.candidate:<20} {cfg.primary_metric}={r.metrics[cfg.primary_metric]:.4f}")

    decision = None
    if not args.no_register:
        decision = register_and_maybe_promote(
            experiment_id,
            sweep_id,
            cfg.registered_model_name,
            cfg.primary_metric,
            cfg.min_improvement,
        )
        status = "promoted to @champion" if decision.promoted else "not promoted"
        print(f"Registered {decision.model_name} v{decision.version}: {status} ({decision.reason})")

    data_fp = dataset_fingerprint(generate_credit_data(cfg.data.n_samples, cfg.seed))
    report = build_report(
        cfg.experiment_name,
        experiment_id,
        sweep_id,
        cfg.primary_metric,
        decision,
        data_fp,
        cfg.fingerprint(),
    )
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Report written to {out}")


def cmd_predict(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    setup_experiment(cfg.experiment_name, args.tracking_uri, args.artifact_root)
    model = load_champion(cfg.registered_model_name)
    # Fresh, unseen applicants: same generator, different seed.
    batch = generate_credit_data(args.n, seed=cfg.seed + 1000).drop(columns=[TARGET])
    proba = model.predict_proba(batch)[:, 1]
    print(f"Scored {len(batch)} new applicants with {cfg.registered_model_name}@champion")
    for i, p in enumerate(proba):
        print(f"  applicant {i}: default probability {p:.3f}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri", default=DEFAULT_TRACKING_URI)
    parser.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="train all candidates, register and report")
    predict = sub.add_parser("predict", help="score new rows with the @champion model")
    run_all = sub.add_parser("all", help="train + predict")
    for p in (train, predict, run_all):
        p.add_argument("--config", default="configs/experiments.yaml")
    for p in (train, run_all):
        p.add_argument("--report", default="reports/comparison_report.md")
        p.add_argument("--no-register", action="store_true")
    for p in (predict, run_all):
        p.add_argument("-n", type=int, default=5, help="rows to score")

    args = parser.parse_args(argv)
    if args.command == "train":
        cmd_train(args)
    elif args.command == "predict":
        cmd_predict(args)
    else:
        cmd_train(args)
        if not args.no_register:
            cmd_predict(args)


if __name__ == "__main__":
    main()
