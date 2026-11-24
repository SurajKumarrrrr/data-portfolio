"""The consumer loop: poll -> validate -> dedup/window -> detect -> commit."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from sensorstream.anomaly import Alert, AnomalyDetector
from sensorstream.broker import Source
from sensorstream.models import InvalidMessage, parse_reading
from sensorstream.sink import SQLiteSink
from sensorstream.windowing import TumblingWindowAggregator, WindowResult

log = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    group: str = "sensor-aggregator"
    window_s: float = 60.0
    max_out_of_order_s: float = 15.0
    allowed_lateness_s: float = 300.0
    batch_size: int = 500
    temp_limit_c: float = 75.0
    z_threshold: float = 5.0


@dataclass
class RunStats:
    batches: int = 0
    records: int = 0
    dead_letters: int = 0
    windows_written: int = 0
    alerts: int = 0
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)


class StreamProcessor:
    def __init__(self, source: Source, sink: SQLiteSink, cfg: PipelineConfig | None = None):
        self.source = source
        self.sink = sink
        self.cfg = cfg or PipelineConfig()
        self.agg = TumblingWindowAggregator(
            source.partitions(),
            size_s=self.cfg.window_s,
            max_out_of_order_s=self.cfg.max_out_of_order_s,
            allowed_lateness_s=self.cfg.allowed_lateness_s,
        )
        self.detector = AnomalyDetector(self.cfg.temp_limit_c, self.cfg.z_threshold)
        self.stats = RunStats()
        self._resume()

    def _resume(self) -> None:
        offsets, state = self.sink.load_checkpoint(self.cfg.group)
        for p, off in offsets.items():
            self.source.seek(p, off)
        if state:
            self.agg.restore(state["aggregator"])
            self.detector.restore(state["detector"])
            log.info("resumed from checkpoint at offsets %s", offsets)

    def _state(self) -> dict:
        return {"aggregator": self.agg.snapshot(), "detector": self.detector.snapshot()}

    def step(self) -> int:
        """Process one polled batch and commit it atomically. Returns #records."""
        records = self.source.poll(self.cfg.batch_size)
        if not records:
            return 0
        windows: list[WindowResult] = []
        dead: list[tuple[int, int, str, bytes]] = []
        offsets: dict[int, int] = {}
        for rec in records:
            offsets[rec.partition] = rec.offset + 1
            try:
                reading = parse_reading(rec.value)
            except InvalidMessage as exc:
                dead.append((rec.partition, rec.offset, str(exc), rec.value))
                continue
            windows.extend(self.agg.process(rec.partition, reading))
        alerts = self._detect(windows)
        self.sink.commit_batch(self.cfg.group, windows, alerts, dead, offsets, self._state())
        self._count(records=len(records), windows=len(windows), alerts=len(alerts), dead=len(dead))
        return len(records)

    def _detect(self, windows: list[WindowResult]) -> list[Alert]:
        return [a for w in windows for a in self.detector.check(w)]

    def _count(self, records: int, windows: int, alerts: int, dead: int) -> None:
        self.stats.batches += 1
        self.stats.records += records
        self.stats.windows_written += windows
        self.stats.alerts += alerts
        self.stats.dead_letters += dead

    def flush(self) -> None:
        """Emit all open windows (only for bounded/replayed streams)."""
        windows = self.agg.flush()
        alerts = self._detect(windows)
        self.sink.commit_batch(self.cfg.group, windows, alerts, [], {}, self._state())
        self._count(records=0, windows=len(windows), alerts=len(alerts), dead=0)

    def run(
        self,
        max_batches: int | None = None,
        idle_timeout_s: float = 0.0,
        flush_at_end: bool = True,
    ) -> RunStats:
        """Run until the source is drained (or idle for ``idle_timeout_s``)."""
        t0 = time.perf_counter()
        idle_since: float | None = None
        n = 0
        while max_batches is None or n < max_batches:
            got = self.step()
            n += 1
            if got:
                idle_since = None
                continue
            now = time.monotonic()
            idle_since = idle_since or now
            if now - idle_since >= idle_timeout_s:
                break
        else:  # stopped by max_batches -> simulate a crash: no flush
            self.stats.seconds += time.perf_counter() - t0
            return self.stats
        if flush_at_end:
            self.flush()
        self.stats.seconds += time.perf_counter() - t0
        c = self.agg.counters
        self.stats.extra = {
            "accepted": c.accepted,
            "duplicates_dropped": c.duplicates,
            "late_updates": c.late_updates,
            "too_late_dropped": c.dropped_late,
        }
        return self.stats
