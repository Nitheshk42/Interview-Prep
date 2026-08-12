from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.deps import get_current_user
from app.routers.onboarding import get_full_resume_text
from app.services.resume_tailor import (
    analyze_resume_for_jd, extract_jd_keywords, ats_match_score,
    insert_naturally, render_side_by_side_diff, render_tailored_preview_markdown,
    build_tailored_docx,
)

router = APIRouter(prefix="/resume-tailor", tags=["resume-tailor"])


# ===== /analyze: first pass - find first two projects, suggest bullets to add =====

class AnalyzeRequest(BaseModel):
    jd_text: str
    provider: str = "groq"


class MissingSkill(BaseModel):
    skill: str
    note: str
    draft: str


class ProjectAnalysis(BaseModel):
    original: str
    suggestions: list[str]
    has_any_metric: bool
    missing_skills: list[MissingSkill]


class AnalyzeResponse(BaseModel):
    full_resume_text: str
    jd_keywords: list[str]
    baseline_score: int
    projects: list[ProjectAnalysis]
    truncated: bool = False  # True if the model hit its token limit mid-generation


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest, username: str = Depends(get_current_user)):
    if not payload.jd_text.strip():
        raise HTTPException(status_code=400, detail="Please paste a job description first.")

    full_resume_text = get_full_resume_text(username)
    if not full_resume_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No processed resume found. Please complete onboarding first.",
        )

    projects, truncated = analyze_resume_for_jd(full_resume_text, payload.jd_text, provider=payload.provider)
    if not projects:
        detail = (
            "The AI's response got cut off before a usable result came through - try again, "
            "or switch to a different Answer engine in the sidebar."
            if truncated else
            "Couldn't parse a result — try again."
        )
        raise HTTPException(status_code=502, detail=detail)

    jd_keywords = extract_jd_keywords(payload.jd_text)
    baseline_score, _matched, _missing = ats_match_score(full_resume_text, jd_keywords)

    return AnalyzeResponse(
        full_resume_text=full_resume_text,
        jd_keywords=jd_keywords,
        truncated=truncated,
        baseline_score=baseline_score,
        projects=[ProjectAnalysis(**p) for p in projects],
    )


# ===== /recompute: pure-Python, no LLM call - runs on every checkbox toggle =====

class ProjectState(BaseModel):
    original: str
    approved_bullets: list[str]  # already-resolved bullet text (suggestion or missing-skill draft)


class RecomputeRequest(BaseModel):
    full_resume_text: str
    jd_keywords: list[str]
    projects: list[ProjectState]


class ProjectDiff(BaseModel):
    final_snippet: str
    left_html: str
    right_html: str


class RecomputeResponse(BaseModel):
    diffs: list[ProjectDiff]
    score: int
    matched: list[str]
    missing: list[str]


@router.post("/recompute", response_model=RecomputeResponse)
def recompute(payload: RecomputeRequest, username: str = Depends(get_current_user)):
    diffs = []
    current_text = payload.full_resume_text
    for proj in payload.projects:
        final_snippet = insert_naturally(proj.original, proj.approved_bullets)
        left_html, right_html = render_side_by_side_diff(proj.original, final_snippet)
        diffs.append(ProjectDiff(final_snippet=final_snippet, left_html=left_html, right_html=right_html))
        if proj.original in current_text:
            current_text = current_text.replace(proj.original, final_snippet, 1)

    score, matched, missing = ats_match_score(current_text, payload.jd_keywords)
    return RecomputeResponse(diffs=diffs, score=score, matched=matched, missing=missing)


# ===== /preview and /download: build the final tailored document =====

class Replacement(BaseModel):
    original: str
    final: str


class PreviewRequest(BaseModel):
    full_resume_text: str
    replacements: list[Replacement]


class PreviewResponse(BaseModel):
    markdown: str


@router.post("/preview", response_model=PreviewResponse)
def preview(payload: PreviewRequest, username: str = Depends(get_current_user)):
    pairs = [(r.original, r.final) for r in payload.replacements]
    markdown = render_tailored_preview_markdown(payload.full_resume_text, pairs)
    return PreviewResponse(markdown=markdown)


@router.post("/download")
def download(payload: PreviewRequest, username: str = Depends(get_current_user)):
    pairs = [(r.original, r.final) for r in payload.replacements]
    buffer = build_tailored_docx(payload.full_resume_text, pairs)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=tailored_resume.docx"},
    )
