import os
import shutil
from langchain_chroma import Chroma
from app.core.config import CHROMA_DB_ROOT
from app.services.embeddings import get_embeddings


def _user_path(username: str = None) -> str:
    safe_name = (username or "default").replace("/", "_").replace("\\", "_")
    return str(CHROMA_DB_ROOT / safe_name)


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
    return vectorstore


def get_vectorstore(username: str = None):
    """Load this user's existing vector store, if any."""
    persist_dir = _user_path(username)
    if os.path.exists(persist_dir) and len(os.listdir(persist_dir)) > 0:
        embeddings = get_embeddings()
        return Chroma(persist_directory=persist_dir, embedding_function=embeddings)
    return None
