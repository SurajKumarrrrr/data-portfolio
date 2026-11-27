import numpy as np
import pytest
from scipy import stats

from abtest.frequentist import (
    adjust_pvalues,
    bootstrap_diff_ci,
    srm_check,
    two_proportion_ztest,
    welch_ttest,
)


def test_ztest_matches_chi_square_without_correction():
    r = two_proportion_ztest(200, 2000, 250, 2000)
    chi2, p, _, _ = stats.chi2_contingency([[200, 1800], [250, 1750]], correction=False)
    assert r.p_value == pytest.approx(p, rel=1e-9)
    assert r.statistic**2 == pytest.approx(chi2, rel=1e-9)
    assert r.abs_diff == pytest.approx(0.025)
    assert r.rel_lift == pytest.approx(0.25)
    assert r.ci_low < r.abs_diff < r.ci_high


def test_ztest_identical_groups():
    r = two_proportion_ztest(100, 1000, 100, 1000)
    assert r.p_value == pytest.approx(1.0)
    assert r.ci_low < 0 < r.ci_high


def test_ztest_rejects_bad_counts():
    with pytest.raises(ValueError):
        two_proportion_ztest(11, 10, 5, 10)


def test_welch_matches_scipy():
    rng = np.random.default_rng(1)
    a, b = rng.normal(10, 2, 300), rng.normal(10.5, 4, 500)
    r = welch_ttest(a, b)
    ref = stats.ttest_ind(b, a, equal_var=False)
    assert r.p_value == pytest.approx(ref.pvalue, rel=1e-9)
    assert r.statistic == pytest.approx(ref.statistic, rel=1e-9)


def test_relative_ci_covers_true_lift_most_of_the_time():
    rng = np.random.default_rng(3)
    covered = 0
    for _ in range(400):
        a, b = rng.exponential(10, 2000), rng.exponential(11, 2000)
        r = welch_ttest(a, b)
        covered += r.rel_ci_low <= 0.1 <= r.rel_ci_high
    assert 0.92 <= covered / 400 <= 0.98


def test_bootstrap_close_to_welch_ci():
    rng = np.random.default_rng(2)
    a, b = rng.normal(0, 1, 2000), rng.normal(0.1, 1, 2000)
    lo, hi = bootstrap_diff_ci(a, b, n_boot=1000, seed=0)
    r = welch_ttest(a, b)
    assert lo == pytest.approx(r.ci_low, abs=0.01)
    assert hi == pytest.approx(r.ci_high, abs=0.01)


def test_srm_detects_broken_split():
    assert not srm_check([5000, 5040], [0.5, 0.5])["srm_detected"]
    assert srm_check([5000, 5400], [0.5, 0.5])["srm_detected"]
    assert not srm_check([9000, 1010], [0.9, 0.1])["srm_detected"]


def test_holm_and_bh_known_values():
    p = [0.01, 0.04, 0.03, 0.005]
    assert adjust_pvalues(p, "holm") == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert adjust_pvalues(p, "bh") == pytest.approx([0.02, 0.04, 0.04, 0.02])
    with pytest.raises(ValueError):
        adjust_pvalues(p, "nope")


def test_adjusted_pvalues_capped_at_one():
    assert max(adjust_pvalues([0.6, 0.7, 0.9], "holm")) == 1.0
