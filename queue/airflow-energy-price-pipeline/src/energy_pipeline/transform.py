"""Transform + validate: raw SMARD series -> typed hourly records, with quality gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from energy_pipeline.timeutils import (
    BERLIN,
    day_bounds_utc,
    expected_hours,
    from_epoch_ms,
)

# Harmonised min/max clearing prices of the SDAC day-ahead market (EUR/MWh).
MIN_PRICE = -500.0
MAX_PRICE = 4000.0


class DataQualityError(ValueError):
    """Raised when a delivery day fails validation; the Airflow task then fails loudly."""


@dataclass(frozen=True)
class HourlyPrice:
    delivery_date: date
    ts_utc: datetime
    local_hour: int
    price_eur_mwh: float


@dataclass
class QualityReport:
    delivery_date: date
    expected: int
    received: int
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate(series: list[list], delivery_date: date) -> QualityReport:
    """Check completeness, uniqueness, nulls, hour alignment and price bounds."""
    start, end = day_bounds_utc(delivery_date)
    report = QualityReport(delivery_date, expected_hours(delivery_date), len(series))
    seen: set[int] = set()
    for point in series:
        if len(point) != 2:
            report.issues.append(f"malformed point {point!r}")
            continue
        ts_ms, value = point
        if ts_ms in seen:
            report.issues.append(f"duplicate timestamp {from_epoch_ms(ts_ms).isoformat()}")
        seen.add(ts_ms)
        ts = from_epoch_ms(ts_ms)
        if not (start <= ts < end):
            report.issues.append(f"timestamp {ts.isoformat()} outside delivery day")
        if ts_ms % 3_600_000 != 0:
            report.issues.append(f"timestamp {ts.isoformat()} not on the full hour")
        if value is None:
            report.issues.append(f"null price at {ts.isoformat()}")
        elif not (MIN_PRICE <= float(value) <= MAX_PRICE):
            report.issues.append(f"price {value} at {ts.isoformat()} outside [{MIN_PRICE}, {MAX_PRICE}]")
    if len(seen) != report.expected:
        report.issues.append(f"expected {report.expected} hours, got {len(seen)} distinct")
    return report


def to_records(series: list[list], delivery_date: date) -> list[HourlyPrice]:
    """Validate and convert; raises ``DataQualityError`` if any check fails."""
    report = validate(series, delivery_date)
    if not report.ok:
        shown = "; ".join(report.issues[:5])
        raise DataQualityError(f"{delivery_date}: {len(report.issues)} issue(s): {shown}")
    records = []
    for ts_ms, value in sorted(series, key=lambda p: p[0]):
        ts = from_epoch_ms(ts_ms)
        records.append(
            HourlyPrice(
                delivery_date=delivery_date,
                ts_utc=ts,
                local_hour=ts.astimezone(BERLIN).hour,
                price_eur_mwh=float(value),
            )
        )
    return records
