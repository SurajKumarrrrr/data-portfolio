PY ?= python3
export PYTHONPATH := src

.PHONY: install install-airflow test lint run report airflow-up clean

install:
	$(PY) -m pip install -r requirements-dev.txt

install-airflow:
	$(PY) -m pip install -r requirements-airflow.txt \
	  --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.1.8/constraints-3.12.txt

lint:
	ruff check .

test:
	$(PY) -m pytest -q

## Full-year demo: backfill 2025 with one simulated bad day, re-run to show idempotency, write report
run:
	-$(PY) -m energy_pipeline backfill --start 2025-01-01 --end 2025-12-31 --drop-hour-on 2025-08-14
	$(PY) -m energy_pipeline backfill --start 2025-01-01 --end 2025-12-31
	$(PY) -m energy_pipeline report --out reports/summary.md

airflow-up:
	docker compose up --build

clean:
	rm -rf data reports .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
