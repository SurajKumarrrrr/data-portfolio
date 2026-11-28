PY ?= python
export PYTHONPATH := src

.PHONY: install test lint run ui clean

install:
	$(PY) -m pip install -r requirements.txt

lint:
	ruff check .

test:
	$(PY) -m pytest -q

run:
	$(PY) -m mlflow_tracking.cli all --config configs/experiments.yaml

ui:
	mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

clean:
	rm -rf mlflow.db mlartifacts reports/*.md .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
