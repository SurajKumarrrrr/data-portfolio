"""DAG integrity test – runs only where Airflow is installed (see requirements-airflow.txt)."""

from pathlib import Path

import pytest

pytest.importorskip("airflow")

DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"


def test_dag_imports_and_structure():
    from airflow.models import DagBag

    bag = DagBag(dag_folder=str(DAGS_DIR), include_examples=False)
    assert bag.import_errors == {}
    dag = bag.dags.get("energy_day_ahead_prices")  # no metadata DB needed
    assert dag is not None
    assert dag.max_active_runs == 1
    assert dag.task_dict["extract"].downstream_task_ids == {"validate"}
    assert dag.task_dict["validate"].downstream_task_ids == {"load"}
    assert dag.task_dict["load"].downstream_task_ids == {"check_loaded"}
    assert dag.task_dict["validate"].retries == 0
    assert dag.task_dict["extract"].retries == 3
