"""Airflow DAG: daily load of German day-ahead electricity prices into DuckDB.

extract (retries) -> validate (no retries, data problem) -> load (idempotent) -> check

Written for Airflow 3 (``airflow.sdk``). All logic lives in the ``energy_pipeline``
package, so this file only wires tasks together.
"""

from __future__ import annotations

from datetime import date, timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task

from energy_pipeline.load import connect
from energy_pipeline.pipeline import Settings, step_extract, step_load, step_validate
from energy_pipeline.sources import get_source
from energy_pipeline.timeutils import delivery_date_for_run

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}


def _resolve_delivery_date() -> date:
    """Use the ``delivery_date`` param for manual runs, else derive it from the schedule."""
    ctx = get_current_context()
    override = ctx["params"].get("delivery_date")
    if override:
        return date.fromisoformat(override)
    return delivery_date_for_run(ctx["data_interval_end"])


@dag(
    dag_id="energy_day_ahead_prices",
    description="Daily SMARD-style day-ahead price ingestion into DuckDB",
    schedule="30 13 * * *",  # after the ~12:45 CET auction publication
    start_date=pendulum.datetime(2025, 1, 1, tz="Europe/Berlin"),
    catchup=False,  # history is loaded with `airflow backfill create` or the CLI
    max_active_runs=1,  # DuckDB allows a single writer
    default_args=DEFAULT_ARGS,
    params={"delivery_date": None},
    tags=["energy", "duckdb", "smard"],
    doc_md=__doc__,
)
def energy_day_ahead_prices():
    @task
    def extract() -> str:
        settings = Settings.from_env()
        return step_extract(get_source(settings.source), _resolve_delivery_date(), settings)

    @task(retries=0)
    def validate(raw_file: str) -> str:
        step_validate(raw_file)
        return raw_file

    @task
    def load(raw_file: str) -> dict[str, int]:
        ctx = get_current_context()
        return step_load(raw_file, Settings.from_env(), run_id=ctx["run_id"])

    @task(retries=0)
    def check_loaded(counts: dict[str, int]) -> None:
        """Post-load assertion: the day exists exactly once with a full set of hours."""
        d = _resolve_delivery_date()
        con = connect(Settings.from_env().db_path)
        try:
            n_hours, rows = con.execute(
                "SELECT max(s.n_hours), count(h.ts_utc) FROM daily_price_stats s "
                "JOIN hourly_prices h USING (delivery_date) WHERE delivery_date = ?",
                [d],
            ).fetchone()
        finally:
            con.close()
        if not rows or n_hours != rows or rows != counts["inserted"]:
            raise ValueError(f"{d}: stats say {n_hours} hours, table has {rows}, loaded {counts}")

    check_loaded(load(validate(extract())))


energy_day_ahead_prices()
