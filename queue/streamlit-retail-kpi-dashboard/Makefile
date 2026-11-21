.PHONY: install data test lint run report clean

export PYTHONPATH := src

install:
	pip install -r requirements.txt

data:
	python -m retail_kpi.generate --out data

test:
	pytest -q

lint:
	ruff check .

report: data
	python -m retail_kpi.report --data data

run: data
	streamlit run app.py

clean:
	rm -rf data .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
