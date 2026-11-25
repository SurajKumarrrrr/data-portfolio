.PHONY: install install-cpu lint test run data clean

install:
	pip install -r requirements.txt

# smaller download: CPU-only PyTorch wheel
install-cpu:
	pip install torch --index-url https://download.pytorch.org/whl/cpu
	pip install -r requirements.txt

lint:
	ruff check .

test:
	pytest -q

# full experiment: 6,000 synthetic reviews, 4 baselines + tiny Transformer (~2 min on CPU)
run:
	PYTHONPATH=src python -m gersent run --out reports

data:
	PYTHONPATH=src python -m gersent generate --out data/reviews.csv

clean:
	rm -rf reports data .pytest_cache .ruff_cache
