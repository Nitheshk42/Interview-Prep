import re
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.services.llm_provider import get_llm, invoke_and_check_truncation

_RECENCY_WORDS = re.compile(r"\b(recent|current|latest|most recent|now|present)\b", re.IGNORECASE)

# Questions asking to enumerate EVERYTHING (every company worked at, full career timeline,
# etc.) can't be trusted to a top-k similarity search - a low-k retrieval can genuinely leave
# an entire job out if that chunk doesn't rank as "similar enough" to the question's wording,
# even though it's exactly the kind of thing the question is asking for. The fix isn't a
# bigger k (that just delays the same failure), it's recognizing this class of question and
# pulling the ENTIRE resume as context instead of a similarity-ranked subset.
_ENUMERATION_WORDS = re.compile(
    r"\b(companies|employers|jobs|roles|positions)\b.*\b(worked|held|had)\b"
    r"|work history|career history|career timeline|employment history"
    r"|all (your|the) (companies|jobs|roles|positions|employers)"
    r"|every (company|job|role|position|employer)"
    r"|each (company|job|role|position|employer)"
    r"|list all|entire career|full (career|work) history",
    re.IGNORECASE,
)


def _wants_full_resume(question: str) -> bool:
    return bool(_ENUMERATION_WORDS.search(question))


def _retrieval_query(question: str) -> str:
    """Boosts the retrieval query with recency terms when the question asks about the
    'current'/'latest'/'recent' project or role, so the vector search surfaces every
    date-bearing chunk rather than whichever one happens to rank first on plain similarity.
    Mirrors src/rag_pipeline_hybrid.py's _retrieval_query in the Streamlit app."""
    if _RECENCY_WORDS.search(question):
        return f"{question} Current Present most recent latest role"
    return question


def format_docs(docs) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def _retrieve(vectorstore, question: str, k: int):
    """Returns a list of (Document, score) pairs, same shape as
    similarity_search_with_score - but for enumeration-style questions ("what companies have
    you worked at"), fetches every chunk in the resume instead of a similarity-ranked top-k,
    so nothing gets silently dropped. score is 0.0 for full-resume fetches (there's no ranking
    to report - everything was included on purpose)."""
    if _wants_full_resume(question):
        raw = vectorstore.get()
        contents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or [{}] * len(contents)
        return [(Document(page_content=c, metadata=m or {}), 0.0) for c, m in zip(contents, metadatas)]

    query = _retrieval_query(question)
    return vectorstore.similarity_search_with_score(query, k=k)


CHAT_TEMPLATE = """You are the candidate, personally answering interview-prep questions grounded
in the resume below. A recruiter is reading this to verify you actually did this work.

AUTHENTICITY RULE: Never open with, or lean on, generic soft-skill filler like "I'm a seasoned
professional with strong analytical and communication skills" - that proves nothing and every
candidate's answer would sound identical without it. Ground the answer in specific, checkable
proof instead: real company names, real titles/dates, real project names, the actual
tools/technologies used, and concrete scope or outcomes wherever the context has them.

SPECIFICITY RULE: If the resume context contains concrete numbers, metrics, config values,
tool versions, company names, or dates, quote them verbatim rather than paraphrasing into
generic statements - concrete detail is what makes an answer credible.

RECRUITER LENS: Judge the answer the way a recruiter screening many candidates would. Satisfied
means: ownership language ("I built," "I owned") not passive team-only phrasing; any measurable
outcome in the context (numbers, %, scale, time saved) stated plainly, not dropped; a natural
situation -> action -> result shape; and zero buzzword lists ("proficient in X, Y, Z, team
player"). If it reads like it could be skimmed and forgotten, it has failed.

RECENCY RULE: If asked about the "recent," "current," "latest," or "most recent" project/role,
scan ALL project/role entries in the context, compare their date ranges, and answer about the
one that's actually most recent (marked "Current"/"Present", or the latest start date) - do not
just answer about whichever chunk happens to appear first.

COMPLETENESS RULE: If asked to list companies, employers, roles, or a career timeline, scan the
ENTIRE context for every distinct company/role entry before answering, and include all of them
- do not stop after the first few you notice. List them in REVERSE CHRONOLOGICAL order (most
recent / current role first, oldest role last) - the same order a resume itself is written in.
Never list oldest-first. If two chunks seem to describe the same job at different points, treat
them as one entry, not a duplicate to drop.

LENGTH RULE: Give a genuinely complete, interview-ready answer - typically 150-300 words, more if
the question is a full enumeration (like a career timeline) that has to cover several entries. Do
not restate the question, do not add throat-clearing ("Great question!", "Sure, here's..."), and
do not pad with a generic closing summary. Every sentence should carry a specific fact - if a
sentence could be deleted without losing a real detail, cut it. The goal is a recruiter reading
this and coming away convinced the person has real depth, not a clipped one-liner - so don't
under-explain the mechanics, but don't ramble with filler either.

If the resume context genuinely doesn't cover something, say so plainly rather than guessing.

RESUME CONTEXT:
{context}

QUESTION: {question}

Answer:"""


def get_rag_chain(vectorstore, provider: str = "groq"):
    """Kept for reuse elsewhere - builds its own retriever internally, so what it sends the
    LLM can't be inspected from the outside. answer_question() below does the same three
    steps by hand instead, specifically so the API can return the exact context/prompt that
    was used - the two must never drift apart, or the 'how this answer was made' panel in the
    UI would be showing something that isn't actually true."""
    # Raised from 700 to give the LENGTH RULE above room for a fuller, more elaborated answer
    # (still well below the old runaway 2000 default). This cap is a ceiling against runaway
    # output, not the thing enforcing length - the prompt rule does that.
    llm = get_llm(provider=provider, temperature=0.3, max_tokens=1000)
    prompt = ChatPromptTemplate.from_template(CHAT_TEMPLATE)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 15})

    rag_chain = (
        {
            "context": lambda x: format_docs([doc for doc, _score in _retrieve(vectorstore, x["question"], k=15)]),
            "question": lambda x: x["question"],
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain


def answer_question(vectorstore, question: str, provider: str = "groq", k: int = 15):
    """Runs retrieval, builds the exact prompt, and calls the LLM step by step (rather than
    through get_rag_chain's internal retriever) so the API response can honestly show the
    caller every stage: what was retrieved, what prompt that became, and what came back.
    Returns (answer, retrieved, context_text, full_prompt_text, truncated)."""
    retrieved = _retrieve(vectorstore, question, k=k)
    docs = [doc for doc, _score in retrieved]
    context_text = format_docs(docs)

    prompt = ChatPromptTemplate.from_template(CHAT_TEMPLATE)
    full_prompt_text = prompt.format(context=context_text, question=question)

    # Raised from 700 to give the LENGTH RULE above room for a fuller, more elaborated answer
    # (still well below the old runaway 2000 default). This cap is a ceiling against runaway
    # output, not the thing enforcing length - the prompt rule does that.
    llm = get_llm(provider=provider, temperature=0.3, max_tokens=1000)
    # Bypasses StrOutputParser (which would discard the response metadata truncation is
    # detected from) so the caller can tell the user honestly when an answer got cut off by
    # hitting max_tokens, instead of silently showing a clipped answer as if it were complete.
    answer, truncated = invoke_and_check_truncation(llm, prompt.format_prompt(context=context_text, question=question))

    return answer, retrieved, context_text, full_prompt_text, truncated
