#!/bin/bash
# Deploys StudySager to Google Cloud Run + Cloud SQL (Postgres) + Cloud Storage.
#
# WHAT THIS DOES: builds and deploys both the backend (FastAPI) and frontend (React/nginx) as
# two separate Cloud Run services, backed by a small Cloud SQL Postgres instance (durable user
# accounts/chat history) and a GCS bucket (durable resume files + Chroma vector DB backups).
#
# HOW TO RUN:
#   1. Copy deploy.env.example to deploy.env and fill in your real values there. deploy.env is
#      gitignored, so it's safe to commit/push this repo (including this script) without ever
#      leaking your DB password, JWT secret, or API keys - they live only in that local file
#      and, from there, in GCP Secret Manager (never in git, never baked into a Docker image).
#   2. From the studysager/ project root: chmod +x deploy.sh && ./deploy.sh
#
# You need the gcloud CLI installed and authenticated (`gcloud auth login`) with billing enabled
# on the target project. This script runs real gcloud commands against your account and WILL
# incur GCP costs (see the cost note in DEPLOY.md) - review it before running.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/deploy.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE - copy deploy.env.example to deploy.env and fill in your real values first."
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

REGION="${REGION:-us-central1}"
: "${PROJECT_ID:?Set PROJECT_ID in deploy.env}"
: "${DB_PASSWORD:?Set DB_PASSWORD in deploy.env}"
: "${JWT_SECRET:?Set JWT_SECRET in deploy.env}"

REPO="studysager"
SQL_INSTANCE="studysager-db"
DB_NAME="studysager"
DB_USER="studysager"
BUCKET="${PROJECT_ID}-studysager-data"
BACKEND_SVC="studysager-backend"
FRONTEND_SVC="studysager-frontend"

gcloud config set project "$PROJECT_ID"

echo "== Enabling required APIs =="
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com storage.googleapis.com

echo "== Artifact Registry repo (Docker images) =="
gcloud artifacts repositories create "$REPO" --repository-format=docker \
  --location="$REGION" --description="StudySager images" 2>/dev/null || echo "repo already exists, skipping"

echo "== Cloud SQL Postgres instance (this step takes 5-10 minutes) =="
gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1 || \
gcloud sql instances create "$SQL_INSTANCE" \
  --database-version=POSTGRES_15 --tier=db-f1-micro --region="$REGION" \
  --storage-size=10GB --storage-auto-increase

gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" 2>/dev/null || echo "db already exists, skipping"
gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD" 2>/dev/null || \
gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD"

SQL_CONNECTION_NAME=$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')

echo "== Cloud Storage bucket (durable resume + Chroma backups) =="
gcloud storage buckets create "gs://$BUCKET" --location="$REGION" 2>/dev/null || echo "bucket already exists, skipping"

echo "== Secret Manager (API keys never get baked into the image or committed) =="
create_or_update_secret() {
  local name="$1" value="$2"
  [ -z "$value" ] && return 0
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    echo -n "$value" | gcloud secrets versions add "$name" --data-file=-
  else
    echo -n "$value" | gcloud secrets create "$name" --data-file=-
  fi
}
create_or_update_secret studysager-jwt-secret "$JWT_SECRET"
create_or_update_secret studysager-db-password "$DB_PASSWORD"
create_or_update_secret studysager-groq-key "$GROQ_API_KEY"
create_or_update_secret studysager-hf-token "$HF_API_TOKEN"
create_or_update_secret studysager-gemini-key "$GEMINI_API_KEY"
create_or_update_secret studysager-deepseek-key "$DEEPSEEK_API_KEY"

echo "== Building backend image via Cloud Build =="
gcloud builds submit backend --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/backend:latest"

echo "== Deploying backend to Cloud Run =="
# DATABASE_URL uses the Unix socket Cloud Run mounts automatically when --add-cloudsql-instances
# is set - no separate Cloud SQL Proxy sidecar needed.
DATABASE_URL="postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${SQL_CONNECTION_NAME}"

gcloud run deploy "$BACKEND_SVC" \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/backend:latest" \
  --region "$REGION" --platform managed --allow-unauthenticated \
  --add-cloudsql-instances "$SQL_CONNECTION_NAME" \
  --set-env-vars "DATABASE_URL=${DATABASE_URL},GCS_BUCKET_NAME=${BUCKET}" \
  --set-secrets "JWT_SECRET=studysager-jwt-secret:latest,GROQ_API_KEY=studysager-groq-key:latest,HF_API_TOKEN=studysager-hf-token:latest,GEMINI_API_KEY=studysager-gemini-key:latest,DEEPSEEK_API_KEY=studysager-deepseek-key:latest" \
  --memory 1Gi --cpu 1 --min-instances 0 --max-instances 4

BACKEND_URL=$(gcloud run services describe "$BACKEND_SVC" --region "$REGION" --format='value(status.url)')
echo "Backend deployed at: $BACKEND_URL"

echo "== Building frontend image via Cloud Build =="
gcloud builds submit frontend --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/frontend:latest"

echo "== Deploying frontend to Cloud Run =="
gcloud run deploy "$FRONTEND_SVC" \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/frontend:latest" \
  --region "$REGION" --platform managed --allow-unauthenticated \
  --set-env-vars "API_URL=${BACKEND_URL}" \
  --memory 256Mi --cpu 1 --min-instances 0 --max-instances 4

FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SVC" --region "$REGION" --format='value(status.url)')
echo "Frontend deployed at: $FRONTEND_URL"

echo "== Re-deploying backend with the frontend's URL allowed in CORS =="
gcloud run services update "$BACKEND_SVC" --region "$REGION" \
  --update-env-vars "EXTRA_CORS_ORIGINS=${FRONTEND_URL}"

echo ""
echo "Done. Open: $FRONTEND_URL"
