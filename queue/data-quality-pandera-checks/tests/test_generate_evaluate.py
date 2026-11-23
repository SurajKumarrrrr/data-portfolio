from dq_checks.evaluate import detection_report, unexpected_flags
from dq_checks.generate import DEFECT_TYPES, generate
from dq_checks.validate import validate_tables


def test_generator_is_deterministic():
    a = generate(n_customers=50, seed=11, defects_per_type=1)
    b = generate(n_customers=50, seed=11, defects_per_type=1)
    for name in ("customers", "orders", "order_items"):
        assert a.tables()[name].equals(b.tables()[name])
    assert a.defects.equals(b.defects)


def test_every_defect_type_is_injected(dirty_dataset):
    assert set(dirty_dataset.defects["defect_type"]) == set(DEFECT_TYPES)


def test_all_injected_defects_detected_without_extra_flags(dirty_dataset, as_of):
    result = validate_tables(dirty_dataset.tables(), as_of)
    det = detection_report(result.failures, dirty_dataset.defects)
    assert (det["recall"] == 1.0).all(), det[det["recall"] < 1]
    assert unexpected_flags(result.failures, dirty_dataset.defects).empty


def test_detection_report_counts_misses(dirty_dataset, as_of):
    result = validate_tables(dirty_dataset.tables(), as_of)
    without_email_rule = result.failures[result.failures["rule"] != "email_format"]
    det = detection_report(without_email_rule, dirty_dataset.defects).set_index("defect_type")
    assert det.loc["malformed_email", "detected"] == 0
    assert det.loc["malformed_email", "recall"] == 0.0
