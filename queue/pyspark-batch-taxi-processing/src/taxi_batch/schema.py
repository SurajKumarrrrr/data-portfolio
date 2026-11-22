"""Explicit schemas. Never rely on schema inference in a production batch job:
it costs an extra pass over the data and silently changes types when the input drifts."""

from __future__ import annotations

from pyspark.sql import types as T

TIMESTAMP_FORMAT = "yyyy-MM-dd HH:mm:ss"

# Column names follow the public NYC TLC yellow-taxi data dictionary.
RAW_TRIP_SCHEMA = T.StructType(
    [
        T.StructField("VendorID", T.IntegerType()),
        T.StructField("tpep_pickup_datetime", T.TimestampType()),
        T.StructField("tpep_dropoff_datetime", T.TimestampType()),
        T.StructField("passenger_count", T.IntegerType()),
        T.StructField("trip_distance", T.DoubleType()),
        T.StructField("PULocationID", T.IntegerType()),
        T.StructField("DOLocationID", T.IntegerType()),
        T.StructField("payment_type", T.IntegerType()),
        T.StructField("fare_amount", T.DoubleType()),
        T.StructField("tip_amount", T.DoubleType()),
        T.StructField("tolls_amount", T.DoubleType()),
        T.StructField("total_amount", T.DoubleType()),
    ]
)

ZONE_SCHEMA = T.StructType(
    [
        T.StructField("LocationID", T.IntegerType()),
        T.StructField("Borough", T.StringType()),
        T.StructField("Zone", T.StringType()),
        T.StructField("service_zone", T.StringType()),
    ]
)

# Business key used for de-duplication of re-delivered records.
TRIP_KEY = [
    "VendorID",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "PULocationID",
    "DOLocationID",
]

PAYMENT_CREDIT_CARD = 1
PAYMENT_CASH = 2
