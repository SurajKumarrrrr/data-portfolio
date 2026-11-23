"""Table contracts for the e-commerce dataset and their translation to pandera schemas.

A contract is a small, declarative description of a table: columns, logical types,
nullability, the primary key and named checks. ``to_pandera`` turns it into a
``pandera.DataFrameSchema`` so pandera does the heavy lifting (lazy validation,
failure-case collection) while rule names stay under our control.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
import pandera.pandas as pa

from dq_checks.rules import RULES

LogicalType = Literal["int", "float", "str", "datetime"]

PANDAS_DTYPES: dict[str, str] = {
    "int": "Int64",
    "float": "float64",
    "str": "str",
    "datetime": "datetime64[ns]",
}

ALLOWED_COUNTRIES = ("DE", "AT", "CH", "FR", "NL", "BE", "LU", "PL", "DK", "IT", "ES")
ORDER_STATUSES = ("placed", "shipped", "delivered", "cancelled", "returned")
SHIPPED_STATUSES = ("shipped", "delivered", "returned")
EMAIL_RE = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
SKU_RE = r"^SKU-\d{5}$"
PRICE_WARN_THRESHOLD = 2000.0


def rule_check(name: str, fn: Callable[..., pd.Series | bool]) -> pa.Check:
    """Build a pandera Check whose name is a rule from the catalogue."""
    if name not in RULES:
        raise KeyError(f"unknown rule {name!r}; register it in rules.py first")
    return pa.Check(fn, name=name)


@dataclass(frozen=True)
class ColumnSpec:
    type: LogicalType
    nullable: bool = False
    checks: tuple[pa.Check, ...] = ()


@dataclass(frozen=True)
class TableContract:
    name: str
    key: tuple[str, ...]
    columns: dict[str, ColumnSpec]
    frame_checks: tuple[pa.Check, ...] = field(default_factory=tuple)

    def to_pandera(self) -> pa.DataFrameSchema:
        cols = {
            col: pa.Column(
                PANDAS_DTYPES[spec.type],
                checks=list(spec.checks),
                nullable=spec.nullable,
            )
            for col, spec in self.columns.items()
        }
        key = list(self.key)
        checks = [rule_check("unique_key", lambda df: ~df.duplicated(subset=key, keep=False))]
        checks.extend(self.frame_checks)
        return pa.DataFrameSchema(cols, checks=checks, name=self.name, strict=False)


def build_contracts(as_of: pd.Timestamp) -> dict[str, TableContract]:
    """Contracts for customers, orders and order_items.

    ``as_of`` is the logical load date; timestamps after it are rejected. Passing it
    in (instead of using ``now()``) keeps validation deterministic and testable.
    """
    as_of = pd.Timestamp(as_of)
    not_future = rule_check("not_in_future", lambda s: s <= as_of)

    customers = TableContract(
        name="customers",
        key=("customer_id",),
        columns={
            "customer_id": ColumnSpec("int", checks=(rule_check("positive_id", lambda s: s > 0),)),
            "email": ColumnSpec(
                "str",
                checks=(
                    rule_check("email_format", lambda s: s.str.fullmatch(EMAIL_RE)),
                    rule_check("email_lowercase", lambda s: s == s.str.lower()),
                ),
            ),
            "country": ColumnSpec(
                "str", checks=(rule_check("valid_country", lambda s: s.isin(ALLOWED_COUNTRIES)),)
            ),
            "segment": ColumnSpec(
                "str",
                checks=(rule_check("valid_segment", lambda s: s.isin(("consumer", "business"))),),
            ),
            "signup_date": ColumnSpec("datetime", checks=(not_future,)),
        },
    )

    def shipped_after_ordered(df: pd.DataFrame) -> pd.Series:
        unknown = df["shipped_ts"].isna() | df["order_ts"].isna()  # nulls are other rules' job
        return unknown | (df["shipped_ts"] >= df["order_ts"])

    def delivered_has_ship_ts(df: pd.DataFrame) -> pd.Series:
        return ~df["status"].isin(SHIPPED_STATUSES) | df["shipped_ts"].notna()

    orders = TableContract(
        name="orders",
        key=("order_id",),
        columns={
            "order_id": ColumnSpec("int", checks=(rule_check("positive_id", lambda s: s > 0),)),
            "customer_id": ColumnSpec("int"),
            "order_ts": ColumnSpec("datetime", checks=(not_future,)),
            "status": ColumnSpec(
                "str", checks=(rule_check("valid_status", lambda s: s.isin(ORDER_STATUSES)),)
            ),
            "currency": ColumnSpec(
                "str", checks=(rule_check("valid_currency", lambda s: s.isin(("EUR", "CHF"))),)
            ),
            "total_amount": ColumnSpec(
                "float", checks=(rule_check("non_negative_amount", lambda s: s >= 0),)
            ),
            "shipped_ts": ColumnSpec("datetime", nullable=True, checks=(not_future,)),
        },
        frame_checks=(
            rule_check("shipped_after_ordered", shipped_after_ordered),
            rule_check("delivered_has_ship_ts", delivered_has_ship_ts),
        ),
    )

    order_items = TableContract(
        name="order_items",
        key=("order_id", "line_no"),
        columns={
            "order_id": ColumnSpec("int"),
            "line_no": ColumnSpec("int", checks=(rule_check("positive_id", lambda s: s > 0),)),
            "sku": ColumnSpec("str", checks=(rule_check("sku_format", lambda s: s.str.fullmatch(SKU_RE)),)),
            "quantity": ColumnSpec(
                "int", checks=(rule_check("quantity_range", lambda s: s.between(1, 100)),)
            ),
            "unit_price": ColumnSpec(
                "float",
                checks=(
                    rule_check("positive_price", lambda s: s > 0),
                    rule_check("price_plausible", lambda s: s <= PRICE_WARN_THRESHOLD),
                ),
            ),
        },
    )

    return {c.name: c for c in (customers, orders, order_items)}
