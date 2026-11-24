"""Command line entry points.

* ``run --mode memory``  - generate, produce, consume and evaluate fully offline.
* ``produce``            - push the synthetic stream to a real Kafka topic.
* ``consume``            - run the stream processor against a real Kafka topic.
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from sensorstream.broker import InMemoryBroker
from sensorstream.evaluate import alert_quality, window_accuracy
from sensorstream.generator import GeneratorConfig, generate
from sensorstream.pipeline import PipelineConfig, StreamProcessor
from sensorstream.sink import SQLiteSink


def run_memory(db: str, seed: int, crash_after: int | None, partitions: int) -> dict:
    stream = generate(GeneratorConfig(seed=seed))
    broker = InMemoryBroker(partitions)
    broker.producer().send_many(stream.messages)
    cfg = PipelineConfig()
    sink = SQLiteSink(db)

    restarts, before_crash, seconds = 0, 0, 0.0
    if crash_after:
        first = StreamProcessor(broker.consumer(), sink, cfg).run(max_batches=crash_after)
        restarts, before_crash, seconds = 1, first.records, first.seconds
    proc = StreamProcessor(broker.consumer(), sink, cfg)  # resumes from checkpoint
    stats = proc.run()
    seconds += stats.seconds

    top = sink.query(
        "SELECT site, COUNT(*), ROUND(AVG(temp_mean), 2), ROUND(MAX(temp_max), 2) "
        "FROM window_aggregates GROUP BY site ORDER BY site"
    )
    report = {
        "generator": {**stream.stats, "messages_total": len(stream.messages)},
        "pipeline": {
            "partitions": partitions,
            "restarts": restarts,
            "records_before_crash": before_crash,
            "records_after_restart": stats.records,
            "dead_letters": sink.query("SELECT COUNT(*) FROM dead_letters")[0][0],
            **stats.extra,
            "throughput_msgs_per_s": round((before_crash + stats.records) / seconds),
        },
        "window_accuracy": window_accuracy(sink, stream.truth, cfg.window_s),
        "alerts": alert_quality(sink, stream.overheat, cfg.window_s),
        "per_site": [
            {"site": s, "windows": n, "avg_temp_c": a, "max_temp_c": m} for s, n, a, m in top
        ],
    }
    sink.close()
    return report


def produce_kafka(bootstrap: str, topic: str, seed: int, speedup: float) -> int:
    from sensorstream.broker import KafkaProducerAdapter

    cfg = GeneratorConfig(seed=seed)
    stream = generate(cfg)
    producer = KafkaProducerAdapter(bootstrap, topic)
    tick = cfg.interval_s / speedup if speedup > 0 else 0.0  # one tick = n_sensors msgs
    for i, (key, value) in enumerate(stream.messages, start=1):
        producer.send(key, value)
        if tick and i % cfg.n_sensors == 0:
            time.sleep(tick)
    producer.flush()
    return len(stream.messages)


def consume_kafka(bootstrap: str, topic: str, db: str, idle_timeout: float) -> dict:
    from sensorstream.broker import KafkaSourceAdapter

    sink = SQLiteSink(db)
    proc = StreamProcessor(KafkaSourceAdapter(bootstrap, topic), sink)
    stats = proc.run(idle_timeout_s=idle_timeout, flush_at_end=False)
    return {"records": stats.records, "windows_written": stats.windows_written,
            "alerts": stats.alerts, "dead_letters": stats.dead_letters, **stats.extra}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="sensorstream")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="offline end-to-end run with the in-memory broker")
    r.add_argument("--mode", choices=["memory"], default="memory")
    r.add_argument("--db", default="data/sensors.db")
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--partitions", type=int, default=3)
    r.add_argument("--crash-after", type=int, default=15,
                   help="simulate a consumer crash after N batches (0 = no crash)")

    p = sub.add_parser("produce", help="send the synthetic stream to Kafka")
    p.add_argument("--bootstrap", default="localhost:9092")
    p.add_argument("--topic", default="sensor-readings")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--speedup", type=float, default=0, help="0 = as fast as possible")

    c = sub.add_parser("consume", help="run the stream processor against Kafka")
    c.add_argument("--bootstrap", default="localhost:9092")
    c.add_argument("--topic", default="sensor-readings")
    c.add_argument("--db", default="data/sensors.db")
    c.add_argument("--idle-timeout", type=float, default=30.0)

    a = ap.parse_args(argv)
    if a.cmd == "run":
        out = run_memory(a.db, a.seed, a.crash_after or None, a.partitions)
    elif a.cmd == "produce":
        out = {"sent": produce_kafka(a.bootstrap, a.topic, a.seed, a.speedup)}
    else:
        out = consume_kafka(a.bootstrap, a.topic, a.db, a.idle_timeout)
    print(json.dumps(out, indent=2))
    return 0
