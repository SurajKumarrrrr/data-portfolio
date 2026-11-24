import math

from sensorstream.windowing import TumblingWindowAggregator


def agg(**kw):
    defaults = dict(size_s=60, max_out_of_order_s=10, allowed_lateness_s=120)
    defaults.update(kw)
    return TumblingWindowAggregator([0], **defaults)


def test_window_assignment():
    a = agg()
    assert a.window_start(0) == 0
    assert a.window_start(59.9) == 0
    assert a.window_start(60) == 60


def test_window_emitted_only_after_watermark_passes_end(make_reading):
    a = agg()
    assert a.process(0, make_reading(seq=0, ts=10, temp=40)) == []
    assert a.process(0, make_reading(seq=1, ts=50, temp=42)) == []
    assert a.process(0, make_reading(seq=2, ts=65, temp=50)) == []  # wm = 55 < 60
    out = a.process(0, make_reading(seq=3, ts=71, temp=50))  # wm = 61
    assert len(out) == 1
    w = out[0]
    assert (w.window_start, w.count, w.temp_mean, w.temp_max) == (0, 2, 41.0, 42.0)
    assert not w.is_update


def test_out_of_order_within_bound_is_included(make_reading):
    a = agg()
    a.process(0, make_reading(seq=1, ts=55))
    a.process(0, make_reading(seq=0, ts=45))  # arrives after a newer event
    out = a.process(0, make_reading(seq=2, ts=75))
    assert out[0].count == 2


def test_late_event_updates_emitted_window(make_reading):
    a = agg()
    a.process(0, make_reading(seq=0, ts=10, temp=40))
    a.process(0, make_reading(seq=5, ts=100, temp=40))  # wm 90 -> emit [0,60)
    out = a.process(0, make_reading(seq=1, ts=20, temp=46))  # late, within lateness
    assert len(out) == 1 and out[0].is_update
    assert out[0].count == 2 and out[0].temp_mean == 43.0
    assert a.counters.late_updates == 1


def test_too_late_event_dropped(make_reading):
    a = agg()
    a.process(0, make_reading(seq=0, ts=10))
    a.process(0, make_reading(seq=9, ts=400))  # wm 390 > 60 + 120
    assert a.process(0, make_reading(seq=1, ts=20)) == []
    assert a.counters.dropped_late == 1


def test_duplicates_ignored(make_reading):
    a = agg()
    r = make_reading(seq=0, ts=10)
    a.process(0, r)
    a.process(0, r)
    assert a.counters.duplicates == 1
    assert a.flush()[0].count == 1


def test_watermark_is_min_over_partitions(make_reading):
    a = TumblingWindowAggregator([0, 1], size_s=60, max_out_of_order_s=0)
    a.process(0, make_reading("a", 0, 500))
    assert a.watermark == -math.inf  # partition 1 has not delivered anything yet
    out = a.process(1, make_reading("b", 0, 30))
    assert a.watermark == 30 and out == []
    out = a.process(1, make_reading("b", 1, 61))
    assert [w.sensor_id for w in out] == ["b"]


def test_snapshot_restore_roundtrip(make_reading):
    a = agg()
    for i in range(5):
        a.process(0, make_reading(seq=i, ts=i * 20))
    b = agg()
    b.restore(a.snapshot())
    assert b.watermark == a.watermark
    assert b.flush() == a.flush()
