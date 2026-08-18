from fastapi import Header, HTTPException, status
from app.core.security import decode_access_token
from app import db


def get_current_user(authorization: str = Header(default=None)) -> str:
    """Expects 'Authorization: Bearer <token>'. Raises 401 if missing/invalid.

    Also confirms the user still exists in the database, not just that the JWT signature is
    valid. On an ephemeral-disk deploy (e.g. Render free tier without a persistent DB), a
    redeploy wipes the local SQLite file, but a browser can still be holding a token signed with
    the same JWT_SECRET - without this check, that "ghost" session would sail through auth while
    every subsequent DB lookup silently no-ops (UPDATE ... WHERE username = <nobody>), producing
    confusing default/empty responses instead of a clear "please log in again"."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if not db.user_exists(username):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired - please log in again")
    return username


# Free-tier daily caps, per usage bucket. "questions" covers Chat/Hybrid/Level Answers combined
# (one shared pool, not per-tool - simplest to build and reason about); "resume_sync" covers
# Resume Sync's tool-breakdown + vendor Q&A actions combined. An active Career Sprint purchase
# bypasses both caps entirely - see db.has_active_sprint().
FREE_TIER_CAPS = {
    "questions": 10,
    "resume_sync": 3,
}


def enforce_usage_cap(bucket: str):
    """Returns a FastAPI dependency that: (1) requires a valid logged-in user, (2) lets Sprint
    purchasers through uncapped, (3) otherwise blocks with 402 once today's free cap is hit, and
    (4) increments the counter on every allowed call. 402 Payment Required (not 429) so the
    frontend can tell "you're rate-limited, wait" apart from "you're capped, go pay" - the two
    need different UI (a retry-later message vs. an upgrade prompt)."""
    from fastapi import Depends

    limit = FREE_TIER_CAPS[bucket]

    def dependency(username: str = Depends(get_current_user)) -> str:
        if db.has_active_sprint(username):
            db.increment_usage_today(username, bucket)  # tracked for visibility even though uncapped
            return username
        used = db.get_usage_today(username, bucket)
        if used >= limit:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"You've hit today's free limit ({limit}/day) for this. "
                    "Upgrade to Career Sprint for unlimited use during your prep window."
                ),
            )
        db.increment_usage_today(username, bucket)
        return username

    return dependency
