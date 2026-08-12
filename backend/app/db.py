import sqlite3
from datetime import datetime
from app.core.config import DB_PATH
from app.core.security import hash_password, verify_password


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            email TEXT,
            password_hash TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            username TEXT PRIMARY KEY,
            level TEXT,
            resume_uploaded INTEGER DEFAULT 0,
            favorite_tabs TEXT DEFAULT '',
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            message TEXT NOT NULL,
            created_at TEXT
        )
    """)
    # Saved chat sessions (ChatGPT-style history) - one row per "conversation" the user starts
    # in a given section (chat / hybrid / level). Reopening a session just replays its stored
    # messages from here - no LLM call, no tokens spent - which is the whole point: a question
    # you already asked and saved never needs to be regenerated.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            section TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'New chat',
            jd_hash TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)
    # jd_hash lets Resume Sync's vendor-Q&A feature recognize "I've seen this exact JD before"
    # and reuse the saved answer set instead of generating it again - added via ALTER TABLE so
    # existing databases created before this column existed still upgrade cleanly.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
    if "jd_hash" not in existing_cols:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN jd_hash TEXT")
    # Each message stores the question plus the FULL response JSON the section's /ask endpoint
    # returned (answer, retrieved chunks, prompt, everything) - so reopening a saved chat can
    # show exactly what was shown originally, not just the plain text answer.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
    """)
    conn.commit()
    return conn


def _now() -> str:
    return datetime.utcnow().isoformat()


def create_chat_session(username: str, section: str, title: str, jd_hash: str | None = None) -> int:
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO chat_sessions (username, section, title, jd_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (username, section, title[:80] or "New chat", jd_hash, now, now),
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def find_session_by_jd_hash(username: str, section: str, jd_hash: str) -> int | None:
    """Looks up an existing session for this exact JD (by normalized hash) so a repeat JD can
    reuse its saved vendor Q&A instead of spending tokens generating it again."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM chat_sessions WHERE username = ? AND section = ? AND jd_hash = ? ORDER BY id DESC LIMIT 1",
        (username, section, jd_hash),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def list_chat_sessions(username: str, section: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT s.id, s.title, s.updated_at, COUNT(m.id) as message_count
           FROM chat_sessions s LEFT JOIN chat_messages m ON m.session_id = s.id
           WHERE s.username = ? AND s.section = ?
           GROUP BY s.id ORDER BY s.updated_at DESC""",
        (username, section),
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "title": r[1], "updated_at": r[2], "message_count": r[3]}
        for r in rows
    ]


def get_chat_session(username: str, session_id: int) -> dict | None:
    conn = get_conn()
    session_row = conn.execute(
        "SELECT id, section, title, updated_at FROM chat_sessions WHERE id = ? AND username = ?",
        (session_id, username),
    ).fetchone()
    if not session_row:
        conn.close()
        return None
    message_rows = conn.execute(
        "SELECT id, question, response_json, created_at FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
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
    conn = get_conn()
    owned = conn.execute(
        "SELECT 1 FROM chat_sessions WHERE id = ? AND username = ?", (session_id, username)
    ).fetchone()
    if not owned:
        conn.close()
        return False
    now = _now()
    conn.execute(
        "INSERT INTO chat_messages (session_id, question, response_json, created_at) VALUES (?, ?, ?, ?)",
        (session_id, question, response_json, now),
    )
    conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()
    conn.close()
    return True


def rename_chat_session(username: str, session_id: int, title: str) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE chat_sessions SET title = ? WHERE id = ? AND username = ?",
        (title[:80], session_id, username),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_chat_session(username: str, session_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM chat_sessions WHERE id = ? AND username = ?", (session_id, username)
    )
    conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def create_user(username: str, email: str, password: str):
    """Returns (success, message)."""
    if not username or not password:
        return False, "Username and password are required."
    conn = get_conn()
    existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        return False, "Username already taken."
    conn.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (username, email, hash_password(password)),
    )
    conn.execute(
        "INSERT INTO profiles (username, level, resume_uploaded) VALUES (?, NULL, 0)",
        (username,),
    )
    conn.commit()
    conn.close()
    return True, "Account created."


def verify_user(username: str, password: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not row:
        return False
    return verify_password(password, row[0])


def get_profile(username: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT level, resume_uploaded, favorite_tabs FROM profiles WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    if not row:
        return {"level": None, "resume_uploaded": False, "favorite_tabs": []}
    favorite_tabs = [t for t in (row[2] or "").split("|") if t]
    return {"level": row[0], "resume_uploaded": bool(row[1]), "favorite_tabs": favorite_tabs}


def set_profile_level(username: str, level: str):
    conn = get_conn()
    conn.execute("UPDATE profiles SET level = ? WHERE username = ?", (level, username))
    conn.commit()
    conn.close()


def set_favorite_tabs(username: str, tabs: list[str]):
    conn = get_conn()
    conn.execute(
        "UPDATE profiles SET favorite_tabs = ? WHERE username = ?",
        ("|".join(tabs), username),
    )
    conn.commit()
    conn.close()


def mark_resume_uploaded(username: str):
    conn = get_conn()
    conn.execute("UPDATE profiles SET resume_uploaded = 1 WHERE username = ?", (username,))
    conn.commit()
    conn.close()


def save_feedback(username: str, message: str) -> bool:
    if not message or not message.strip():
        return False
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback (username, message, created_at) VALUES (?, ?, ?)",
        (username, message.strip(), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return True
