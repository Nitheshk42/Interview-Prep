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
from app.deps import enforce_usage_cap
from app import db
from app.routers.onboarding import get_full_resume_text
from app.services.resume_sync import generate_tool_breakdown, generate_vendor_qa, jd_fingerprint

router = APIRouter(prefix="/resume-sync", tags=["resume-sync"])


def _call_llm_or_friendly_error(fn, *args, **kwargs):
    """Both endpoints below send the full resume text as input, which makes them the two calls
    in the app most likely to hit an upstream LLM provider failure - either Groq's hard
    12,000-tokens-PER-REQUEST ceiling (a real, longer resume can genuinely fill most of that on
    input alone), or a plain provider-side outage/overload (seen in production: Gemini returning
    "503 - This model is currently experiencing high demand... UNAVAILABLE"). Both come back from
    the SDK as a raw exception, which - left uncaught - becomes an unhandled 500, and a 500 strips
    CORS headers, which is what makes the browser report a confusing "Failed to fetch"/"blocked by
    CORS policy" instead of a real error message (the request never had a CORS problem; the
    backend crashed before a response could be built at all). Catching both cases here and
    returning a real HTTPException means the user sees an honest, actionable message instead."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        message = str(exc)
        lower = message.lower()
        if "413" in message or "rate_limit_exceeded" in lower or "tokens per minute" in lower:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Your resume is too long for one request on the current Answer engine's free "
                    "tier. Try switching the Answer engine in the sidebar (Gemini doesn't have "
                    "this same per-request limit), or trim your resume and try again."
                ),
            )
        if "503" in message or "unavailable" in lower or "overloaded" in lower or "high demand" in lower:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The Answer engine is temporarily overloaded on their end - this isn't "
                    "something wrong with your resume. Try again in a moment, or switch the "
                    "Answer engine in the sidebar."
                ),
            )
        raise


class ToolBreakdownRequest(BaseModel):
    provider: str = "groq"


class ToolUsage(BaseModel):
    client: str
    detail: str = ""
    inferred: bool = False


class ToolItem(BaseModel):
    tool: str
    experience: str
    level: str
    clients: list[str]
    # This was missing before - FastAPI's response_model silently drops any dict key not
    # declared on the Pydantic model, so every FRESH sync was losing the per-client usage detail
    # right here even though generate_tool_breakdown() produced it correctly. It only ever showed
    # up when reopening an old *cached* session, because that path reads the raw stored JSON
    # directly (see chat_sessions.py's get_session) and never passes through this model at all.
    usages: list[ToolUsage] = []


class ToolBreakdownResponse(BaseModel):
    tools: list[ToolItem]
    truncated: bool = False


@router.post("/tool-breakdown", response_model=ToolBreakdownResponse)
def tool_breakdown(payload: ToolBreakdownRequest, username: str = Depends(enforce_usage_cap("resume_sync"))):
    resume_text = get_full_resume_text(username)
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="No processed resume found. Please complete onboarding first.")

    tools, truncated = _call_llm_or_friendly_error(generate_tool_breakdown, resume_text, provider=payload.provider)
    if not tools:
        raise HTTPException(
            status_code=502,
            detail="Couldn't extract a tool breakdown from the resume — try again, or switch the Answer engine.",
        )
    db.increment_usage_today(username, "resume_sync")  # counted only now that a breakdown actually came back
    return ToolBreakdownResponse(tools=tools, truncated=truncated)


class VendorQaRequest(BaseModel):
    jd_text: str = ""  # optional - blank means "generic vendor screening prep, no specific JD yet"
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
def vendor_qa(payload: VendorQaRequest, username: str = Depends(enforce_usage_cap("resume_sync"))):
    has_jd = bool(payload.jd_text and payload.jd_text.strip())

    # A blank JD still gets a stable fingerprint (jd_fingerprint("") is deterministic), so the
    # same dedup-by-hash mechanism below also covers "generic prep, no JD" - a second click with
    # no JD reuses the saved generic session instead of spending tokens regenerating the same
    # resume-only questions again.
    jd_hash = jd_fingerprint(payload.jd_text or "")

    # Dedup: this exact JD (or "no JD" case) was already prepped for this user - reuse it, spend zero tokens.
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

    items, truncated = _call_llm_or_friendly_error(
        generate_vendor_qa,
        resume_text, payload.jd_text, provider=payload.provider, num_questions=payload.num_questions,
    )
    if not items:
        raise HTTPException(
            status_code=502,
            detail="Couldn't generate vendor Q&A — try again, or switch the Answer engine.",
        )

    title = (payload.jd_text.strip().splitlines()[0][:80] if has_jd else None) or "Vendor screening prep"
    session_id = db.create_chat_session(username, "resume_sync_qa", title, jd_hash=jd_hash)
    response_payload = {"items": [i for i in items], "truncated": truncated}
    db.append_chat_message(username, session_id, payload.jd_text.strip(), json.dumps(response_payload))

    # Not counted for the from_cache path above (no LLM call was made there, so it shouldn't cost
    # a slot) - only this fresh-generation path spends real tokens, so only this one counts.
    db.increment_usage_today(username, "resume_sync")
    return VendorQaResponse(items=items, truncated=truncated, from_cache=False, session_id=session_id)
