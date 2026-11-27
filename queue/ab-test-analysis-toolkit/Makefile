.PHONY: install test lint run quick clean

install:
	pip install -r requirements.txt
	pip install -e .

lint:
	ruff check .

test:
	pytest -q

run:
	PYTHONPATH=src python -m abtest.run --n-users 60000 --out reports

quick:
	PYTHONPATH=src python -m abtest.run --n-users 10000 --sims 300 --out reports

clean:
	rm -rf reports/*.md reports/*.json .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
