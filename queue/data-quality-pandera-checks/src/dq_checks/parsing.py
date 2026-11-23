"""Type parsing that turns raw (string-ish) frames into typed frames.

Pandera's own coercion stops at the first bad value per column and then produces
TypeErrors in every downstream check. Parsing first, with ``errors="coerce"``,
lets us report each unparseable cell as a ``parse_error`` and still run all other
checks on the remaining values.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dq_checks.contracts import PANDAS_DTYPES, TableContract

FAILURE_COLUMNS = ["table", "rule", "column", "row_index", "failure_case"]


@dataclass
class ParseResult:
    frame: pd.DataFrame
    failures: pd.DataFrame


def _parse_column(raw: pd.Series, logical_type: str) -> pd.Series:
    if logical_type == "int":
        num = pd.to_numeric(raw, errors="coerce")
        num = num.where(np.isclose(num.fillna(0) % 1, 0))  # 3.5 is not an int
        return num.astype("Int64")
    if logical_type == "float":
        return pd.to_numeric(raw, errors="coerce").astype("float64")
    if logical_type == "datetime":
        return pd.to_datetime(raw, errors="coerce", format="mixed").astype("datetime64[ns]")
    stripped = raw.astype("str").str.strip()
    return stripped.where(raw.notna() & (stripped != ""), None)


def parse_table(raw: pd.DataFrame, contract: TableContract) -> ParseResult:
    """Parse ``raw`` according to ``contract`` and collect structural failures."""
    failures: list[dict[str, object]] = []
    typed = pd.DataFrame(index=raw.index)

    for col in raw.columns:
        if col not in contract.columns:
            failures.append(_failure(contract.name, "unexpected_column", col, None, col))

    for col, spec in contract.columns.items():
        if col not in raw.columns:
            failures.append(_failure(contract.name, "missing_column", col, None, col))
            typed[col] = pd.Series(pd.NA, index=raw.index).astype(PANDAS_DTYPES[spec.type])
            continue
        parsed = _parse_column(raw[col], spec.type)
        bad = raw[col].notna() & (raw[col].astype("str").str.strip() != "") & parsed.isna()
        for idx in raw.index[bad]:
            failures.append(_failure(contract.name, "parse_error", col, idx, raw.at[idx, col]))
        typed[col] = parsed

    return ParseResult(typed, pd.DataFrame(failures, columns=FAILURE_COLUMNS))


def _failure(table: str, rule: str, column: str, row_index: object, case: object) -> dict[str, object]:
    return {
        "table": table,
        "rule": rule,
        "column": column,
        "row_index": row_index,
        "failure_case": case,
    }
