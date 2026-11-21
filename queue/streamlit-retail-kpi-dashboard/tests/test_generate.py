import pandas as pd

from retail_kpi.generate import GeneratorConfig, ensure_data, generate

SMALL = GeneratorConfig(start="2025-01-01", end="2025-03-31", base_orders_per_day=20, seed=7)


def test_same_seed_gives_identical_data():
    a, b = generate(SMALL), generate(SMALL)
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


def test_different_seed_changes_data():
    a = generate(SMALL)
    b = generate(GeneratorConfig(**{**SMALL.__dict__, "seed": 8}))
    assert not a["orders"].equals(b["orders"])


def test_keys_unique_and_referentially_intact():
    t = generate(SMALL)
    assert t["orders"]["order_id"].is_unique
    assert t["order_items"]["line_id"].is_unique
    assert not t["order_items"].duplicated(["order_id", "product_id"]).any()
    assert set(t["order_items"]["order_id"]) <= set(t["orders"]["order_id"])
    assert set(t["order_items"]["product_id"]) <= set(t["products"]["product_id"])
    assert set(t["orders"]["store_id"]) <= set(t["stores"]["store_id"])


def test_value_ranges():
    t = generate(SMALL)
    items, products = t["order_items"], t["products"]
    assert (items["quantity"] >= 1).all()
    assert items["discount"].between(0, 0.2).all()
    assert (products["unit_cost"] < products["unit_price"] * 1.0).all()
    dates = pd.to_datetime(t["orders"]["order_date"])
    assert dates.min() >= pd.Timestamp("2025-01-01")
    assert dates.max() <= pd.Timestamp("2025-03-31")


def test_physical_stores_closed_on_sunday():
    t = generate(SMALL)
    orders = t["orders"]
    sunday = pd.to_datetime(orders["order_date"]).dt.weekday == 6
    assert set(orders.loc[sunday, "channel"]) == {"online"}


def test_ensure_data_writes_once(tmp_path):
    ensure_data(tmp_path, SMALL)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["order_items.parquet", "orders.parquet", "products.parquet", "stores.parquet"]
    mtime = (tmp_path / "orders.parquet").stat().st_mtime_ns
    ensure_data(tmp_path, SMALL)
    assert (tmp_path / "orders.parquet").stat().st_mtime_ns == mtime
