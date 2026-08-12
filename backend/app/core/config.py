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

CORS_ORIGINS = [
    "http://localhost:5173",  # Vite dev server default
    "http://127.0.0.1:5173",
]
