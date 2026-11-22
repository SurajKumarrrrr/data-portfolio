# Project roadmap

The daily builder takes the first unchecked item, builds it, and ticks it off.
Reorder, add or delete lines freely. Format: `- [ ] repo-name — one-line idea`.

- [x] db-delay-etl-pipeline — ETL pipeline for Deutsche Bahn-style train delay data: extract, clean, load into DuckDB, delay KPIs per station/hour
- [x] sql-interview-case-studies — 15 SQL problems (window functions, CTEs, gaps & islands) on a Dockerised PostgreSQL e-commerce schema, with tested solutions
- [x] fastapi-churn-prediction-service — scikit-learn churn model served with FastAPI + Docker, with input validation, tests and a model card
- [x] dbt-duckdb-ecommerce-analytics — dbt project on DuckDB: staging → marts, tests, docs, star schema for orders/customers
- [x] airflow-energy-price-pipeline — Airflow DAG ingesting German day-ahead electricity prices (SMARD-style), idempotent daily loads, docker-compose
- [x] frankfurt-rent-price-analysis — EDA and regression on Frankfurt rental listings (synthetic, realistic), feature importance, clear findings
- [x] streamlit-retail-kpi-dashboard — interactive Streamlit dashboard for sales KPIs with filters and cached queries
- [x] pyspark-batch-taxi-processing — PySpark batch job: partitioning, joins, aggregations, local Spark, unit tests with chispa
- [ ] data-quality-pandera-checks — reusable data-quality layer with pandera schemas, failing-row reports and CI gate
- [ ] kafka-sensor-streaming-pipeline — docker-compose Kafka producer/consumer for IoT sensor data with windowed aggregates
- [ ] german-review-sentiment-nlp — sentiment classification for German product reviews (TF-IDF baseline vs small transformer)
- [ ] energy-demand-forecasting — time-series forecasting of German electricity load: baselines, SARIMA, gradient boosting, backtesting
- [ ] ab-test-analysis-toolkit — A/B testing library: power analysis, frequentist + Bayesian tests, report generation
- [ ] mlflow-experiment-tracking — reproducible ML training with MLflow tracking, model registry and comparison report
- [ ] customer-segmentation-rfm — RFM + KMeans customer segmentation with business-ready segment profiles
- [ ] fraud-detection-imbalanced — fraud detection on imbalanced data: SMOTE vs class weights, PR-AUC, threshold tuning
- [ ] incremental-api-ingestion — incremental REST API ingestion with watermarks, retries, pagination and state handling
- [ ] gtfs-transit-analysis-rhein-main — analysis of a GTFS public-transport feed (RMV-style): service frequency, coverage maps
- [ ] polars-vs-pandas-benchmark — reproducible benchmark of Polars vs pandas vs DuckDB on common transformations
- [ ] delta-lake-local-lakehouse — local lakehouse with delta-rs: bronze/silver/gold layers, time travel, schema evolution
- [ ] data-contracts-pydantic — data contracts between producer and consumer with Pydantic, versioning and contract tests
- [ ] cli-data-profiler — installable Python CLI that profiles CSV/Parquet files and outputs an HTML report
- [ ] iot-anomaly-detection — anomaly detection on machine sensor data (Isolation Forest, rolling z-scores), Industrie 4.0 framing
- [ ] recommender-system-implicit — product recommender with implicit feedback (ALS) and offline evaluation (precision@k)
- [ ] postgres-cdc-pipeline — change data capture from PostgreSQL with logical replication into an analytics table
- [ ] terraform-aws-data-lake — Terraform for an S3 + Glue + Athena data lake, with tflint/checkov in CI (plan only)
- [ ] geo-analysis-germany — geospatial analysis with GeoPandas: population vs public services per German district
- [ ] local-rag-document-qa — document Q&A over German PDFs with local embeddings and a small evaluation set
- [ ] scd2-dimension-loader — Slowly Changing Dimension Type 2 loader in SQL + Python with full test coverage
- [ ] data-pipeline-observability — pipeline monitoring: run metadata, freshness/volume checks, alerting via webhook
