import os
import shutil
import uuid
from langchain_chroma import Chroma
from app.core.config import CHROMA_DB_ROOT
from app.services.embeddings import get_embeddings
from app.services import gcs_storage

# ROOT-CAUSE FIX for the "attempt to write a readonly database" (SQLite error 1032,
# READONLY_DBMOVED) crash seen on Render: the old code did shutil.rmtree(persist_dir) followed by
# immediately opening a fresh Chroma PersistentClient at that *same* path. chromadb keeps an
# internal per-path client/connection cache inside the process, so re-opening the identical path
# right after deleting it can hand back a stale handle bound to the old (now-gone) inode - the next
# write then trips SQLite's "has this file been moved out from under me?" safety check and fails,
# even though the directory itself is perfectly writable. This isn't a permissions or /tmp-vs-disk
# issue; it's specifically about reusing a path across a delete+recreate cycle.
#
# The fix: never delete-and-reopen the same directory. Every (re)process gets its own uniquely
# named version directory under the user's folder, a small CURRENT pointer file records which
# version is active, and old versions are cleaned up only *after* the new one is confirmed built -
# so there's never a moment where a live connection's path stops existing underneath it.


def _user_dir(username: str = None) -> str:
    safe_name = (username or "default").replace("/", "_").replace("\\", "_")
    return str(CHROMA_DB_ROOT / safe_name)


def _pointer_path(user_dir: str) -> str:
    return os.path.join(user_dir, "CURRENT")


def _new_version_dir(user_dir: str) -> str:
    return os.path.join(user_dir, f"v_{uuid.uuid4().hex[:12]}")


def _read_current(user_dir: str) -> str | None:
    pointer = _pointer_path(user_dir)
    if not os.path.isfile(pointer):
        return None
    with open(pointer, "r") as f:
        name = f.read().strip()
    version_dir = os.path.join(user_dir, name) if name else None
    if version_dir and os.path.isdir(version_dir) and os.listdir(version_dir):
        return version_dir
    return None


def _write_current(user_dir: str, version_dir: str):
    with open(_pointer_path(user_dir), "w") as f:
        f.write(os.path.basename(version_dir))


def _blob_path(username: str = None) -> str:
    safe_name = (username or "default").replace("/", "_").replace("\\", "_")
    return f"chroma/{safe_name}.tar.gz"


def create_vector_store(docs, embeddings=None, username: str = None):
    """Create a new vector store for this user, replacing any previous resume data. Builds the
    new collection in a brand-new versioned directory (see module docstring for why), then only
    switches the CURRENT pointer - and only then best-effort cleans up older versions."""
    if embeddings is None:
        embeddings = get_embeddings()

    user_dir = _user_dir(username)
    os.makedirs(user_dir, exist_ok=True)
    version_dir = _new_version_dir(user_dir)

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=version_dir,
    )

    _write_current(user_dir, version_dir)

    # Cloud Run's/Render's local disk is ephemeral - snapshot the already-embedded collection to
    # GCS so a later cold-start instance can restore it directly instead of re-embedding via the
    # Hugging Face API. No-op locally/on Render where GCS_BUCKET_NAME isn't set.
    gcs_storage.backup_dir(version_dir, _blob_path(username))

    # Best-effort cleanup of older versions now that the new one is live and confirmed working.
    # Never touches version_dir itself, and any failure here (stale handle, permissions) is safe
    # to ignore - it's just disk hygiene, not correctness.
    for name in os.listdir(user_dir):
        old_dir = os.path.join(user_dir, name)
        if name.startswith("v_") and old_dir != version_dir and os.path.isdir(old_dir):
            try:
                shutil.rmtree(old_dir)
            except Exception:
                pass

    return vectorstore


def get_vectorstore(username: str = None):
    """Load this user's existing vector store, if any. On a cold start where the local disk is
    empty (e.g. a Render redeploy or free-tier spin-down wiped it - the local disk is ephemeral,
    unlike the Postgres-backed account/profile data), tries two recovery paths in order before
    giving up and returning None:

    1. Restore a previously-backed-up snapshot from GCS, if configured (fast - already-embedded,
       no API calls).
    2. Rebuild from the plain resume text saved in Postgres during onboarding (see
       onboarding.py's process_resume() / db.set_resume_text()). This re-embeds via the
       embeddings API, so it's slower and does cost API usage - but it happens silently, once,
       and the result is immediately persisted (and GCS-backed up if configured) so every
       following request in this process hits path 1 or the fast local-disk case instead. The
       alternative - returning None here - is what used to make a user's resume "disappear" and
       force a manual re-upload even though nothing about their account was actually lost."""
    user_dir = _user_dir(username)
    current = _read_current(user_dir)

    if not current:
        os.makedirs(user_dir, exist_ok=True)
        version_dir = _new_version_dir(user_dir)
        if gcs_storage.restore_dir(version_dir, _blob_path(username)):
            _write_current(user_dir, version_dir)
            current = version_dir

    if not current:
        current = _rebuild_from_stored_text(username)

    if current:
        embeddings = get_embeddings()
        return Chroma(persist_directory=current, embedding_function=embeddings)
    return None


def _rebuild_from_stored_text(username: str = None) -> str | None:
    """Last-resort recovery: re-embeds the resume text saved in Postgres during onboarding, if
    any, and persists the result exactly like a fresh create_vector_store() call would. Returns
    the new version directory path, or None if there's no stored text to rebuild from (e.g. this
    user genuinely never uploaded a resume)."""
    from app import db
    from langchain_core.documents import Document
    from app.services.text_splitter import split_documents

    resume_text = db.get_resume_text(username)
    if not resume_text:
        return None

    splits = split_documents([Document(page_content=resume_text)])
    create_vector_store(splits, username=username)
    return _read_current(_user_dir(username))
