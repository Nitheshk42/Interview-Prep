from fastapi import Header, HTTPException, status
from app.core.security import decode_access_token


def get_current_user(authorization: str = Header(default=None)) -> str:
    """Expects 'Authorization: Bearer <token>'. Raises 401 if missing/invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return username
