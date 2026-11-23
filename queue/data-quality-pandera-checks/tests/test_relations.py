import pandas as pd

from dq_checks.relations import check_foreign_key, check_order_after_signup, check_order_totals


def test_foreign_key_ignores_nulls_and_flags_orphans():
    parent = pd.DataFrame({"customer_id": pd.array([1, 2], dtype="Int64")})
    child = pd.DataFrame({"customer_id": pd.array([1, 3, None], dtype="Int64")})
    out = check_foreign_key(child, parent, child_table="orders", column="customer_id", rule="fk")
    assert out["row_index"].tolist() == [1]
    assert out["failure_case"].tolist() == [3]


def test_order_totals_with_tolerance():
    orders = pd.DataFrame(
        {"order_id": pd.array([1, 2, 3], dtype="Int64"), "total_amount": [20.0, 10.005, 5.0]}
    )
    items = pd.DataFrame(
        {
            "order_id": pd.array([1, 1, 2], dtype="Int64"),
            "quantity": pd.array([2, 1, 1], dtype="Int64"),
            "unit_price": [5.0, 10.0, 10.0],
        }
    )
    out = check_order_totals(orders, items)
    # order 1 matches, order 2 within 0.01, order 3 has no items but a total of 5
    assert out["row_index"].tolist() == [2]
    assert out["failure_case"].iloc[0] == "5.0 vs items 0.0"


def test_order_after_signup():
    customers = pd.DataFrame(
        {
            "customer_id": pd.array([1, 2], dtype="Int64"),
            "signup_date": pd.to_datetime(["2024-01-10", "2024-01-01"]),
        }
    )
    orders = pd.DataFrame(
        {
            "customer_id": pd.array([1, 2, 9], dtype="Int64"),
            "order_ts": pd.to_datetime(["2024-01-05", "2024-01-05", "2020-01-01"]),
        }
    )
    out = check_order_after_signup(orders, customers)
    assert out["row_index"].tolist() == [0]
