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

# Monetization tables - built now (ahead of Stripe actually being turned on) so the whole gating
# path (usage caps, "you've hit the free limit", checkout, webhook activation) can be wired up and
# tested end-to-end with zero live payments happening. Nothing in here charges anyone until real
# STRIPE_* env vars are set - see payments.py.
purchases = Table(
    "purchases", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(255), ForeignKey("users.username"), nullable=False),
    Column("tier", String(32), nullable=False),  # "sprint" | "student" | "pro_monthly"
    Column("status", String(32), nullable=False, server_default="pending"),  # pending|active|expired|cancelled
    Column("stripe_customer_id", String(255)),
    Column("stripe_session_id", String(255)),
    # Only set for the recurring "pro_monthly" tier - lets the webhook find and deactivate the
    # right row when Stripe reports the subscription itself was cancelled (customer.subscription.
    # deleted), since a subscription's lifecycle isn't tied to a single Checkout Session the way
    # the one-time tiers are.
    Column("stripe_subscription_id", String(255)),
    # NULL for pro_monthly (a subscription stays active until cancelled, not until a fixed date) -
    # set to a real timestamp for the one-time tiers (sprint/student), which DO expire.
    Column("expires_at", String(64)),
    Column("created_at", String(64)),
)

# One row per (username, day, bucket) - counts free-tier usage so a cap can be enforced without a
# separate cron job to reset counters; "today" is just whatever date string is being incremented.
usage_daily = Table(
    "usage_daily", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(255), ForeignKey("users.username"), nullable=False),
    Column("day", String(10), nullable=False),  # YYYY-MM-DD (UTC)
    Column("bucket", String(32), nullable=False),  # "questions" | "resume_sync"
    Column("count", Integer, nullable=False, server_default="0"),
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
        "ALTER TABLE purchases ADD COLUMN stripe_subscription_id VARCHAR(255)",
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
    # Child rows (chat_messages) must go first - chat_messages.session_id is a foreign key to
    # chat_sessions.id. SQLite doesn't enforce foreign keys by default, so deleting the parent
    # first silently "worked" locally, but Postgres does enforce them: deleting chat_sessions
    # while chat_messages still reference it raises a foreign key violation, which rolled back
    # the whole transaction and made delete silently fail once this moved to Postgres.
    with _engine.begin() as conn:
        conn.execute(text("DELETE FROM chat_messages WHERE session_id = :id"), {"id": session_id})
        result = conn.execute(
            text("DELETE FROM chat_sessions WHERE id = :id AND username = :username"),
            {"id": session_id, "username": username},
        )
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


# ===== Monetization: purchases + usage caps (dormant until Stripe env vars are set) =====

def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def create_pending_purchase(username: str, tier: str, stripe_session_id: str) -> int:
    """Recorded the moment a Stripe Checkout Session is created, before the user has actually
    paid - lets the success-page redirect look up "did this session complete?" and lets the
    webhook (which may arrive slightly before or after the browser redirect) find the right row
    to activate by stripe_session_id rather than trusting anything the browser tells it."""
    now = _now()
    with _engine.begin() as conn:
        result = conn.execute(
            text("""INSERT INTO purchases (username, tier, status, stripe_session_id, created_at)
                    VALUES (:username, :tier, 'pending', :stripe_session_id, :now) RETURNING id"""),
            {"username": username, "tier": tier, "stripe_session_id": stripe_session_id, "now": now},
        )
        return result.scalar()


def activate_purchase(
    stripe_session_id: str, stripe_customer_id: str | None, expires_at: str | None,
    stripe_subscription_id: str | None = None,
) -> bool:
    """Called from the Stripe webhook on checkout.session.completed - the only place a purchase
    should ever flip from pending to active, since it's the only signal that's actually been
    verified by Stripe's webhook signature, not just claimed by the browser.

    expires_at is None for the recurring pro_monthly tier (a subscription doesn't have a fixed
    end date - it stays active until cancelled, see deactivate_subscription below) and a real
    timestamp for the one-time tiers (sprint/student)."""
    with _engine.begin() as conn:
        result = conn.execute(
            text("""UPDATE purchases SET status = 'active', stripe_customer_id = :cust,
                    expires_at = :exp, stripe_subscription_id = :sub_id WHERE stripe_session_id = :sid"""),
            {"cust": stripe_customer_id, "exp": expires_at, "sub_id": stripe_subscription_id, "sid": stripe_session_id},
        )
        return result.rowcount > 0


def deactivate_subscription(stripe_subscription_id: str) -> bool:
    """Called from the webhook on customer.subscription.deleted - the signal that a pro_monthly
    subscription actually ended (cancelled, or payment failed and Stripe gave up retrying), since
    unlike the one-time tiers there's no expires_at counting down on its own."""
    with _engine.begin() as conn:
        result = conn.execute(
            text("UPDATE purchases SET status = 'cancelled' WHERE stripe_subscription_id = :sub_id"),
            {"sub_id": stripe_subscription_id},
        )
        return result.rowcount > 0


def get_active_purchase(username: str) -> dict | None:
    """Returns {tier, expires_at} for whichever paid tier is currently active, or None. A row
    counts as active if status='active' AND EITHER it has no expiry (pro_monthly - active until
    cancelled) OR its expires_at is still in the future (sprint/student - active until the window
    runs out). Only one active tier is expected at a time in practice, but if somehow more than
    one exists, the one with the furthest-out (or no) expiry wins - the more generous access."""
    now = _now()
    with _engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT tier, expires_at FROM purchases WHERE username = :username
                    AND status = 'active' AND (expires_at IS NULL OR expires_at > :now)"""),
            {"username": username, "now": now},
        ).fetchall()
        if not rows:
            return None
        # None (no expiry) sorts as "furthest out" - a pro_monthly subscription wins over a
        # simultaneously-active one-time tier, since it's the more generous access anyway.
        best = max(rows, key=lambda r: (r[1] is None, r[1] or ""))
        return {"tier": best[0], "expires_at": best[1]}


def has_active_sprint(username: str) -> bool:
    """Kept for any old caller - has_active_paid() below is the general form any NEW code should
    use, since a Pro Monthly subscriber should also bypass the free-tier caps, not just Sprint."""
    purchase = get_active_purchase(username)
    return purchase is not None and purchase["tier"] == "sprint"


def has_active_paid(username: str) -> bool:
    """True if ANY paid tier (sprint, student, or pro_monthly) is currently active - this is what
    the free-tier usage cap should actually check, not just Sprint specifically."""
    return get_active_purchase(username) is not None


def get_active_sprint_expiry(username: str) -> str | None:
    """Kept for any old caller - get_active_purchase() above is the general form."""
    purchase = get_active_purchase(username)
    return purchase["expires_at"] if purchase and purchase["tier"] == "sprint" else None


def get_usage_today(username: str, bucket: str) -> int:
    with _engine.connect() as conn:
        row = conn.execute(
            text("SELECT count FROM usage_daily WHERE username = :username AND day = :day AND bucket = :bucket"),
            {"username": username, "day": _today(), "bucket": bucket},
        ).fetchone()
        return row[0] if row else 0


def increment_usage_today(username: str, bucket: str) -> int:
    """Upserts the counter for (username, today, bucket) and returns the new count. Written as a
    plain select-then-insert-or-update rather than an ON CONFLICT clause because the exact upsert
    syntax differs between SQLite and Postgres - this stays dialect-portable like the rest of the
    file, at the cost of a small (harmless) race under true concurrent requests from the same user."""
    day = _today()
    with _engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, count FROM usage_daily WHERE username = :username AND day = :day AND bucket = :bucket"),
            {"username": username, "day": day, "bucket": bucket},
        ).fetchone()
        if row:
            new_count = row[1] + 1
            conn.execute(
                text("UPDATE usage_daily SET count = :count WHERE id = :id"),
                {"count": new_count, "id": row[0]},
            )
            return new_count
        conn.execute(
            text("INSERT INTO usage_daily (username, day, bucket, count) VALUES (:username, :day, :bucket, 1)"),
            {"username": username, "day": day, "bucket": bucket},
        )
        return 1
