from datetime import date

import pytest

from energy_pipeline.sources import SyntheticSmardSource
from energy_pipeline.transform import DataQualityError, to_records, validate

D = date(2025, 2, 12)


@pytest.fixture
def series():
    return SyntheticSmardSource().fetch_day(D)


def test_clean_day_passes(series):
    report = validate(series, D)
    assert report.ok and report.expected == report.received == 24
    records = to_records(series, D)
    assert [r.local_hour for r in records] == list(range(24))
    assert records[0].ts_utc.isoformat() == "2025-02-11T23:00:00+00:00"


def test_missing_hour_detected(series):
    report = validate(series[:-1], D)
    assert not report.ok
    assert "expected 24 hours, got 23" in report.issues[-1]


def test_duplicates_nulls_bounds_alignment(series):
    bad = [list(p) for p in series]
    bad[1] = [bad[0][0], bad[1][1]]  # duplicate ts (and therefore one hour missing)
    bad[2][1] = None
    bad[3][1] = 5000.0
    bad[4][0] += 60_000  # 1 minute off the hour
    issues = " | ".join(validate(bad, D).issues)
    for needle in ("duplicate timestamp", "null price", "outside [-500.0, 4000.0]", "not on the full hour"):
        assert needle in issues


def test_point_outside_day(series):
    shifted = [[ts + 24 * 3_600_000, v] for ts, v in series]
    assert any("outside delivery day" in i for i in validate(shifted, D).issues)


def test_to_records_raises_on_bad_data(series):
    with pytest.raises(DataQualityError, match="2025-02-12"):
        to_records(series[:10], D)


def test_negative_prices_are_valid(series):
    series[5][1] = -135.4
    assert validate(series, D).ok


def test_fall_back_day_has_hour_two_twice():
    d = date(2025, 10, 26)
    hours = [r.local_hour for r in to_records(SyntheticSmardSource().fetch_day(d), d)]
    assert len(hours) == 25 and hours.count(2) == 2
