import pandas as pd
import pytest

from dq_checks.generate import AS_OF, generate


def as_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Mimic a CSV load: everything becomes a string (or missing)."""
    return df.astype("object").where(df.notna(), None).map(lambda v: None if v is None else str(v))


@pytest.fixture(scope="session")
def clean_dataset():
    return generate(n_customers=120, seed=1, defects_per_type=0)


@pytest.fixture(scope="session")
def dirty_dataset():
    return generate(n_customers=200, seed=3, defects_per_type=2)


@pytest.fixture
def clean_raw(clean_dataset):
    return {name: as_raw(df) for name, df in clean_dataset.tables().items()}


@pytest.fixture
def as_of():
    return AS_OF
