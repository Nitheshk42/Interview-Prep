from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import get_current_user
from app.services.rag_pipeline_hybrid import generate_general_jd_questions

router = APIRouter(prefix="/general-jd-chat", tags=["general-jd-chat"])


class GeneralJdRequest(BaseModel):
    jd_text: str
    provider: str = "groq"
    num_questions: int = 6
    exclude_questions: list[str] = []


class GeneralJdItem(BaseModel):
    question: str
    answers: dict[str, str]  # Junior/Mid-Level/Senior/Architect -> answer text


class GeneralJdResponse(BaseModel):
    items: list[GeneralJdItem]
    truncated: bool = False  # True if the model hit its token limit mid-generation


@router.post("/generate", response_model=GeneralJdResponse)
def generate(payload: GeneralJdRequest, username: str = Depends(get_current_user)):
    # No vectorstore/auth-dependent grounding needed here by design - this tab deliberately
    # generates from general LLM knowledge only. get_current_user still gates the endpoint so
    # it's not open to unauthenticated callers.
    if not payload.jd_text.strip():
        raise HTTPException(status_code=400, detail="Please paste a job description first.")

    items, truncated = generate_general_jd_questions(
        payload.jd_text,
        provider=payload.provider,
        num_questions=payload.num_questions,
        exclude_questions=payload.exclude_questions or None,
    )
    if not items:
        detail = (
            "The AI's response got cut off before any complete question came through - try "
            "asking for fewer questions, or switch to a different Answer engine in the sidebar."
            if truncated else
            "Couldn't generate questions — try again."
        )
        raise HTTPException(status_code=502, detail=detail)

    return GeneralJdResponse(items=[GeneralJdItem(**i) for i in items], truncated=truncated)
