import csv
from collections import Counter, defaultdict
from pathlib import Path

from ecom.generate import (
    FREE_SHIPPING_THRESHOLD_CENTS,
    SHIPPING_FEE_CENTS,
    GenConfig,
    generate,
)


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_generation_is_deterministic(tmp_path: Path, small_cfg: GenConfig) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a, small_cfg)
    generate(b, small_cfg)
    for name in ("customers", "orders", "order_items", "payments"):
        assert (a / f"{name}.csv").read_bytes() == (b / f"{name}.csv").read_bytes()


def test_different_seed_changes_data(tmp_path: Path) -> None:
    generate(tmp_path / "a", GenConfig(n_customers=50, seed=1))
    generate(tmp_path / "b", GenConfig(n_customers=50, seed=2))
    assert (tmp_path / "a/orders.csv").read_bytes() != (tmp_path / "b/orders.csv").read_bytes()


def test_row_counts_returned(tmp_path: Path) -> None:
    counts = generate(tmp_path, GenConfig(n_customers=80, n_products=20))
    assert counts["customers"] == 80
    assert counts["products"] == 20
    assert counts["orders"] > 0 and counts["order_items"] >= counts["orders"] / 2


def test_orders_contain_redelivered_duplicates(raw_dir: Path) -> None:
    orders = _read(raw_dir / "orders.csv")
    dupes = [oid for oid, n in Counter(o["order_id"] for o in orders).items() if n > 1]
    assert dupes, "staging dedup logic needs duplicates to work on"


def test_successful_payment_equals_items_plus_shipping(raw_dir: Path) -> None:
    items = _read(raw_dir / "order_items.csv")
    payments = _read(raw_dir / "payments.csv")
    net = defaultdict(int)
    for i in items:
        net[i["order_id"]] += int(i["quantity"]) * int(i["unit_price_cents"]) - int(i["discount_cents"])
    for p in payments:
        if p["status"] != "success":
            continue
        n = net[p["order_id"]]
        shipping = 0 if n >= FREE_SHIPPING_THRESHOLD_CENTS else SHIPPING_FEE_CENTS
        assert int(p["amount_cents"]) == n + shipping


def test_cancelled_orders_have_no_successful_payment(raw_dir: Path) -> None:
    orders = _read(raw_dir / "orders.csv")
    latest = {}
    for o in sorted(orders, key=lambda r: r["_loaded_at"]):
        latest[o["order_id"]] = o["status"]
    cancelled = {oid for oid, s in latest.items() if s == "cancelled"}
    paid = {p["order_id"] for p in _read(raw_dir / "payments.csv") if p["status"] == "success"}
    assert cancelled and not (cancelled & paid)
