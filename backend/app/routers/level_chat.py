from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import get_current_user
from app.services.vector_store import get_vectorstore
from app.services.rag_pipeline_hybrid import answer_at_level, LEVEL_ORDER
from app.services.rag_pipeline import _wants_full_resume
from app.routers.chat import _relative_match_pcts, RetrievedChunk
from app.routers.hybrid_chat import HybridSide

router = APIRouter(prefix="/level-chat", tags=["level-chat"])

# Four independent LLM calls (one per seniority level) - run them concurrently rather than one
# after another, same reasoning as hybrid_chat's two-sided answers.
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


class LevelChatRequest(BaseModel):
    question: str
    provider: str = "groq"


class LevelChatResponse(BaseModel):
    answers: dict[str, HybridSide]  # keyed by level name, in LEVEL_ORDER


def _build_level_side(vectorstore, question, level, provider):
    answer, retrieved, context, prompt, truncated = answer_at_level(vectorstore, question, level, provider=provider)
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


@router.post("/ask", response_model=LevelChatResponse)
def ask(payload: LevelChatRequest, username: str = Depends(get_current_user)):
    if not payload.question or not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    vectorstore = get_vectorstore(username)
    if not vectorstore:
        raise HTTPException(
            status_code=400,
            detail="No processed resume found. Please complete onboarding first.",
        )

    futures = {
        level: _EXECUTOR.submit(_build_level_side, vectorstore, payload.question, level, payload.provider)
        for level in LEVEL_ORDER
    }
    answers = {level: fut.result() for level, fut in futures.items()}

    return LevelChatResponse(answers=answers)
