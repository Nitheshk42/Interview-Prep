import os
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader


def load_documents(data_dir: str):
    """Loads every PDF and DOCX file in data_dir."""
    documents = []
    if not os.path.exists(data_dir):
        return documents
    for fname in sorted(os.listdir(data_dir)):
        fpath = os.path.join(data_dir, fname)
        lower = fname.lower()
        if lower.endswith(".pdf"):
            documents.extend(PyPDFLoader(fpath).load())
        elif lower.endswith(".docx") or lower.endswith(".doc"):
            documents.extend(Docx2txtLoader(fpath).load())
    return documents
