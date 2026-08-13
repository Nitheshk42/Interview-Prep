"""Backs up each user's raw resume upload + their Chroma vector DB directory to Google Cloud
Storage after processing, and restores them on a cold start where the container's local disk is
empty (e.g. a fresh Cloud Run instance after a redeploy). Entirely inert when GCS_BUCKET_NAME is
unset (local dev) - every function becomes a no-op so nothing here affects local behavior.

Why a full tar snapshot instead of re-processing the resume from scratch on every cold start:
Chroma's persisted collection already contains the computed embeddings - restoring the snapshot
is a plain file copy, while rebuilding would mean calling the Hugging Face embeddings API again
for every chunk, which is slower and burns API quota for no reason on every cold start."""
import os
import io
import tarfile
from functools import lru_cache
from app.core.config import GCS_BUCKET_NAME


def enabled() -> bool:
    return bool(GCS_BUCKET_NAME)


@lru_cache(maxsize=1)
def _bucket():
    from google.cloud import storage
    client = storage.Client()
    return client.bucket(GCS_BUCKET_NAME)


def _tar_dir(local_dir: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(local_dir, arcname=".")
    return buf.getvalue()


def _untar_dir(data: bytes, local_dir: str):
    os.makedirs(local_dir, exist_ok=True)
    buf = io.BytesIO(data)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(local_dir)


def backup_dir(local_dir: str, blob_path: str):
    """Uploads a local directory as a single tar.gz blob. No-op if GCS isn't configured or the
    directory doesn't exist/is empty."""
    if not enabled() or not os.path.isdir(local_dir) or not os.listdir(local_dir):
        return
    blob = _bucket().blob(blob_path)
    blob.upload_from_string(_tar_dir(local_dir), content_type="application/gzip")


def restore_dir(local_dir: str, blob_path: str) -> bool:
    """Downloads and extracts a previously-backed-up directory. Returns True if a backup was
    found and restored, False otherwise (including when GCS isn't configured)."""
    if not enabled():
        return False
    blob = _bucket().blob(blob_path)
    if not blob.exists():
        return False
    data = blob.download_as_bytes()
    _untar_dir(data, local_dir)
    return True


def backup_file(local_path: str, blob_path: str):
    if not enabled() or not os.path.isfile(local_path):
        return
    _bucket().blob(blob_path).upload_from_filename(local_path)
