"""Storage layer - built on SQLAlchemy Core (not the ORM) so the exact same code works against
SQLite locally (DATABASE_URL unset -> falls back to the local file at DB_PATH) and against Cloud
SQL Postgres in production (DATABASE_URL set to a postgresql+psycopg2://... connection string,
see backend/app/core/config.py). Table DDL is expressed once via SQLAlchemy's MetaData/Table
objects, which generates the correct dialect-specific auto-increment syntax for either backend
automatically - no separate SQLite-vs-Postgres SQL to maintain. Every query uses SQLAlchemy's
text() with named (:param) bind parameters, which both dialects accept identically."""
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Text, ForeignKey
from app.core.config import DATABASE_URL
from app.core.security import hash_password, verify_password

_engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
_metadata = MetaData()

users = Table(
    "users", _metadata,
    Column("username", String(255), primary_key=True),
    Column("email", String(255)),
    Column("password_hash", Text, nullable=False),
)

profiles = Table(
    "profiles", _metadata,
    Column("username", String(255), ForeignKey("users.username"), primary_key=True),
    Column("level", String(50)),
    Column("resume_uploaded", Integer, server_default="0"),
    Column("favorite_tabs", Text, server_default=""),
    # Plain extracted resume text (not the file itself) - kept here so the vector store can be
    # silently rebuilt from it on a cold start where the local disk (and its Chroma files) got
    # wiped, e.g. a Render redeploy or free-tier spin-down. Without this, a user's resume
    # "vanishes" until they manually re-upload, even though their account/profile persisted fine
    # in Postgres - see vector_store.py's get_vectorstore() for the rebuild-on-demand logic.
    Column("resume_text", Text),
)

feedback = Table(
    "feedback", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(255)),
    Column("message", Text, nullable=False),
    Column("created_at", String(64)),
)

chat_sessions = Table(
    "chat_sessions", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(255), ForeignKey("users.username"), nullable=False),
    Column("section", String(64), nullable=False),
    Column("title", String(255), nullable=False, server_default="New chat"),
    Column("jd_hash", String(64)),
    Column("created_at", String(64)),
    Column("updated_at", String(64)),
)

chat_messages = Table(
    "chat_messages", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", Integer, ForeignKey("chat_sessions.id"), nullable=False),
    Column("question", Text, nullable=False),
    Column("response_json", Text, nullable=False),
    Column("created_at", String(64)),
)


def init_db():
    """Creates every table that doesn't exist yet, on either backend. Call once at app startup
    (see app/main.py) instead of on every request - avoids the DDL round-trip per query that the
    old sqlite3-per-call get_conn() pattern used to do.

    Gunicorn boots multiple worker processes, and each one runs this on startup against the same
    database file/instance. On a cold start (fresh, empty DB) two workers can both see "table
    doesn't exist yet" and both issue CREATE TABLE at nearly the same moment - one wins, the other
    gets an "already exists" OperationalError even though create_all() itself already checks
    first. That's a benign race, not a real failure (gunicorn just respawns the worker and it
    succeeds against the now-existing tables), so it's swallowed here instead of crashing the
    worker boot."""
    try:
        _metadata.create_all(_engine)
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise

    # create_all() only creates whole tables that don't exist yet - it never ALTERs an existing
    # table to add a column defined after that table was first created (e.g. profiles.resume_text,
    # added after the "profiles" table already existed in production Postgres). Each ALTER is
    # wrapped individually so one already-applied migration doesn't block the next, and a
    # column that already exists (re-running this on every boot, across workers) is a no-op.
    migrations = [
        "ALTER TABLE profiles ADD COLUMN resume_text TEXT",
    ]
    for stmt in migrations:
        try:
            with _engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as exc:
            if "already exists" not in str(exc).lower() and "duplicate column" not in str(exc).lower():
                raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_chat_session(username: str, section: str, title: str, jd_hash: str | None = None) -> int:
    # RETURNING id works on both backends (SQLite 3.35+ and Postgres) and avoids relying on
    # driver-specific lastrowid behavior, which psycopg2 doesn't reliably populate.
    now = _now()
    with _engine.begin() as conn:
        result = conn.execute(
            text("""INSERT INTO chat_sessions (username, section, title, jd_hash, created_at, updated_at)
                    VALUES (:username, :section, :title, :jd_hash, :now, :now) RETURNING id"""),
            {"username": username, "section": section, "title": (title or "New chat")[:80], "jd_hash": jd_hash, "now": now},
        )
        return result.scalar()


def find_session_by_jd_hash(username: str, section: str, jd_hash: str) -> int | None:
    """Looks up an existing session for this exact JD (by normalized hash) so a repeat JD can
    reuse its saved vendor Q&A instead of spending tokens generating it again."""
    with _engine.connect() as conn:
        row = conn.execute(
            text("""SELECT id FROM chat_sessions WHERE username = :username AND section = :section
                    AND jd_hash = :jd_hash ORDER BY id DESC LIMIT 1"""),
            {"username": username, "section": section, "jd_hash": jd_hash},
        ).fetchone()
        return row[0] if row else None


def list_chat_sessions(username: str, section: str) -> list[dict]:
    with _engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT s.id, s.title, s.updated_at, COUNT(m.id) as message_count
                    FROM chat_sessions s LEFT JOIN chat_messages m ON m.session_id = s.id
                    WHERE s.username = :username AND s.section = :section
                    GROUP BY s.id, s.title, s.updated_at ORDER BY s.updated_at DESC"""),
            {"username": username, "section": section},
        ).fetchall()
        return [{"id": r[0], "title": r[1], "updated_at": r[2], "message_count": r[3]} for r in rows]


def search_chat_sessions(username: str, section: str, query: str) -> list[dict]:
    """Matches against the session TITLE, every stored QUESTION, and the raw response JSON text
    (covers generated answers too, e.g. finding a past chat by something the model said, not
    just by what you typed) - a plain case-insensitive substring match, no LLM involved, so this
    costs nothing and works instantly even on a large history."""
    like = f"%{query.lower()}%"
    with _engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT s.id, s.title, s.updated_at, COUNT(m.id) as message_count
                    FROM chat_sessions s LEFT JOIN chat_messages m ON m.session_id = s.id
                    WHERE s.username = :username AND s.section = :section
                    AND s.id IN (
                        SELECT id FROM chat_sessions WHERE username = :username AND section = :section
                        AND LOWER(title) LIKE :like
                        UNION
                        SELECT session_id FROM chat_messages
                        WHERE LOWER(question) LIKE :like OR LOWER(response_json) LIKE :like
                    )
                    GROUP BY s.id, s.title, s.updated_at ORDER BY s.updated_at DESC"""),
            {"username": username, "section": section, "like": like},
        ).fetchall()
        return [{"id": r[0], "title": r[1], "updated_at": r[2], "message_count": r[3]} for r in rows]


def get_chat_session(username: str, session_id: int) -> dict | None:
    with _engine.connect() as conn:
        session_row = conn.execute(
            text("SELECT id, section, title, updated_at FROM chat_sessions WHERE id = :id AND username = :username"),
            {"id": session_id, "username": username},
        ).fetchone()
        if not session_row:
            return None
        message_rows = conn.execute(
            text("SELECT id, question, response_json, created_at FROM chat_messages WHERE session_id = :id ORDER BY id ASC"),
            {"id": session_id},
        ).fetchall()
        return {
            "id": session_row[0],
            "section": session_row[1],
            "title": session_row[2],
            "updated_at": session_row[3],
            "messages": [
                {"id": m[0], "question": m[1], "response": m[2], "created_at": m[3]}
                for m in message_rows
            ],
        }


def append_chat_message(username: str, session_id: int, question: str, response_json: str) -> bool:
    """Returns False if the session doesn't exist or doesn't belong to this user."""
    now = _now()
    with _engine.begin() as conn:
        owned = conn.execute(
            text("SELECT 1 FROM chat_sessions WHERE id = :id AND username = :username"),
            {"id": session_id, "username": username},
        ).fetchone()
        if not owned:
            return False
        conn.execute(
            text("""INSERT INTO chat_messages (session_id, question, response_json, created_at)
                    VALUES (:session_id, :question, :response_json, :now)"""),
            {"session_id": session_id, "question": question, "response_json": response_json, "now": now},
        )
        conn.execute(
            text("UPDATE chat_sessions SET updated_at = :now WHERE id = :id"),
            {"now": now, "id": session_id},
        )
        return True


def rename_chat_session(username: str, session_id: int, title: str) -> bool:
    with _engine.begin() as conn:
        result = conn.execute(
            text("UPDATE chat_sessions SET title = :title WHERE id = :id AND username = :username"),
            {"title": title[:80], "id": session_id, "username": username},
        )
        return result.rowcount > 0


def delete_chat_session(username: str, session_id: int) -> bool:
    with _engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM chat_sessions WHERE id = :id AND username = :username"),
            {"id": session_id, "username": username},
        )
        conn.execute(text("DELETE FROM chat_messages WHERE session_id = :id"), {"id": session_id})
        return result.rowcount > 0


def create_user(username: str, email: str, password: str):
    """Returns (success, message)."""
    if not username or not password:
        return False, "Username and password are required."
    with _engine.begin() as conn:
        existing = conn.execute(text("SELECT 1 FROM users WHERE username = :username"), {"username": username}).fetchone()
        if existing:
            return False, "Username already taken."
        conn.execute(
            text("INSERT INTO users (username, email, password_hash) VALUES (:username, :email, :password_hash)"),
            {"username": username, "email": email, "password_hash": hash_password(password)},
        )
        conn.execute(
            text("INSERT INTO profiles (username, level, resume_uploaded) VALUES (:username, NULL, 0)"),
            {"username": username},
        )
        return True, "Account created."


def verify_user(username: str, password: str) -> bool:
    with _engine.connect() as conn:
        row = conn.execute(text("SELECT password_hash FROM users WHERE username = :username"), {"username": username}).fetchone()
        if not row:
            return False
        return verify_password(password, row[0])


def user_exists(username: str) -> bool:
    with _engine.connect() as conn:
        row = conn.execute(text("SELECT 1 FROM users WHERE username = :username"), {"username": username}).fetchone()
        return row is not None


def get_profile(username: str) -> dict:
    with _engine.connect() as conn:
        row = conn.execute(
            text("SELECT level, resume_uploaded, favorite_tabs FROM profiles WHERE username = :username"),
            {"username": username},
        ).fetchone()
        if not row:
            return {"level": None, "resume_uploaded": False, "favorite_tabs": []}
        favorite_tabs = [t for t in (row[2] or "").split("|") if t]
        return {"level": row[0], "resume_uploaded": bool(row[1]), "favorite_tabs": favorite_tabs}


def set_profile_level(username: str, level: str):
    with _engine.begin() as conn:
        conn.execute(text("UPDATE profiles SET level = :level WHERE username = :username"), {"level": level, "username": username})


def set_resume_text(username: str, resume_text: str):
    """Stores the plain extracted resume text in Postgres (durable) so the vector store can be
    silently rebuilt from it later if the local disk copy gets wiped - see get_resume_text()."""
    with _engine.begin() as conn:
        conn.execute(
            text("UPDATE profiles SET resume_text = :resume_text WHERE username = :username"),
            {"resume_text": resume_text, "username": username},
        )


def get_resume_text(username: str) -> str | None:
    with _engine.connect() as conn:
        row = conn.execute(
            text("SELECT resume_text FROM profiles WHERE username = :username"),
            {"username": username},
        ).fetchone()
        return row[0] if row and row[0] else None


def set_favorite_tabs(username: str, tabs: list[str]):
    with _engine.begin() as conn:
        conn.execute(
            text("UPDATE profiles SET favorite_tabs = :tabs WHERE username = :username"),
            {"tabs": "|".join(tabs), "username": username},
        )


def mark_resume_uploaded(username: str):
    with _engine.begin() as conn:
        conn.execute(text("UPDATE profiles SET resume_uploaded = 1 WHERE username = :username"), {"username": username})


def save_feedback(username: str, message: str) -> bool:
    if not message or not message.strip():
        return False
    with _engine.begin() as conn:
        conn.execute(
            text("INSERT INTO feedback (username, message, created_at) VALUES (:username, :message, :now)"),
            {"username": username, "message": message.strip(), "now": _now()},
        )
        return True
