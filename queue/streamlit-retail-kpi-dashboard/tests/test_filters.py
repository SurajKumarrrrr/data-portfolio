from datetime import date

import pytest

from retail_kpi.filters import Filters


def test_minimal_filter_only_has_date_clause():
    where, params = Filters(date(2025, 1, 1), date(2025, 1, 31)).to_sql()
    assert where == "WHERE order_date BETWEEN ? AND ?"
    assert params == [date(2025, 1, 1), date(2025, 1, 31)]


def test_multi_value_filters_use_placeholders():
    f = Filters(date(2025, 1, 1), date(2025, 1, 31), regions=("West", "Süd"), channels=("online",))
    where, params = f.to_sql()
    assert "region IN (?, ?)" in where
    assert "channel IN (?)" in where
    assert "category" not in where
    assert params[2:] == ["West", "Süd", "online"]


def test_injection_attempt_stays_a_parameter():
    evil = "West'); DROP TABLE orders; --"
    where, params = Filters(date(2025, 1, 1), date(2025, 1, 2), regions=(evil,)).to_sql()
    assert evil not in where
    assert evil in params


def test_previous_period_has_same_length_and_is_adjacent():
    f = Filters(date(2025, 3, 1), date(2025, 3, 31), categories=("Toys",))
    p = f.previous_period()
    assert p.n_days == f.n_days == 31
    assert p.end == date(2025, 2, 28)
    assert p.start == date(2025, 1, 29)
    assert p.categories == ("Toys",)


def test_filters_are_hashable_cache_keys():
    a = Filters(date(2025, 1, 1), date(2025, 1, 2), regions=("West",))
    b = Filters(date(2025, 1, 1), date(2025, 1, 2), regions=("West",))
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_start_after_end_rejected():
    with pytest.raises(ValueError):
        Filters(date(2025, 2, 1), date(2025, 1, 1))
