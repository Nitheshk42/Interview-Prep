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
