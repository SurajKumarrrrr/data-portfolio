import pytest

from gersent.data import generate_reviews


@pytest.fixture(scope="session")
def reviews():
    return generate_reviews(1500, seed=11)
