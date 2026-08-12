from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app import db
from app.core.security import create_access_token
from app.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    username: str
    email: str = ""
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    profile: dict


@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest):
    success, message = db.create_user(payload.username, payload.email, payload.password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    token = create_access_token(payload.username)
    return AuthResponse(
        access_token=token,
        username=payload.username,
        profile=db.get_profile(payload.username),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    if not db.verify_user(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="That username or password doesn't match.")
    token = create_access_token(payload.username)
    return AuthResponse(
        access_token=token,
        username=payload.username,
        profile=db.get_profile(payload.username),
    )


@router.get("/me")
def me(username: str = Depends(get_current_user)):
    return {"username": username, "profile": db.get_profile(username)}


class FeedbackRequest(BaseModel):
    message: str


@router.post("/feedback")
def feedback(payload: FeedbackRequest, username: str = Depends(get_current_user)):
    ok = db.save_feedback(username, payload.message)
    if not ok:
        raise HTTPException(status_code=400, detail="Write something before submitting.")
    return {"ok": True}
