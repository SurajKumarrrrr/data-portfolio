.PHONY: install data test lint run clean

export PYTHONPATH := src
ROWS ?= 150000

install:
	pip install -r requirements.txt

data:
	python -m taxi_batch.generate --rows $(ROWS) --out data/raw/trips

test:
	pytest -q

lint:
	ruff check .

run: data
	python -m taxi_batch.job --input data/raw/trips --zones data/reference/taxi_zones.csv --output data/output

clean:
	rm -rf data/raw data/output spark-warehouse .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
