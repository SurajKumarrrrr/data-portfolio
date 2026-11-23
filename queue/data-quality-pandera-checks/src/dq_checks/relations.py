"""Cross-table checks that a single-table pandera schema cannot express.

Each function takes typed frames and returns failures in the shared long format
(table, rule, column, row_index, failure_case).
"""

from __future__ import annotations

import pandas as pd

from dq_checks.parsing import FAILURE_COLUMNS

TOTAL_TOLERANCE = 0.01


def _to_failures(table: str, rule: str, column: str, values: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "table": table,
            "rule": rule,
            "column": column,
            "row_index": values.index.to_list(),
            "failure_case": values.astype("object").to_list(),
        },
        columns=FAILURE_COLUMNS,
    )


def check_foreign_key(
    child: pd.DataFrame,
    parent: pd.DataFrame,
    *,
    child_table: str,
    column: str,
    rule: str,
) -> pd.DataFrame:
    """Rows of ``child`` whose ``column`` is not null and not present in ``parent``."""
    known = set(parent[column].dropna().to_list())
    values = child[column]
    orphan = values.notna() & ~values.isin(known)
    return _to_failures(child_table, rule, column, values[orphan])


def check_order_totals(orders: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    """Orders whose total_amount differs from sum(quantity * unit_price) of their items.

    Orders without any line items are also flagged (their expected total is 0 only
    if total_amount is 0).
    """
    line_value = (items["quantity"].astype("float64") * items["unit_price"]).round(2)
    expected = line_value.groupby(items["order_id"]).sum()
    exp = orders["order_id"].map(expected).fillna(0.0).astype("float64")
    diff = (orders["total_amount"] - exp).abs()
    comparable = orders["total_amount"].notna() & orders["order_id"].notna()
    bad = comparable & (diff > TOTAL_TOLERANCE)
    cases = (
        orders.loc[bad, "total_amount"].round(2).astype(str) + " vs items " + exp[bad].round(2).astype(str)
    )
    return _to_failures("orders", "total_matches_items", "total_amount", cases)


def check_order_after_signup(orders: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Orders placed before the customer's signup date (soft rule)."""
    signup = customers.drop_duplicates("customer_id").set_index("customer_id")["signup_date"]
    signup_for_order = orders["customer_id"].map(signup)
    bad = signup_for_order.notna() & orders["order_ts"].notna() & (orders["order_ts"] < signup_for_order)
    return _to_failures("orders", "order_after_signup", "order_ts", orders.loc[bad, "order_ts"])


def check_relations(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    customers, orders, items = tables["customers"], tables["orders"], tables["order_items"]
    parts = [
        check_foreign_key(
            orders, customers, child_table="orders", column="customer_id", rule="fk_customer_exists"
        ),
        check_foreign_key(
            items, orders, child_table="order_items", column="order_id", rule="fk_order_exists"
        ),
        check_order_totals(orders, items),
        check_order_after_signup(orders, customers),
    ]
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=FAILURE_COLUMNS)
