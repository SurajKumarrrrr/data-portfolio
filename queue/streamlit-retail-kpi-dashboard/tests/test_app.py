"""Smoke test of the Streamlit UI with Streamlit's headless AppTest runner."""

from pathlib import Path

import pytest

from tests.conftest import write_tiny_dataset

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RETAIL_KPI_DATA_DIR", str(write_tiny_dataset(tmp_path / "data")))
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def test_app_renders_kpis_without_errors(app):
    assert not app.exception
    labels = [m.label for m in app.metric]
    assert labels == [
        "Net revenue", "Orders", "Avg order value", "Customers", "Gross margin", "Return rate",
    ]
    assert app.metric[0].value == "€88"  # 60 (Jan) + 28 (Feb)
    assert app.metric[1].value == "4"


def test_category_filter_updates_metrics(app):
    app.sidebar.multiselect[1].select("Fashion").run()  # Region, Category, Channel
    assert not app.exception
    assert app.metric[0].value == "€50"

