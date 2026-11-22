from __future__ import annotations

import csv
from datetime import datetime

from taxi_batch.generate import HEADER, generate_trips, load_zones, write_monthly_csv


def test_generator_is_deterministic():
    zones = load_zones()
    a = generate_trips(500, datetime(2025, 1, 1), 31, zones, seed=7)
    b = generate_trips(500, datetime(2025, 1, 1), 31, zones, seed=7)
    c = generate_trips(500, datetime(2025, 1, 1), 31, zones, seed=8)
    assert a == b
    assert a != c
    assert len(a) == 500


def test_generator_injects_defects():
    rows = generate_trips(5000, datetime(2025, 1, 1), 31, load_zones(), seed=1)
    assert any(r[3] == "" for r in rows)  # null passenger_count
    assert any(r[5] == 999 for r in rows)  # unknown zone
    assert any(float(r[8]) < 0 for r in rows)  # negative fare


def test_write_monthly_csv_splits_by_month(tmp_path):
    rows = generate_trips(2000, datetime(2025, 1, 1), 59, load_zones(), seed=3)
    paths = write_monthly_csv(rows, tmp_path)
    assert [p.name for p in paths] == ["yellow_tripdata_2025-01.csv", "yellow_tripdata_2025-02.csv"]
    with paths[0].open() as fh:
        reader = csv.reader(fh)
        assert next(reader) == HEADER
        assert all(r[1].startswith("2025-01") for r in reader)
