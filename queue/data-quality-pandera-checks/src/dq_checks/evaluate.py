"""Measure detection against the injected-defect manifest (ground truth)."""

from __future__ import annotations

import pandas as pd


def detection_report(failures: pd.DataFrame, defects: pd.DataFrame) -> pd.DataFrame:
    """Per defect type: how many injected rows were flagged by the expected rule.

    A defect counts as detected when a failure with the same table, row and the
    rule the defect was designed to violate exists.
    """
    if defects.empty:
        return pd.DataFrame(columns=["defect_type", "expected_rule", "injected", "detected", "recall"])
    hits = failures.dropna(subset=["row_index"])[["table", "row_index", "rule"]].drop_duplicates()
    hits = hits.assign(row_index=hits["row_index"].astype(int), hit=True)
    merged = defects.merge(
        hits,
        left_on=["table", "row_index", "expected_rule"],
        right_on=["table", "row_index", "rule"],
        how="left",
    )
    merged["hit"] = merged["hit"].fillna(False).astype(bool)
    out = (
        merged.groupby(["defect_type", "expected_rule"], sort=False)
        .agg(injected=("hit", "size"), detected=("hit", "sum"))
        .reset_index()
    )
    out["recall"] = (out["detected"] / out["injected"]).round(3)
    return out


def unexpected_flags(failures: pd.DataFrame, defects: pd.DataFrame) -> pd.DataFrame:
    """Failures on rows that carry no injected defect (should be empty)."""
    labelled = set(zip(defects["table"], defects["row_index"].astype(int), strict=True))
    rowed = failures.dropna(subset=["row_index"])
    mask = [(t, int(r)) not in labelled for t, r in zip(rowed["table"], rowed["row_index"], strict=True)]
    return rowed[mask]
