import pytest

from mlflow_tracking.registry import should_promote


def test_first_model_always_promoted():
    assert should_promote(0.70, None, 0.01) == (True, "no champion yet")


@pytest.mark.parametrize(
    "challenger,champion,min_imp,expected",
    [
        (0.80, 0.78, 0.01, True),
        (0.785, 0.78, 0.01, False),
        (0.78, 0.78, 0.0, True),
        (0.77, 0.78, 0.0, False),
    ],
)
def test_gate(challenger, champion, min_imp, expected):
    promoted, reason = should_promote(challenger, champion, min_imp)
    assert promoted is expected
    assert reason
