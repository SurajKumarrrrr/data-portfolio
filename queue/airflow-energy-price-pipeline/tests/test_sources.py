from datetime import date

import pytest

from energy_pipeline.sources import SmardHttpSource, SyntheticSmardSource, get_source
from energy_pipeline.timeutils import day_bounds_utc, hourly_timestamps_utc, to_epoch_ms


def test_synthetic_is_deterministic_and_complete():
    src = SyntheticSmardSource(seed=7)
    d = date(2025, 5, 4)
    a, b = src.fetch_day(d), src.fetch_day(d)
    assert a == b
    assert [p[0] for p in a] == [to_epoch_ms(t) for t in hourly_timestamps_utc(d)]
    assert SyntheticSmardSource(seed=8).fetch_day(d) != a


def test_synthetic_respects_dst_and_bounds():
    src = SyntheticSmardSource()
    assert len(src.fetch_day(date(2025, 3, 30))) == 23
    assert len(src.fetch_day(date(2025, 10, 26))) == 25
    for d in (date(2025, 1, 1), date(2025, 7, 6)):
        assert all(-500 <= v <= 4000 for _, v in src.fetch_day(d))


def test_synthetic_seasonality_winter_more_expensive_than_summer():
    src = SyntheticSmardSource()

    def avg(month: int) -> float:
        vals = [v for day in range(1, 29) for _, v in src.fetch_day(date(2025, month, day))]
        return sum(vals) / len(vals)

    assert avg(1) > avg(7) + 20


def test_synthetic_can_drop_an_hour():
    d = date(2025, 2, 3)
    assert len(SyntheticSmardSource(drop_hour_on={d}).fetch_day(d)) == 23


def _fake_smard(delivery_date: date):
    """Two weekly chunks; the day spans the boundary between them."""
    start, end = day_bounds_utc(delivery_date)
    s, e = to_epoch_ms(start), to_epoch_ms(end)
    chunk_a, chunk_b = s - 3 * 3_600_000 * 24, s + 12 * 3_600_000
    hour = 3_600_000
    data = {
        "index": {"timestamps": [chunk_a - 7 * 24 * hour, chunk_a, chunk_b]},
        chunk_a: {"series": [[t, 50.0] for t in range(chunk_a, chunk_b, hour)]},
        chunk_b: {"series": [[t, 60.0] for t in range(chunk_b, e + 48 * hour, hour)]},
    }
    calls: list[str] = []

    def fetch(url: str) -> dict:
        calls.append(url)
        if url.endswith("index_hour.json"):
            return data["index"]
        return data[int(url.rsplit("_", 1)[1].removesuffix(".json"))]

    return fetch, calls


def test_smard_http_source_merges_chunks_and_filters_day():
    d = date(2025, 4, 9)
    fetch, calls = _fake_smard(d)
    series = SmardHttpSource(fetch_json=fetch).fetch_day(d)
    assert len(series) == 24
    assert [v for _, v in series] == [50.0] * 12 + [60.0] * 12
    assert sum("hour_" in c for c in calls) == 2  # the oldest chunk is not fetched
    assert "/4169/DE-LU/" in calls[0]


def test_smard_http_source_retries_then_fails():
    attempts = []

    def broken(url: str) -> dict:
        attempts.append(url)
        raise OSError("connection reset")

    src = SmardHttpSource(fetch_json=broken, retries=3, backoff_seconds=0)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        src.fetch_day(date(2025, 1, 1))
    assert len(attempts) == 3


def test_get_source():
    assert get_source("synthetic").name == "synthetic"
    assert get_source("smard").name == "smard"
    with pytest.raises(ValueError):
        get_source("entsoe")
