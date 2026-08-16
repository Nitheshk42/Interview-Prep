"""Central place to pick which LLM backend answers are generated with - mirrors
src/llm_provider.py in the Streamlit app. Here the provider is passed in explicitly per
request (from the frontend's selected value) instead of read from st.session_state."""
import os
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

PROVIDERS = {
    # Both Groq and Gemini free tiers reset every 24 hours, but on SEPARATE quota buckets -
    # so Gemini is a genuinely useful backup once Groq's daily cap is hit, not a duplicate of
    # the same limit. Gemini: 20 requests/day PER MODEL (aistudio.google.com/usage) but plenty
    # of tokens per request.
    # Ollama/DeepSeek removed from the selector - not actually wired up for deployed use (Ollama
    # needs a local machine running it, DeepSeek needs a paid API key) - see get_llm() below,
    # which still supports both if you ever set them up again, just not exposed in the UI.
    "groq": "Groq (GPT-OSS 120B) — daily free limit",
    "gemini": "Gemini (free tier) — separate daily limit",
}
DEFAULT_PROVIDER = "groq"


def get_llm(provider: str = DEFAULT_PROVIDER, temperature: float = 0.3, max_tokens: int = 1024):
    provider = provider or DEFAULT_PROVIDER

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY missing! Get a free key (no card required) at "
                "aistudio.google.com/apikey and set it in backend/.env"
            )
        return ChatOpenAI(
            # gemini-2.5-flash (and the rest of the 2.5 line) stopped being available to new
            # API users as Google pushes everyone to Gemini 3 - "gemini-flash-latest" is an
            # alias Google keeps pointed at whatever the current stable Flash model is, so
            # this doesn't need to be manually bumped every time they rename/retire a model.
            model="gemini-flash-latest",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            # Gemini's current Flash models "think" before answering by default, and on the
            # OpenAI-compatible endpoint those invisible reasoning tokens are drawn from the
            # SAME max_tokens budget as the visible answer - with a budget sized for a normal
            # answer (600-1000ish), thinking alone can burn the whole thing before any visible
            # text comes out, which is exactly what produced answers cut off after a sentence
            # (and the slowness - thinking adds real latency). This turns thinking off so the
            # full token budget goes to the actual answer, matching Groq's directness/speed.
            extra_body={"extra_body": {"google": {"thinking_config": {"thinking_budget": 0}}}},
        )

    if provider == "ollama":
        # Ollama runs models locally on your own machine (download from ollama.com) and
        # exposes an OpenAI-compatible endpoint at localhost:11434 - genuinely free, no daily
        # request cap, no account needed. The "api_key" here is a required-but-unused
        # placeholder; Ollama doesn't check it. OLLAMA_MODEL lets you swap models via .env
        # without a code change (default: llama3.1:8b - good balance of quality/speed/RAM use
        # for a resume-QA task; run `ollama pull llama3.1:8b` once before using this).
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key="ollama",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY missing! Get one at platform.deepseek.com/api_keys "
                "(requires a small account top-up - DeepSeek is not free despite the low "
                "cost) and set it in backend/.env"
            )
        return ChatOpenAI(
            model="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # default: groq, with automatic fallback to a smaller/faster model on rate limit/error.
    # llama-3.3-70b-versatile is decommissioned by Groq as of 2026-08-16 (per their deprecation
    # email) - requests to it stop being served entirely past that date, not just deprioritized.
    # Replaced with openai/gpt-oss-120b, Groq's recommended replacement and, as of this change,
    # a "Production" (not Preview) tier model on their model list - meaning it's meant for
    # production use and isn't subject to being pulled at short notice the way Preview models
    # are. The fallback model is openai/gpt-oss-20b - also Production tier, smaller/faster, same
    # family so behavior stays consistent between primary and fallback.
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY missing! Set it in backend/.env")

    primary = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
    )
    fallback = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
    )
    return primary.with_fallbacks([fallback])


def invoke_and_check_truncation(llm, prompt_value):
    """Runs the LLM directly (bypassing StrOutputParser, which throws away everything except
    the text) so the caller can tell whether the response was cut off by hitting max_tokens
    mid-generation, versus finishing naturally. Returns (content: str, truncated: bool).

    finish_reason == "length" (OpenAI/Groq/most OpenAI-compatible APIs, which covers Groq,
    Gemini, DeepSeek, and Ollama here) means the model wanted to keep going but was cut off -
    exactly the case that silently produced broken, partial answers before this existed."""
    response = llm.invoke(prompt_value)
    content = getattr(response, "content", None)
    if content is None:
        content = str(response)
    metadata = getattr(response, "response_metadata", None) or {}
    finish_reason = str(metadata.get("finish_reason", "")).lower()
    truncated = finish_reason in ("length", "max_tokens")
    return content, truncated
