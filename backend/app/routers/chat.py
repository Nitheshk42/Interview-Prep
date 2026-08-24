from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import enforce_usage_cap
from app.services.vector_store import get_vectorstore
from app.services.rag_pipeline import answer_question, _wants_full_resume
from app import db

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    provider: str = "groq"


class RetrievedChunk(BaseModel):
    content: str
    distance: float
    match_pct: int  # 0-100, relative to the other chunks retrieved for this question


class ChatResponse(BaseModel):
    answer: str
    retrieved: list[RetrievedChunk]
    context: str  # the concatenated chunk text the LLM actually received
    prompt: str  # the full prompt (instructions + context + question) sent to the LLM
    full_resume_used: bool  # True when every chunk was pulled in (enumeration-style question)
    truncated: bool = False  # True when the answer was cut off by hitting the token limit


def _relative_match_pcts(distances: list[float]) -> list[int]:
    """Chroma's raw distance is an L2 distance in embedding space - not something a person can
    look at and judge ("is 0.83 good?"). Converting each chunk's distance into a 0-100 score
    relative to the others *retrieved for this question* gives an honest, readable signal:
    100 = the closest match among what was retrieved, trailing off from there. This is NOT a
    universal similarity percentage (that would need a fixed distance scale, which Chroma
    doesn't guarantee), just a relative ranking made human-readable.
    """
    if not distances:
        return []
    lo, hi = min(distances), max(distances)
    if hi == lo:
        return [100 for _ in distances]
    return [round(100 * (1 - (d - lo) / (hi - lo))) for d in distances]


@router.post("/ask", response_model=ChatResponse)
def ask(payload: ChatRequest, username: str = Depends(enforce_usage_cap("questions"))):
    if not payload.question or not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    vectorstore = get_vectorstore(username)
    if not vectorstore:
        raise HTTPException(
            status_code=400,
            detail="No processed resume found. Please complete onboarding first.",
        )

    answer, retrieved, context, prompt, truncated = answer_question(
        vectorstore, payload.question, provider=payload.provider
    )
    full_resume_used = _wants_full_resume(payload.question)
    match_pcts = _relative_match_pcts([float(score) for _doc, score in retrieved])
    db.increment_usage_today(username, "questions")  # counted only now that an answer actually came back
    return ChatResponse(
        answer=answer,
        retrieved=[
            RetrievedChunk(content=doc.page_content, distance=float(score), match_pct=pct)
            for (doc, score), pct in zip(retrieved, match_pcts)
        ],
        context=context,
        prompt=prompt,
        full_resume_used=full_resume_used,
        truncated=truncated,
    )
