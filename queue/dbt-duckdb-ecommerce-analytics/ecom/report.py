"""Query the finished marts and print a compact business summary."""

from __future__ import annotations

from pathlib import Path

import duckdb

QUERIES: dict[str, str] = {
    "Headline KPIs": """
        select
            count(*)                                        as orders,
            count(*) filter (where is_revenue_order)        as revenue_orders,
            round(sum(net_revenue), 2)                      as net_revenue_eur,
            round(sum(net_revenue) / nullif(count(*) filter (where is_revenue_order), 0), 2)
                                                            as avg_order_value_eur,
            round(100.0 * avg(case when status = 'returned' then 1 else 0 end), 2)
                                                            as return_rate_pct,
            round(100.0 * avg(case when status = 'cancelled' then 1 else 0 end), 2)
                                                            as cancel_rate_pct
        from main_marts.fct_orders
    """,
    "Revenue by year": """
        select year(month_start) as year, sum(orders) as orders,
               round(sum(net_revenue), 2) as net_revenue_eur
        from main_marts.mart_monthly_revenue group by 1 order by 1
    """,
    "Top months by net revenue": """
        select strftime(month_start, '%Y-%m') as month, orders, net_revenue, avg_order_value,
               new_customers
        from main_marts.mart_monthly_revenue order by net_revenue desc limit 3
    """,
    "Category performance": """
        select category, units_sold, net_revenue, gross_margin, gross_margin_pct, return_rate_pct
        from main_marts.mart_category_performance order by net_revenue desc
    """,
    "Customer segments": """
        select customer_segment, count(*) as customers,
               round(sum(lifetime_net_revenue), 2) as net_revenue_eur,
               round(100.0 * sum(lifetime_net_revenue)
                     / sum(sum(lifetime_net_revenue)) over (), 1) as revenue_share_pct
        from main_marts.dim_customers group by 1 order by net_revenue_eur desc
    """,
    "Average cohort retention (months 1, 3, 6)": """
        select months_since_first_order,
               round(100.0 * sum(active_customers) / sum(cohort_size), 1) as retention_pct
        from main_marts.mart_cohort_retention
        where months_since_first_order in (1, 3, 6)
        group by 1 order by 1
    """,
}


def build_report(db_path: Path) -> dict[str, list[tuple]]:
    """Run all summary queries; return {title: rows (header first)}."""
    out: dict[str, list[tuple]] = {}
    # not read_only: dbt may still hold a connection in this process
    with duckdb.connect(str(db_path)) as con:
        for title, sql in QUERIES.items():
            cur = con.execute(sql)
            header = tuple(d[0] for d in cur.description)
            out[title] = [header, *cur.fetchall()]
    return out


def format_report(report: dict[str, list[tuple]]) -> str:
    lines: list[str] = []
    for title, rows in report.items():
        lines.append(f"\n## {title}")
        header, *body = rows
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for row in body:
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)
