"""Broker abstraction with an in-memory implementation and a Kafka adapter.

The pipeline only talks to the small ``Producer`` / ``Source`` protocols, so the
exact same processing code runs against a real Kafka cluster (docker compose)
and against ``InMemoryBroker`` in tests and offline demos.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Record:
    partition: int
    offset: int
    key: bytes
    value: bytes


class Producer(Protocol):
    def send(self, key: bytes, value: bytes) -> None: ...
    def flush(self) -> None: ...


class Source(Protocol):
    def partitions(self) -> list[int]: ...
    def seek(self, partition: int, offset: int) -> None: ...
    def poll(self, max_records: int = 500) -> list[Record]: ...


def partition_for(key: bytes, n_partitions: int) -> int:
    """Deterministic key -> partition mapping (same key, same partition)."""
    return zlib.crc32(key) % n_partitions


class InMemoryBroker:
    """A single topic with N append-only partitions."""

    def __init__(self, n_partitions: int = 3) -> None:
        self.n_partitions = n_partitions
        self.logs: list[list[tuple[bytes, bytes]]] = [[] for _ in range(n_partitions)]

    def producer(self) -> InMemoryProducer:
        return InMemoryProducer(self)

    def consumer(self, chunk: int = 50) -> InMemoryConsumer:
        return InMemoryConsumer(self, chunk)


class InMemoryProducer:
    def __init__(self, broker: InMemoryBroker) -> None:
        self.broker = broker

    def send(self, key: bytes, value: bytes) -> None:
        self.broker.logs[partition_for(key, self.broker.n_partitions)].append((key, value))

    def send_many(self, messages: Iterable[tuple[bytes, bytes]]) -> int:
        n = 0
        for key, value in messages:
            self.send(key, value)
            n += 1
        return n

    def flush(self) -> None:  # nothing buffered
        return None


class InMemoryConsumer:
    """Round-robin poll over all partitions, ``chunk`` records per partition per turn.

    Reading partitions unevenly is realistic: it makes event time advance at a
    different pace per partition, which is exactly why the watermark is the
    minimum over partitions.
    """

    def __init__(self, broker: InMemoryBroker, chunk: int = 50) -> None:
        self.broker = broker
        self.chunk = chunk
        self.positions = [0] * broker.n_partitions

    def partitions(self) -> list[int]:
        return list(range(self.broker.n_partitions))

    def seek(self, partition: int, offset: int) -> None:
        self.positions[partition] = offset

    def poll(self, max_records: int = 500) -> list[Record]:
        out: list[Record] = []
        progressed = True
        while len(out) < max_records and progressed:
            progressed = False
            for p, log in enumerate(self.broker.logs):
                start = self.positions[p]
                end = min(len(log), start + self.chunk, start + max_records - len(out))
                for off in range(start, end):
                    key, value = log[off]
                    out.append(Record(p, off, key, value))
                if end > start:
                    self.positions[p] = end
                    progressed = True
                if len(out) >= max_records:
                    break
        return out


class KafkaProducerAdapter:  # pragma: no cover - needs a running broker
    def __init__(self, bootstrap: str, topic: str) -> None:
        from kafka import KafkaProducer

        self.topic = topic
        self._p = KafkaProducer(bootstrap_servers=bootstrap, acks="all", linger_ms=20)

    def send(self, key: bytes, value: bytes) -> None:
        self._p.send(self.topic, key=key, value=value)

    def flush(self) -> None:
        self._p.flush()


class KafkaSourceAdapter:  # pragma: no cover - needs a running broker
    """Manually assigned consumer; offsets are managed by the sink, not by Kafka."""

    def __init__(self, bootstrap: str, topic: str) -> None:
        from kafka import KafkaConsumer, TopicPartition

        self._tp = TopicPartition
        self.topic = topic
        self._c = KafkaConsumer(
            bootstrap_servers=bootstrap, enable_auto_commit=False, auto_offset_reset="earliest"
        )
        parts = self._c.partitions_for_topic(topic) or set()
        self._parts = sorted(parts)
        self._c.assign([TopicPartition(topic, p) for p in self._parts])
        self._c.seek_to_beginning()

    def partitions(self) -> list[int]:
        return list(self._parts)

    def seek(self, partition: int, offset: int) -> None:
        self._c.seek(self._tp(self.topic, partition), offset)

    def poll(self, max_records: int = 500) -> list[Record]:
        batches = self._c.poll(timeout_ms=1000, max_records=max_records)
        out = [
            Record(tp.partition, m.offset, m.key or b"", m.value)
            for tp, msgs in batches.items()
            for m in msgs
        ]
        return sorted(out, key=lambda r: (r.partition, r.offset))
