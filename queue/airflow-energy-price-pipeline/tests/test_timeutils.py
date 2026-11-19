from datetime import UTC, date, datetime

import pytest

from energy_pipeline.timeutils import (
    date_range,
    day_bounds_utc,
    delivery_date_for_run,
    expected_hours,
    hourly_timestamps_utc,
)


@pytest.mark.parametrize(
    ("d", "hours"),
    [(date(2025, 3, 30), 23), (date(2025, 10, 26), 25), (date(2025, 6, 1), 24)],
)
def test_expected_hours_handles_dst(d, hours):
    assert expected_hours(d) == hours
    assert len(hourly_timestamps_utc(d)) == hours


def test_day_bounds_are_berlin_midnight_in_utc():
    start, end = day_bounds_utc(date(2025, 1, 15))
    assert start == datetime(2025, 1, 14, 23, tzinfo=UTC)
    assert end == datetime(2025, 1, 15, 23, tzinfo=UTC)
    summer_start, _ = day_bounds_utc(date(2025, 7, 1))
    assert summer_start == datetime(2025, 6, 30, 22, tzinfo=UTC)


def test_delivery_date_for_run_is_next_berlin_day():
    # 13:30 Berlin on 2025-03-10 == 12:30 UTC -> loads 2025-03-11
    assert delivery_date_for_run(datetime(2025, 3, 10, 12, 30, tzinfo=UTC)) == date(2025, 3, 11)
    # 23:30 UTC on Dec 31 is already Jan 1 in Berlin -> loads Jan 2
    assert delivery_date_for_run(datetime(2024, 12, 31, 23, 30, tzinfo=UTC)) == date(2025, 1, 2)


def test_date_range_inclusive_and_validates():
    assert date_range(date(2025, 1, 30), date(2025, 2, 2)) == [
        date(2025, 1, 30),
        date(2025, 1, 31),
        date(2025, 2, 1),
        date(2025, 2, 2),
    ]
    with pytest.raises(ValueError):
        date_range(date(2025, 2, 2), date(2025, 2, 1))
