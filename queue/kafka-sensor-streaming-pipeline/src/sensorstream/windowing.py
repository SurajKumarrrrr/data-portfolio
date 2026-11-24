"""Event-time tumbling windows with per-partition watermarks and allowed lateness.

Semantics (same model as Flink / Kafka Streams, reduced to the essentials):

* Every reading belongs to the window ``[floor(ts / size) * size, +size)``.
* Watermark = min over partitions of (max event time seen in partition)
  minus ``max_out_of_order_s``. It is the operator's promise "no more events
  older than this are expected".
* A window is **emitted** once the watermark passes its end.
* It is **kept** for ``allowed_lateness_s`` more; late events in that period
  update it and the window is re-emitted (the sink upserts, so this is safe).
* Events for windows older than that are **dropped** to a side output.
* Duplicates are detected by ``(sensor_id, seq)`` and ignored.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from sensorstream.models import SensorReading


@dataclass
class WindowState:
    sensor_id: str
    site: str
    window_start: float
    count: int = 0
    temp_sum: float = 0.0
    temp_min: float = math.inf
    temp_max: float = -math.inf
    hum_sum: float = 0.0
    vib_max: float = 0.0
    emitted: bool = False

    def add(self, r: SensorReading) -> None:
        self.count += 1
        self.temp_sum += r.temperature_c
        self.temp_min = min(self.temp_min, r.temperature_c)
        self.temp_max = max(self.temp_max, r.temperature_c)
        self.hum_sum += r.humidity_pct
        self.vib_max = max(self.vib_max, r.vibration_mm_s)


@dataclass(frozen=True)
class WindowResult:
    sensor_id: str
    site: str
    window_start: float
    window_end: float
    count: int
    temp_mean: float
    temp_min: float
    temp_max: float
    humidity_mean: float
    vibration_max: float
    is_update: bool  # True when re-emitted because of a late event


@dataclass
class Counters:
    accepted: int = 0
    duplicates: int = 0
    late_updates: int = 0
    dropped_late: int = 0
    windows_emitted: int = 0


class TumblingWindowAggregator:
    def __init__(
        self,
        partitions: list[int],
        size_s: float = 60.0,
        max_out_of_order_s: float = 15.0,
        allowed_lateness_s: float = 300.0,
    ) -> None:
        self.size_s = size_s
        self.max_out_of_order_s = max_out_of_order_s
        self.allowed_lateness_s = allowed_lateness_s
        self.partition_max: dict[int, float] = {p: -math.inf for p in partitions}
        self.windows: dict[tuple[str, float], WindowState] = {}
        self.seen: dict[tuple[str, int], float] = {}
        self.counters = Counters()

    # ---- time -----------------------------------------------------------
    @property
    def watermark(self) -> float:
        return min(self.partition_max.values()) - self.max_out_of_order_s

    def window_start(self, ts: float) -> float:
        return math.floor(ts / self.size_s) * self.size_s

    # ---- processing -------------------------------------------------------
    def process(self, partition: int, r: SensorReading) -> list[WindowResult]:
        """Add one reading; return any windows that became (re-)emittable."""
        dedup_key = (r.sensor_id, r.seq)
        if dedup_key in self.seen:
            self.counters.duplicates += 1
            return []

        start = self.window_start(r.event_ts)
        end = start + self.size_s
        if end + self.allowed_lateness_s <= self.watermark:
            self.counters.dropped_late += 1
            return []

        self.seen[dedup_key] = r.event_ts
        self.counters.accepted += 1
        key = (r.sensor_id, start)
        state = self.windows.get(key)
        if state is None:
            state = self.windows[key] = WindowState(r.sensor_id, r.site, start)
        state.add(r)

        out: list[WindowResult] = []
        if state.emitted:  # late event for an already emitted window -> re-emit
            self.counters.late_updates += 1
            out.append(self._result(state, is_update=True))

        if r.event_ts > self.partition_max.get(partition, -math.inf):
            self.partition_max[partition] = r.event_ts
            out.extend(self._advance())
        return out

    def _advance(self) -> list[WindowResult]:
        wm = self.watermark
        out: list[WindowResult] = []
        for key in sorted(self.windows, key=lambda k: (k[1], k[0])):
            state = self.windows[key]
            end = state.window_start + self.size_s
            if not state.emitted and end <= wm:
                state.emitted = True
                self.counters.windows_emitted += 1
                out.append(self._result(state, is_update=False))
            if end + self.allowed_lateness_s <= wm:
                del self.windows[key]
        horizon = wm - self.allowed_lateness_s - self.size_s
        self.seen = {k: ts for k, ts in self.seen.items() if ts >= horizon}
        return out

    def flush(self) -> list[WindowResult]:
        """End of a bounded stream: emit every open window."""
        out = []
        for key in sorted(self.windows, key=lambda k: (k[1], k[0])):
            state = self.windows[key]
            if not state.emitted:
                state.emitted = True
                self.counters.windows_emitted += 1
                out.append(self._result(state, is_update=False))
        self.windows.clear()
        return out

    def _result(self, s: WindowState, is_update: bool) -> WindowResult:
        return WindowResult(
            sensor_id=s.sensor_id,
            site=s.site,
            window_start=s.window_start,
            window_end=s.window_start + self.size_s,
            count=s.count,
            temp_mean=round(s.temp_sum / s.count, 4),
            temp_min=s.temp_min,
            temp_max=s.temp_max,
            humidity_mean=round(s.hum_sum / s.count, 4),
            vibration_max=s.vib_max,
            is_update=is_update,
        )

    # ---- checkpointing -------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "partition_max": {str(p): v for p, v in self.partition_max.items()},
            "windows": [asdict(w) for w in self.windows.values()],
            "seen": [[s, q, ts] for (s, q), ts in self.seen.items()],
            "counters": asdict(self.counters),
        }

    def restore(self, snap: dict) -> None:
        self.partition_max = {int(p): float(v) for p, v in snap["partition_max"].items()}
        self.windows = {}
        for w in snap["windows"]:
            st = WindowState(**w)
            self.windows[(st.sensor_id, st.window_start)] = st
        self.seen = {(s, int(q)): float(ts) for s, q, ts in snap["seen"]}
        self.counters = Counters(**snap["counters"])
