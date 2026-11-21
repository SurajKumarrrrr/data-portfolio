"""Deterministic synthetic retail data generator.

Produces four Parquet tables (stores, products, orders, order_items) for a fictional
German multi-channel retailer. All randomness comes from a single seeded NumPy
Generator, so the same seed always yields byte-identical data.

The data is SYNTHETIC. Seasonality, growth and return behaviour are modelling choices,
not real-world facts.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

STORES: list[tuple[str, str, str]] = [
    # (city, region, channel)
    ("Frankfurt", "West", "store"),
    ("Köln", "West", "store"),
    ("Düsseldorf", "West", "store"),
    ("Hamburg", "Nord", "store"),
    ("Bremen", "Nord", "store"),
    ("München", "Süd", "store"),
    ("Stuttgart", "Süd", "store"),
    ("Berlin", "Ost", "store"),
    ("Leipzig", "Ost", "store"),
    ("Online", "Online", "online"),
]

# category -> (number of products, price range in EUR, cost ratio, return probability)
CATEGORIES: dict[str, tuple[int, tuple[float, float], float, float]] = {
    "Electronics": (12, (49.0, 899.0), 0.78, 0.06),
    "Home & Kitchen": (14, (9.0, 249.0), 0.58, 0.04),
    "Fashion": (16, (14.0, 179.0), 0.45, 0.14),
    "Sports": (10, (12.0, 299.0), 0.55, 0.05),
    "Beauty": (10, (4.0, 89.0), 0.40, 0.02),
    "Toys": (8, (7.0, 129.0), 0.52, 0.03),
}

# Relative weight of December etc. (index 0 = January)
MONTH_SEASONALITY = np.array([0.82, 0.78, 0.90, 0.93, 0.97, 0.95, 0.92, 0.94, 1.00, 1.05, 1.28, 1.62])
# Monday..Sunday; Sunday stores are closed in Germany, online keeps selling
WEEKDAY_STORE = np.array([0.85, 0.88, 0.92, 0.98, 1.18, 1.45, 0.0])
WEEKDAY_ONLINE = np.array([1.05, 1.00, 0.97, 0.95, 0.92, 0.95, 1.20])


@dataclass(frozen=True)
class GeneratorConfig:
    start: str = "2024-01-01"
    end: str = "2025-12-31"
    base_orders_per_day: float = 60.0
    yearly_growth: float = 0.12
    n_customers: int = 9_000
    seed: int = 42


def make_stores() -> pd.DataFrame:
    rows = [
        {
            "store_id": i + 1,
            "store_name": f"{city} {'Webshop' if channel == 'online' else 'Store'}",
            "city": city,
            "region": region,
            "channel": channel,
        }
        for i, (city, region, channel) in enumerate(STORES)
    ]
    return pd.DataFrame(rows)


def make_products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    pid = 1
    for category, (n, (lo, hi), cost_ratio, _) in CATEGORIES.items():
        # log-uniform prices: many cheap items, a few expensive ones
        prices = np.exp(rng.uniform(np.log(lo), np.log(hi), size=n))
        for k, price in enumerate(prices, start=1):
            unit_price = round(float(price), 2)
            cost = unit_price * cost_ratio * rng.uniform(0.9, 1.1)
            rows.append(
                {
                    "product_id": pid,
                    "product_name": f"{category} Item {k:02d}",
                    "category": category,
                    "unit_price": unit_price,
                    "unit_cost": round(float(cost), 2),
                }
            )
            pid += 1
    return pd.DataFrame(rows)


def make_orders(cfg: GeneratorConfig, rng: np.random.Generator, stores: pd.DataFrame) -> pd.DataFrame:
    days = pd.date_range(cfg.start, cfg.end, freq="D")
    t_years = (days - days[0]).days.to_numpy() / 365.25
    trend = (1 + cfg.yearly_growth) ** t_years
    month_w = MONTH_SEASONALITY[days.month.to_numpy() - 1]

    store_ids = stores["store_id"].to_numpy()
    is_online = (stores["channel"] == "online").to_numpy()
    # store size: online is the biggest single "store"
    size = np.where(is_online, 3.0, rng.uniform(0.7, 1.3, size=len(stores)))
    size = size / size.sum()

    frames = []
    for s_idx, store_id in enumerate(store_ids):
        wd = WEEKDAY_ONLINE if is_online[s_idx] else WEEKDAY_STORE
        lam = cfg.base_orders_per_day * size[s_idx] * trend * month_w * wd[days.weekday.to_numpy()]
        counts = rng.poisson(lam)
        frames.append(
            pd.DataFrame(
                {
                    "order_date": np.repeat(days.to_numpy(), counts),
                    "store_id": store_id,
                    "channel": "online" if is_online[s_idx] else "store",
                }
            )
        )
    orders = pd.concat(frames, ignore_index=True).sort_values(["order_date", "store_id"], kind="stable")
    orders = orders.reset_index(drop=True)
    orders.insert(0, "order_id", np.arange(1, len(orders) + 1))
    # repeat customers: Zipf-like popularity over the customer base
    popularity = 1.0 / np.arange(1, cfg.n_customers + 1) ** 0.6
    orders["customer_id"] = rng.choice(
        cfg.n_customers, size=len(orders), p=popularity / popularity.sum()
    ) + 1
    orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.date
    return orders[["order_id", "order_date", "store_id", "customer_id", "channel"]]


def make_order_items(
    rng: np.random.Generator, orders: pd.DataFrame, products: pd.DataFrame
) -> pd.DataFrame:
    n_lines = rng.geometric(0.55, size=len(orders))  # mean ~1.8 lines per order
    order_ids = np.repeat(orders["order_id"].to_numpy(), n_lines)
    is_online = np.repeat((orders["channel"] == "online").to_numpy(), n_lines)

    # cheaper products sell more often
    weights = 1.0 / np.sqrt(products["unit_price"].to_numpy())
    p_idx = rng.choice(len(products), size=len(order_ids), p=weights / weights.sum())
    prod = products.iloc[p_idx].reset_index(drop=True)

    quantity = rng.geometric(0.7, size=len(order_ids))
    discount = rng.choice([0.0, 0.05, 0.10, 0.20], size=len(order_ids), p=[0.72, 0.12, 0.10, 0.06])
    base_return = prod["category"].map({c: v[3] for c, v in CATEGORIES.items()}).to_numpy()
    # online orders are returned roughly twice as often (illustrative assumption)
    return_p = np.clip(base_return * np.where(is_online, 2.0, 1.0), 0, 1)
    returned = rng.random(len(order_ids)) < return_p

    items = pd.DataFrame(
        {
            "order_id": order_ids,
            "product_id": prod["product_id"].to_numpy(),
            "quantity": quantity,
            "unit_price": prod["unit_price"].to_numpy(),
            "discount": discount,
            "returned": returned,
        }
    )
    # an order cannot contain the same product twice: merge duplicates
    items = (
        items.groupby(["order_id", "product_id"], as_index=False, sort=True)
        .agg(
            quantity=("quantity", "sum"),
            unit_price=("unit_price", "first"),
            discount=("discount", "first"),
            returned=("returned", "first"),
        )
    )
    items.insert(0, "line_id", np.arange(1, len(items) + 1))
    return items


def generate(cfg: GeneratorConfig | None = None) -> dict[str, pd.DataFrame]:
    """Generate all tables in memory."""
    cfg = cfg or GeneratorConfig()
    rng = np.random.default_rng(cfg.seed)
    stores = make_stores()
    products = make_products(rng)
    orders = make_orders(cfg, rng, stores)
    items = make_order_items(rng, orders, products)
    return {"stores": stores, "products": products, "orders": orders, "order_items": items}


def write(tables: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)


def ensure_data(out_dir: Path, cfg: GeneratorConfig | None = None) -> Path:
    """Generate data into ``out_dir`` unless all tables already exist."""
    needed = ["stores", "products", "orders", "order_items"]
    if not all((out_dir / f"{n}.parquet").exists() for n in needed):
        write(generate(cfg), out_dir)
    return out_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic retail data")
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    tables = generate(GeneratorConfig(seed=args.seed))
    write(tables, args.out)
    for name, df in tables.items():
        print(f"{name:12s} {len(df):>8,d} rows")


if __name__ == "__main__":
    main()
