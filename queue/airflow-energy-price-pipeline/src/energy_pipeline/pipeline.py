"""Orchestration-agnostic pipeline steps.

The Airflow DAG calls these functions, and so does the CLI. Keeping business logic
out of the DAG file means it is unit-testable without an Airflow installation.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from energy_pipeline.extract import extract_day, read_raw
from energy_pipeline.load import connect, load_day
from energy_pipeline.sources import PriceSource, get_source
from energy_pipeline.timeutils import date_range
from energy_pipeline.transform import DataQualityError, to_records, validate

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    raw_dir: Path
    db_path: Path
    source: str

    @classmethod
    def from_env(cls) -> Settings:
        base = Path(os.environ.get("ENERGY_DATA_DIR", "data"))
        return cls(
            raw_dir=Path(os.environ.get("ENERGY_RAW_DIR", base / "raw")),
            db_path=Path(os.environ.get("ENERGY_DB_PATH", base / "warehouse.duckdb")),
            source=os.environ.get("ENERGY_SOURCE", "synthetic"),
        )


@dataclass(frozen=True)
class DayResult:
    delivery_date: date
    status: str  # "loaded" | "failed_quality"
    rows_inserted: int = 0
    rows_deleted: int = 0
    error: str | None = None


def step_extract(source: PriceSource, delivery_date: date, settings: Settings) -> str:
    path = extract_day(source, delivery_date, settings.raw_dir)
    log.info("landed %s", path)
    return str(path)


def step_validate(raw_file: str) -> dict:
    """Run quality checks on a landed file; raises so the task (not the load) fails."""
    payload = read_raw(Path(raw_file))
    d = date.fromisoformat(payload["delivery_date"])
    report = validate(payload["series"], d)
    if not report.ok:
        raise DataQualityError(f"{d}: " + "; ".join(report.issues[:5]))
    return {"delivery_date": d.isoformat(), "hours": report.received}


def step_load(raw_file: str, settings: Settings, run_id: str = "manual") -> dict[str, int]:
    payload = read_raw(Path(raw_file))
    d = date.fromisoformat(payload["delivery_date"])
    records = to_records(payload["series"], d)
    con = connect(settings.db_path)
    try:
        return load_day(con, records, d, payload["source"], run_id=run_id)
    finally:
        con.close()


def run_day(
    delivery_date: date, settings: Settings, source: PriceSource | None = None, run_id: str = "cli"
) -> DayResult:
    src = source or get_source(settings.source)
    raw_file = step_extract(src, delivery_date, settings)
    try:
        step_validate(raw_file)
    except DataQualityError as exc:
        log.warning("quality gate failed: %s", exc)
        return DayResult(delivery_date, "failed_quality", error=str(exc))
    counts = step_load(raw_file, settings, run_id=run_id)
    return DayResult(delivery_date, "loaded", counts["inserted"], counts["deleted"])


def backfill(
    start: date, end: date, settings: Settings, source: PriceSource | None = None
) -> list[DayResult]:
    """Sequentially (re)load a date range – same code path as a daily run."""
    src = source or get_source(settings.source)
    return [run_day(d, settings, src, run_id=f"backfill-{start}-{end}") for d in date_range(start, end)]
