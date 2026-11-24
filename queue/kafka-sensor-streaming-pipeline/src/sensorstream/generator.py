"""Deterministic synthetic IoT sensor stream.

Simulates machines on a few factory sites. Besides clean readings it injects the
problems a real stream has, so the consumer has something to handle:

* out-of-order delivery (small network jitter)
* late events (a sensor buffers offline and flushes minutes later)
* duplicates (producer retries)
* malformed payloads
* overheating episodes (the anomalies we want to alert on)
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field

from sensorstream.models import SensorReading

SITES = ("frankfurt", "offenbach", "darmstadt")


@dataclass
class GeneratorConfig:
    n_sensors: int = 12
    duration_s: int = 2 * 60 * 60
    interval_s: float = 5.0
    cycle_period_s: float = 8 * 60 * 60
    start_ts: float = 1_767_225_600.0  # 2026-01-01T00:00:00Z
    jitter_max_s: float = 8.0
    late_prob: float = 0.004
    late_delay_s: tuple[float, float] = (180.0, 600.0)
    duplicate_prob: float = 0.01
    malformed_prob: float = 0.002
    n_overheat_episodes: int = 4
    overheat_len_s: int = 15 * 60
    seed: int = 42


@dataclass
class GeneratedStream:
    """Messages in *delivery* order plus the clean ground truth for evaluation."""

    messages: list[tuple[bytes, bytes]]  # (key, value)
    truth: list[SensorReading]
    overheat: dict[str, tuple[float, float]] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)


def generate(cfg: GeneratorConfig | None = None) -> GeneratedStream:
    cfg = cfg or GeneratorConfig()
    rng = random.Random(cfg.seed)
    sensors = [f"sensor-{i:03d}" for i in range(cfg.n_sensors)]
    site_of = {s: SITES[i % len(SITES)] for i, s in enumerate(sensors)}
    base_temp = {s: rng.uniform(35.0, 55.0) for s in sensors}

    overheat: dict[str, tuple[float, float]] = {}
    for s in rng.sample(sensors, k=min(cfg.n_overheat_episodes, len(sensors))):
        start = cfg.start_ts + rng.uniform(0.2, 0.7) * cfg.duration_s
        overheat[s] = (start, start + cfg.overheat_len_s)

    truth: list[SensorReading] = []
    # (delivery_time, tiebreak, key, value)
    outbox: list[tuple[float, int, bytes, bytes]] = []
    stats = {"clean": 0, "late": 0, "duplicates": 0, "malformed": 0}
    n_steps = int(cfg.duration_s / cfg.interval_s)
    counter = 0

    for step in range(n_steps):
        t = cfg.start_ts + step * cfg.interval_s
        for s in sensors:
            # slow load cycle (one period per shift) + sensor noise
            cycle = 3.0 * math.sin(2 * math.pi * (t - cfg.start_ts) / cfg.cycle_period_s)
            temp = base_temp[s] + cycle + rng.gauss(0, 0.6)
            vib = abs(rng.gauss(2.0, 0.4))
            if s in overheat and overheat[s][0] <= t < overheat[s][1]:
                temp += 28.0
                vib *= 3.0
            reading = SensorReading(
                sensor_id=s,
                site=site_of[s],
                seq=step,
                event_ts=round(t, 3),
                temperature_c=round(temp, 3),
                humidity_pct=round(min(100.0, max(0.0, rng.gauss(45, 5))), 3),
                vibration_mm_s=round(vib, 3),
            )
            truth.append(reading)
            stats["clean"] += 1

            delay = rng.uniform(0, cfg.jitter_max_s)
            if rng.random() < cfg.late_prob:
                delay = rng.uniform(*cfg.late_delay_s)
                stats["late"] += 1
            counter += 1
            outbox.append((t + delay, counter, reading.key, reading.to_bytes()))

            if rng.random() < cfg.duplicate_prob:
                counter += 1
                outbox.append((t + delay + 1.0, counter, reading.key, reading.to_bytes()))
                stats["duplicates"] += 1

        if rng.random() < cfg.malformed_prob * cfg.n_sensors:
            counter += 1
            bad = rng.choice(
                [b"{not json", json.dumps({"sensor_id": "sensor-999"}).encode(), b"[1,2,3]"]
            )
            outbox.append((t, counter, b"unknown", bad))
            stats["malformed"] += 1

    outbox.sort(key=lambda m: (m[0], m[1]))
    return GeneratedStream(
        messages=[(k, v) for _, _, k, v in outbox], truth=truth, overheat=overheat, stats=stats
    )
