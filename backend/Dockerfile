# Cloud Run listens on $PORT (defaults to 8080) - gunicorn is bound to that below.
FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 (Postgres) and building any wheels without prebuilt binaries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run's filesystem is writable but ephemeral - point app data at /tmp so it's always
# writable regardless of how the container is deployed. Durable state lives in Cloud SQL +
# Cloud Storage (see app/db.py and app/services/gcs_storage.py), so this being ephemeral is fine.
ENV APP_DATA_DIR=/tmp/data
ENV PORT=8080

EXPOSE 8080

# 2 workers is a reasonable default for Cloud Run's typical 1-2 vCPU allocation; each worker
# handles requests via uvicorn's async event loop. --timeout raised because LLM calls (JD/vendor
# Q&A generation especially) can legitimately take 20-60s.
CMD exec gunicorn -k uvicorn.workers.UvicornWorker -w 2 --timeout 120 -b 0.0.0.0:${PORT} app.main:app
