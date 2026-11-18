"""Deterministic synthetic e-commerce source data.

Produces five raw CSV extracts that look like what an OLTP shop system plus a payment
provider would deliver: customers, products, orders, order_items and payments.

The data is intentionally a little messy so the dbt staging layer has real work to do:
- e-mails with mixed case and stray whitespace, country codes in mixed case
- prices stored as integer cents, timestamps as ISO strings
- ~3% of orders re-delivered by the extractor with a later ``_loaded_at`` and an
  updated status (the staging model must keep only the latest version)
- failed payment attempts before successful ones, refunds for returned orders
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

START = datetime(2024, 1, 1)
END = datetime(2025, 12, 31, 23, 59)

FIRST_NAMES = ["Anna", "Lukas", "Mia", "Leon", "Emma", "Finn", "Sofia", "Paul", "Lea", "Jonas",
               "Hannah", "Elias", "Lina", "Noah", "Marie", "Ben", "Clara", "Felix", "Ida", "Max"]
LAST_NAMES = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker",
              "Schulz", "Hoffmann", "Koch", "Richter", "Klein", "Wolf", "Neumann", "Schwarz"]
COUNTRIES = ["DE", "AT", "CH", "NL", "FR"]
COUNTRY_P = [0.70, 0.12, 0.08, 0.06, 0.04]
CATEGORIES = {
    "Electronics": (2500, 40000),
    "Home & Kitchen": (900, 12000),
    "Books": (700, 4500),
    "Fashion": (1500, 15000),
    "Sports": (1200, 20000),
    "Beauty": (500, 6000),
}
PAYMENT_METHODS = ["card", "paypal", "klarna", "sepa_debit"]
PAYMENT_P = [0.35, 0.30, 0.20, 0.15]
FREE_SHIPPING_THRESHOLD_CENTS = 5000
SHIPPING_FEE_CENTS = 499
# monthly demand multiplier (Jan..Dec) – Q4 peak
SEASONALITY = [0.85, 0.80, 0.90, 0.95, 1.0, 0.95, 0.90, 0.95, 1.0, 1.05, 1.45, 1.60]


@dataclass(frozen=True)
class GenConfig:
    n_customers: int = 5000
    n_products: int = 250
    seed: int = 42


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _messy_email(first: str, last: str, idx: int, rng: np.random.Generator) -> str:
    local = f"{first}.{last}{idx}".lower().replace("ü", "ue")
    email = f"{local}@example.com"
    r = rng.random()
    if r < 0.10:
        email = email.upper()
    elif r < 0.18:
        email = f"  {email} "
    return email


def generate_customers(cfg: GenConfig, rng: np.random.Generator) -> list[dict]:
    rows = []
    span_days = (END - START).days - 30
    for i in range(1, cfg.n_customers + 1):
        first = FIRST_NAMES[rng.integers(len(FIRST_NAMES))]
        last = LAST_NAMES[rng.integers(len(LAST_NAMES))]
        country = str(rng.choice(COUNTRIES, p=COUNTRY_P))
        if rng.random() < 0.07:
            country = country.lower()
        signup = START + timedelta(days=int(rng.integers(span_days)),
                                   seconds=int(rng.integers(86400)))
        rows.append({
            "customer_id": i,
            "first_name": first,
            "last_name": last,
            "email": _messy_email(first, last, i, rng),
            "country_code": country,
            "signup_at": _ts(signup),
            "marketing_opt_in": "true" if rng.random() < 0.4 else "false",
        })
    return rows


def generate_products(cfg: GenConfig, rng: np.random.Generator) -> list[dict]:
    rows = []
    cats = list(CATEGORIES)
    for i in range(1, cfg.n_products + 1):
        cat = cats[i % len(cats)]
        lo, hi = CATEGORIES[cat]
        price = int(round(rng.uniform(lo, hi), -1)) - 1  # x.x9 style prices
        margin = rng.uniform(0.25, 0.55)
        rows.append({
            "product_id": i,
            "sku": f"SKU-{cat[:3].upper()}-{i:05d}",
            "product_name": f"{cat} item {i}",
            "category": cat,
            "unit_price_cents": price,
            "unit_cost_cents": int(price * (1 - margin)),
            "is_active": "true" if rng.random() < 0.92 else "false",
        })
    return rows


def _order_status(order_ts: datetime, rng: np.random.Generator) -> str:
    age_days = (END - order_ts).days
    r = rng.random()
    if r < 0.05:
        return "cancelled"
    if age_days < 3:
        return "placed"
    if age_days < 7:
        return "shipped"
    if r < 0.12:
        return "returned"
    return "delivered"


def generate_orders(
    cfg: GenConfig,
    customers: list[dict],
    products: list[dict],
    rng: np.random.Generator,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Generate orders, order items and payments in one pass so totals stay consistent."""
    orders: list[dict] = []
    items: list[dict] = []
    payments: list[dict] = []
    # popularity is skewed: a few products sell a lot
    popularity = rng.zipf(1.6, size=len(products)).astype(float)
    popularity = np.minimum(popularity, 50)
    popularity /= popularity.sum()

    order_id = item_id = payment_id = 0
    for c in customers:
        if rng.random() < 0.18:  # registered but never ordered
            continue
        n_orders = int(rng.geometric(0.35))
        ts = datetime.fromisoformat(c["signup_at"]) + timedelta(hours=float(rng.uniform(0.5, 24 * 20)))
        for _ in range(n_orders):
            if ts > END:
                break
            # seasonality: thin out orders in weak months by retrying a later date
            if rng.random() > SEASONALITY[ts.month - 1] / max(SEASONALITY):
                ts += timedelta(days=float(rng.exponential(20)))
                if ts > END:
                    break
            order_id += 1
            status = _order_status(ts, rng)
            ship_country = c["country_code"].upper()

            gross = discount = 0
            for _ in range(int(rng.integers(1, 5))):
                item_id += 1
                p = products[int(rng.choice(len(products), p=popularity))]
                qty = int(rng.choice([1, 1, 1, 2, 2, 3]))
                line = p["unit_price_cents"] * qty
                disc = int(line * 0.10) if rng.random() < 0.15 else 0
                gross += line
                discount += disc
                items.append({
                    "order_item_id": item_id,
                    "order_id": order_id,
                    "product_id": p["product_id"],
                    "quantity": qty,
                    "unit_price_cents": p["unit_price_cents"],
                    "discount_cents": disc,
                })
            net_items = gross - discount
            shipping = 0 if net_items >= FREE_SHIPPING_THRESHOLD_CENTS else SHIPPING_FEE_CENTS
            total = net_items + shipping
            loaded = ts + timedelta(hours=1)
            orders.append({
                "order_id": order_id,
                "customer_id": c["customer_id"],
                "order_ts": _ts(ts),
                "status": status if status != "delivered" or rng.random() > 0.03 else "shipped",
                "shipping_country": ship_country,
                "shipping_cents": shipping,
                "_loaded_at": _ts(loaded),
            })
            # re-delivered record with later load time and the final status
            if orders[-1]["status"] != status or rng.random() < 0.02:
                dup = dict(orders[-1])
                dup["status"] = status
                dup["_loaded_at"] = _ts(loaded + timedelta(days=float(rng.uniform(1, 5))))
                orders.append(dup)

            method = str(rng.choice(PAYMENT_METHODS, p=PAYMENT_P))
            pay_ts = ts + timedelta(minutes=float(rng.uniform(1, 30)))
            if rng.random() < 0.06 or status == "cancelled":
                payment_id += 1
                payments.append({"payment_id": payment_id, "order_id": order_id,
                                 "payment_method": method, "status": "failed",
                                 "amount_cents": total, "created_at": _ts(pay_ts)})
                pay_ts += timedelta(minutes=5)
            if status != "cancelled":
                payment_id += 1
                payments.append({"payment_id": payment_id, "order_id": order_id,
                                 "payment_method": method, "status": "success",
                                 "amount_cents": total, "created_at": _ts(pay_ts)})
            if status == "returned":
                payment_id += 1
                payments.append({"payment_id": payment_id, "order_id": order_id,
                                 "payment_method": method, "status": "refunded",
                                 "amount_cents": total,
                                 "created_at": _ts(pay_ts + timedelta(days=float(rng.uniform(5, 20))))})
            ts += timedelta(days=float(rng.exponential(75)))
    return orders, items, payments


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate(out_dir: Path, cfg: GenConfig | None = None) -> dict[str, int]:
    """Write all raw CSVs to ``out_dir`` and return row counts per table."""
    cfg = cfg or GenConfig()
    rng = np.random.default_rng(cfg.seed)
    customers = generate_customers(cfg, rng)
    products = generate_products(cfg, rng)
    orders, items, payments = generate_orders(cfg, customers, products, rng)
    tables = {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": items,
        "payments": payments,
    }
    for name, rows in tables.items():
        _write_csv(out_dir / f"{name}.csv", rows)
    return {name: len(rows) for name, rows in tables.items()}
