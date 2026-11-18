install:
	pip install -r requirements.txt

lint:
	ruff check .

test:
	pytest -q

run:
	python -m ecom.pipeline

docs: run
	cd dbt_project && DUCKDB_PATH=../warehouse.duckdb dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .

clean:
	rm -rf data warehouse.duckdb dbt_project/target dbt_project/logs logs .pytest_cache .ruff_cache

.PHONY: install lint test run docs clean
