# Deploying StudySager to GCP

Architecture: two Cloud Run services (backend FastAPI, frontend nginx/React) + a small Cloud SQL
Postgres instance (durable user accounts, chat history) + a Cloud Storage bucket (durable resume
files and each user's Chroma vector DB, backed up after processing and restored automatically on
a cold start).

This matters because Cloud Run containers have **ephemeral local disk** - the SQLite file, the
Chroma DB, and uploaded resumes the app currently keeps on local disk would all be wiped on every
redeploy or scale-to-zero cold start if left as-is. The code changes already made
(`app/db.py` → SQLAlchemy against Postgres, `app/services/gcs_storage.py` → GCS backup/restore)
handle this: locally, nothing changes (still SQLite + local disk, since `DATABASE_URL` and
`GCS_BUCKET_NAME` are unset); in Cloud Run, those two env vars switch both over to the durable
backends automatically.

**I can't run the actual deployment for you** - I don't have credentials for your GCP account in
this sandbox, and provisioning billed cloud resources is something you should run yourself with
your own authenticated `gcloud` session. Everything below is ready to run as-is.

## Prerequisites (do these once, in a terminal on your Mac)

1. Install the gcloud CLI: `brew install --cask google-cloud-sdk` (or see
   [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)).
2. `gcloud auth login` and `gcloud auth application-default login`.
3. Make sure billing is enabled on your GCP project (Console → Billing).
4. Install Docker Desktop if you want to test the images locally first (optional - Cloud Build
   builds them remotely either way, so this isn't required to deploy).

## Cost note

This is a genuinely low-cost setup for personal/light use, not free:

- Cloud Run: scales to zero when idle - you only pay for actual request time. Roughly a few
  dollars/month for occasional personal use.
- Cloud SQL `db-f1-micro`: **does not scale to zero** - this is the main recurring cost, roughly
  $8-10/month even completely idle. If you want to avoid this entirely, see "Cheaper alternative"
  below.
- Cloud Storage: pennies/month for resume-sized files.

**Cheaper alternative**: skip Cloud SQL and instead mount a GCS bucket as a Cloud Run volume for
the SQLite file directly (`gcloud run deploy --add-volume` with `type=cloud-storage`). This keeps
everything serverless with no always-on cost, at the tradeoff of SQLite-over-GCS-FUSE having
weaker write-concurrency guarantees than a real Postgres instance - fine for a single-user or
low-concurrency personal deployment, riskier if multiple people hit it at once. Ask me if you'd
rather set this up instead - it's a smaller code change (skip the SQLAlchemy Postgres path
entirely, just point `APP_DATA_DIR` at the mounted volume).

## Deploy

1. Open `deploy.sh` at the project root and fill in the variables at the top: your
   `PROJECT_ID`, a `DB_PASSWORD`, a `JWT_SECRET` (long random string - do not reuse the one in
   your local `.env`), and your LLM provider keys (same values as `backend/.env`).
2. From the `studysager/` folder:
   ```
   chmod +x deploy.sh
   ./deploy.sh
   ```
3. This takes roughly 10-15 minutes (Cloud SQL instance creation is the slow part). It will
   print the frontend's live URL at the end.

What it does, in order: enables the needed GCP APIs, creates an Artifact Registry repo for your
Docker images, creates the Cloud SQL Postgres instance + database + user, creates the GCS bucket,
stores your API keys in Secret Manager (never baked into the image or committed to git), builds
and deploys the backend to Cloud Run wired to Cloud SQL via its built-in Unix socket connection,
builds and deploys the frontend to Cloud Run pointed at the backend's URL, then updates the
backend's CORS allow-list to include the frontend's URL now that it's known.

## After the first deploy

- **Redeploying after a code change**: re-run the relevant build+deploy block from `deploy.sh`
  (or just re-run the whole script - it's idempotent, existing resources are skipped/updated
  rather than recreated).
- **Custom domain**: `gcloud run domain-mappings create --service studysager-frontend
  --domain yourdomain.com --region us-central1` (requires domain verification in Search Console
  first).
- **Logs**: `gcloud run services logs read studysager-backend --region us-central1`.
- **Rolling back**: `gcloud run services update-traffic studysager-backend --to-revisions
  REVISION=100` (list revisions with `gcloud run revisions list --service studysager-backend`).

## Local development is unaffected

Nothing about local `npm run dev` / `uvicorn` workflow changes - `DATABASE_URL` and
`GCS_BUCKET_NAME` are simply unset locally, so `db.py` falls back to the SQLite file and
`gcs_storage.py`'s functions become no-ops, exactly like before this migration.
