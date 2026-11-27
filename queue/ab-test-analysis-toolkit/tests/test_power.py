import math

import pytest

from abtest.power import (
    duration_days,
    mde_proportions,
    power_proportions,
    sample_size_means,
    sample_size_proportions,
)


def test_sample_size_matches_textbook_value():
    # 10% -> 12% at alpha=0.05, power=0.8: classic answer is ~3,841 per group
    assert sample_size_proportions(0.10, 0.02, relative=False) == 3841
    assert sample_size_proportions(0.10, 0.20) == 3841


def test_sample_size_grows_with_smaller_effect_and_higher_power():
    base = sample_size_proportions(0.05, 0.10)
    assert sample_size_proportions(0.05, 0.05) > 3.5 * base
    assert sample_size_proportions(0.05, 0.10, power=0.9) > base


def test_sample_size_means_formula():
    # (1.96 + 0.8416)^2 * 2 * sd^2 / mde^2 with sd=10, mde=1 -> 1570
    assert sample_size_means(10, 1) == 1570


def test_power_at_planned_sample_is_target():
    n = sample_size_proportions(0.08, 0.10)
    assert power_proportions(0.08, 0.10, n) == pytest.approx(0.8, abs=0.002)


def test_mde_inverts_sample_size():
    n = sample_size_proportions(0.08, 0.10)
    assert mde_proportions(0.08, n) == pytest.approx(0.10, rel=0.01)


def test_unequal_allocation_needs_more_control_users_when_ratio_small():
    assert sample_size_proportions(0.1, 0.1, ratio=0.5) > sample_size_proportions(0.1, 0.1)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        sample_size_proportions(0.9, 0.2)  # target rate > 1
    with pytest.raises(ValueError):
        sample_size_means(0, 1)
    with pytest.raises(ValueError):
        mde_proportions(0.5, 2)


def test_duration():
    assert duration_days(10_000, 3_000) == math.ceil(20_000 / 3_000)
    assert duration_days(10_000, 3_000, traffic_share=0.5) == 14
