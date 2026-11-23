.PHONY: install test lint run gate clean

PY ?= python

install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e .

lint:
	ruff check .

test:
	$(PY) -m pytest -q

# Generate defective data, validate it, score detection against the injected-defect manifest.
run:
	$(PY) -m dq_checks generate --out data/raw --customers 500 --seed 42 --defects-per-type 3
	$(PY) -m dq_checks evaluate --data-dir data/raw --out-dir reports

# The CI gate: clean data must pass (exit 0), defective data must be blocked (exit 1).
gate:
	$(PY) -m dq_checks generate --out data/clean --clean
	$(PY) -m dq_checks validate --data-dir data/clean --out-dir reports/clean --fail-on warning
	$(PY) -m dq_checks generate --out data/raw
	! $(PY) -m dq_checks validate --data-dir data/raw --out-dir reports/raw

clean:
	rm -rf data reports .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
