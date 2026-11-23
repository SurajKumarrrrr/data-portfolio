import pandas as pd

from dq_checks.contracts import build_contracts
from dq_checks.generate import AS_OF
from dq_checks.parsing import parse_table


def _items(**overrides):
    base = {
        "order_id": ["1", "2", "3"],
        "line_no": ["1", "1", "1"],
        "sku": ["SKU-00001", "SKU-00002", "SKU-00003"],
        "quantity": ["1", "2", "3"],
        "unit_price": ["9.99", "1.50", "3"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_parse_types_and_reports_bad_cells():
    contract = build_contracts(AS_OF)["order_items"]
    res = parse_table(_items(quantity=["1", "two", "2.5"]), contract)
    assert str(res.frame["quantity"].dtype) == "Int64"
    assert res.frame["quantity"].isna().tolist() == [False, True, True]
    bad = res.failures
    assert bad["rule"].tolist() == ["parse_error", "parse_error"]
    assert bad["row_index"].tolist() == [1, 2]
    assert bad["failure_case"].tolist() == ["two", "2.5"]


def test_missing_values_are_not_parse_errors():
    contract = build_contracts(AS_OF)["order_items"]
    res = parse_table(_items(sku=["SKU-00001", None, "  "]), contract)
    assert res.failures.empty
    assert res.frame["sku"].isna().tolist() == [False, True, True]


def test_missing_and_unexpected_columns():
    contract = build_contracts(AS_OF)["order_items"]
    raw = _items().drop(columns="sku").assign(comment="x")
    res = parse_table(raw, contract)
    assert set(zip(res.failures["rule"], res.failures["column"], strict=True)) == {
        ("missing_column", "sku"),
        ("unexpected_column", "comment"),
    }
    assert "comment" not in res.frame.columns
    assert res.frame["sku"].isna().all()


def test_datetime_parsing():
    contract = build_contracts(AS_OF)["customers"]
    raw = pd.DataFrame(
        {
            "customer_id": ["1", "2"],
            "email": ["a@b.de", "c@d.de"],
            "country": ["DE", "AT"],
            "segment": ["consumer", "business"],
            "signup_date": ["2024-05-01", "2024-02-30"],
        }
    )
    res = parse_table(raw, contract)
    assert res.frame["signup_date"].iloc[0] == pd.Timestamp("2024-05-01")
    assert res.failures["row_index"].tolist() == [1]
