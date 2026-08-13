from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import get_current_user
from app.services.vector_store import get_vectorstore
from app.services.rag_pipeline_hybrid import route_question, answer_resume_fact, answer_technical_deep_dive
from app.services.rag_pipeline import _wants_full_resume
from app.routers.chat import _relative_match_pcts, RetrievedChunk

# Resume-fact and technical-deep-dive answers are two independent LLM calls that don't depend
# on each other - running them one after another (as answer_question does elsewhere) roughly
# doubles wall-clock time for no reason. A tiny thread pool runs them concurrently instead;
# both are I/O-bound (waiting on the LLM API), so threads are enough - no need for asyncio here.
_EXECUTOR = ThreadPoolExecutor(max_workers=2)

router = APIRouter(prefix="/hybrid-chat", tags=["hybrid-chat"])


class HybridChatRequest(BaseModel):
    question: str
    provider: str = "groq"


class HybridSide(BaseModel):
    answer: str
    retrieved: list[RetrievedChunk]
    context: str
    prompt: str
    full_resume_used: bool
    truncated: bool = False  # True when this answer was cut off by hitting the token limit


class HybridChatResponse(BaseModel):
    category: str
    reason: str
    resume: HybridSide
    technical: HybridSide


def _build_side(vectorstore, question, provider, fn):
    answer, retrieved, context, prompt, truncated = fn(vectorstore, question, provider=provider)
    match_pcts = _relative_match_pcts([float(score) for _doc, score in retrieved])
    return HybridSide(
        answer=answer,
        retrieved=[
            RetrievedChunk(content=doc.page_content, distance=float(score), match_pct=pct)
            for (doc, score), pct in zip(retrieved, match_pcts)
        ],
        context=context,
        prompt=prompt,
        full_resume_used=_wants_full_resume(question),
        truncated=truncated,
    )


@router.post("/ask", response_model=HybridChatResponse)
def ask(payload: HybridChatRequest, username: str = Depends(get_current_user)):
    if not payload.question or not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    vectorstore = get_vectorstore(username)
    if not vectorstore:
        raise HTTPException(
            status_code=400,
            detail="No processed resume found. Please complete onboarding first.",
        )

    category, reason = route_question(payload.question)

    resume_future = _EXECUTOR.submit(_build_side, vectorstore, payload.question, payload.provider, answer_resume_fact)
    technical_future = _EXECUTOR.submit(_build_side, vectorstore, payload.question, payload.provider, answer_technical_deep_dive)
    resume_side = resume_future.result()
    technical_side = technical_future.result()

    return HybridChatResponse(category=category, reason=reason, resume=resume_side, technical=technical_side)
