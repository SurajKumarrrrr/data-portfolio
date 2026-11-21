"""Command-line KPI report: the same queries the dashboard runs, printed as text.

Also times one full dashboard refresh (all queries) to show the latency users would see
on a cache miss.
"""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

from retail_kpi import kpis
from retail_kpi.db import connect
from retail_kpi.filters import Filters
from retail_kpi.generate import ensure_data


def dashboard_refresh(con, f: Filters) -> None:
    """Run every query a single dashboard render needs."""
    kpis.kpi_summary(con, f)
    kpis.kpi_deltas(con, f)
    kpis.revenue_trend(con, f, "week")
    kpis.top_products(con, f, 10)
    kpis.breakdown(con, f, "category")
    kpis.breakdown(con, f, "region")
    kpis.weekday_profile(con, f)


def time_refresh(con, f: Filters, repeats: int = 5) -> float:
    """Median wall-clock milliseconds for one uncached dashboard refresh."""
    timings = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        dashboard_refresh(con, f)
        timings.append((time.perf_counter() - t0) * 1000)
    return sorted(timings)[len(timings) // 2]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the retail KPI report")
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args(argv)

    con = connect(ensure_data(args.data))
    f25 = Filters(date(2025, 1, 1), date(2025, 12, 31))

    s = kpis.kpi_summary(con, f25)
    d = kpis.kpi_deltas(con, f25)
    print("== 2025 headline KPIs (vs 2024) ==")
    for key, value in s.to_dict().items():
        delta = d[key]
        unit = "pp" if key.endswith("_pct") else "%"
        delta_txt = "n/a" if delta is None else f"{delta:+.2f} {unit}"
        value_txt = f"{value:>14,d}" if isinstance(value, int) else f"{value:>14,.2f}"
        print(f"{key:18s} {value_txt}   {delta_txt}")

    print("\n== 2025 revenue by category ==")
    print(kpis.breakdown(con, f25, "category").round(2).to_string(index=False))
    print("\n== 2025 revenue by channel ==")
    print(kpis.breakdown(con, f25, "channel").round(2).to_string(index=False))
    print("\n== 2025 top 5 products ==")
    print(kpis.top_products(con, f25, 5).round(2).to_string(index=False))

    monthly = kpis.revenue_trend(con, f25, "month")
    peak = monthly.loc[monthly["net_revenue"].idxmax()]
    low = monthly.loc[monthly["net_revenue"].idxmin()]
    print(
        f"\nPeak month: {peak['period']:%b} ({peak['net_revenue']:,.0f} EUR), "
        f"lowest: {low['period']:%b} ({low['net_revenue']:,.0f} EUR)"
    )

    online_west = Filters(f25.start, f25.end, regions=("Online", "West"), categories=("Fashion",))
    n_rows = con.execute("SELECT count(*) FROM sales").fetchone()[0]
    print(f"\n== Query latency on {n_rows:,} sales lines (median of 5) ==")
    print(f"full refresh, no filters      : {time_refresh(con, f25):6.1f} ms")
    print(f"full refresh, 3 filters active: {time_refresh(con, online_west):6.1f} ms")


if __name__ == "__main__":
    main()
