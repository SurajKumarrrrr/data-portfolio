from sensorstream.generator import GeneratorConfig, generate


def test_deterministic():
    cfg = GeneratorConfig(n_sensors=3, duration_s=600, seed=1)
    assert generate(cfg).messages == generate(cfg).messages


def test_injects_problems():
    s = generate(GeneratorConfig(n_sensors=6, duration_s=3600, seed=3))
    assert s.stats["clean"] == 6 * 720
    assert len(s.messages) == s.stats["clean"] + s.stats["duplicates"] + s.stats["malformed"]
    assert s.stats["duplicates"] > 0 and s.stats["late"] > 0
