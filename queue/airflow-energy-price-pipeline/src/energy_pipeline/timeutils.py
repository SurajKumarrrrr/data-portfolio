"""Time helpers: delivery days are defined in Europe/Berlin local time.

A delivery day has 23, 24 or 25 hours depending on daylight-saving transitions,
so every timestamp is stored in UTC and the local day is derived from it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def day_bounds_utc(delivery_date: date) -> tuple[datetime, datetime]:
    """Return [start, end) of a Berlin-local delivery day as UTC datetimes."""
    start_local = datetime.combine(delivery_date, datetime.min.time(), tzinfo=BERLIN)
    end_local = datetime.combine(delivery_date + timedelta(days=1), datetime.min.time(), tzinfo=BERLIN)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def expected_hours(delivery_date: date) -> int:
    """Number of hourly products in a delivery day (23 / 24 / 25)."""
    start, end = day_bounds_utc(delivery_date)
    return int((end - start).total_seconds() // 3600)


def hourly_timestamps_utc(delivery_date: date) -> list[datetime]:
    """All hour starts of a delivery day in UTC."""
    start, _ = day_bounds_utc(delivery_date)
    return [start + timedelta(hours=h) for h in range(expected_hours(delivery_date))]


def to_epoch_ms(ts: datetime) -> int:
    return int(ts.timestamp() * 1000)


def from_epoch_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def delivery_date_for_run(data_interval_end: datetime) -> date:
    """Map an Airflow run to the delivery day it should load.

    The DAG fires daily at 13:30 Berlin time, after the EPEX day-ahead auction
    results (published ~12:45 CET) for the *next* day are available. The run whose
    interval ends on day D therefore loads delivery day D + 1.
    """
    local_end = data_interval_end.astimezone(BERLIN)
    return local_end.date() + timedelta(days=1)


def date_range(start: date, end: date) -> list[date]:
    """Inclusive list of dates from start to end."""
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
