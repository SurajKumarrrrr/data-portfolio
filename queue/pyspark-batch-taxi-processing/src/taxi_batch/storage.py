"""Readers and writers. Kept separate from transforms so transforms stay pure and testable."""

from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from taxi_batch.schema import RAW_TRIP_SCHEMA, TIMESTAMP_FORMAT, ZONE_SCHEMA


def read_raw_trips(spark: SparkSession, path: str | Path, fmt: str = "csv") -> DataFrame:
    """Read raw trips as CSV (bundled synthetic data) or Parquet (official TLC files).

    Both paths return exactly ``RAW_TRIP_SCHEMA`` so downstream code is format-agnostic.
    Official TLC Parquet stores e.g. ``passenger_count`` as double, so we cast explicitly.
    """
    if fmt == "csv":
        return (
            spark.read.option("header", "true")
            .option("mode", "PERMISSIVE")
            .option("timestampFormat", TIMESTAMP_FORMAT)
            .schema(RAW_TRIP_SCHEMA)
            .csv(str(path))
        )
    if fmt == "parquet":
        df = spark.read.parquet(str(path))
        return df.select(
            [F.col(f.name).cast(f.dataType).alias(f.name) for f in RAW_TRIP_SCHEMA.fields]
        )
    raise ValueError(f"Unsupported input format: {fmt!r}")


def read_zones(spark: SparkSession, path: str | Path) -> DataFrame:
    """Read the taxi zone lookup table (LocationID → Borough/Zone)."""
    return spark.read.option("header", "true").schema(ZONE_SCHEMA).csv(str(path))


def write_parquet(
    df: DataFrame, path: str | Path, partition_by: list[str] | None = None
) -> None:
    """Write Parquet with dynamic partition overwrite, so re-running a day is idempotent."""
    writer = df.write.mode("overwrite")
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.parquet(str(path))
