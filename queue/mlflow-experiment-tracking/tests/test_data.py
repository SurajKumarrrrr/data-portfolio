import pandas as pd

from mlflow_tracking.data import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    dataset_fingerprint,
    generate_credit_data,
)


def test_deterministic():
    pd.testing.assert_frame_equal(generate_credit_data(500, 1), generate_credit_data(500, 1))


def test_fingerprint_tracks_content():
    a = generate_credit_data(500, 1)
    assert dataset_fingerprint(a) == dataset_fingerprint(generate_credit_data(500, 1))
    assert dataset_fingerprint(a) != dataset_fingerprint(generate_credit_data(500, 2))
    b = a.copy()
    b.loc[0, "age"] += 1
    assert dataset_fingerprint(a) != dataset_fingerprint(b)


def test_schema_and_ranges():
    df = generate_credit_data(3000, 42)
    assert list(df.columns) == NUMERIC_FEATURES + CATEGORICAL_FEATURES + [TARGET]
    assert df.isna().sum().sum() == 0
    assert df["age"].between(19, 70).all()
    assert (df["debt_to_income"] >= 0).all()
    assert 0.08 < df[TARGET].mean() < 0.25


def test_signal_exists():
    df = generate_credit_data(4000, 42)
    late = df.groupby(df["late_payments_12m"] > 0)[TARGET].mean()
    assert late[True] > late[False]
