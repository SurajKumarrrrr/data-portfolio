import pytest

from abtest.data import generate_experiment


@pytest.fixture(scope="session")
def experiment_df():
    return generate_experiment(n_users=20_000, seed=7)
