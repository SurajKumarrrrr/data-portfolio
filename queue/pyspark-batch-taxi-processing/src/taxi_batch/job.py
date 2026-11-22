"""Batch job: raw trips → deduplicated, validated, enriched silver table + gold aggregates.

Usage:
    python -m taxi_batch.job --input data/raw/trips --zones data/reference/taxi_zones.csv \
        --output data/output
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from taxi_batch import transforms as t
from taxi_batch.spark import get_spark
from taxi_batch.storage import read_raw_trips, read_zones, write_parquet


@dataclass
class RunSummary:
    raw_rows: int
    duplicates_removed: int
    valid_rows: int
    quarantined_rows: int
    reject_reasons: dict[str, int]
    silver_partitions: int
    seconds: float
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class JobResult:
    silver: DataFrame
    quarantine: DataFrame
    gold: dict[str, DataFrame]


def build(raw: DataFrame, zones: DataFrame) -> JobResult:
    """Wire the transformation graph. Lazy: nothing executes until an action/write."""
    deduped = t.deduplicate(raw)
    flagged = t.add_reject_reason(t.enrich_with_zones(deduped, zones))
    valid, quarantine = t.split_valid_invalid(flagged)
    silver = t.add_trip_features(valid)
    gold = {
        "daily_borough_kpis": t.daily_borough_kpis(silver),
        "hourly_zone_demand": t.hourly_zone_demand(silver),
        "top_routes": t.top_routes(silver, n=5),
    }
    return JobResult(silver=silver, quarantine=quarantine, gold=gold)


def run(
    spark: SparkSession, input_path: str, zones_path: str, output: str, fmt: str = "csv"
) -> RunSummary:
    start = time.perf_counter()
    out = Path(output)
    raw = read_raw_trips(spark, input_path, fmt).cache()
    zones = read_zones(spark, zones_path)
    result = build(raw, zones)

    # Silver is reused by three gold aggregates: materialise it once instead of
    # recomputing the dedupe + join + validation lineage for each output.
    silver = result.silver.cache()
    write_parquet(
        silver.repartition("pickup_date"), out / "silver" / "trips", partition_by=["pickup_date"]
    )
    write_parquet(result.quarantine, out / "quarantine" / "trips")
    gold = result.gold
    for name, df in gold.items():
        write_parquet(df.coalesce(1), out / "gold" / name)

    # Metrics come from the written outputs, so they describe what was actually persisted.
    silver_written = spark.read.parquet(str(out / "silver" / "trips"))
    quarantine_written = spark.read.parquet(str(out / "quarantine" / "trips"))
    raw_rows = raw.count()
    deduped_rows = raw.dropDuplicates(t.TRIP_KEY).count()
    reasons = {
        r["reject_reason"]: r["count"] for r in t.reject_summary(quarantine_written).collect()
    }
    summary = RunSummary(
        raw_rows=raw_rows,
        duplicates_removed=raw_rows - deduped_rows,
        valid_rows=silver_written.count(),
        quarantined_rows=quarantine_written.count(),
        reject_reasons=reasons,
        silver_partitions=silver_written.select("pickup_date").distinct().count(),
        seconds=round(time.perf_counter() - start, 1),
        outputs={
            "silver": str(out / "silver" / "trips"),
            "quarantine": str(out / "quarantine" / "trips"),
            **{name: str(out / "gold" / name) for name in gold},
        },
    )
    (out / "run_summary.json").write_text(json.dumps(asdict(summary), indent=2))
    silver.unpersist()
    raw.unpersist()
    return summary


def print_report(spark: SparkSession, summary: RunSummary) -> None:
    """Print the run summary plus a few headline numbers from the gold tables."""
    print(json.dumps(asdict(summary), indent=2))
    kpis = spark.read.parquet(summary.outputs["daily_borough_kpis"])
    print("\nTotals per pickup borough:")
    (
        kpis.groupBy("pickup_borough")
        .agg(
            F.sum("trips").alias("trips"),
            F.round(F.sum("revenue"), 0).alias("revenue"),
            F.round(F.avg("avg_fare"), 2).alias("avg_fare"),
            F.round(F.avg("avg_tip_pct_card"), 1).alias("avg_tip_pct_card"),
        )
        .orderBy(F.desc("trips"))
        .show(truncate=False)
    )
    silver = spark.read.parquet(summary.outputs["silver"])
    print("Average speed by time of day (mph):")
    (
        silver.groupBy("time_of_day")
        .agg(F.round(F.avg("avg_speed_mph"), 1).alias("avg_speed_mph"), F.count("*").alias("n"))
        .orderBy("avg_speed_mph")
        .show(truncate=False)
    )
    print("Top route per borough:")
    (
        spark.read.parquet(summary.outputs["top_routes"])
        .filter("rank = 1")
        .select("pickup_borough", "pickup_zone", "dropoff_zone", "trips", "avg_duration_min")
        .orderBy(F.desc("trips"))
        .show(truncate=False)
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Taxi trips batch job")
    parser.add_argument("--input", required=True)
    parser.add_argument("--zones", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=["csv", "parquet"], default="csv")
    parser.add_argument("--shuffle-partitions", type=int, default=8)
    args = parser.parse_args(argv)

    spark = get_spark(shuffle_partitions=args.shuffle_partitions)
    spark.sparkContext.setLogLevel("WARN")
    try:
        summary = run(spark, args.input, args.zones, args.output, args.format)
        print_report(spark, summary)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
