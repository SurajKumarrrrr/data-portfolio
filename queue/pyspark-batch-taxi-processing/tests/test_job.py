"""End-to-end test: generate → run the job → check persisted outputs and invariants."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from taxi_batch import job
from taxi_batch.generate import generate_trips, load_zones, write_monthly_csv
from taxi_batch.storage import read_raw_trips

ZONES = Path(__file__).resolve().parents[1] / "data" / "reference" / "taxi_zones.csv"


@pytest.fixture(scope="module")
def run_output(spark, tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e")
    rows = generate_trips(4000, datetime(2025, 1, 1), 14, load_zones(), seed=11)
    write_monthly_csv(rows, base / "raw")
    summary = job.run(spark, str(base / "raw"), str(ZONES), str(base / "out"))
    return base / "out", summary


def test_row_counts_reconcile(run_output):
    _, s = run_output
    assert s.raw_rows == 4000
    assert s.duplicates_removed > 0
    assert s.raw_rows - s.duplicates_removed == s.valid_rows + s.quarantined_rows
    assert sum(s.reject_reasons.values()) == s.quarantined_rows


def test_outputs_written(spark, run_output):
    out, s = run_output
    assert json.loads((out / "run_summary.json").read_text())["valid_rows"] == s.valid_rows
    assert s.silver_partitions == 14
    assert sorted(p.name for p in (out / "silver" / "trips").glob("pickup_date=*"))[0] == (
        "pickup_date=2025-01-01"
    )
    for name in ("daily_borough_kpis", "hourly_zone_demand", "top_routes"):
        assert spark.read.parquet(str(out / "gold" / name)).count() > 0


def test_silver_has_no_invalid_rows(spark, run_output):
    out, _ = run_output
    silver = spark.read.parquet(str(out / "silver" / "trips"))
    assert silver.filter("duration_min <= 0 or trip_distance <= 0 or fare_amount < 0").count() == 0
    assert silver.filter("pickup_zone is null or passenger_count is null").count() == 0


def test_rerun_is_idempotent(spark, run_output, tmp_path):
    out, s = run_output
    raw_dir = out.parent / "raw"
    again = job.run(spark, str(raw_dir), str(ZONES), str(out))
    assert again.valid_rows == s.valid_rows
    assert spark.read.parquet(str(out / "silver" / "trips")).count() == s.valid_rows


def test_parquet_input_is_cast_to_raw_schema(spark, tmp_path):
    # Official TLC parquet stores passenger_count as double; the reader must cast it.
    df = spark.createDataFrame(
        [(1, datetime(2025, 1, 1, 8), datetime(2025, 1, 1, 8, 10), 1.0, 2.0, 161, 230, 1,
          10.0, 2.0, 0.0, 14.5, "extra")],
        "VendorID long, tpep_pickup_datetime timestamp, tpep_dropoff_datetime timestamp, "
        "passenger_count double, trip_distance double, PULocationID long, DOLocationID long, "
        "payment_type long, fare_amount double, tip_amount double, tolls_amount double, "
        "total_amount double, store_and_fwd_flag string",
    )
    df.write.parquet(str(tmp_path / "p"))
    out = read_raw_trips(spark, tmp_path / "p", fmt="parquet")
    assert out.schema["passenger_count"].dataType.typeName() == "integer"
    assert "store_and_fwd_flag" not in out.columns


def test_unknown_format_raises(spark):
    with pytest.raises(ValueError, match="Unsupported"):
        read_raw_trips(spark, "x", fmt="json")
