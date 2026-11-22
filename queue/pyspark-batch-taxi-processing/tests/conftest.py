from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pyspark.sql import DataFrame, SparkSession

from taxi_batch.schema import RAW_TRIP_SCHEMA, ZONE_SCHEMA
from taxi_batch.spark import get_spark


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    session = get_spark("taxi-batch-tests", master="local[2]", shuffle_partitions=2)
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture
def zones(spark: SparkSession) -> DataFrame:
    rows = [
        (132, "Queens", "JFK Airport", "Airports"),
        (161, "Manhattan", "Midtown Center", "Yellow Zone"),
        (230, "Manhattan", "Times Sq/Theatre District", "Yellow Zone"),
        (181, "Brooklyn", "Park Slope", "Boro Zone"),
    ]
    return spark.createDataFrame(rows, ZONE_SCHEMA)


def ts(s: str) -> datetime:
    """Timezone-aware UTC timestamp, so the result doesn't depend on the machine's local TZ
    (Spark converts naive Python datetimes using the *Python process* time zone)."""
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def trip(
    pickup: str = "2025-01-06 08:00:00",
    dropoff: str = "2025-01-06 08:12:00",
    pu: int = 161,
    do: int = 230,
    distance: float = 2.0,
    fare: float = 12.0,
    tip: float = 2.4,
    passengers: int | None = 1,
    payment: int = 1,
    vendor: int = 1,
    total: float | None = None,
) -> tuple:
    """Build one raw trip row in RAW_TRIP_SCHEMA order with sensible defaults."""
    return (
        vendor,
        ts(pickup) if pickup else None,
        ts(dropoff) if dropoff else None,
        passengers,
        distance,
        pu,
        do,
        payment,
        fare,
        tip,
        0.0,
        total if total is not None else round(fare + tip + 2.5, 2),
    )


@pytest.fixture
def make_trips(spark: SparkSession):
    def _make(rows: list[tuple]) -> DataFrame:
        return spark.createDataFrame(rows, RAW_TRIP_SCHEMA)

    return _make
