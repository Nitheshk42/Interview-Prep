import os
from functools import lru_cache
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings

MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def get_embeddings():
    """Calls Hugging Face's hosted Inference API (same approach as the Streamlit app) instead
    of running the embedding model locally - keeps this backend free of torch/transformers."""
    api_key = os.getenv("HF_API_TOKEN")
    if not api_key:
        raise ValueError(
            "HF_API_TOKEN missing! Get a free token at huggingface.co/settings/tokens "
            "and set it in backend/.env"
        )
    return HuggingFaceInferenceAPIEmbeddings(
        api_key=api_key,
        model_name=MODEL_NAME,
        api_url=f"https://router.huggingface.co/hf-inference/models/{MODEL_NAME}/pipeline/feature-extraction",
    )
