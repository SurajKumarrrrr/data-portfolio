"""End-to-end analysis of a user-level experiment table."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .bayesian import beta_binomial, decide
from .cuped import cuped_adjust
from .frequentist import (
    TestResult,
    adjust_pvalues,
    bootstrap_diff_ci,
    srm_check,
    two_proportion_ztest,
    welch_ttest,
)


@dataclass(frozen=True)
class Metric:
    column: str
    kind: str  # "binary" or "continuous"
    role: str = "secondary"  # "primary", "secondary" or "guardrail"
    covariate: str | None = None  # pre-period column for CUPED


DEFAULT_METRICS = (
    Metric("converted", "binary", "primary"),
    Metric("add_to_cart", "binary", "secondary"),
    Metric("revenue", "continuous", "guardrail", covariate="pre_revenue"),
)


@dataclass
class ExperimentAnalysis:
    n_control: int
    n_treatment: int
    srm: dict
    results: list[TestResult]
    adjusted_p: dict[str, float]
    roles: dict[str, str]
    bayes: dict
    cuped: dict = field(default_factory=dict)
    bootstrap: dict = field(default_factory=dict)
    segments: list[dict] = field(default_factory=list)
    decision: str = ""


def _split(df: pd.DataFrame, col: str, variant_col: str) -> tuple[pd.Series, pd.Series]:
    return (df.loc[df[variant_col] == "control", col],
            df.loc[df[variant_col] == "treatment", col])


def _test_metric(df: pd.DataFrame, m: Metric, alpha: float, variant_col: str) -> TestResult:
    c, t = _split(df, m.column, variant_col)
    if m.kind == "binary":
        return two_proportion_ztest(int(c.sum()), len(c), int(t.sum()), len(t), alpha, m.column)
    return welch_ttest(c.to_numpy(), t.to_numpy(), alpha, m.column)


def make_decision(srm: dict, results: list[TestResult], adjusted_p: dict[str, float],
                  roles: dict[str, str], alpha: float) -> str:
    """Pre-registered decision rule: SRM gate, primary metric, guardrails."""
    if srm["srm_detected"]:
        return "INVALID: sample ratio mismatch - fix assignment before reading results"
    by_name = {r.metric: r for r in results}
    for name, role in roles.items():
        r = by_name[name]
        if role == "guardrail" and adjusted_p[name] < alpha and r.abs_diff < 0:
            return f"DO NOT SHIP: guardrail '{name}' degraded significantly"
    primary = next(n for n, role in roles.items() if role == "primary")
    p = by_name[primary]
    if adjusted_p[primary] < alpha:
        return "SHIP" if p.abs_diff > 0 else "DO NOT SHIP: primary metric got worse"
    return "INCONCLUSIVE: primary metric not significant - keep control or extend test"


def analyze_experiment(df: pd.DataFrame, metrics: tuple[Metric, ...] = DEFAULT_METRICS,
                       alpha: float = 0.05, variant_col: str = "variant",
                       segment_col: str | None = "device", seed: int = 0,
                       n_boot: int = 1000) -> ExperimentAnalysis:
    counts = df[variant_col].value_counts()
    n_c, n_t = int(counts.get("control", 0)), int(counts.get("treatment", 0))
    srm = srm_check([n_c, n_t], [0.5, 0.5])

    results = [_test_metric(df, m, alpha, variant_col) for m in metrics]
    adj = adjust_pvalues([r.p_value for r in results], "holm")
    adjusted_p = {r.metric: p for r, p in zip(results, adj, strict=True)}
    roles = {m.column: m.role for m in metrics}

    primary = next(m for m in metrics if m.role == "primary")
    c, t = _split(df, primary.column, variant_col)
    bayes_res = beta_binomial(int(c.sum()), len(c), int(t.sum()), len(t), seed=seed)
    bayes = {**bayes_res.to_dict(), "decision": decide(bayes_res)}

    cuped, boot = {}, {}
    for m in metrics:
        if m.kind != "continuous":
            continue
        c, t = _split(df, m.column, variant_col)
        boot[m.column] = bootstrap_diff_ci(c.to_numpy(), t.to_numpy(), n_boot, alpha, seed)
        if m.covariate:
            cr = cuped_adjust(df[m.column].to_numpy(), df[m.covariate].to_numpy())
            adj_df = df.assign(_adj=cr.adjusted)
            c_adj, t_adj = _split(adj_df, "_adj", variant_col)
            raw = next(r for r in results if r.metric == m.column)
            cup = welch_ttest(c_adj.to_numpy(), t_adj.to_numpy(), alpha, f"{m.column} (CUPED)")
            cuped[m.column] = {
                "theta": cr.theta, "correlation": cr.correlation,
                "variance_reduction": cr.variance_reduction,
                "raw": raw.to_dict(), "adjusted": cup.to_dict(),
                "ci_width_reduction": 1 - (cup.ci_high - cup.ci_low) / (raw.ci_high - raw.ci_low),
            }

    segments = []
    if segment_col:
        for seg, part in df.groupby(segment_col):
            r = _test_metric(part, primary, alpha, variant_col)
            segments.append({"segment": seg, "n": len(part), **r.to_dict()})

    decision = make_decision(srm, results, adjusted_p, roles, alpha)
    return ExperimentAnalysis(n_c, n_t, srm, results, adjusted_p, roles, bayes, cuped, boot,
                              segments, decision)
