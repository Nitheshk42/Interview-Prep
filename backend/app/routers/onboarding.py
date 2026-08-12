import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from app import db
from app.deps import get_current_user
from app.core.config import UPLOADS_ROOT

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

LEVELS = ["Junior", "Mid-Level", "Senior", "Architect"]


def user_data_dir(username: str) -> str:
    safe_name = username.replace("/", "_").replace("\\", "_")
    path = os.path.join(UPLOADS_ROOT, safe_name)
    return path


def get_full_resume_text(username: str) -> str:
    """Loads the user's stored resume file fresh and joins every page/chunk's raw text -
    used by Resume Tailor, which needs the whole document as one string rather than the
    vector store's small retrieved chunks. Cheap enough to just re-read on each request
    instead of caching, since resumes are small and this keeps the backend stateless."""
    from app.services.document_loader import load_documents

    data_dir = user_data_dir(username)
    documents = load_documents(data_dir)
    return "\n".join(doc.page_content for doc in documents)


def process_resume(file_path_and_names: list[tuple[str, bytes]], username: str):
    """Saves uploaded resume file(s), wipes any previous resume for this user, and
    reprocesses into a fresh vector store. Mirrors src/onboarding.py's process_resume()."""
    import shutil
    from app.services.document_loader import load_documents
    from app.services.text_splitter import split_documents
    from app.services.embeddings import get_embeddings
    from app.services.vector_store import create_vector_store

    data_dir = user_data_dir(username)
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    os.makedirs(data_dir, exist_ok=True)

    for fname, content in file_path_and_names:
        fpath = os.path.join(data_dir, fname)
        with open(fpath, "wb") as f:
            f.write(content)

    documents = load_documents(data_dir)
    splits = split_documents(documents)
    embeddings_model = get_embeddings()
    create_vector_store(splits, embeddings_model, username=username)
    db.mark_resume_uploaded(username)


@router.post("/complete")
async def complete_onboarding(
    resume: UploadFile = File(...),
    level: str = Form(...),
    favorite_tabs: str = Form(""),  # pipe-delimited section labels
    username: str = Depends(get_current_user),
):
    if level not in LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {LEVELS}")

    content = await resume.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    process_resume([(resume.filename, content)], username)
    db.set_profile_level(username, level)
    tabs = [t for t in favorite_tabs.split("|") if t]
    db.set_favorite_tabs(username, tabs)

    return {"ok": True, "profile": db.get_profile(username)}


@router.post("/reprocess-resume")
async def reprocess_resume(
    resume: UploadFile = File(...),
    username: str = Depends(get_current_user),
):
    """Used by the 'upload a different resume' flow after onboarding is already done."""
    content = await resume.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    process_resume([(resume.filename, content)], username)
    return {"ok": True, "profile": db.get_profile(username)}
