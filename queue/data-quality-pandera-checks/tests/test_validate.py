import pandas as pd
import pytest

from dq_checks.rules import RULES, Severity
from dq_checks.validate import validate_tables


def _rules_for(result, table, row):
    f = result.failures
    return set(f.loc[(f["table"] == table) & (f["row_index"] == row), "rule"])


def test_clean_data_passes_every_rule(clean_raw, as_of):
    result = validate_tables(clean_raw, as_of)
    assert result.failures.empty, result.failures.head()
    assert result.gate_passed("warning")
    assert all(len(result.quarantine[t]) == 0 for t in result.quarantine)


def test_every_reported_rule_is_registered(dirty_dataset, as_of):
    result = validate_tables(dirty_dataset.tables(), as_of)
    assert set(result.failures["rule"]) <= set(RULES)


@pytest.mark.parametrize(
    ("table", "column", "value", "expected_rule"),
    [
        ("customers", "email", "no-at-sign.de", "email_format"),
        ("customers", "email", "Upper@Example.de", "email_lowercase"),
        ("customers", "country", "Deutschland", "valid_country"),
        ("customers", "segment", "vip", "valid_segment"),
        ("customers", "signup_date", "2030-01-01", "not_in_future"),
        ("customers", "customer_id", "-5", "positive_id"),
        ("orders", "status", "pending", "valid_status"),
        ("orders", "currency", "USD", "valid_currency"),
        ("orders", "order_ts", "not a date", "parse_error"),
        ("order_items", "sku", "SKU-1", "sku_format"),
        ("order_items", "quantity", "101", "quantity_range"),
        ("order_items", "unit_price", "0", "positive_price"),
    ],
)
def test_single_cell_defect_is_caught(clean_raw, as_of, table, column, value, expected_rule):
    clean_raw[table].loc[0, column] = value
    result = validate_tables(clean_raw, as_of)
    assert expected_rule in _rules_for(result, table, 0)


def test_unparseable_cell_is_not_double_reported(clean_raw, as_of):
    clean_raw["orders"].loc[0, "order_ts"] = "yesterday"
    result = validate_tables(clean_raw, as_of)
    assert _rules_for(result, "orders", 0) == {"parse_error"}


def test_frame_level_rule_reports_one_row_with_key(clean_raw, as_of):
    orders = clean_raw["orders"]
    idx = orders.index[orders["shipped_ts"].notna()][0]
    orders.loc[idx, "shipped_ts"] = "2000-01-01 00:00:00"
    result = validate_tables(clean_raw, as_of)
    hit = result.failures[result.failures["rule"] == "shipped_after_ordered"]
    assert len(hit) == 1
    assert hit["failure_case"].iloc[0] == f"order_id={orders.loc[idx, 'order_id']}"


def test_duplicate_composite_key(clean_raw, as_of):
    items = clean_raw["order_items"]
    clean_raw["order_items"] = pd.concat([items, items.iloc[[0]]], ignore_index=True)
    result = validate_tables(clean_raw, as_of)
    dup = result.failures[result.failures["rule"] == "unique_key"]
    assert sorted(dup["row_index"].tolist()) == [0, len(items)]


def test_warning_keeps_row_error_quarantines_it(clean_raw, as_of):
    clean_raw["customers"].loc[0, "email"] = "Upper@Example.de"  # warning
    clean_raw["customers"].loc[1, "country"] = "XX"  # error
    result = validate_tables(clean_raw, as_of)
    q = result.quarantine["customers"]
    assert q.index.tolist() == [1]
    assert q["dq_reasons"].iloc[0] == "valid_country"
    assert 0 in result.clean["customers"].index
    assert result.n_errors == 1 and result.n_warnings == 1
    assert not result.gate_passed("error")
    assert result.gate_passed("never")


def test_price_change_cascades_to_order_total(clean_raw, as_of):
    clean_raw["order_items"].loc[0, "unit_price"] = "4999"
    result = validate_tables(clean_raw, as_of)
    by_severity = result.failures.groupby("severity")["rule"].agg(set).to_dict()
    assert by_severity[Severity.WARNING] == {"price_plausible"}
    assert by_severity[Severity.ERROR] == {"total_matches_items"}  # parent order no longer adds up


def test_unknown_gate_mode_raises(clean_raw, as_of):
    result = validate_tables(clean_raw, as_of)
    with pytest.raises(ValueError):
        result.gate_passed("sometimes")


def test_dirty_dataset_quarantine_sizes_add_up(dirty_dataset, as_of):
    tables = dirty_dataset.tables()
    result = validate_tables(tables, as_of)
    for name, df in tables.items():
        assert len(result.clean[name]) + len(result.quarantine[name]) == len(df)
    assert result.n_errors > 0
