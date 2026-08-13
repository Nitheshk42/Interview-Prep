import os
import shutil
from langchain_chroma import Chroma
from app.core.config import CHROMA_DB_ROOT
from app.services.embeddings import get_embeddings
from app.services import gcs_storage


def _user_path(username: str = None) -> str:
    safe_name = (username or "default").replace("/", "_").replace("\\", "_")
    return str(CHROMA_DB_ROOT / safe_name)


def _blob_path(username: str = None) -> str:
    safe_name = (username or "default").replace("/", "_").replace("\\", "_")
    return f"chroma/{safe_name}.tar.gz"


def create_vector_store(docs, embeddings=None, username: str = None):
    """Create a new vector store for this user, replacing any previous resume data."""
    if embeddings is None:
        embeddings = get_embeddings()

    persist_dir = _user_path(username)
    if os.path.exists(persist_dir):
        shutil.rmtree(persist_dir)
    os.makedirs(CHROMA_DB_ROOT, exist_ok=True)

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=persist_dir,
    )

    # Cloud Run's local disk is ephemeral - snapshot the already-embedded collection to GCS so a
    # later cold-start instance can restore it directly instead of re-embedding via the Hugging
    # Face API. No-op locally where GCS_BUCKET_NAME isn't set.
    gcs_storage.backup_dir(persist_dir, _blob_path(username))
    return vectorstore


def get_vectorstore(username: str = None):
    """Load this user's existing vector store, if any. On a cold start where the local disk is
    empty, first tries to restore a previously-backed-up snapshot from GCS (if configured) before
    giving up and returning None."""
    persist_dir = _user_path(username)
    if not (os.path.exists(persist_dir) and len(os.listdir(persist_dir)) > 0):
        gcs_storage.restore_dir(persist_dir, _blob_path(username))

    if os.path.exists(persist_dir) and len(os.listdir(persist_dir)) > 0:
        embeddings = get_embeddings()
        return Chroma(persist_directory=persist_dir, embedding_function=embeddings)
    return None
