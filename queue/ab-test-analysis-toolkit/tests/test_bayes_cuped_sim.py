import numpy as np
import pytest

from abtest.bayesian import beta_binomial, decide
from abtest.cuped import cuped_adjust
from abtest.simulation import simulate_peeking, simulate_power


def test_bayes_clear_winner():
    r = beta_binomial(500, 10_000, 650, 10_000)
    assert r.prob_treatment_better > 0.999
    assert r.expected_loss_treatment < r.expected_loss_control
    assert r.rel_lift_ci_low > 0
    assert decide(r) == "ship treatment"


def test_bayes_symmetric_when_equal():
    r = beta_binomial(300, 5_000, 300, 5_000, seed=1)
    assert r.prob_treatment_better == pytest.approx(0.5, abs=0.01)
    assert r.expected_loss_treatment == pytest.approx(r.expected_loss_control, rel=0.05)
    assert decide(r, loss_threshold=1e-5) == "keep collecting data"


def test_bayes_posterior_mean_uses_prior():
    r = beta_binomial(0, 0, 10, 10, prior=(1, 1))
    assert r.control_posterior_mean == 0.5
    assert r.treatment_posterior_mean == pytest.approx(11 / 12)


def test_cuped_reduces_variance_and_keeps_effect():
    rng = np.random.default_rng(1)
    n = 20_000
    x = rng.normal(50, 10, n)
    treat = rng.random(n) < 0.5
    y = 0.8 * x + rng.normal(0, 5, n) + 2.0 * treat
    res = cuped_adjust(y, x)
    assert res.theta == pytest.approx(0.8, abs=0.03)
    assert res.variance_reduction > 0.6
    raw = y[treat].mean() - y[~treat].mean()
    adj = res.adjusted[treat].mean() - res.adjusted[~treat].mean()
    assert adj == pytest.approx(2.0, abs=0.15)
    assert abs(adj - raw) < 0.5


def test_cuped_constant_covariate_is_noop():
    y = np.arange(10.0)
    res = cuped_adjust(y, np.ones(10))
    assert res.variance_reduction == 0
    np.testing.assert_array_equal(res.adjusted, y)


def test_empirical_power_and_type1_error():
    assert simulate_power(0.1, 0.1, 5000, n_sims=4000, seed=1) == pytest.approx(0.05, abs=0.015)
    assert simulate_power(0.10, 0.12, 3841, n_sims=4000, seed=1) == pytest.approx(0.80, abs=0.03)


def test_peeking_inflates_false_positives():
    res = simulate_peeking(0.1, 10_000, n_looks=10, n_sims=3000, seed=2)
    assert res["fixed_horizon_fpr"] == pytest.approx(0.05, abs=0.015)
    assert res["peeking_fpr"] > 0.12
    assert res["bonferroni_peeking_fpr"] <= 0.05
