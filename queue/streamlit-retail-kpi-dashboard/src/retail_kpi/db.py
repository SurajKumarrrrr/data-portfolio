"""DuckDB connection setup: Parquet files are exposed as views, plus one wide `sales` view."""

from __future__ import annotations

from pathlib import Path

import duckdb

TABLES = ("stores", "products", "orders", "order_items")

SALES_VIEW = """
CREATE OR REPLACE VIEW sales AS
SELECT
    i.line_id,
    o.order_id,
    o.order_date,
    o.customer_id,
    o.channel,
    s.store_id,
    s.store_name,
    s.city,
    s.region,
    p.product_id,
    p.product_name,
    p.category,
    i.quantity,
    i.discount,
    i.returned,
    i.quantity * i.unit_price * (1 - i.discount)           AS gross_revenue,
    CASE WHEN i.returned THEN 0
         ELSE i.quantity * i.unit_price * (1 - i.discount) END AS net_revenue,
    CASE WHEN i.returned THEN 0
         ELSE i.quantity * p.unit_cost END                 AS net_cost
FROM order_items AS i
JOIN orders   AS o USING (order_id)
JOIN stores   AS s USING (store_id)
JOIN products AS p USING (product_id)
"""


def connect(data_dir: Path | str) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB database with views over the Parquet files in ``data_dir``.

    Views (not tables) keep start-up instant: DuckDB scans the Parquet files lazily and
    pushes filters down into the scan.
    """
    data_dir = Path(data_dir)
    con = duckdb.connect(":memory:")
    for name in TABLES:
        path = data_dir / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing table file: {path}")
        # Paths cannot be bound as parameters in DDL; escape single quotes instead.
        safe = str(path).replace("'", "''")
        con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{safe}')")
    con.execute(SALES_VIEW)
    return con


def filter_options(con: duckdb.DuckDBPyConnection) -> dict[str, list]:
    """Distinct values used to populate the dashboard's filter widgets."""
    min_d, max_d = con.execute("SELECT min(order_date), max(order_date) FROM orders").fetchone()

    def distinct(sql: str) -> list[str]:
        return [r[0] for r in con.execute(sql).fetchall()]

    return {
        "date_range": [min_d, max_d],
        "regions": distinct("SELECT DISTINCT region FROM stores ORDER BY region"),
        "categories": distinct("SELECT DISTINCT category FROM products ORDER BY category"),
        "channels": distinct("SELECT DISTINCT channel FROM stores ORDER BY channel"),
    }
