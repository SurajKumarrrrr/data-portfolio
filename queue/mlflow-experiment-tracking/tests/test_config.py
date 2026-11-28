import pytest
import yaml

from mlflow_tracking.config import load_config, parse_config


def test_parse_valid(small_raw):
    cfg = parse_config(small_raw)
    assert cfg.seed == 7
    assert [c.name for c in cfg.candidates] == ["lr", "rf"]
    assert cfg.data.n_samples == 900


@pytest.mark.parametrize("key", ["experiment_name", "registered_model_name", "candidates"])
def test_missing_required_key(small_raw, key):
    del small_raw[key]
    with pytest.raises(ValueError, match=key):
        parse_config(small_raw)


def test_unknown_model_rejected(small_raw):
    small_raw["candidates"][0]["model"] = "xgboost_magic"
    with pytest.raises(ValueError, match="unknown model"):
        parse_config(small_raw)


def test_duplicate_names_rejected(small_raw):
    small_raw["candidates"][1]["name"] = "lr"
    with pytest.raises(ValueError, match="unique"):
        parse_config(small_raw)


def test_invalid_test_size(small_raw):
    small_raw["data"]["test_size"] = 0.9
    with pytest.raises(ValueError, match="test_size"):
        parse_config(small_raw)


def test_fingerprint_stable_and_sensitive(small_raw):
    a = parse_config(small_raw).fingerprint()
    assert a == parse_config(small_raw).fingerprint()
    small_raw["candidates"][0]["params"]["C"] = 0.5
    assert parse_config(small_raw).fingerprint() != a


def test_load_config_from_yaml(tmp_path, small_raw):
    path = tmp_path / "exp.yaml"
    path.write_text(yaml.safe_dump(small_raw))
    assert load_config(path).registered_model_name == "test-model"


def test_shipped_config_is_valid():
    cfg = load_config("configs/experiments.yaml")
    assert len(cfg.candidates) >= 3
