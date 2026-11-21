"""KPI queries. Every function takes a DuckDB connection and a :class:`Filters` object."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import duckdb
import pandas as pd

from retail_kpi.filters import Filters

GRAINS = ("day", "week", "month")


@dataclass(frozen=True)
class KpiSummary:
    net_revenue: float
    gross_revenue: float
    orders: int
    customers: int
    units: int
    avg_order_value: float
    gross_margin_pct: float
    return_rate_pct: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def kpi_summary(con: duckdb.DuckDBPyConnection, f: Filters) -> KpiSummary:
    """Headline KPIs.

    * net revenue excludes returned lines; gross revenue includes them
    * AOV = net revenue / orders
    * gross margin = (net revenue - net cost) / net revenue
    * return rate = returned revenue / gross revenue (value-based, not line-based)
    """
    where, params = f.to_sql()
    row = con.execute(
        f"""
        SELECT
            coalesce(sum(net_revenue), 0)                    AS net_revenue,
            coalesce(sum(gross_revenue), 0)                  AS gross_revenue,
            count(DISTINCT order_id)                         AS orders,
            count(DISTINCT customer_id)                      AS customers,
            coalesce(sum(quantity) FILTER (NOT returned), 0) AS units,
            coalesce(sum(net_cost), 0)                       AS net_cost
        FROM sales {where}
        """,
        params,
    ).fetchone()
    net, gross, orders, customers, units, cost = row
    return KpiSummary(
        net_revenue=round(float(net), 2),
        gross_revenue=round(float(gross), 2),
        orders=int(orders),
        customers=int(customers),
        units=int(units),
        avg_order_value=round(float(net) / orders, 2) if orders else 0.0,
        gross_margin_pct=round(100 * (net - cost) / net, 2) if net else 0.0,
        return_rate_pct=round(100 * (gross - net) / gross, 2) if gross else 0.0,
    )


def pct_change(current: float, previous: float) -> float | None:
    """Relative change in percent; ``None`` when there is no baseline."""
    if not previous:
        return None
    return round(100 * (current - previous) / previous, 2)


def kpi_deltas(con: duckdb.DuckDBPyConnection, f: Filters) -> dict[str, float | None]:
    """Change of each KPI vs. the previous period of equal length.

    Percentage KPIs (margin, return rate) are compared in percentage points.
    """
    cur = kpi_summary(con, f).to_dict()
    prev = kpi_summary(con, f.previous_period()).to_dict()
    out: dict[str, float | None] = {}
    for key, value in cur.items():
        if key.endswith("_pct"):
            out[key] = round(value - prev[key], 2) if prev["orders"] else None
        else:
            out[key] = pct_change(value, prev[key])
    return out


def revenue_trend(con: duckdb.DuckDBPyConnection, f: Filters, grain: str = "week") -> pd.DataFrame:
    """Net revenue and orders per day/week/month."""
    if grain not in GRAINS:
        raise ValueError(f"grain must be one of {GRAINS}, got {grain!r}")
    where, params = f.to_sql()
    return con.execute(
        f"""
        SELECT date_trunc('{grain}', order_date)::DATE AS period,
               sum(net_revenue)          AS net_revenue,
               count(DISTINCT order_id)  AS orders
        FROM sales {where}
        GROUP BY ALL
        ORDER BY period
        """,
        params,
    ).df()


def top_products(con: duckdb.DuckDBPyConnection, f: Filters, n: int = 10) -> pd.DataFrame:
    """Best-selling products by net revenue, with margin and return rate."""
    if n < 1:
        raise ValueError("n must be positive")
    where, params = f.to_sql()
    return con.execute(
        f"""
        SELECT product_name, category,
               sum(net_revenue)                                      AS net_revenue,
               coalesce(sum(quantity) FILTER (NOT returned), 0)::BIGINT AS units,
               100 * (sum(net_revenue) - sum(net_cost))
                   / nullif(sum(net_revenue), 0)                     AS margin_pct,
               100 * (1 - sum(net_revenue) / nullif(sum(gross_revenue), 0)) AS return_rate_pct
        FROM sales {where}
        GROUP BY ALL
        ORDER BY net_revenue DESC, product_name
        LIMIT ?
        """,
        [*params, n],
    ).df()


def breakdown(con: duckdb.DuckDBPyConnection, f: Filters, dimension: str) -> pd.DataFrame:
    """Net revenue, share and margin per category / region / channel / city."""
    allowed = {"category", "region", "channel", "city"}
    if dimension not in allowed:
        raise ValueError(f"dimension must be one of {sorted(allowed)}")
    where, params = f.to_sql()
    return con.execute(
        f"""
        SELECT {dimension},
               sum(net_revenue)                                   AS net_revenue,
               100 * sum(net_revenue) / sum(sum(net_revenue)) OVER () AS share_pct,
               100 * (sum(net_revenue) - sum(net_cost))
                   / nullif(sum(net_revenue), 0)                  AS margin_pct,
               100 * (1 - sum(net_revenue) / nullif(sum(gross_revenue), 0)) AS return_rate_pct
        FROM sales {where}
        GROUP BY ALL
        ORDER BY net_revenue DESC
        """,
        params,
    ).df()


def weekday_profile(con: duckdb.DuckDBPyConnection, f: Filters) -> pd.DataFrame:
    """Average net revenue per weekday (ISO: 1 = Monday) and channel."""
    where, params = f.to_sql()
    return con.execute(
        f"""
        WITH daily AS (
            SELECT order_date, channel, sum(net_revenue) AS rev
            FROM sales {where}
            GROUP BY ALL
        )
        SELECT isodow(order_date) AS weekday, channel, avg(rev) AS avg_net_revenue
        FROM daily
        GROUP BY ALL
        ORDER BY weekday, channel
        """,
        params,
    ).df()
