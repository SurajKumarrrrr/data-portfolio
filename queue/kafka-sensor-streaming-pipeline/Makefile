.PHONY: install test lint run up down

install:
	pip install -r requirements.txt

lint:
	ruff check .

test:
	pytest -q

# Runs the full pipeline offline against the in-memory broker
run:
	PYTHONPATH=src python -m sensorstream run --mode memory --db data/sensors.db

# Real Kafka (KRaft) + producer + consumer via docker compose
up:
	docker compose up --build

down:
	docker compose down -v
