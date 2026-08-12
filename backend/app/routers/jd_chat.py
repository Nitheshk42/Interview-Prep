from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import get_current_user
from app.services.vector_store import get_vectorstore
from app.services.rag_pipeline_hybrid import (
    check_domain_alignment, generate_jd_questions, CATEGORY_DEFINITIONS,
)

router = APIRouter(prefix="/jd-chat", tags=["jd-chat"])


class JdGenerateRequest(BaseModel):
    jd_text: str
    provider: str = "groq"
    num_questions: int = 5
    exclude_questions: list[str] = []
    check_alignment: bool = True  # skip on "more questions" clicks - already shown once


class JdItem(BaseModel):
    category: str
    question: str
    answer: str


class JdAlignment(BaseModel):
    aligned: str
    note: str


class JdGenerateResponse(BaseModel):
    items: list[JdItem]
    alignment: JdAlignment | None = None
    truncated: bool = False  # True if the model hit its token limit mid-generation


@router.post("/generate", response_model=JdGenerateResponse)
def generate(payload: JdGenerateRequest, username: str = Depends(get_current_user)):
    if not payload.jd_text.strip():
        raise HTTPException(status_code=400, detail="Please paste a job description first.")

    vectorstore = get_vectorstore(username)
    if not vectorstore:
        raise HTTPException(
            status_code=400,
            detail="No processed resume found. Please complete onboarding first.",
        )

    alignment = None
    if payload.check_alignment:
        alignment = check_domain_alignment(vectorstore, payload.jd_text)

    items, truncated = generate_jd_questions(
        vectorstore,
        payload.jd_text,
        provider=payload.provider,
        num_questions=payload.num_questions,
        categories=list(CATEGORY_DEFINITIONS.keys()),
        exclude_questions=payload.exclude_questions or None,
    )
    if not items:
        detail = (
            "The AI's response got cut off before any complete question came through - try "
            "again, or switch to a different Answer engine in the sidebar."
            if truncated else
            "Couldn't generate questions — try again."
        )
        raise HTTPException(status_code=502, detail=detail)

    return JdGenerateResponse(
        items=[JdItem(**i) for i in items],
        alignment=JdAlignment(**alignment) if alignment else None,
        truncated=truncated,
    )
