import sys
try:
    # Debian slim's system sqlite3 is older than the 3.35+ that chromadb requires. pysqlite3-binary
    # ships a modern statically-linked sqlite3 build; swapping it into sys.modules BEFORE anything
    # (langchain-chroma/chromadb included) imports the stdlib sqlite3 module makes every downstream
    # `import sqlite3` transparently get the newer build instead. Must be the very first thing that
    # runs in this file - any import above this would import the old sqlite3 first and it'd be too
    # late. Only installed on Linux x86_64 (see requirements.txt), so this no-ops on Mac/dev.
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import CORS_ORIGINS
from app.routers import auth, onboarding, chat, hybrid_chat, level_chat, jd_chat, general_jd_chat, resume_tailor, chat_sessions, resume_sync, payments
from app import db

app = FastAPI(title="StudySager API", version="0.1.0")


@app.on_event("startup")
def _startup():
    # Creates any missing tables once per process (not per-request like the old sqlite3-per-call
    # pattern did) - works identically against the local SQLite file or a Cloud SQL Postgres
    # instance, since db.py's schema is defined via dialect-portable SQLAlchemy Table objects.
    db.init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(chat.router)
app.include_router(hybrid_chat.router)
app.include_router(level_chat.router)
app.include_router(jd_chat.router)
app.include_router(general_jd_chat.router)
app.include_router(resume_tailor.router)
app.include_router(chat_sessions.router)
app.include_router(resume_sync.router)
app.include_router(payments.router)


@app.get("/health")
def health():
    return {"status": "ok"}
