import pytest

from mlflow_tracking.config import Candidate
from mlflow_tracking.data import TARGET, generate_credit_data
from mlflow_tracking.models import build_pipeline


@pytest.mark.parametrize(
    "model,params",
    [
        ("logistic_regression", {"C": 0.5}),
        ("random_forest", {"n_estimators": 10, "max_depth": 3}),
        ("hist_gradient_boosting", {"max_iter": 20}),
    ],
)
def test_pipeline_fits_and_predicts(model, params):
    df = generate_credit_data(400, 3)
    X, y = df.drop(columns=[TARGET]), df[TARGET]
    pipe = build_pipeline(Candidate("c", model, params), seed=0)
    pipe.fit(X, y)
    proba = pipe.predict_proba(X)
    assert proba.shape == (400, 2)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_unseen_category_is_handled():
    df = generate_credit_data(400, 3)
    X, y = df.drop(columns=[TARGET]), df[TARGET]
    for model in ("logistic_regression", "random_forest"):
        pipe = build_pipeline(Candidate("c", model, {}), seed=0).fit(X, y)
        X_new = X.head(3).copy()
        X_new["loan_purpose"] = "wedding"
        assert pipe.predict_proba(X_new).shape == (3, 2)


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        build_pipeline(Candidate("c", "svm", {}), seed=0)
