"""Integration test: full ELT run with dbt build (models + all data tests) on a small dataset."""

from pathlib import Path

import duckdb
import pytest

from ecom.generate import GenConfig
from ecom.pipeline import run_pipeline
from ecom.report import QUERIES, format_report


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    base = tmp_path_factory.mktemp("e2e")
    db = base / "wh.duckdb"
    report = run_pipeline(base / "raw", db, GenConfig(n_customers=300, n_products=60, seed=11))
    return db, report


def test_dbt_build_produces_marts(built: tuple[Path, dict]) -> None:
    db, _ = built
    with duckdb.connect(str(db)) as con:
        tables = {r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = 'main_marts'"
        ).fetchall()}
    assert {"fct_orders", "fct_order_items", "dim_customers", "dim_products", "dim_date",
            "mart_monthly_revenue", "mart_cohort_retention",
            "mart_category_performance"} <= tables


def test_dedup_keeps_latest_status(built: tuple[Path, dict]) -> None:
    db, _ = built
    with duckdb.connect(str(db)) as con:
        mismatches = con.execute("""
            with latest as (
                select order_id, arg_max(status, _loaded_at) as status
                from raw.orders group by order_id
            )
            select count(*) from latest l
            join main_marts.fct_orders f on f.order_id = cast(l.order_id as integer)
            where f.status <> l.status
        """).fetchone()[0]
    assert mismatches == 0


def test_cohort_month_zero_is_full_retention(built: tuple[Path, dict]) -> None:
    db, _ = built
    with duckdb.connect(str(db)) as con:
        rates = con.execute(
            "select distinct retention_rate from main_marts.mart_cohort_retention "
            "where months_since_first_order = 0").fetchall()
    assert rates == [(1,)]


def test_segments_cover_all_customers(built: tuple[Path, dict]) -> None:
    db, _ = built
    with duckdb.connect(str(db)) as con:
        n_dim, n_raw = con.execute(
            "select (select count(*) from main_marts.dim_customers),"
            " (select count(*) from raw.customers)").fetchone()
    assert n_dim == n_raw == 300


def test_report_has_every_section(built: tuple[Path, dict]) -> None:
    _, report = built
    assert set(report) == set(QUERIES)
    text = format_report(report)
    assert "## Headline KPIs" in text and "| orders |" in text
