from sensorstream.broker import InMemoryBroker, partition_for


def test_same_key_same_partition():
    assert partition_for(b"sensor-001", 3) == partition_for(b"sensor-001", 3)


def test_per_key_order_preserved_and_all_records_consumed():
    broker = InMemoryBroker(3)
    msgs = [(f"k{i % 5}".encode(), str(i).encode()) for i in range(200)]
    broker.producer().send_many(msgs)
    consumer = broker.consumer(chunk=7)
    got = []
    while batch := consumer.poll(max_records=33):
        assert len(batch) <= 33
        got.extend(batch)
    assert len(got) == 200
    for k in {k for k, _ in msgs}:
        values = [int(r.value) for r in got if r.key == k]
        assert values == sorted(values)


def test_seek_replays_from_offset():
    broker = InMemoryBroker(1)
    broker.producer().send_many([(b"k", str(i).encode()) for i in range(10)])
    c = broker.consumer()
    c.poll()
    c.seek(0, 8)
    assert [r.offset for r in c.poll()] == [8, 9]
