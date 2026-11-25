"""Metrics, slice-based evaluation and error analysis."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from gersent.data import LABELS
from gersent.text import has_contrast, has_negation, is_transliterated

SLICES: dict[str, Callable[[str], bool]] = {
    "with_negation": has_negation,
    "with_contrast": has_contrast,
    "transliterated_umlauts": is_transliterated,
}


def compute_metrics(y_true: Sequence[str], y_pred: Sequence[str]) -> dict:
    """Accuracy, macro-F1, per-class F1 and confusion matrix (rows = true labels)."""
    labels = list(LABELS)
    per_class = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    return {
        "n": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro",
                                   zero_division=0)),
        "f1_per_class": {lbl: float(v) for lbl, v in zip(labels, per_class, strict=True)},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def slice_metrics(texts: Sequence[str], y_true: Sequence[str],
                  y_pred: Sequence[str]) -> dict[str, dict]:
    """Macro-F1 / accuracy on subsets of the data defined by :data:`SLICES`."""
    df = pd.DataFrame({"text": texts, "y": y_true, "p": y_pred})
    out: dict[str, dict] = {}
    for name, fn in SLICES.items():
        sub = df[df["text"].map(fn)]
        if len(sub) == 0:
            continue
        out[name] = {
            "n": len(sub),
            "accuracy": float(accuracy_score(sub["y"], sub["p"])),
            "macro_f1": float(f1_score(sub["y"], sub["p"], labels=list(LABELS),
                                       average="macro", zero_division=0)),
        }
    return out


def error_examples(texts: Sequence[str], y_true: Sequence[str], y_pred: Sequence[str],
                   k: int = 5) -> list[dict]:
    """First ``k`` misclassified examples (deterministic order) for qualitative review."""
    errors = [
        {"text": t, "true": y, "pred": p}
        for t, y, p in zip(texts, y_true, y_pred, strict=True) if y != p
    ]
    return errors[:k]
