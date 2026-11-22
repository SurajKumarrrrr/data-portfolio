"""Pure DataFrame → DataFrame transformations. No I/O here, so every step is unit-testable."""

from __future__ import annotations

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from taxi_batch.schema import PAYMENT_CREDIT_CARD, TRIP_KEY

MAX_DURATION_MIN = 6 * 60
MAX_DISTANCE_MILES = 100.0
MAX_SPEED_MPH = 80.0
MAX_PASSENGERS = 6

# Ordered: the first matching rule becomes the reject reason, so the most fundamental
# problems (missing data) win over derived ones (implausible speed).
REJECT_REASONS = [
    "missing_timestamp",
    "non_positive_duration",
    "duration_too_long",
    "invalid_distance",
    "negative_amount",
    "invalid_passenger_count",
    "unknown_zone",
    "implausible_speed",
]


def deduplicate(df: DataFrame, key: list[str] = TRIP_KEY) -> DataFrame:
    """Drop re-delivered records that share the same business key."""
    return df.dropDuplicates(key)


def enrich_with_zones(trips: DataFrame, zones: DataFrame) -> DataFrame:
    """Attach pickup and dropoff borough/zone via two broadcast left joins.

    The zone table has a few hundred rows, so broadcasting it avoids shuffling the large
    trip table at all. A left join keeps trips with unknown IDs so they can be quarantined
    instead of silently disappearing (which an inner join would do).
    """
    z = F.broadcast(zones)
    pu = z.select(
        F.col("LocationID").alias("PULocationID"),
        F.col("Borough").alias("pickup_borough"),
        F.col("Zone").alias("pickup_zone"),
    )
    do = z.select(
        F.col("LocationID").alias("DOLocationID"),
        F.col("Borough").alias("dropoff_borough"),
        F.col("Zone").alias("dropoff_zone"),
    )
    return trips.join(pu, "PULocationID", "left").join(do, "DOLocationID", "left")


def _duration_min(pickup: str, dropoff: str) -> Column:
    return (F.unix_timestamp(dropoff) - F.unix_timestamp(pickup)) / 60.0


def add_reject_reason(df: DataFrame) -> DataFrame:
    """Add ``reject_reason`` (null for valid rows) using an ordered rule chain."""
    duration = _duration_min("tpep_pickup_datetime", "tpep_dropoff_datetime")
    speed = F.col("trip_distance") / (duration / 60.0)
    rules: list[tuple[str, Column]] = [
        (
            "missing_timestamp",
            F.col("tpep_pickup_datetime").isNull() | F.col("tpep_dropoff_datetime").isNull(),
        ),
        ("non_positive_duration", duration <= 0),
        ("duration_too_long", duration > MAX_DURATION_MIN),
        (
            "invalid_distance",
            F.col("trip_distance").isNull()
            | (F.col("trip_distance") <= 0)
            | (F.col("trip_distance") > MAX_DISTANCE_MILES),
        ),
        (
            "negative_amount",
            F.col("fare_amount").isNull()
            | (F.col("fare_amount") < 0)
            | (F.col("total_amount") < 0),
        ),
        (
            "invalid_passenger_count",
            F.col("passenger_count").isNull()
            | (F.col("passenger_count") < 1)
            | (F.col("passenger_count") > MAX_PASSENGERS),
        ),
        ("unknown_zone", F.col("pickup_zone").isNull() | F.col("dropoff_zone").isNull()),
        ("implausible_speed", speed > MAX_SPEED_MPH),
    ]
    assert [name for name, _ in rules] == REJECT_REASONS
    reason: Column = F.lit(None).cast("string")
    for name, condition in reversed(rules):
        reason = F.when(condition, F.lit(name)).otherwise(reason)
    return df.withColumn("reject_reason", reason)


def split_valid_invalid(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Split on ``reject_reason`` into (valid without the column, quarantine with it)."""
    valid = df.filter(F.col("reject_reason").isNull()).drop("reject_reason")
    invalid = df.filter(F.col("reject_reason").isNotNull())
    return valid, invalid


def add_trip_features(df: DataFrame) -> DataFrame:
    """Derive analysis columns: duration, speed, date/hour partitions, tip share."""
    duration = _duration_min("tpep_pickup_datetime", "tpep_dropoff_datetime")
    hour = F.hour("tpep_pickup_datetime")
    return (
        df.withColumn("duration_min", F.round(duration, 2))
        .withColumn("avg_speed_mph", F.round(F.col("trip_distance") / (duration / 60.0), 2))
        .withColumn("pickup_date", F.to_date("tpep_pickup_datetime"))
        .withColumn("pickup_hour", hour)
        .withColumn(
            "is_weekend", F.dayofweek("tpep_pickup_datetime").isin(1, 7)
        )  # Spark: 1 = Sunday, 7 = Saturday
        .withColumn(
            "time_of_day",
            F.when(hour.between(6, 9), "morning_peak")
            .when(hour.between(10, 15), "midday")
            .when(hour.between(16, 19), "evening_peak")
            .when(hour.between(20, 23), "evening")
            .otherwise("night"),
        )
        .withColumn(
            "tip_pct",
            # Cash tips are not recorded in TLC data, so tip share is only meaningful for cards.
            F.when(
                (F.col("payment_type") == PAYMENT_CREDIT_CARD) & (F.col("fare_amount") > 0),
                F.round(F.col("tip_amount") / F.col("fare_amount") * 100, 2),
            ),
        )
        .withColumn(
            "is_airport_trip",
            F.col("pickup_zone").contains("Airport") | F.col("dropoff_zone").contains("Airport"),
        )
    )


def daily_borough_kpis(trips: DataFrame) -> DataFrame:
    """Daily KPIs per pickup borough."""
    return (
        trips.groupBy("pickup_date", "pickup_borough")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.sum("total_amount"), 2).alias("revenue"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
            F.round(F.avg("trip_distance"), 2).alias("avg_distance"),
            F.round(F.percentile_approx("duration_min", 0.5), 2).alias("median_duration_min"),
            F.round(F.avg("tip_pct"), 2).alias("avg_tip_pct_card"),
        )
        .orderBy("pickup_date", "pickup_borough")
    )


def hourly_zone_demand(trips: DataFrame) -> DataFrame:
    """Average pickups per hour of day per zone, split into weekday vs weekend.

    Dividing by the number of distinct days of that type gives a comparable rate, rather
    than raw counts that are inflated for weekdays (5 vs 2 days per week).
    """
    days = trips.groupBy("is_weekend").agg(F.countDistinct("pickup_date").alias("n_days"))
    counts = trips.groupBy("pickup_zone", "pickup_borough", "is_weekend", "pickup_hour").agg(
        F.count("*").alias("trips"),
        F.round(F.avg("avg_speed_mph"), 2).alias("avg_speed_mph"),
    )
    return (
        counts.join(F.broadcast(days), "is_weekend")
        .withColumn("avg_trips_per_day", F.round(F.col("trips") / F.col("n_days"), 2))
        .drop("n_days")
        .orderBy("pickup_zone", "is_weekend", "pickup_hour")
    )


def top_routes(trips: DataFrame, n: int = 5) -> DataFrame:
    """Top-``n`` pickup→dropoff zone pairs per pickup borough, ranked with a window.

    ``row_number`` gives exactly ``n`` rows per borough; ties are broken by revenue and
    then by zone names so the output is deterministic.
    """
    routes = trips.groupBy("pickup_borough", "pickup_zone", "dropoff_zone").agg(
        F.count("*").alias("trips"),
        F.round(F.sum("total_amount"), 2).alias("revenue"),
        F.round(F.avg("duration_min"), 2).alias("avg_duration_min"),
    )
    w = Window.partitionBy("pickup_borough").orderBy(
        F.desc("trips"), F.desc("revenue"), "pickup_zone", "dropoff_zone"
    )
    return (
        routes.withColumn("rank", F.row_number().over(w))
        .filter(F.col("rank") <= n)
        .orderBy("pickup_borough", "rank")
    )


def reject_summary(quarantine: DataFrame) -> DataFrame:
    """Count quarantined rows per reason."""
    return quarantine.groupBy("reject_reason").count().orderBy(F.desc("count"), "reject_reason")
