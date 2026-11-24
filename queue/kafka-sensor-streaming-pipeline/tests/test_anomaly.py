from sensorstream.anomaly import AnomalyDetector
from sensorstream.windowing import WindowResult


def win(ts, mean, mx=None, update=False):
    return WindowResult("s1", "x", ts, ts + 60, 12, mean, mean - 1, mx or mean + 1, 45, 2,
                        update)


def test_static_threshold():
    d = AnomalyDetector(temp_limit_c=75)
    assert [a.rule for a in d.check(win(0, 70, mx=80))] == ["static_threshold"]


def test_zscore_needs_warmup_then_fires_on_step():
    d = AnomalyDetector(warmup=5, z_threshold=5)
    for i in range(5):
        assert d.check(win(i * 60, 40 + 0.1 * (i % 2))) == []
    alerts = d.check(win(600, 60))
    assert [a.rule for a in alerts] == ["ewma_zscore"]
    assert alerts[0].value > 5


def test_anomalous_windows_do_not_shift_baseline():
    d = AnomalyDetector(warmup=3)
    for i in range(5):
        d.check(win(i * 60, 40))
    before = d.baselines["s1"].mean
    d.check(win(400, 70))
    assert d.baselines["s1"].mean == before


def test_late_updates_skip_baseline():
    d = AnomalyDetector()
    d.check(win(0, 40))
    d.check(win(0, 41, update=True))
    assert d.baselines["s1"].n == 1
