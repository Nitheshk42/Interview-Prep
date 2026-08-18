import os
from pathlib import Path
from dotenv import load_dotenv

# backend/.env - loaded once, on import, before anything else reads os.environ.
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = Path(os.getenv("APP_DATA_DIR") or (BACKEND_ROOT / "data"))
DATA_ROOT.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_ROOT / "studysager.db"
CHROMA_DB_ROOT = DATA_ROOT / "chroma_db"
UPLOADS_ROOT = DATA_ROOT / "uploads"

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-to-a-random-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days - a browser tab session shouldn't need to re-login daily

# Local dev: unset -> falls back to the SQLite file at DB_PATH (see db.py). In production, set
# this to a Postgres connection string (Render's managed Postgres, Cloud SQL, Supabase, etc.) so
# user accounts/chats survive redeploys instead of living on the container's ephemeral disk.
# SQLAlchemy's engine understands both dialects transparently, so db.py itself never needs to
# know which one is active.
_raw_database_url = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
# Render (and Heroku, and others) hand back "postgres://..." - a scheme name SQLAlchemy's
# psycopg2 driver doesn't recognize (it wants "postgresql://" or "postgresql+psycopg2://").
# Normalizing here means the raw value from the platform can be used as-is everywhere else.
if _raw_database_url.startswith("postgres://"):
    _raw_database_url = _raw_database_url.replace("postgres://", "postgresql+psycopg2://", 1)
DATABASE_URL = _raw_database_url

# Local dev: unset -> resumes/Chroma vector data live only on local disk (fine, it's durable
# there). In Cloud Run, set this to a GCS bucket name so uploaded resumes and each user's Chroma
# collection are backed up after every (re)process and restored automatically on a cold start
# (see gcs_storage.py) - the container's own disk is wiped on every new instance/redeploy.
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")

# Comma-separated list of extra allowed origins (e.g. your deployed frontend's Cloud Run URL or
# custom domain) - added on top of the local Vite dev server origins below.
_EXTRA_ORIGINS = [o.strip() for o in os.getenv("EXTRA_CORS_ORIGINS", "").split(",") if o.strip()]

CORS_ORIGINS = [
    "http://localhost:5173",  # Vite dev server default
    "http://127.0.0.1:5173",
    *_EXTRA_ORIGINS,
]

# Monetization (Career Sprint one-time purchase) - all three unset by default, which keeps the
# whole payments feature dormant (see routers/payments.py: it returns a clear 503 instead of a
# raw Stripe SDK error when these are missing). Set these in backend/.env locally or in Render's
# environment settings when actually turning monetization on - nothing here charges anyone until
# STRIPE_SECRET_KEY is a real live/test key.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_SPRINT = os.getenv("STRIPE_PRICE_ID_SPRINT", "")
# Where Stripe Checkout redirects after a successful/cancelled payment - the deployed frontend
# origin in production, the Vite dev server locally.
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
SPRINT_DURATION_DAYS = 14
