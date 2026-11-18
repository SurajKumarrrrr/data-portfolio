from pathlib import Path

import pytest

from ecom.generate import GenConfig, generate


@pytest.fixture(scope="session")
def small_cfg() -> GenConfig:
    return GenConfig(n_customers=300, n_products=60, seed=7)


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory: pytest.TempPathFactory, small_cfg: GenConfig) -> Path:
    out = tmp_path_factory.mktemp("raw")
    generate(out, small_cfg)
    return out
