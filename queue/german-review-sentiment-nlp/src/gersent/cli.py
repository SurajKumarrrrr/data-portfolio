"""Command line interface: ``gersent generate | run | predict``."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib

from gersent.data import generate_reviews
from gersent.pipeline import ExperimentConfig, run_experiment


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gersent", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="write the synthetic dataset to CSV")
    gen.add_argument("--n", type=int, default=6000)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--out", type=Path, default=Path("data/reviews.csv"))

    run = sub.add_parser("run", help="train + evaluate all models, write reports/")
    run.add_argument("--n", type=int, default=6000)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--out", type=Path, default=Path("reports"))
    run.add_argument("--models", nargs="*", default=None)

    pred = sub.add_parser("predict", help="classify texts with the saved best baseline")
    pred.add_argument("texts", nargs="+")
    pred.add_argument("--model", type=Path, default=Path("reports/best_baseline.joblib"))

    args = parser.parse_args(argv)
    if args.cmd == "generate":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        generate_reviews(args.n, seed=args.seed).to_csv(args.out, index=False)
        print(f"wrote {args.n} reviews to {args.out}")
    elif args.cmd == "run":
        summary = run_experiment(ExperimentConfig(n_reviews=args.n, seed=args.seed),
                                 out_dir=args.out, models=args.models)
        print((args.out / "results.md").read_text(encoding="utf-8"))
        print(f"data: {summary['data']}")
    else:
        model = joblib.load(args.model)
        for text, label in zip(args.texts, model.predict(args.texts), strict=True):
            print(f"{label:8s} | {text}")


if __name__ == "__main__":
    main()
