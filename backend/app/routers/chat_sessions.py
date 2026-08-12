"""ChatGPT-style saved chat history, shared across any section that has a running Q&A thread
(Chat Assistant, Hybrid Chat, EXP Level Answers). Each "session" belongs to one section and
holds an ordered list of Q&A turns. The whole point: reopening a saved session just replays the
stored response JSON straight from SQLite - no LLM call, no tokens spent - unlike asking the
same question fresh, which always costs tokens again."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import get_current_user
from app import db

router = APIRouter(prefix="/sessions", tags=["chat-sessions"])

VALID_SECTIONS = {"chat", "hybrid", "level", "resume_sync_tools", "resume_sync_qa"}


def _check_section(section: str):
    if section not in VALID_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown section '{section}'.")


class CreateSessionRequest(BaseModel):
    section: str
    title: str = "New chat"


class SessionSummary(BaseModel):
    id: int
    title: str
    updated_at: str
    message_count: int


class AppendMessageRequest(BaseModel):
    question: str
    response: dict  # the exact JSON the section's /ask endpoint returned


class MessageOut(BaseModel):
    id: int
    question: str
    response: dict
    created_at: str


class SessionDetail(BaseModel):
    id: int
    section: str
    title: str
    updated_at: str
    messages: list[MessageOut]


class RenameRequest(BaseModel):
    title: str


@router.get("", response_model=list[SessionSummary])
def list_sessions(section: str, username: str = Depends(get_current_user)):
    _check_section(section)
    return db.list_chat_sessions(username, section)


@router.post("", response_model=SessionSummary)
def create_session(payload: CreateSessionRequest, username: str = Depends(get_current_user)):
    _check_section(payload.section)
    session_id = db.create_chat_session(username, payload.section, payload.title)
    sessions = db.list_chat_sessions(username, payload.section)
    match = next((s for s in sessions if s["id"] == session_id), None)
    return match


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: int, username: str = Depends(get_current_user)):
    session = db.get_chat_session(username, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat not found.")
    session["messages"] = [
        {**m, "response": json.loads(m["response"])} for m in session["messages"]
    ]
    return session


@router.post("/{session_id}/messages")
def add_message(session_id: int, payload: AppendMessageRequest, username: str = Depends(get_current_user)):
    ok = db.append_chat_message(username, session_id, payload.question, json.dumps(payload.response))
    if not ok:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {"ok": True}


@router.patch("/{session_id}")
def rename_session(session_id: int, payload: RenameRequest, username: str = Depends(get_current_user)):
    ok = db.rename_chat_session(username, session_id, payload.title)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {"ok": True}


@router.delete("/{session_id}")
def delete_session(session_id: int, username: str = Depends(get_current_user)):
    ok = db.delete_chat_session(username, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {"ok": True}
