"""Load raw CSV extracts into the ``raw`` schema of a DuckDB warehouse.

This is the "EL" in ELT: no business logic, every column lands as VARCHAR exactly as
delivered, plus an ingestion timestamp. Type casting and cleaning happen in dbt staging.
Loads are idempotent (``CREATE OR REPLACE``), so re-running never duplicates data.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

RAW_TABLES = ("customers", "products", "orders", "order_items", "payments")


def load_raw(csv_dir: Path, db_path: Path) -> dict[str, int]:
    """Load every expected CSV from ``csv_dir`` into ``raw.<table>``; return row counts."""
    missing = [t for t in RAW_TABLES if not (csv_dir / f"{t}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"Missing raw extracts in {csv_dir}: {', '.join(missing)}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        for table in RAW_TABLES:
            path = (csv_dir / f"{table}.csv").as_posix()
            con.execute(
                f"""
                CREATE OR REPLACE TABLE raw.{table} AS
                SELECT *, current_timestamp AS _ingested_at
                FROM read_csv(?, header = true, all_varchar = true)
                """,
                [path],
            )
            counts[table] = con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]
    return counts
