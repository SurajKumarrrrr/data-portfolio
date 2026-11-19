"""Load step: idempotent upsert of one delivery day into DuckDB + daily aggregates.

Idempotency strategy: *delete-then-insert per partition inside one transaction*.
The partition key is ``delivery_date``; re-running any day (retry, backfill, manual
clear in Airflow) replaces that day completely and never duplicates rows.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from energy_pipeline.transform import HourlyPrice

DDL = """
CREATE TABLE IF NOT EXISTS hourly_prices (
    delivery_date  DATE      NOT NULL,
    ts_utc         TIMESTAMP NOT NULL PRIMARY KEY,
    local_hour     SMALLINT  NOT NULL,
    price_eur_mwh  DOUBLE    NOT NULL,
    source         VARCHAR   NOT NULL,
    loaded_at      TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS daily_price_stats (
    delivery_date      DATE PRIMARY KEY,
    n_hours            SMALLINT NOT NULL,
    base_avg           DOUBLE   NOT NULL,
    peak_avg           DOUBLE,          -- NULL on weekends (EEX peak = Mon-Fri 08-20h)
    offpeak_avg        DOUBLE,
    min_price          DOUBLE   NOT NULL,
    max_price          DOUBLE   NOT NULL,
    intraday_spread    DOUBLE   NOT NULL,
    negative_hours     SMALLINT NOT NULL,
    cheapest_hour      SMALLINT NOT NULL,
    most_expensive_hour SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS load_audit (
    run_id         VARCHAR   NOT NULL,
    delivery_date  DATE      NOT NULL,
    source         VARCHAR   NOT NULL,
    rows_deleted   INTEGER   NOT NULL,
    rows_inserted  INTEGER   NOT NULL,
    loaded_at      TIMESTAMP NOT NULL DEFAULT current_timestamp
);
"""

AGGREGATE_SQL = """
INSERT INTO daily_price_stats
SELECT
    delivery_date,
    count(*)                                                  AS n_hours,
    round(avg(price_eur_mwh), 2)                              AS base_avg,
    round(avg(price_eur_mwh) FILTER (WHERE is_peak), 2)       AS peak_avg,
    round(avg(price_eur_mwh) FILTER (WHERE NOT is_peak), 2)   AS offpeak_avg,
    min(price_eur_mwh)                                        AS min_price,
    max(price_eur_mwh)                                        AS max_price,
    round(max(price_eur_mwh) - min(price_eur_mwh), 2)         AS intraday_spread,
    count(*) FILTER (WHERE price_eur_mwh < 0)                 AS negative_hours,
    arg_min(local_hour, price_eur_mwh)                        AS cheapest_hour,
    arg_max(local_hour, price_eur_mwh)                        AS most_expensive_hour
FROM (
    SELECT *,
           isodow(delivery_date) <= 5 AND local_hour BETWEEN 8 AND 19 AS is_peak
    FROM hourly_prices
    WHERE delivery_date = ?
)
GROUP BY delivery_date
"""


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(DDL)
    return con


def load_day(
    con: duckdb.DuckDBPyConnection,
    records: list[HourlyPrice],
    delivery_date: date,
    source: str,
    run_id: str = "manual",
) -> dict[str, int]:
    """Replace one delivery day in ``hourly_prices`` and ``daily_price_stats`` atomically."""
    if any(r.delivery_date != delivery_date for r in records):
        raise ValueError("all records must belong to the delivery date being loaded")
    rows = [
        (r.delivery_date, r.ts_utc.replace(tzinfo=None), r.local_hour, r.price_eur_mwh, source)
        for r in records
    ]
    con.execute("BEGIN TRANSACTION")
    try:
        deleted = con.execute(
            "SELECT count(*) FROM hourly_prices WHERE delivery_date = ?", [delivery_date]
        ).fetchone()[0]
        con.execute("DELETE FROM daily_price_stats WHERE delivery_date = ?", [delivery_date])
        con.execute("DELETE FROM hourly_prices WHERE delivery_date = ?", [delivery_date])
        if rows:
            con.executemany(
                "INSERT INTO hourly_prices "
                "(delivery_date, ts_utc, local_hour, price_eur_mwh, source) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            con.execute(AGGREGATE_SQL, [delivery_date])
        con.execute(
            "INSERT INTO load_audit (run_id, delivery_date, source, rows_deleted, rows_inserted) "
            "VALUES (?, ?, ?, ?, ?)",
            [run_id, delivery_date, source, deleted, len(rows)],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {"deleted": int(deleted), "inserted": len(rows)}
