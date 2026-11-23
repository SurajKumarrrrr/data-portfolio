"""Turn a ValidationResult into artefacts: markdown report, JSON summary, CSV files."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dq_checks.rules import RULES, Severity
from dq_checks.validate import TABLE_ORDER, ValidationResult


def rule_summary(result: ValidationResult) -> pd.DataFrame:
    """One row per (table, rule): failing cells, distinct failing rows, share of table."""
    f = result.failures
    if f.empty:
        return pd.DataFrame(columns=["table", "rule", "severity", "failures", "rows", "pct_rows", "examples"])
    grouped = f.groupby(["table", "rule", "severity"], sort=False)
    summary = grouped.agg(
        failures=("rule", "size"),
        rows=("row_index", "nunique"),
        examples=("failure_case", lambda s: ", ".join(dict.fromkeys(s.astype(str)))[:80]),
    ).reset_index()
    summary["pct_rows"] = [
        round(100 * r / result.row_counts[t], 2) if result.row_counts[t] else 0.0
        for t, r in zip(summary["table"], summary["rows"], strict=True)
    ]
    order = {Severity.ERROR.value: 0, Severity.WARNING.value: 1}
    summary = summary.sort_values(
        ["severity", "table", "rows"],
        key=lambda c: c.map(order) if c.name == "severity" else c,
        ascending=[True, True, False],
    )
    return summary[["table", "rule", "severity", "failures", "rows", "pct_rows", "examples"]].reset_index(
        drop=True
    )


def table_summary(result: ValidationResult) -> pd.DataFrame:
    rows = []
    for name in TABLE_ORDER:
        total = result.row_counts[name]
        quarantined = len(result.quarantine.get(name, []))
        warned = result.failures[
            (result.failures["table"] == name) & (result.failures["severity"] == Severity.WARNING)
        ]["row_index"].nunique()
        rows.append(
            {
                "table": name,
                "rows": total,
                "clean": total - quarantined,
                "quarantined": quarantined,
                "rows_with_warnings": int(warned),
                "pass_rate_pct": round(100 * (total - quarantined) / total, 2) if total else 100.0,
            }
        )
    return pd.DataFrame(rows)


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_none_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        cells = [str(v).replace("|", "\\|") for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(result: ValidationResult, fail_on: str = "error") -> str:
    status = "PASSED" if result.gate_passed(fail_on) else "FAILED"
    rules = rule_summary(result)
    if not rules.empty:
        rules["description"] = rules["rule"].map(lambda r: RULES[r].description if r in RULES else r)
    parts = [
        "# Data quality report\n",
        f"**Gate ({fail_on}): {status}** — {result.n_errors} error failures, "
        f"{result.n_warnings} warning failures.\n",
        "## Tables\n",
        _md_table(table_summary(result)),
        "## Rules that failed\n",
        _md_table(rules),
        "`row_index` in `failing_rows.csv` is the 0-based data row of the input file.\n",
    ]
    return "\n".join(parts)


def summary_dict(result: ValidationResult, fail_on: str = "error") -> dict[str, object]:
    return {
        "gate": {"fail_on": fail_on, "passed": result.gate_passed(fail_on)},
        "errors": result.n_errors,
        "warnings": result.n_warnings,
        "tables": table_summary(result).to_dict(orient="records"),
        "rules": rule_summary(result).drop(columns="examples").to_dict(orient="records"),
    }


def write_report(result: ValidationResult, out_dir: Path, fail_on: str = "error") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(render_markdown(result, fail_on), encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(summary_dict(result, fail_on), indent=2), encoding="utf-8"
    )
    result.failures.to_csv(out_dir / "failing_rows.csv", index=False)
    for sub, frames in (("clean", result.clean), ("quarantine", result.quarantine)):
        (out_dir / sub).mkdir(exist_ok=True)
        for name, df in frames.items():
            df.to_csv(out_dir / sub / f"{name}.csv", index=False)
