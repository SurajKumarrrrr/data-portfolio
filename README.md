# Data Science & Data Engineering Portfolio

Suraj Kumar Ajampudi (SK) · M.Sc. Data Science, Hochschule Fulda · ~2 years Data Engineering experience · Frankfurt am Main

Each project below is a standalone repo with runnable code, tests, CI and a README explaining the problem, approach and results.
Stack across the projects: Python, SQL, pandas/Polars, PySpark, dbt, Airflow, DuckDB/PostgreSQL, Docker, FastAPI, scikit-learn, Streamlit, GitHub Actions.

## Projects

| Project | What it shows | Added |
|---|---|---|
| [db-delay-etl-pipeline](https://github.com/SurajKumarrrrr/db-delay-etl-pipeline) | Idempotent batch ETL for Deutsche Bahn-style train delay data: Python, pandas, DuckDB star schema, punctuality KPIs, CI | 2026-11-16 |
| [sql-interview-case-studies](https://github.com/SurajKumarrrrr/sql-interview-case-studies) | 15 SQL case studies (window functions, cohorts, gaps & islands) on e-commerce data, auto-tested on PostgreSQL + DuckDB | 2026-11-16 |
| [fastapi-churn-prediction-service](https://github.com/SurajKumarrrrr/fastapi-churn-prediction-service) | Churn model (scikit-learn) served via FastAPI + Docker: validated API, tests, CI and a generated model card | 2026-11-17 |
| [dbt-duckdb-ecommerce-analytics](https://github.com/SurajKumarrrrr/dbt-duckdb-ecommerce-analytics) | dbt + DuckDB ELT project: raw → staging → star schema marts for e-commerce, 67 data tests, CI | 2026-11-18 |
| [airflow-energy-price-pipeline](https://github.com/SurajKumarrrrr/airflow-energy-price-pipeline) | Airflow 3 DAG loading German day-ahead power prices (SMARD-style) into DuckDB: idempotent, DST-safe, tested | 2026-11-19 |
| [frankfurt-rent-price-analysis](https://github.com/SurajKumarrrrr/frankfurt-rent-price-analysis) | Rent analysis for Frankfurt-style listings: data cleaning, EDA, Ridge vs gradient boosting, effect recovery | 2026-11-20 |
| [streamlit-retail-kpi-dashboard](https://github.com/SurajKumarrrrr/streamlit-retail-kpi-dashboard) | Interactive Streamlit retail KPI dashboard on DuckDB: parameterised SQL, filters, cached queries, tested | 2026-11-21 |
| [pyspark-batch-taxi-processing](https://github.com/SurajKumarrrrr/pyspark-batch-taxi-processing) | PySpark batch job for NYC-TLC-style taxi trips: data-quality quarantine, broadcast joins, window ranks, partitioned Parquet | 2026-11-22 |
| [data-quality-pandera-checks](https://github.com/SurajKumarrrrr/data-quality-pandera-checks) | Reusable data-quality layer: pandera contracts, cross-table checks, quarantine + failing-row reports, CI gate | 2026-11-23 |
| [kafka-sensor-streaming-pipeline](https://github.com/SurajKumarrrrr/kafka-sensor-streaming-pipeline) | Kafka IoT sensor streaming pipeline: event-time tumbling windows, watermarks, DLQ, idempotent SQLite sink, docker-compose | 2026-11-24 |
| [german-review-sentiment-nlp](https://github.com/SurajKumarrrrr/german-review-sentiment-nlp) | German product-review sentiment: TF-IDF + negation baselines vs a tiny PyTorch Transformer, slice eval | 2026-11-25 |
| [energy-demand-forecasting](https://github.com/SurajKumarrrrr/energy-demand-forecasting) | Day-ahead forecasting of German-style hourly electricity load: naive baselines, SARIMA, gradient boosting, rolling backtest | 2026-11-26 |
| [ab-test-analysis-toolkit](https://github.com/SurajKumarrrrr/ab-test-analysis-toolkit) | A/B testing toolkit: power analysis, z/Welch tests, CUPED, Bayesian Beta-Binomial, SRM checks, peeking simulation | 2026-11-27 |
| [mlflow-experiment-tracking](https://github.com/SurajKumarrrrr/mlflow-experiment-tracking) | Reproducible ML training with MLflow: config-driven experiments, model registry with champion/challenger gate, reports | 2026-11-28 |
