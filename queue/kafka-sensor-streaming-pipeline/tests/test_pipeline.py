import pytest

from sensorstream.broker import InMemoryBroker
from sensorstream.evaluate import alert_quality, window_accuracy
from sensorstream.pipeline import PipelineConfig, StreamProcessor
from sensorstream.sink import SQLiteSink

TABLE = "SELECT * FROM window_aggregates ORDER BY sensor_id, window_start"


def run(stream, crash_after=None, batch_size=200):
    broker = InMemoryBroker(3)
    broker.producer().send_many(stream.messages)
    sink = SQLiteSink()
    cfg = PipelineConfig(batch_size=batch_size)
    if crash_after:
        StreamProcessor(broker.consumer(), sink, cfg).run(max_batches=crash_after)
    StreamProcessor(broker.consumer(), sink, cfg).run()
    return sink


def test_end_to_end_counts(small_stream):
    sink = run(small_stream)
    dead = sink.query("SELECT COUNT(*) FROM dead_letters")[0][0]
    assert dead == small_stream.stats["malformed"]
    total = sink.query("SELECT SUM(count) FROM window_aggregates")[0][0]
    # every clean reading is counted once, except events beyond allowed lateness
    assert small_stream.stats["clean"] - small_stream.stats["late"] <= total
    assert total <= small_stream.stats["clean"]


def test_matches_batch_ground_truth(small_stream):
    acc = window_accuracy(run(small_stream), small_stream.truth, 60)
    assert acc["streamed_windows"] == acc["expected_windows"]
    assert acc["exact_match_pct"] > 97


@pytest.mark.parametrize("crash_after", [1, 7, 23])
def test_crash_and_resume_gives_identical_output(small_stream, crash_after):
    clean = run(small_stream).query(TABLE)
    resumed = run(small_stream, crash_after=crash_after).query(TABLE)
    assert resumed == clean


def test_replaying_a_batch_is_idempotent(small_stream):
    broker = InMemoryBroker(3)
    broker.producer().send_many(small_stream.messages)
    sink = SQLiteSink()
    StreamProcessor(broker.consumer(), sink).run()
    before = sink.query(TABLE)
    sink.conn.execute("DELETE FROM consumer_offsets")
    sink.conn.execute("DELETE FROM checkpoints")
    StreamProcessor(broker.consumer(), sink).run()  # full replay from offset 0
    assert sink.query(TABLE) == before


def test_zscore_detects_all_incidents(small_stream):
    q = alert_quality(run(small_stream), small_stream.overheat, 60)
    n = len(small_stream.overheat)
    assert q["ewma_zscore"]["incidents_detected"] == f"{n}/{n}"
    assert q["ewma_zscore"]["precision"] > 0.8
