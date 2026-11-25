"""End-to-end experiment: generate data, train all models, evaluate, write reports."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import pandas as pd

from gersent.baselines import BASELINES
from gersent.data import generate_reviews, train_val_test_split
from gersent.evaluate import compute_metrics, error_examples, slice_metrics
from gersent.transformer import TransformerConfig, TransformerSentiment

CHALLENGE_PATH = Path(__file__).resolve().parents[2] / "challenge" / "challenge_set.csv"


@dataclass
class ExperimentConfig:
    n_reviews: int = 6000
    seed: int = 42
    label_noise: float = 0.03
    transformer: TransformerConfig = field(default_factory=TransformerConfig)
    challenge_path: Path = CHALLENGE_PATH


def _evaluate(model, name: str, train_seconds: float, test: pd.DataFrame,
              challenge: pd.DataFrame | None) -> dict:
    texts, y = test["text"].tolist(), test["label"].tolist()
    start = time.perf_counter()
    pred = list(model.predict(texts))
    infer_ms = (time.perf_counter() - start) / len(texts) * 1000
    result = {
        "model": name,
        "train_seconds": round(train_seconds, 2),
        "inference_ms_per_review": round(infer_ms, 4),
        "test": compute_metrics(y, pred),
        "test_slices": slice_metrics(texts, y, pred),
        "errors": error_examples(texts, y, pred, k=3),
    }
    if challenge is not None:
        c_pred = list(model.predict(challenge["text"].tolist()))
        result["challenge"] = compute_metrics(challenge["label"].tolist(), c_pred)
        result["challenge_predictions"] = c_pred
    return result


def run_experiment(cfg: ExperimentConfig, out_dir: Path | None = None,
                   models: list[str] | None = None) -> dict:
    """Train and evaluate every model. Returns a JSON-serialisable result dict."""
    df = generate_reviews(cfg.n_reviews, seed=cfg.seed, label_noise=cfg.label_noise)
    train, val, test = train_val_test_split(df, seed=cfg.seed)
    challenge = pd.read_csv(cfg.challenge_path) if cfg.challenge_path.exists() else None
    wanted = models or [*BASELINES, "tiny_transformer"]

    results: list[dict] = []
    fitted: dict[str, object] = {}
    for name in wanted:
        start = time.perf_counter()
        if name == "tiny_transformer":
            model = TransformerSentiment(cfg.transformer).fit(
                train["text"].tolist(), train["label"].tolist(),
                val["text"].tolist(), val["label"].tolist())
        else:
            # baselines have no early stopping, so train+val is fair game
            fit_df = pd.concat([train, val])
            model = BASELINES[name]().fit(fit_df["text"], fit_df["label"])
        res = _evaluate(model, name, time.perf_counter() - start, test, challenge)
        if name == "tiny_transformer":
            res["n_parameters"] = model.n_parameters()
            res["epochs_trained"] = len(model.history)
            res["history"] = model.history
        results.append(res)
        fitted[name] = model

    summary = {
        "data": {"n_reviews": len(df), "train": len(train), "val": len(val), "test": len(test),
                 "label_distribution": df["label"].value_counts().to_dict(),
                 "seed": cfg.seed, "label_noise": cfg.label_noise, "synthetic": True},
        "results": results,
    }
    if challenge is not None:
        summary["challenge_texts"] = challenge.to_dict(orient="records")

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        (out_dir / "results.md").write_text(to_markdown(summary), encoding="utf-8")
        best = max((r for r in results if r["model"] != "tiny_transformer"),
                   key=lambda r: r["test"]["macro_f1"], default=None)
        if best is not None:
            joblib.dump(fitted[best["model"]], out_dir / "best_baseline.joblib")
    return summary


def to_markdown(summary: dict) -> str:
    """Render the comparison tables that are pasted into the README."""
    lines = ["| Model | Test accuracy | Test macro-F1 | F1 neutral | Challenge acc. (n=30) "
             "| Train time (s) | Inference (ms/review) |",
             "|---|---|---|---|---|---|---|"]
    for r in summary["results"]:
        ch = r.get("challenge", {}).get("accuracy")
        lines.append(
            f"| {r['model']} | {r['test']['accuracy']:.3f} | {r['test']['macro_f1']:.3f} "
            f"| {r['test']['f1_per_class']['neutral']:.3f} "
            f"| {'' if ch is None else f'{ch:.3f}'} | {r['train_seconds']:.1f} "
            f"| {r['inference_ms_per_review']:.3f} |")
    lines += ["", "Macro-F1 on test slices:", "",
              "| Model | " + " | ".join(summary["results"][0]["test_slices"]) + " |",
              "|---|" + "---|" * len(summary["results"][0]["test_slices"])]
    for r in summary["results"]:
        cells = [f"{v['macro_f1']:.3f} (n={v['n']})" for v in r["test_slices"].values()]
        lines.append(f"| {r['model']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
