FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir "kafka-python>=2.0,<4" "pandas>=2.0,<4"
COPY src ./src
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "sensorstream"]
