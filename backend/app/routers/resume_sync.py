"""Resume Sync: tool-by-tool experience breakdown, and vendor JD screening prep. Both reuse the
generic chat_sessions history infrastructure (see chat_sessions.py) so past syncs/JD-preps are
listed and reopenable like any other saved chat - reopening never calls the LLM.

The vendor JD prep endpoint additionally dedups by JD content: if the exact same JD (normalized,
whitespace/case-insensitive) was already prepped for this user, the existing saved session is
returned directly instead of generating a new one - this is the actual token-saving mechanism
the user asked for, not just "saved for browsing"."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import get_current_user
from app import db
from app.routers.onboarding import get_full_resume_text
from app.services.resume_sync import generate_tool_breakdown, generate_vendor_qa, jd_fingerprint

router = APIRouter(prefix="/resume-sync", tags=["resume-sync"])


class ToolBreakdownRequest(BaseModel):
    provider: str = "groq"


class ToolItem(BaseModel):
    tool: str
    experience: str
    level: str
    clients: list[str]


class ToolBreakdownResponse(BaseModel):
    tools: list[ToolItem]
    truncated: bool = False


@router.post("/tool-breakdown", response_model=ToolBreakdownResponse)
def tool_breakdown(payload: ToolBreakdownRequest, username: str = Depends(get_current_user)):
    resume_text = get_full_resume_text(username)
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="No processed resume found. Please complete onboarding first.")

    tools, truncated = generate_tool_breakdown(resume_text, provider=payload.provider)
    if not tools:
        raise HTTPException(
            status_code=502,
            detail="Couldn't extract a tool breakdown from the resume — try again, or switch the Answer engine.",
        )
    return ToolBreakdownResponse(tools=tools, truncated=truncated)


class VendorQaRequest(BaseModel):
    jd_text: str
    provider: str = "groq"
    num_questions: int = 8


class VendorQaItem(BaseModel):
    category: str
    question: str
    answer: str


class VendorQaResponse(BaseModel):
    items: list[VendorQaItem]
    truncated: bool = False
    from_cache: bool = False  # True when this exact JD was already prepped - no LLM call made
    session_id: int


@router.post("/vendor-qa", response_model=VendorQaResponse)
def vendor_qa(payload: VendorQaRequest, username: str = Depends(get_current_user)):
    if not payload.jd_text or not payload.jd_text.strip():
        raise HTTPException(status_code=400, detail="Job description cannot be empty.")

    jd_hash = jd_fingerprint(payload.jd_text)

    # Dedup: this exact JD was already prepped for this user - reuse it, spend zero tokens.
    existing_id = db.find_session_by_jd_hash(username, "resume_sync_qa", jd_hash)
    if existing_id:
        session = db.get_chat_session(username, existing_id)
        if session and session["messages"]:
            cached = json.loads(session["messages"][-1]["response"])
            return VendorQaResponse(
                items=cached["items"], truncated=cached.get("truncated", False),
                from_cache=True, session_id=existing_id,
            )

    resume_text = get_full_resume_text(username)
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="No processed resume found. Please complete onboarding first.")

    items, truncated = generate_vendor_qa(
        resume_text, payload.jd_text, provider=payload.provider, num_questions=payload.num_questions
    )
    if not items:
        raise HTTPException(
            status_code=502,
            detail="Couldn't generate vendor Q&A — try again, or switch the Answer engine.",
        )

    title = payload.jd_text.strip().splitlines()[0][:80] or "Vendor JD prep"
    session_id = db.create_chat_session(username, "resume_sync_qa", title, jd_hash=jd_hash)
    response_payload = {"items": [i for i in items], "truncated": truncated}
    db.append_chat_message(username, session_id, payload.jd_text.strip(), json.dumps(response_payload))

    return VendorQaResponse(items=items, truncated=truncated, from_cache=False, session_id=session_id)
