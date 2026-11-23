"""Orchestrates parsing, pandera schema validation and cross-table checks.

Output is a single long-format failures table plus a quarantine split:
rows with at least one ERROR failure are moved out, rows with only WARNINGs stay.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pandera.pandas as pa

from dq_checks.contracts import TableContract, build_contracts
from dq_checks.parsing import FAILURE_COLUMNS, parse_table
from dq_checks.relations import check_relations
from dq_checks.rules import Severity, severity_of

TABLE_ORDER = ("customers", "orders", "order_items")


@dataclass
class ValidationResult:
    failures: pd.DataFrame
    row_counts: dict[str, int]
    clean: dict[str, pd.DataFrame] = field(default_factory=dict)
    quarantine: dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def n_errors(self) -> int:
        return int((self.failures["severity"] == Severity.ERROR).sum())

    @property
    def n_warnings(self) -> int:
        return int((self.failures["severity"] == Severity.WARNING).sum())

    def gate_passed(self, fail_on: str = "error") -> bool:
        """CI gate: ``error`` fails on errors, ``warning`` on any failure, ``never`` never."""
        if fail_on == "never":
            return True
        if fail_on == "warning":
            return self.failures.empty
        if fail_on == "error":
            return self.n_errors == 0
        raise ValueError(f"fail_on must be error, warning or never, got {fail_on!r}")


def _schema_failures(typed: pd.DataFrame, contract: TableContract) -> pd.DataFrame:
    """Run the pandera schema lazily and normalise ``failure_cases``."""
    try:
        contract.to_pandera().validate(typed, lazy=True)
    except pa.errors.SchemaErrors as exc:
        fc = exc.failure_cases
    else:
        return pd.DataFrame(columns=FAILURE_COLUMNS)

    fc = fc.rename(columns={"check": "rule", "index": "row_index"})
    fc["table"] = contract.name
    frame_level = fc["schema_context"] == "DataFrameSchema"

    # Column-level failures: one row per failing cell.
    cell = fc.loc[~frame_level, FAILURE_COLUMNS]

    # Frame-level checks are reported once per column by pandera; collapse to one
    # failure per row and describe the row by its primary key instead.
    frame = fc.loc[frame_level & fc["row_index"].notna()].drop_duplicates(["rule", "row_index"]).copy()
    if not frame.empty:
        key = list(contract.key)
        frame["column"] = ",".join(key)
        frame["failure_case"] = [
            ", ".join(f"{k}={typed.at[idx, k]}" for k in key) for idx in frame["row_index"]
        ]
    return pd.concat([cell, frame[FAILURE_COLUMNS]], ignore_index=True)


def _drop_parse_followups(failures: pd.DataFrame) -> pd.DataFrame:
    """An unparseable cell becomes null; don't also report it as ``not_nullable``."""
    keys = ["table", "column", "row_index"]
    parse = failures.loc[failures["rule"] == "parse_error", keys].drop_duplicates()
    if parse.empty:
        return failures
    marked = failures.merge(parse.assign(_parsed=True), on=keys, how="left")
    followup = (marked["rule"] == "not_nullable") & marked["_parsed"].eq(True)
    return failures.loc[~followup.to_numpy()].reset_index(drop=True)


def validate_tables(raw_tables: dict[str, pd.DataFrame], as_of: pd.Timestamp | str) -> ValidationResult:
    """Validate the three tables and split each into clean and quarantined rows."""
    contracts = build_contracts(pd.Timestamp(as_of))
    typed: dict[str, pd.DataFrame] = {}
    parts: list[pd.DataFrame] = []

    for name in TABLE_ORDER:
        parsed = parse_table(raw_tables[name], contracts[name])
        typed[name] = parsed.frame
        parts.append(parsed.failures)
        parts.append(_schema_failures(parsed.frame, contracts[name]))
    parts.append(check_relations(typed))

    non_empty = [p for p in parts if not p.empty]
    failures = pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame(columns=FAILURE_COLUMNS)
    failures["row_index"] = pd.to_numeric(failures["row_index"], errors="coerce").astype("Int64")
    failures = _drop_parse_followups(failures)
    failures["failure_case"] = (
        failures["failure_case"]
        .astype("object")
        .map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    )
    failures["severity"] = failures["rule"].map(severity_of).astype("str")
    failures = failures.sort_values(["table", "rule", "row_index"], na_position="first", kind="stable")
    failures = failures.reset_index(drop=True)

    result = ValidationResult(failures, {n: len(raw_tables[n]) for n in TABLE_ORDER})
    for name in TABLE_ORDER:
        errs = failures[(failures["table"] == name) & (failures["severity"] == Severity.ERROR)]
        bad_rows = set(errs["row_index"].dropna().astype(int))
        raw = raw_tables[name]
        mask = raw.index.isin(sorted(bad_rows))
        reasons = (
            errs.dropna(subset=["row_index"])
            .groupby("row_index")["rule"]
            .agg(lambda r: ";".join(sorted(set(r))))
        )
        quarantined = raw.loc[mask].copy()
        quarantined["dq_reasons"] = reasons.reindex(quarantined.index).fillna("").to_numpy()
        result.clean[name] = raw.loc[~mask].copy()
        result.quarantine[name] = quarantined
    return result
