"""Streaming anomaly rules evaluated on emitted windows.

Two rules, deliberately simple and explainable:

* ``static_threshold`` - window max temperature above a fixed limit.
* ``ewma_zscore`` - window mean temperature deviates from the sensor's own
  exponentially weighted baseline by more than ``z`` standard deviations. This
  adapts to sensors that simply run hotter than others.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from sensorstream.windowing import WindowResult


@dataclass(frozen=True)
class Alert:
    sensor_id: str
    window_start: float
    rule: str
    value: float
    detail: str


@dataclass
class Baseline:
    mean: float
    var: float
    n: int


class AnomalyDetector:
    def __init__(
        self,
        temp_limit_c: float = 75.0,
        z_threshold: float = 5.0,
        alpha: float = 0.3,
        warmup: int = 10,
        min_std: float = 0.5,
    ) -> None:
        self.temp_limit_c = temp_limit_c
        self.z_threshold = z_threshold
        self.alpha = alpha
        self.warmup = warmup
        self.min_std = min_std
        self.baselines: dict[str, Baseline] = {}

    def check(self, w: WindowResult) -> list[Alert]:
        alerts: list[Alert] = []
        if w.temp_max > self.temp_limit_c:
            alerts.append(
                Alert(w.sensor_id, w.window_start, "static_threshold", w.temp_max,
                      f"max {w.temp_max:.1f}C > {self.temp_limit_c:.1f}C")
            )
        if w.is_update:  # late corrections must not move the baseline twice
            return alerts

        b = self.baselines.get(w.sensor_id)
        if b is None:
            self.baselines[w.sensor_id] = Baseline(w.temp_mean, 0.0, 1)
            return alerts

        std = max(math.sqrt(b.var), self.min_std)
        z = (w.temp_mean - b.mean) / std
        anomalous = b.n >= self.warmup and abs(z) > self.z_threshold
        if anomalous:
            alerts.append(
                Alert(w.sensor_id, w.window_start, "ewma_zscore", round(z, 2),
                      f"mean {w.temp_mean:.1f}C vs baseline {b.mean:.1f}C (z={z:.1f})")
            )
        else:  # only learn from normal windows so an incident doesn't become "normal"
            diff = w.temp_mean - b.mean
            b.mean += self.alpha * diff
            b.var = (1 - self.alpha) * (b.var + self.alpha * diff * diff)
            b.n += 1
        return alerts

    def snapshot(self) -> dict:
        return {s: asdict(b) for s, b in self.baselines.items()}

    def restore(self, snap: dict) -> None:
        self.baselines = {s: Baseline(**b) for s, b in snap.items()}
