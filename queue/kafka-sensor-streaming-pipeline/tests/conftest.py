import pytest

from sensorstream.generator import GeneratorConfig, generate
from sensorstream.models import SensorReading


@pytest.fixture
def make_reading():
    def _make(sensor="s1", seq=0, ts=0.0, temp=40.0, site="frankfurt") -> SensorReading:
        return SensorReading(sensor, site, seq, ts, temp, 45.0, 2.0)

    return _make


@pytest.fixture(scope="session")
def small_stream():
    return generate(GeneratorConfig(n_sensors=6, duration_s=60 * 60, seed=7))
