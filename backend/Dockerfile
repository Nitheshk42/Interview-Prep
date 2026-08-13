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

# Both Cloud Run's and Render's container filesystems are writable but ephemeral - app data
# resets on redeploy/cold start either way (durable state, where configured, lives in Cloud SQL +
# Cloud Storage - see app/db.py and app/services/gcs_storage.py). Deliberately NOT using /tmp:
# some sandboxed container runtimes (observed on Render) give /tmp inconsistent enough file-
# identity semantics that SQLite - which Chroma uses internally - trips its READONLY_DBMOVED
# safety check and refuses to write, even though the directory is genuinely writable. A plain
# directory under the app's own working directory doesn't have this problem on either platform.
RUN mkdir -p /app/data
ENV APP_DATA_DIR=/app/data
ENV PORT=8080

EXPOSE 8080

# 2 workers is a reasonable default for Cloud Run's typical 1-2 vCPU allocation; each worker
# handles requests via uvicorn's async event loop. --timeout raised because LLM calls (JD/vendor
# Q&A generation especially) can legitimately take 20-60s.
CMD exec gunicorn -k uvicorn.workers.UvicornWorker -w 2 --timeout 120 -b 0.0.0.0:${PORT} app.main:app
