"""Shared fixtures: a tiny hand-built dataset with known KPI values."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from retail_kpi.db import connect


def write_tiny_dataset(path: Path) -> Path:
    """Two stores, two products, four orders across two months.

    Hand-computed for 2025-02 (orders 3 and 4):
      order 3 (West store): 2 x A @10, 10% discount -> 18.00, cost 2 x 6 = 12
      order 4 (online)    : 1 x B @50, returned     -> gross 50, net 0
                            1 x A @10               -> 10.00, cost 6
      net = 28, gross = 78, cost = 18, orders = 2, units (not returned) = 3
    """
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "store_id": [1, 2],
            "store_name": ["Frankfurt Store", "Online Webshop"],
            "city": ["Frankfurt", "Online"],
            "region": ["West", "Online"],
            "channel": ["store", "online"],
        }
    ).to_parquet(path / "stores.parquet")
    pd.DataFrame(
        {
            "product_id": [1, 2],
            "product_name": ["A", "B"],
            "category": ["Toys", "Fashion"],
            "unit_price": [10.0, 50.0],
            "unit_cost": [6.0, 20.0],
        }
    ).to_parquet(path / "products.parquet")
    pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4],
            "order_date": [date(2025, 1, 10), date(2025, 1, 20), date(2025, 2, 3), date(2025, 2, 9)],
            "store_id": [1, 2, 1, 2],
            "customer_id": [100, 101, 100, 102],
            "channel": ["store", "online", "store", "online"],
        }
    ).to_parquet(path / "orders.parquet")
    pd.DataFrame(
        {
            "line_id": [1, 2, 3, 4, 5],
            "order_id": [1, 2, 3, 4, 4],
            "product_id": [1, 2, 1, 2, 1],
            "quantity": [1, 1, 2, 1, 1],
            "unit_price": [10.0, 50.0, 10.0, 50.0, 10.0],
            "discount": [0.0, 0.0, 0.1, 0.0, 0.0],
            "returned": [False, False, False, True, False],
        }
    ).to_parquet(path / "order_items.parquet")
    return path


@pytest.fixture(scope="session")
def tiny_dir(tmp_path_factory) -> Path:
    return write_tiny_dataset(tmp_path_factory.mktemp("tiny"))


@pytest.fixture()
def con(tiny_dir):
    c = connect(tiny_dir)
    yield c
    c.close()
