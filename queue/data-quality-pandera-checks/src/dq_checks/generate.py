"""Deterministic synthetic e-commerce data with optional, labelled defects.

The generator first produces a *clean* dataset that satisfies every contract, then
(optionally) injects defects of known types into known rows and writes a
``defects.csv`` manifest. The manifest is the ground truth used to measure how
many injected defects the validation layer catches.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from dq_checks.contracts import ALLOWED_COUNTRIES

AS_OF = pd.Timestamp("2026-01-01")
FIRST_NAMES = [
    "anna",
    "lukas",
    "mia",
    "leon",
    "emma",
    "paul",
    "sofia",
    "jonas",
    "lea",
    "finn",
    "priya",
    "arjun",
]
LAST_NAMES = [
    "mueller",
    "schmidt",
    "schneider",
    "fischer",
    "weber",
    "meyer",
    "wagner",
    "becker",
    "kumar",
    "rao",
]
DOMAINS = ["example.de", "mail.example.com", "shop-test.eu", "example.at"]

# defect type -> (table, rule expected to catch it)
DEFECT_TYPES: dict[str, tuple[str, str]] = {
    "null_email": ("customers", "not_nullable"),
    "malformed_email": ("customers", "email_format"),
    "uppercase_email": ("customers", "email_lowercase"),
    "invalid_country": ("customers", "valid_country"),
    "duplicate_customer_id": ("customers", "unique_key"),
    "future_signup": ("customers", "not_in_future"),
    "negative_total": ("orders", "non_negative_amount"),
    "unknown_status": ("orders", "valid_status"),
    "orphan_customer": ("orders", "fk_customer_exists"),
    "shipped_before_order": ("orders", "shipped_after_ordered"),
    "delivered_without_ship_ts": ("orders", "delivered_has_ship_ts"),
    "total_mismatch": ("orders", "total_matches_items"),
    "unparseable_ts": ("orders", "parse_error"),
    "order_before_signup": ("orders", "order_after_signup"),
    "zero_quantity": ("order_items", "quantity_range"),
    "malformed_sku": ("order_items", "sku_format"),
    "price_outlier": ("order_items", "price_plausible"),
    "orphan_order": ("order_items", "fk_order_exists"),
}


@dataclass
class Dataset:
    customers: pd.DataFrame
    orders: pd.DataFrame
    order_items: pd.DataFrame
    defects: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {"customers": self.customers, "orders": self.orders, "order_items": self.order_items}

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, df in self.tables().items():
            df.to_csv(out_dir / f"{name}.csv", index=False)
        self.defects.to_csv(out_dir / "defects.csv", index=False)


def generate_clean(n_customers: int = 500, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    ids = np.arange(1, n_customers + 1)
    first = rng.choice(FIRST_NAMES, n_customers)
    last = rng.choice(LAST_NAMES, n_customers)
    emails = [f"{fn}.{ln}{i}@{rng.choice(DOMAINS)}" for fn, ln, i in zip(first, last, ids, strict=True)]
    signup = AS_OF - pd.to_timedelta(rng.integers(30, 3 * 365, n_customers), unit="D")
    customers = pd.DataFrame(
        {
            "customer_id": ids,
            "email": emails,
            "country": rng.choice(ALLOWED_COUNTRIES, n_customers, p=_country_weights()),
            "segment": rng.choice(["consumer", "business"], n_customers, p=[0.85, 0.15]),
            "signup_date": signup.strftime("%Y-%m-%d"),
        }
    )

    orders_rows, item_rows = [], []
    order_id = 100_000
    for cid, sdate in zip(ids, signup, strict=True):
        for _ in range(rng.poisson(2.5)):
            order_id += 1
            span = max(int((AS_OF - sdate).total_seconds()) - 7 * 86400, 3600)
            ots = sdate + pd.Timedelta(seconds=int(rng.integers(0, span)))
            status = rng.choice(
                ["placed", "shipped", "delivered", "cancelled", "returned"], p=[0.08, 0.12, 0.68, 0.07, 0.05]
            )
            sts = (
                ots + pd.Timedelta(hours=int(rng.integers(4, 96)))
                if status in ("shipped", "delivered", "returned")
                else None
            )
            total = 0.0
            for line in range(1, int(rng.integers(1, 5)) + 1):
                qty = int(rng.integers(1, 4))
                price = round(float(rng.lognormal(3.2, 0.8)) + 1.0, 2)
                price = min(price, 1500.0)
                total += round(qty * price, 2)
                item_rows.append((order_id, line, f"SKU-{int(rng.integers(10000, 99999)):05d}", qty, price))
            orders_rows.append(
                (
                    order_id,
                    int(cid),
                    ots,
                    status,
                    rng.choice(["EUR", "CHF"], p=[0.93, 0.07]),
                    round(total, 2),
                    sts,
                )
            )

    orders = pd.DataFrame(
        orders_rows,
        columns=["order_id", "customer_id", "order_ts", "status", "currency", "total_amount", "shipped_ts"],
    )
    for col in ("order_ts", "shipped_ts"):
        orders[col] = pd.to_datetime(orders[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
    items = pd.DataFrame(item_rows, columns=["order_id", "line_no", "sku", "quantity", "unit_price"])
    return customers, orders, items


def _country_weights() -> list[float]:
    w = np.array([60, 10, 8, 4, 4, 3, 1, 4, 2, 2, 2], dtype=float)
    return list(w / w.sum())


def inject_defects(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    items: pd.DataFrame,
    per_type: int = 3,
    seed: int = 7,
) -> Dataset:
    """Inject ``per_type`` defects of every type into disjoint rows.

    Rows are drawn without replacement per table so each defective row carries
    exactly one defect type, which makes detection measurable per type.
    """
    rng = np.random.default_rng(seed)
    customers, orders, items = customers.copy(), orders.copy(), items.copy()
    manifest: list[tuple[str, int, str, str]] = []

    def pick(df: pd.DataFrame, n: int, exclude: set[int]) -> list[int]:
        pool = np.setdiff1d(df.index.to_numpy(), np.fromiter(exclude, dtype=int, count=len(exclude)))
        chosen = rng.choice(pool, n, replace=False).tolist()
        exclude.update(chosen)
        return chosen

    used: dict[str, set[int]] = {"customers": set(), "orders": set(), "order_items": set()}

    def log(defect: str, idx: int) -> None:
        table, rule = DEFECT_TYPES[defect]
        manifest.append((table, int(idx), defect, rule))

    for i in pick(customers, per_type, used["customers"]):
        customers.at[i, "email"] = None
        log("null_email", i)
    for i in pick(customers, per_type, used["customers"]):
        customers.at[i, "email"] = customers.at[i, "email"].split("@")[0] + "@"
        log("malformed_email", i)
    for i in pick(customers, per_type, used["customers"]):
        customers.at[i, "email"] = customers.at[i, "email"].title()
        log("uppercase_email", i)
    for i in pick(customers, per_type, used["customers"]):
        customers.at[i, "country"] = rng.choice(["XX", "Germany", "de"])
        log("invalid_country", i)

    # A future signup on a customer with orders would also trigger the
    # order_after_signup warning, so only customers without orders get one.
    future_pool = customers.drop(index=list(used["customers"]))
    future_pool = future_pool[~future_pool["customer_id"].isin(orders["customer_id"])]
    for i in rng.choice(future_pool.index.to_numpy(), per_type, replace=False).tolist():
        used["customers"].add(i)
        customers.at[i, "signup_date"] = (AS_OF + pd.Timedelta(days=int(rng.integers(5, 200)))).strftime(
            "%Y-%m-%d"
        )
        log("future_signup", i)

    for i in pick(orders, per_type, used["orders"]):
        cid = orders.at[i, "customer_id"]
        signup = pd.Timestamp(customers.loc[customers["customer_id"] == cid, "signup_date"].iloc[0])
        new_ts = signup - pd.Timedelta(days=int(rng.integers(1, 30)))
        orders.at[i, "order_ts"] = new_ts.strftime("%Y-%m-%d %H:%M:%S")
        if pd.notna(orders.at[i, "shipped_ts"]):
            orders.at[i, "shipped_ts"] = (new_ts + pd.Timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        log("order_before_signup", i)

    for i in pick(orders, per_type, used["orders"]):
        orders.at[i, "total_amount"] = -abs(orders.at[i, "total_amount"])
        log("negative_total", i)
    for i in pick(orders, per_type, used["orders"]):
        orders.at[i, "status"] = rng.choice(["pending_payment", "SHIPPED", "lost"])
        log("unknown_status", i)
    for i in pick(orders, per_type, used["orders"]):
        orders.at[i, "customer_id"] = 900_000 + i
        log("orphan_customer", i)
    shipped = orders[orders["shipped_ts"].notna()]
    for i in pick(shipped, per_type, used["orders"]):
        ots = pd.Timestamp(orders.at[i, "order_ts"])
        orders.at[i, "shipped_ts"] = (ots - pd.Timedelta(hours=int(rng.integers(1, 48)))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        log("shipped_before_order", i)
    delivered = orders[orders["status"] == "delivered"]
    for i in pick(delivered, per_type, used["orders"]):
        orders.at[i, "shipped_ts"] = None
        log("delivered_without_ship_ts", i)
    for i in pick(orders, per_type, used["orders"]):
        orders.at[i, "total_amount"] = round(orders.at[i, "total_amount"] + float(rng.integers(5, 50)), 2)
        log("total_mismatch", i)
    for i in pick(orders, per_type, used["orders"]):
        orders.at[i, "order_ts"] = rng.choice(["31.02.2025 10:00", "yesterday", "2025-13-01"])
        log("unparseable_ts", i)

    # Item-level defects only on orders not otherwise touched, so changing a line
    # item does not create an unlabelled total mismatch on the parent order:
    # quantity/price defects are compensated by adjusting the parent's total.
    item_edits: tuple[tuple[str, str, object], ...] = (
        ("zero_quantity", "quantity", 0),
        ("malformed_sku", "sku", "sku-123"),
        ("price_outlier", "unit_price", 4999.0),
    )
    for defect, column, value in item_edits:
        clean_orders = orders.loc[~orders.index.isin(list(used["orders"])), "order_id"]
        pool = items[items["order_id"].isin(clean_orders)]
        for i in pick(pool, per_type, used["order_items"]):
            items.at[i, column] = value
            oid = items.at[i, "order_id"]
            o_idx = int(orders.index[orders["order_id"] == oid][0])
            used["orders"].add(o_idx)
            sub = items[items["order_id"] == oid]
            orders.at[o_idx, "total_amount"] = round(
                float((sub["quantity"] * sub["unit_price"]).round(2).sum()), 2
            )
            log(defect, i)

    # Appended rows: duplicate customer ids and orphan order items.
    dup_src = rng.choice(customers.index.difference(list(used["customers"])), per_type, replace=False)
    dups = customers.loc[dup_src].copy()
    dups["email"] = [f"dup{k}@example.de" for k in range(per_type)]
    start = len(customers)
    customers = pd.concat([customers, dups], ignore_index=True)
    for k, src in enumerate(dup_src):
        log("duplicate_customer_id", int(src))
        log("duplicate_customer_id", start + k)

    orphans = pd.DataFrame(
        {
            "order_id": [999_000 + k for k in range(per_type)],
            "line_no": 1,
            "sku": [f"SKU-{10000 + k:05d}" for k in range(per_type)],
            "quantity": 1,
            "unit_price": 9.99,
        }
    )
    start = len(items)
    items = pd.concat([items, orphans], ignore_index=True)
    for k in range(per_type):
        log("orphan_order", start + k)

    defects = pd.DataFrame(manifest, columns=["table", "row_index", "defect_type", "expected_rule"])
    return Dataset(customers, orders, items, defects)


def generate(n_customers: int = 500, seed: int = 42, defects_per_type: int = 3) -> Dataset:
    """Generate a dataset; ``defects_per_type=0`` returns clean data."""
    customers, orders, items = generate_clean(n_customers, seed)
    if defects_per_type <= 0:
        empty = pd.DataFrame(columns=["table", "row_index", "defect_type", "expected_rule"])
        return Dataset(customers, orders, items, empty)
    return inject_defects(customers, orders, items, per_type=defects_per_type, seed=seed + 1)
