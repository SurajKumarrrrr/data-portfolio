"""Streamlit retail KPI dashboard.

Run with ``streamlit run app.py``. Data is generated on first start if missing.
Set ``RETAIL_KPI_DATA_DIR`` to point at another folder of Parquet files.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from retail_kpi import kpis  # noqa: E402
from retail_kpi.db import connect, filter_options  # noqa: E402
from retail_kpi.filters import Filters  # noqa: E402
from retail_kpi.formatting import fmt_delta, fmt_eur  # noqa: E402
from retail_kpi.generate import ensure_data  # noqa: E402

DATA_DIR = Path(os.environ.get("RETAIL_KPI_DATA_DIR", Path(__file__).parent / "data"))
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

st.set_page_config(page_title="Retail KPI Dashboard", page_icon="📊", layout="wide")


@st.cache_resource(show_spinner="Preparing data…")
def get_connection():
    """One DuckDB connection per server process, shared across sessions."""
    return connect(ensure_data(DATA_DIR))


# Cached query wrappers: the Filters dataclass is frozen, so it hashes cleanly and every
# distinct filter combination is computed once, then served from cache for 10 minutes.
@st.cache_data(ttl=600)
def cached_summary(f: Filters) -> dict:
    return kpis.kpi_summary(get_connection().cursor(), f).to_dict()


@st.cache_data(ttl=600)
def cached_deltas(f: Filters) -> dict:
    return kpis.kpi_deltas(get_connection().cursor(), f)


@st.cache_data(ttl=600)
def cached_trend(f: Filters, grain: str) -> pd.DataFrame:
    return kpis.revenue_trend(get_connection().cursor(), f, grain)


@st.cache_data(ttl=600)
def cached_top(f: Filters, n: int) -> pd.DataFrame:
    return kpis.top_products(get_connection().cursor(), f, n)


@st.cache_data(ttl=600)
def cached_breakdown(f: Filters, dim: str) -> pd.DataFrame:
    return kpis.breakdown(get_connection().cursor(), f, dim)


@st.cache_data(ttl=600)
def cached_weekday(f: Filters) -> pd.DataFrame:
    return kpis.weekday_profile(get_connection().cursor(), f)


@st.cache_data
def cached_options() -> dict:
    return filter_options(get_connection().cursor())


def sidebar_filters(opts: dict) -> tuple[Filters, str]:
    st.sidebar.header("Filters")
    lo, hi = opts["date_range"]
    # default: the latest 365 days, so the KPI deltas compare with the year before
    default_start = max(lo, hi - timedelta(days=364))
    picked = st.sidebar.date_input("Date range", value=(default_start, hi), min_value=lo, max_value=hi)
    # while the user is picking, date_input briefly returns a single date
    start, end = (picked[0], picked[-1]) if isinstance(picked, tuple | list) else (picked, picked)
    regions = st.sidebar.multiselect("Region", opts["regions"])
    categories = st.sidebar.multiselect("Category", opts["categories"])
    channels = st.sidebar.multiselect("Channel", opts["channels"])
    grain = st.sidebar.radio("Trend granularity", ["day", "week", "month"], index=1, horizontal=True)
    st.sidebar.caption("Empty selection = all values. Data is synthetic.")
    f = Filters(start, end, tuple(regions), tuple(categories), tuple(channels))
    return f, grain


def kpi_row(f: Filters) -> None:
    s, d = cached_summary(f), cached_deltas(f)
    cols = st.columns(6)
    cols[0].metric("Net revenue", fmt_eur(s["net_revenue"]), fmt_delta(d["net_revenue"]))
    cols[1].metric("Orders", f"{s['orders']:,}", fmt_delta(d["orders"]))
    cols[2].metric("Avg order value", f"€{s['avg_order_value']:,.2f}", fmt_delta(d["avg_order_value"]))
    cols[3].metric("Customers", f"{s['customers']:,}", fmt_delta(d["customers"]))
    cols[4].metric(
        "Gross margin", f"{s['gross_margin_pct']:.1f}%", fmt_delta(d["gross_margin_pct"], "pp")
    )
    cols[5].metric(
        "Return rate",
        f"{s['return_rate_pct']:.1f}%",
        fmt_delta(d["return_rate_pct"], "pp"),
        delta_color="inverse",
    )
    st.caption(f"Deltas compare with the previous {f.n_days} days.")


def main() -> None:
    st.title("Retail KPI Dashboard")
    opts = cached_options()
    f, grain = sidebar_filters(opts)

    if cached_summary(f)["orders"] == 0:
        st.warning("No sales match the current filters.")
        return

    kpi_row(f)

    trend = cached_trend(f, grain)
    st.plotly_chart(
        px.line(trend, x="period", y="net_revenue", title=f"Net revenue per {grain}",
                labels={"period": "", "net_revenue": "Net revenue (€)"}),
        width="stretch",
    )
    st.caption("The first and last period can be partial if the date range cuts through them.")

    left, right = st.columns(2)
    cat = cached_breakdown(f, "category")
    left.plotly_chart(
        px.bar(cat, x="net_revenue", y="category", orientation="h", title="Revenue by category",
               hover_data={"share_pct": ":.1f", "margin_pct": ":.1f"},
               labels={"net_revenue": "Net revenue (€)", "category": ""})
        .update_yaxes(categoryorder="total ascending"),
        width="stretch",
    )
    reg = cached_breakdown(f, "region")
    right.plotly_chart(
        px.bar(reg, x="region", y="net_revenue", title="Revenue by region",
               labels={"net_revenue": "Net revenue (€)", "region": ""}),
        width="stretch",
    )

    left, right = st.columns(2)
    wd = cached_weekday(f).assign(weekday=lambda d: d["weekday"].map(lambda i: WEEKDAYS[i - 1]))
    left.plotly_chart(
        px.bar(wd, x="weekday", y="avg_net_revenue", color="channel", barmode="group",
               title="Average daily revenue by weekday",
               category_orders={"weekday": WEEKDAYS},
               labels={"avg_net_revenue": "Avg net revenue (€)", "weekday": ""}),
        width="stretch",
    )
    with right:
        st.subheader("Top 10 products")
        st.dataframe(
            cached_top(f, 10),
            hide_index=True,
            column_config={
                "product_name": "Product",
                "category": "Category",
                "units": "Units",
                "net_revenue": st.column_config.NumberColumn("Net revenue", format="€%.0f"),
                "margin_pct": st.column_config.NumberColumn("Margin %", format="%.1f"),
                "return_rate_pct": st.column_config.NumberColumn("Return %", format="%.1f"),
            },
        )


main()
