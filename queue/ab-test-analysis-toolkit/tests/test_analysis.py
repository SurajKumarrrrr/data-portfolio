import json

from abtest.analysis import Metric, analyze_experiment, make_decision
from abtest.data import assign_variant, generate_experiment
from abtest.frequentist import TestResult
from abtest.report import render_markdown
from abtest.run import main


def test_assignment_is_deterministic_and_balanced():
    assert assign_variant("u1") == assign_variant("u1")
    share = sum(assign_variant(f"u{i}") == "treatment" for i in range(20_000)) / 20_000
    assert 0.48 < share < 0.52
    flips = sum(assign_variant(f"u{i}") != assign_variant(f"u{i}", salt="other")
                for i in range(2_000))
    assert 800 < flips < 1200  # a new salt re-randomises


def test_generator_is_reproducible(experiment_df):
    again = generate_experiment(n_users=20_000, seed=7)
    assert experiment_df.equals(again)
    assert set(experiment_df["variant"]) == {"control", "treatment"}
    assert (experiment_df.loc[experiment_df.converted == 0, "revenue"] == 0).all()


def test_analysis_structure(experiment_df):
    a = analyze_experiment(experiment_df, n_boot=200)
    assert a.n_control + a.n_treatment == len(experiment_df)
    assert not a.srm["srm_detected"]
    assert [r.metric for r in a.results] == ["converted", "add_to_cart", "revenue"]
    assert all(a.adjusted_p[r.metric] >= r.p_value for r in a.results)
    assert "revenue" in a.cuped and a.cuped["revenue"]["variance_reduction"] > 0
    assert {s["segment"] for s in a.segments} == {"mobile", "desktop"}
    md = render_markdown(a)
    assert "Decision" in md and "converted" in md


def test_no_effect_experiment_is_not_shipped():
    df = generate_experiment(30_000, seed=11, effects={"conversion_log_odds": 0.0,
                                                       "add_to_cart_log_odds": 0.0})
    a = analyze_experiment(df, n_boot=100)
    assert a.decision.startswith("INCONCLUSIVE")


def test_big_effect_is_detected():
    df = generate_experiment(30_000, seed=5, effects={"conversion_log_odds": 0.3})
    a = analyze_experiment(df, n_boot=100)
    assert a.decision == "SHIP"
    assert a.bayes["prob_treatment_better"] > 0.99


def test_srm_blocks_decision(experiment_df):
    broken = experiment_df.drop(experiment_df[experiment_df.variant == "treatment"].index[:1500])
    a = analyze_experiment(broken, n_boot=50)
    assert a.decision.startswith("INVALID")


def _res(name, diff):
    return TestResult(name, "x", 1, 1 + diff, diff, diff - 1, diff + 1, diff, 0, 0, 0, 0.01)


def test_guardrail_veto():
    roles = {"conv": "primary", "latency": "guardrail"}
    results = [_res("conv", 0.1), _res("latency", -0.2)]
    srm = {"srm_detected": False}
    d = make_decision(srm, results, {"conv": 0.01, "latency": 0.01}, roles, 0.05)
    assert d.startswith("DO NOT SHIP: guardrail")
    d = make_decision(srm, results, {"conv": 0.01, "latency": 0.5}, roles, 0.05)
    assert d == "SHIP"


def test_custom_metrics_without_segments(experiment_df):
    a = analyze_experiment(experiment_df, metrics=(Metric("converted", "binary", "primary"),),
                           segment_col=None)
    assert len(a.results) == 1 and a.segments == [] and a.cuped == {}


def test_cli_writes_reports(tmp_path):
    payload = main(["--n-users", "5000", "--sims", "200", "--out", str(tmp_path)])
    assert (tmp_path / "report.md").exists()
    data = json.loads((tmp_path / "results.json").read_text())
    assert data["plan"]["n_per_group"] == payload["plan"]["n_per_group"]
    assert len(data["results"]) == 3
