from __future__ import annotations

from datetime import date

import pytest
from chispa import assert_df_equality
from pyspark.sql import functions as F
from pyspark.sql import types as T

from taxi_batch import transforms as t
from tests.conftest import trip


def test_deduplicate_removes_redelivered_rows(make_trips):
    df = make_trips([trip(), trip(), trip(pickup="2025-01-06 09:00:00",
                                          dropoff="2025-01-06 09:10:00")])
    assert t.deduplicate(df).count() == 2


def test_deduplicate_keeps_rows_differing_in_key(make_trips):
    df = make_trips([trip(vendor=1), trip(vendor=2)])
    assert t.deduplicate(df).count() == 2


def test_enrich_with_zones_left_join_keeps_unknown_ids(make_trips, zones):
    df = make_trips([trip(pu=161, do=181), trip(pu=999, do=161)])
    out = t.enrich_with_zones(df, zones).select(
        "PULocationID", "pickup_borough", "pickup_zone", "dropoff_borough"
    )
    expected = out.sparkSession.createDataFrame(
        [(161, "Manhattan", "Midtown Center", "Brooklyn"), (999, None, None, "Manhattan")],
        out.schema,
    )
    assert_df_equality(out, expected, ignore_row_order=True, ignore_nullable=True)


def test_enrich_with_zones_uses_broadcast_join(make_trips, zones):
    plan = t.enrich_with_zones(make_trips([trip()]), zones)._jdf.queryExecution().toString()
    assert "BroadcastHashJoin" in plan or "broadcast" in plan.lower()


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (trip(), None),
        (trip(pickup=None), "missing_timestamp"),
        (trip(dropoff="2025-01-06 07:50:00"), "non_positive_duration"),
        (trip(dropoff="2025-01-06 08:00:00"), "non_positive_duration"),
        (trip(dropoff="2025-01-06 15:00:00", distance=20.0), "duration_too_long"),
        (trip(distance=0.0), "invalid_distance"),
        (trip(distance=150.0, dropoff="2025-01-06 13:00:00"), "invalid_distance"),
        (trip(fare=-5.0), "negative_amount"),
        (trip(passengers=None), "invalid_passenger_count"),
        (trip(passengers=0), "invalid_passenger_count"),
        (trip(passengers=9), "invalid_passenger_count"),
        (trip(pu=999), "unknown_zone"),
        (trip(distance=30.0), "implausible_speed"),  # 30 miles in 12 minutes = 150 mph
    ],
)
def test_reject_reason_rules(make_trips, zones, row, reason):
    df = t.add_reject_reason(t.enrich_with_zones(make_trips([row]), zones))
    assert df.first()["reject_reason"] == reason


def test_reject_reason_first_rule_wins(make_trips, zones):
    # Both distance and passenger count are invalid; distance comes first in the chain.
    row = trip(distance=0.0, passengers=0)
    df = t.add_reject_reason(t.enrich_with_zones(make_trips([row]), zones))
    assert df.first()["reject_reason"] == "invalid_distance"


def test_split_valid_invalid_is_a_partition(make_trips, zones):
    df = t.add_reject_reason(
        t.enrich_with_zones(make_trips([trip(), trip(fare=-1.0), trip(pu=999)]), zones)
    )
    valid, invalid = t.split_valid_invalid(df)
    assert valid.count() == 1
    assert invalid.count() == 2
    assert "reject_reason" not in valid.columns
    assert "reject_reason" in invalid.columns


def test_add_trip_features(make_trips, zones):
    rows = [
        trip(),  # Monday 08:00, card, 12 min, 2 miles
        trip(pickup="2025-01-11 23:30:00", dropoff="2025-01-12 00:00:00", pu=132, do=161,
             distance=10.0, fare=70.0, tip=0.0, payment=2),  # Saturday night, cash, airport
    ]
    df = t.add_trip_features(t.enrich_with_zones(make_trips(rows), zones))
    got = df.select(
        "duration_min", "avg_speed_mph", "pickup_date", "pickup_hour", "is_weekend",
        "time_of_day", "tip_pct", "is_airport_trip",
    ).orderBy("pickup_date")
    expected = got.sparkSession.createDataFrame(
        [
            (12.0, 10.0, date(2025, 1, 6), 8, False, "morning_peak", 20.0, False),
            (30.0, 20.0, date(2025, 1, 11), 23, True, "evening", None, True),
        ],
        got.schema,
    )
    assert_df_equality(got, expected, ignore_nullable=True)


@pytest.fixture
def silver(make_trips, zones):
    rows = [
        trip(pu=161, do=230, fare=10.0, tip=2.0),
        trip(pu=161, do=230, fare=14.0, tip=0.0, payment=2, vendor=2),
        trip(pu=161, do=181, pickup="2025-01-06 10:00:00", dropoff="2025-01-06 10:30:00",
             distance=6.0, fare=25.0, tip=5.0),
        trip(pu=181, do=161, pickup="2025-01-11 12:00:00", dropoff="2025-01-11 12:30:00",
             distance=6.0, fare=25.0, tip=4.0),
    ]
    return t.add_trip_features(t.enrich_with_zones(make_trips(rows), zones))


def test_daily_borough_kpis(silver):
    out = t.daily_borough_kpis(silver).collect()
    manhattan = next(r for r in out if r["pickup_borough"] == "Manhattan")
    assert manhattan["pickup_date"] == date(2025, 1, 6)
    assert manhattan["trips"] == 3
    assert manhattan["revenue"] == pytest.approx(10 + 2 + 14 + 0 + 25 + 5 + 3 * 2.5)
    assert manhattan["avg_fare"] == pytest.approx(16.33)
    # Only card trips have a tip share: 20% and 20%.
    assert manhattan["avg_tip_pct_card"] == pytest.approx(20.0)
    assert {r["pickup_borough"] for r in out} == {"Manhattan", "Brooklyn"}


def test_hourly_zone_demand_normalises_by_day_count(silver):
    out = t.hourly_zone_demand(silver)
    row = out.filter(
        (F.col("pickup_zone") == "Midtown Center") & (F.col("pickup_hour") == 8)
    ).first()
    assert row["trips"] == 2
    assert row["avg_trips_per_day"] == 2.0  # one distinct weekday in the data
    assert out.schema["avg_trips_per_day"].dataType == T.DoubleType()


def test_top_routes_ranks_within_borough(silver):
    out = t.top_routes(silver, n=1).collect()
    by_borough = {r["pickup_borough"]: r for r in out}
    assert set(by_borough) == {"Manhattan", "Brooklyn"}
    assert by_borough["Manhattan"]["dropoff_zone"] == "Times Sq/Theatre District"
    assert by_borough["Manhattan"]["trips"] == 2
    assert all(r["rank"] == 1 for r in out)


def test_top_routes_returns_at_most_n_per_borough(silver):
    out = t.top_routes(silver, n=5)
    counts = out.groupBy("pickup_borough").count().collect()
    assert all(r["count"] <= 5 for r in counts)


def test_reject_summary(make_trips, zones):
    df = t.add_reject_reason(
        t.enrich_with_zones(
            make_trips([trip(fare=-1.0), trip(fare=-2.0, vendor=2), trip(pu=999)]), zones
        )
    )
    _, invalid = t.split_valid_invalid(df)
    rows = [tuple(r) for r in t.reject_summary(invalid).collect()]
    assert rows == [("negative_amount", 2), ("unknown_zone", 1)]
