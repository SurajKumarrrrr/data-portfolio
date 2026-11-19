"""Data sources that return SMARD-style hourly series: ``[[epoch_ms, value], ...]``.

* ``SyntheticSmardSource`` – deterministic generator (offline, used in tests and the demo).
* ``SmardHttpSource`` – the public SMARD chart-data API of the Bundesnetzagentur
  (filter 4169 = day-ahead price DE-LU, EUR/MWh). Needs internet access.
"""

from __future__ import annotations

import json
import math
import random
import time
import urllib.request
from collections.abc import Callable
from datetime import date
from typing import Protocol

from energy_pipeline.timeutils import (
    BERLIN,
    day_bounds_utc,
    hourly_timestamps_utc,
    to_epoch_ms,
)

Series = list[list[float | int | None]]

SMARD_BASE_URL = "https://www.smard.de/app/chart_data"
DAY_AHEAD_FILTER = 4169
REGION = "DE-LU"
WEEK_MS = 7 * 24 * 3600 * 1000


class PriceSource(Protocol):
    name: str

    def fetch_day(self, delivery_date: date) -> Series:
        """Return all hourly points of one Berlin-local delivery day."""
        ...


class SyntheticSmardSource:
    """Generates realistic-looking day-ahead prices, identical for every call.

    The random generator is seeded from the delivery date, so re-running a day
    yields exactly the same data – which is what makes idempotency testable.

    Shape: seasonal base level, morning/evening peaks, a midday solar dip that is
    deeper in summer and on weekends (occasionally pushing prices negative), a
    daily wind shock and rare evening scarcity spikes.

    ``drop_hour_on`` lets tests/demo simulate an incomplete delivery from upstream.
    """

    name = "synthetic"

    def __init__(self, seed: int = 42, drop_hour_on: set[date] | None = None) -> None:
        self.seed = seed
        self.drop_hour_on = drop_hour_on or set()

    def fetch_day(self, delivery_date: date) -> Series:
        rng = random.Random(self.seed * 100_000_000 + int(delivery_date.strftime("%Y%m%d")))
        month_angle = 2 * math.pi * (delivery_date.month - 1) / 12
        base = 88 + 22 * math.cos(month_angle)  # winter expensive, summer cheap
        solar_season = 0.5 - 0.5 * math.cos(month_angle)  # 0 in Jan, 1 in Jul
        weekend = delivery_date.weekday() >= 5
        wind_shock = rng.gauss(0, 14)  # windy days are cheap all day
        sunshine = rng.uniform(0.2, 1.25)
        spike_hour = rng.choice([18, 19, 20]) if rng.random() < 0.03 else None

        series: Series = []
        for ts in hourly_timestamps_utc(delivery_date):
            h = ts.astimezone(BERLIN).hour
            shape = (
                25 * math.exp(-(((h - 8) / 1.8) ** 2))
                + 35 * math.exp(-(((h - 19) / 2.0) ** 2))
                - 18 * math.exp(-(((h - 3) / 2.5) ** 2))
            )
            solar_dip = (25 + 95 * solar_season) * sunshine * math.exp(-(((h - 13) / 2.6) ** 2))
            if weekend:
                solar_dip *= 1.35
            price = base + shape - solar_dip - (14 if weekend else 0) - wind_shock
            price += rng.gauss(0, 6)
            if spike_hour is not None and h == spike_hour:
                price += rng.uniform(120, 260)
            price = min(max(price, -500.0), 4000.0)
            series.append([to_epoch_ms(ts), round(price, 2)])

        if delivery_date in self.drop_hour_on and series:
            series.pop(len(series) // 2)
        return series


FetchJson = Callable[[str], dict]


def _urllib_fetch_json(url: str, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "energy-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
        return json.loads(resp.read().decode("utf-8"))


class SmardHttpSource:
    """Reads the public SMARD API, which serves data in weekly chunks.

    ``index_hour.json`` lists chunk start timestamps; each chunk file holds one week
    of ``[ts_ms, value]`` points. We fetch every chunk overlapping the delivery day
    and keep only the points inside it.
    """

    name = "smard"

    def __init__(
        self,
        fetch_json: FetchJson = _urllib_fetch_json,
        retries: int = 3,
        backoff_seconds: float = 2.0,
        filter_id: int = DAY_AHEAD_FILTER,
        region: str = REGION,
    ) -> None:
        self.fetch_json = fetch_json
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.filter_id = filter_id
        self.region = region

    def _get(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return self.fetch_json(url)
            except Exception as exc:  # network errors, HTTP errors, bad JSON
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.backoff_seconds * 2 ** (attempt - 1))
        raise RuntimeError(f"GET {url} failed after {self.retries} attempts") from last_error

    def index_url(self) -> str:
        return f"{SMARD_BASE_URL}/{self.filter_id}/{self.region}/index_hour.json"

    def chunk_url(self, chunk_ts: int) -> str:
        f, r = self.filter_id, self.region
        return f"{SMARD_BASE_URL}/{f}/{r}/{f}_{r}_hour_{chunk_ts}.json"

    def fetch_day(self, delivery_date: date) -> Series:
        start, end = day_bounds_utc(delivery_date)
        start_ms, end_ms = to_epoch_ms(start), to_epoch_ms(end)
        chunks = sorted(self.fetch_json_index())
        wanted = [c for c in chunks if c < end_ms and c + WEEK_MS + 3_600_000 > start_ms]
        points: dict[int, float | None] = {}
        for chunk_ts in wanted:
            for ts, value in self._get(self.chunk_url(chunk_ts)).get("series", []):
                if start_ms <= ts < end_ms:
                    points[int(ts)] = value
        return [[ts, points[ts]] for ts in sorted(points)]

    def fetch_json_index(self) -> list[int]:
        return [int(t) for t in self._get(self.index_url()).get("timestamps", [])]


def get_source(name: str) -> PriceSource:
    if name == "synthetic":
        return SyntheticSmardSource()
    if name == "smard":
        return SmardHttpSource()
    raise ValueError(f"unknown source {name!r} (expected 'synthetic' or 'smard')")
