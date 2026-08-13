"""Hybrid Chat: classify the question, then answer it two independent ways - strictly from
resume facts, and as an interview-style technical deep-dive. Ported from
studysage-rag/src/rag_pipeline_hybrid.py, kept behavior-identical (same prompts, same k=15
retrieval, same recency/terminology rules) so both apps answer the same question the same way."""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.services.llm_provider import get_llm, invoke_and_check_truncation
from app.services.rag_pipeline import _retrieve, format_docs, _wants_full_resume

TERMINOLOGY_RULE = """TERMINOLOGY DISAMBIGUATION: Some acronyms have multiple meanings (e.g. "RAG" can
mean "Retrieval-Augmented Generation" in ML/engineering contexts, or "Red/Amber/Green" status
reporting in project/data-governance contexts). Judge the meaning from the QUESTION'S OWN
wording and topic first - not just whichever meaning happens to appear in the resume context.
If the question mentions chunking, embeddings, retrieval, vector search, PDFs, or LLM pipelines,
"RAG" means Retrieval-Augmented Generation, regardless of what the resume discusses."""


def route_question(question: str):
    """Classify the question so the UI can show WHY each side answered the way it did.
    Returns (category, reason)."""
    llm = get_llm(temperature=0, max_tokens=120)
    template = """Classify this interview-prep question into exactly one category:
- RESUME_FACT: asking what is literally on the resume (skills, companies, dates)
- TECHNICAL_DEEP_DIVE: asking how/why something was done, challenges, tradeoffs
- BOTH: needs both a resume fact and a technical explanation

Question: {question}

Reply in this exact format:
Category: <RESUME_FACT|TECHNICAL_DEEP_DIVE|BOTH>
Reason: <one short sentence>"""
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"question": question})

    category, reason = "BOTH", "Defaulted to showing both views."
    for line in result.splitlines():
        if line.lower().startswith("category:"):
            category = line.split(":", 1)[1].strip()
        elif line.lower().startswith("reason:"):
            reason = line.split(":", 1)[1].strip()
    return category, reason


RESUME_TEMPLATE = """You are the candidate, personally answering an interview question. A
recruiter or hiring manager is reading this answer to verify you ACTUALLY did this work - not to
read a polished bio. Answer ONLY using the resume context below; do not add outside knowledge or
speculation.

AUTHENTICITY RULE - THIS IS THE MOST IMPORTANT RULE: Never open with, or lean on, generic
soft-skill filler like "I'm a seasoned professional with strong analytical and communication
skills" or "I'm a self-motivator who is always looking to grow." That kind of line proves
nothing and every resume answer sounds the same without it - delete it entirely. Instead, open
directly with WHO you are by role/title and WHERE (real company name, real title, real
dates/timeframe from the context), then immediately ground the rest of the answer in specific,
checkable proof: exact project names, the real problem you were solving, the specific
tools/technologies you personally used, and concrete outcomes or scope (numbers, scale, team
size) wherever the context has them. If the candidate's name appears in the resume context, you
may reference it naturally once (e.g. when it reads better in third person context like listing
titles), but the answer should mostly stay in first person ("I").

SPECIFICITY RULE: If the resume context contains concrete numbers, metrics, config values,
tool versions, or specific project/technology names, quote them verbatim rather than
paraphrasing them away into generic statements. Every paragraph must contain at least one fact
that could only be true if this person really worked there - not a sentence that could apply to
any candidate in this field.

RECRUITER LENS: Before finalizing the answer, judge it the way a recruiter screening dozens of
candidates would. A recruiter is satisfied when: (1) the language is OWNERSHIP language - "I
built," "I owned," "I decided" - never passive or team-only phrasing like "the team was
responsible for" when the resume shows this person's individual contribution; (2) wherever the
context has a measurable outcome (a number, %, scale, time saved, users/records/requests
handled), it's stated plainly, not dropped; (3) the answer naturally follows a
situation-action-result shape (what the problem/context was -> what this person specifically did
-> what happened as a result) even without labeling it that way; (4) there are zero buzzword
lists ("proficient in X, Y, Z, communication skills, team player") - only things this person
verifiably did. If the answer reads like it could be skimmed and forgotten, it has failed; if it
reads like something only this candidate could truthfully say, it has succeeded.

""" + TERMINOLOGY_RULE + """

FORMAT: For narrative/conversational questions ("tell me about yourself," "tell me about your
recent project," etc.) write ONE flowing, coherent answer in first person — do not split into
labeled sections or invent extra sub-topics the question didn't ask about. Only use a per-item
breakdown if the question explicitly enumerates a list of distinct named things to go through
one by one (e.g. "top 10 X", "each of these five Y").

RECENCY RULE: If the question asks about the "recent," "current," "latest," or "most recent"
project/role, do NOT just answer about whichever project happens to appear first in the context
below. Scan ALL project/role entries in the context, compare their date ranges, and identify the
one that is actually most recent — the entry marked "Current" / "Present", or if none is marked
that way, the one with the latest start date. Base the answer on that entry specifically. If the
context doesn't make the dates clear enough to tell, say so rather than guessing.

COMPLETENESS RULE: If asked to list companies, employers, roles, or a career timeline, scan the
ENTIRE context for every distinct company/role entry before answering, and include all of them
- do not stop after the first few you notice. List them in REVERSE CHRONOLOGICAL order (most
recent / current role first, oldest role last) - the same order a resume itself is written in.
Never list oldest-first. If two chunks seem to describe the same job at
different points, treat them as one entry, not a duplicate to drop.

LENGTH RULE: Give a genuinely complete answer - typically 150-280 words, more if the question is
a full enumeration that has to cover several entries. No throat-clearing, no restating the
question, no generic closing summary. Every sentence must carry a specific fact - cut anything
that doesn't, but don't under-explain the substance just to be short.

If the resume context doesn't cover something, say so plainly rather than skipping it.

RESUME CONTEXT:
{context}

QUESTION: {question}

Answer strictly from the resume context:"""


TECHNICAL_TEMPLATE = """You are helping prepare for a technical interview follow-up: "walk me through
how you did that." This is the SECOND, deeper layer on top of a separate resume-grounded answer
the candidate already gave - your job is to add value beyond that answer, not restate it. Do not
just re-tell the same career story again; instead pick up where a resume summary stops and go
into the actual engineering reasoning: why specific tools were chosen over alternatives, how
pieces of the system fit together, what could go wrong and how it was handled, and how a general
best-practice from the field applies on top of what the resume literally says.

CRITICAL HONESTY RULE: Only say "I did X" / "In my role I..." if the RESUME CONTEXT below
actually contains evidence of it. Never invent a specific first-person story, project, or
outcome that isn't in the context. If the resume does NOT clearly cover something, say so
plainly and instead explain how you WOULD approach it in general — do not disguise general
knowledge as personal history. Where it's natural, you may layer in relevant general
engineering/domain knowledge (industry-standard practices, common pitfalls, why an approach is
considered best practice) to fine-tune and deepen the resume facts - but always keep it clearly
anchored to what the resume actually shows, not a detached lecture.

RECRUITER LENS: A technical interviewer is satisfied when the candidate can go one level deeper
than the resume bullet without stalling - naming the actual tradeoff they weighed, the specific
failure mode they hit, or the reason one approach beat another for THIS system's constraints
(scale, latency, team size, deadline). Vague confidence ("I made sure it was scalable and
efficient") fails this test just as badly as a resume full of buzzwords does - always replace it
with the specific mechanism that made it scalable/efficient.

SPECIFICITY RULE: When the resume context contains concrete details — exact numbers, metrics,
config values, tool versions, timeframes, specific class/service/project names — carry them
into the answer VERBATIM. Do not smooth a specific number into a vague phrase like "improved
performance." If the resume says "tuned thread pool size to 10," say that exact number.

""" + TERMINOLOGY_RULE + """

FORMAT DECISION — read the question carefully before choosing:
- If it's a NARRATIVE/CONVERSATIONAL question ("tell me about yourself," "walk me through your
  background," "tell me about yourself and your recent project," etc.) — even if it has multiple
  clauses — write ONE single flowing, well-written narrative answer in first person, the way a
  real candidate would actually speak in an interview. Do NOT split it into labeled sections. Do
  NOT invent extra sub-topics the question didn't ask about. Weave the resume's actual companies,
  roles, tools, and specifics naturally into the story, in a logical order (e.g. current role ->
  what you work on -> a recent project -> how you approach it).
- ONLY if the question explicitly enumerates a list of distinct named items to go through one by
  one (e.g. "top 10 OWASP risks," "walk me through each of these five concepts") should you use a
  separate labeled block per item, in this format:
  ### <item name/number>
  **Your resume evidence:** ... **Approach/Tools:** ... **Challenges & Resolution:** ...

Default to the narrative style unless the question is unambiguously a numbered/enumerated list.

RECENCY RULE: If the question asks about the "recent," "current," "latest," or "most recent"
project/role, do NOT default to whichever project happens to appear first in the context below.
Scan ALL project/role entries in the context, compare their date ranges, and identify the one
that is actually most recent — the entry marked "Current" / "Present", or if none is marked that
way, the one with the latest start date. Base the answer on that entry specifically.

COMPLETENESS RULE: If asked to list companies, employers, roles, or a career timeline, scan the
ENTIRE context for every distinct company/role entry before answering, and include all of them
- do not stop after the first few you notice. List them in REVERSE CHRONOLOGICAL order (most
recent / current role first, oldest role last) - the same order a resume itself is written in.
Never list oldest-first.

LENGTH RULE: Give a genuinely complete narrative - typically 180-320 words even in narrative
mode. No throat-clearing, no restating the question, no generic closing summary. Every sentence
should carry a specific fact, tool, or number, but make sure the story is fully fleshed out, not
clipped short.

RESUME CONTEXT:
{context}

QUESTION: {question}

Answer:"""


def _answer_with_template(vectorstore, question: str, template: str, provider: str, temperature: float, max_tokens: int, k: int = 15):
    """Same step-by-step pattern as rag_pipeline.answer_question: retrieve, build the exact
    prompt by hand, then call the LLM - so the caller can honestly show what was retrieved
    and what was sent, not just the final answer. Returns (answer, retrieved, context_text,
    full_prompt_text, truncated)."""
    retrieved = _retrieve(vectorstore, question, k=k)
    docs = [doc for doc, _score in retrieved]
    context_text = format_docs(docs)

    prompt = ChatPromptTemplate.from_template(template)
    full_prompt_text = prompt.format(context=context_text, question=question)

    llm = get_llm(provider=provider, temperature=temperature, max_tokens=max_tokens)
    # Bypasses StrOutputParser so the caller can tell when an answer was cut off by hitting
    # max_tokens, instead of silently showing a clipped answer as if it were complete.
    answer, truncated = invoke_and_check_truncation(llm, prompt.format_prompt(context=context_text, question=question))

    return answer, retrieved, context_text, full_prompt_text, truncated


def answer_resume_fact(vectorstore, question: str, provider: str = "groq"):
    # Raised from 500 to 750 to match the loosened LENGTH RULE in the prompt (still well below
    # the old runaway 2000 default).
    return _answer_with_template(vectorstore, question, RESUME_TEMPLATE, provider, temperature=0.2, max_tokens=750)


def answer_technical_deep_dive(vectorstore, question: str, provider: str = "groq"):
    # Raised from 700 to 900 to match the loosened LENGTH RULE in the prompt.
    return _answer_with_template(vectorstore, question, TECHNICAL_TEMPLATE, provider, temperature=0.3, max_tokens=900)


# ===== EXP Level Answers: one question, answered at four seniority levels =====
# The whole point of this tab is that a recruiter/interviewer should come away believing the
# candidate genuinely did this work - so every level's answer must (a) come from what's
# actually in the resume, in real depth, not a generic summary, and (b) be written in first
# person as the candidate speaking, never as an AI describing "the candidate" from outside.

LEVEL_INSTRUCTIONS = {
    "Junior": (
        "Explain it the way a JUNIOR engineer would: simpler vocabulary, less discussion of "
        "tradeoffs - but still describe the ACTUAL, SPECIFIC steps taken (which tool did what, "
        "in what order, on what data) using the real details from the resume. 'Simple' means "
        "simple to follow, not vague - never replace real mechanics with a generic summary "
        "like 'we built a pipeline to process data.'"
    ),
    "Mid-Level": (
        "Explain the concrete implementation decisions: which specific tool/service handled "
        "which step, why that tool for that step, and the actual sequence of the pipeline/system "
        "as evidenced in the resume."
    ),
    "Senior": (
        "Go into technical tradeoffs grounded in the specific tools/scale mentioned in the "
        "resume: why alternatives were rejected, edge cases that specific setup would hit, "
        "and how you'd mentor others through it."
    ),
    "Architect": (
        "Frame it at the system level using the specific services/architecture from the "
        "resume: scalability, reliability, cross-team/cross-service concerns, and long-term "
        "tradeoffs of THAT actual setup, not a generic architecture essay."
    ),
}

LEVEL_ORDER = ["Junior", "Mid-Level", "Senior", "Architect"]


def _level_template(level: str) -> str:
    instruction = LEVEL_INSTRUCTIONS.get(level, LEVEL_INSTRUCTIONS["Mid-Level"])
    return """You are the candidate, personally answering an interview question about your own
resume. Every answer must sound like it came from someone who actually did this work.

VOICE RULE - THIS IS CRITICAL: Write in FIRST PERSON the entire time ("I built...", "I chose...",
"I ran into..."). Never write in third person, never say "the candidate," "they," "the resume
shows," or anything that sounds like an AI describing someone else's work. You ARE the person
being interviewed. If you slip into describing the resume from the outside instead of speaking
as the person who lived it, the answer has failed at its one job.

CRITICAL - ACTUAL MECHANICS, NOT SUMMARY: The answer must describe WHAT you actually built and
HOW, step by step, using the real tools/services/data named in the resume context - not a
one-line summary of the outcome. A bad answer says "I built a pipeline to ingest and transform
data." A good answer says specifically which service ingested the data, which tool transformed
it, what format it landed in, and why, using names/numbers straight from the context below. This
is the difference between an answer that convinces an interviewer you actually did the work, and
one that sounds memorized or generic - always choose the former.

RECRUITER LENS: Judge the answer the way an interviewer at this seniority level would. Satisfied
means ownership language, a concrete situation -> action -> result shape, and specific
mechanisms instead of vague confidence ("I made it scalable" fails; "I split the job into
per-partition workers so one slow partition didn't block the rest" passes). No buzzword lists.
If it reads like it could have been said by any candidate in this field, it has failed.

SPECIFICITY RULE: Quote concrete numbers, metrics, config values, and tool versions from the
resume context verbatim - never paraphrase them into generic statements.

RECENCY RULE: If asked about the "recent," "current," "latest," or "most recent" project/role,
identify the entry marked "Current"/"Present" (or the latest start date) among ALL entries in
the context, and answer about that one specifically - do not default to whichever appears first.

COMPLETENESS RULE: If asked to list companies, employers, roles, or a career timeline, scan the
ENTIRE context for every distinct entry and include all of them, in REVERSE CHRONOLOGICAL order
(most recent/current first, oldest last) - never oldest-first, never incomplete.

DO NOT relabel your actual job title or seniority from the resume - if the resume says "Senior
Data Engineer," keep that as the real fact. The Junior/Mid/Senior/Architect level below only
controls HOW MUCH DEPTH and TECHNICAL VOCABULARY you use in explaining it, not what your real
title was.

""" + TERMINOLOGY_RULE + """

RESUME CONTEXT:
{context}

QUESTION: {question}

""" + instruction + """

LENGTH RULE: This tab generates FOUR of these answers per question (one per level), so keep each
one focused, but still give it real room - roughly 150-230 words. Do not sacrifice real
mechanics/specificity for length - cut generic connective sentences instead, not the concrete
details. No throat-clearing, no restating the question, no generic closing summary. Speak as
yourself, in first person, the whole way through.

Answer:"""


def answer_at_level(vectorstore, question: str, level: str, provider: str = "groq"):
    template = _level_template(level)
    # Raised from 450 to 650 - four of these run concurrently per question (up to ~2600 output
    # tokens/question, vs. the old runaway 7200), which still leaves headroom under Groq's
    # 100K tokens/day free-tier cap for a normal session. The LENGTH RULE above does the real
    # work of keeping each answer properly elaborated without ballooning; this is just a ceiling.
    return _answer_with_template(vectorstore, question, template, provider, temperature=0.4, max_tokens=650)


# ===== My JD Answers: paste a JD, get resume-grounded likely interview questions =====

CATEGORY_DEFINITIONS = {
    "Technical": "Technical skills the JD asks for that match the resume.",
    "Behavioral": "Behavioral/experience questions tied to resume projects (teamwork, conflict, ownership).",
    "Resume": (
        "Questions asking the candidate to describe their own project/role/responsibilities "
        "directly from the resume — e.g. 'What was your role in project X?', 'Describe your "
        "responsibilities in Y', 'What was project Z about?'. The answer must be a factual "
        "description pulled straight from the resume context, not general advice."
    ),
    "Gap": "Skills the JD wants that aren't clearly on the resume (still give a good answer strategy).",
}


def check_domain_alignment(vectorstore, jd_text: str):
    """Quick check: does this JD's core domain actually match what's evidenced in the resume?
    Returns {"aligned": bool_str, "note": str} so the UI can warn the user before generating
    Q&A that would otherwise falsely imply a fit."""
    llm = get_llm(temperature=0, max_tokens=150)
    retrieved = _retrieve(vectorstore, jd_text, k=6)
    context = format_docs([doc for doc, _score in retrieved])
    template = """Compare the core domain/role of this JOB DESCRIPTION against the candidate's
RESUME CONTEXT below. Judge whether the JD's primary domain (e.g. the main tech stack, role
type, or industry it's hiring for) is actually reflected in the resume - not just a shared
buzzword here and there.

JOB DESCRIPTION:
{jd_text}

RESUME CONTEXT:
{context}

Reply in exactly this format:
Aligned: <YES|PARTIAL|NO>
Note: <one short sentence explaining the core domain match or mismatch>"""
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"jd_text": jd_text, "context": context})

    aligned, note = "PARTIAL", "Could not determine domain fit."
    for line in result.splitlines():
        if line.lower().startswith("aligned:"):
            aligned = line.split(":", 1)[1].strip().upper()
        elif line.lower().startswith("note:"):
            note = line.split(":", 1)[1].strip()
    return {"aligned": aligned, "note": note}


def generate_jd_questions(vectorstore, jd_text: str, provider: str = "groq", num_questions=5, categories=None, exclude_questions=None):
    """Given a job description, retrieve the most relevant resume chunks and generate a
    structured list of likely interview questions with resume-grounded model answers."""
    categories = categories or list(CATEGORY_DEFINITIONS.keys())
    llm = get_llm(provider=provider, temperature=0.5, max_tokens=1800)
    retrieved = _retrieve(vectorstore, jd_text, k=6)
    context = format_docs([doc for doc, _score in retrieved])

    category_desc = "\n".join(f"- {c}: {CATEGORY_DEFINITIONS[c]}" for c in categories)
    avoid_block = ""
    if exclude_questions:
        avoid_list = "\n".join(f"- {q}" for q in exclude_questions)
        avoid_block = f"\nDo NOT repeat or closely rephrase any of these already-asked questions:\n{avoid_list}\n"

    category_options = " | ".join(categories)
    template = """You are an interview coach. Below is a JOB DESCRIPTION and the candidate's
RESUME CONTEXT (retrieved as most relevant to this JD).

JOB DESCRIPTION:
{jd_text}

RESUME CONTEXT:
{context}

HONESTY ABOUT DOMAIN FIT: First, judge whether the JD's core domain (main tech stack, role
type) actually matches what's in the resume. If the resume has genuinely little or no overlap
with the JD's core domain, do NOT pretend a fit — weight questions toward the "Gap" category,
and for any question you do write, the answer must honestly acknowledge what's transferable
(general engineering fundamentals, adjacent tools) rather than inventing direct experience the
resume doesn't show. Never fabricate a project or skill the resume doesn't evidence just because
the JD asks for it.

""" + TERMINOLOGY_RULE + """

Generate exactly {num_questions} likely interview questions for this JD, ONLY using these categories:
{category_desc}
{avoid_block}
QUESTION STYLE: Phrase each question the way a real interviewer would say it out loud, naming
the actual company/project/technology from the resume where relevant — e.g. "Walk me through
the Kafka producer you built at Wells Fargo" rather than "Describe your experience with Kafka."

ANSWER STYLE: Write the answer as a flowing first-person narrative (not bullet points) - you ARE
the candidate speaking, never an AI describing someone else's background. Carry over any concrete
numbers, config values, tool versions, or metrics from the resume VERBATIM — never smooth them
into vague phrases. If the resume doesn't have that level of detail for a given point, don't
invent it; keep the answer honest about what's actually there. No throat-clearing, no restating
the question - every sentence should carry a specific fact.

AUTHENTICITY RULE: Never open with generic soft-skill filler ("I'm a dedicated professional with
strong communication skills") - it proves nothing and every candidate's answer would sound
identical without it. Use ownership language ("I built," "I owned," "I decided") over passive
team-speak, and a natural situation-action-result shape. If it reads like it could be skimmed and
forgotten, or like something any candidate in this field could have said, it has failed.

For EACH question, output in this EXACT format (use "---" as a separator between questions, no extra text):

Category: <one of: {category_options}>
Question: <the interview question, phrased naturally, naming specifics from the resume>
Answer: <first-person narrative answer, 3-5 sentences, as concrete as the resume allows>
---

Begin now:"""
    prompt = ChatPromptTemplate.from_template(template)
    messages = prompt.format_messages(
        jd_text=jd_text, context=context, num_questions=num_questions,
        category_desc=category_desc, avoid_block=avoid_block, category_options=category_options,
    )
    result, truncated = invoke_and_check_truncation(llm, messages)

    items = []
    blocks = result.split("---")
    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue
        category, question, answer = "General", "", ""
        for line in block.splitlines():
            if line.lower().startswith("category:"):
                category = line.split(":", 1)[1].strip()
            elif line.lower().startswith("question:"):
                question = line.split(":", 1)[1].strip()
            elif line.lower().startswith("answer:"):
                answer = line.split(":", 1)[1].strip()
            elif answer:
                answer += " " + line.strip()
        # If this is the LAST block and the response was truncated, this question may be
        # mid-sentence rather than genuinely incomplete text - drop it rather than show a
        # cut-off answer, same reasoning as generate_general_jd_questions below.
        if i == len(blocks) - 1 and truncated:
            continue
        if question and answer:
            items.append({"category": category, "question": question, "answer": answer})
    return items, truncated


# ===== General JD Answers: pure LLM knowledge, no resume, all 4 seniority levels =====

def generate_general_jd_questions(jd_text: str, provider: str = "groq", num_questions=6, exclude_questions=None):
    """Given ONLY a job description - no resume, no retrieval, no candidate-specific context
    at all - generates likely interview questions the way a general-purpose LLM would if you
    just pasted the JD in and asked for interview prep. Answers are generated at all four
    seniority levels using generic, best-practice domain knowledge - deliberately NOT grounded
    in anyone's actual resume.

    Unlike the fanned-out calls (Hybrid Chat, EXP Level Answers), this is ONE call that has to
    produce num_questions x 4 full answers - so it genuinely needs more headroom than a
    single-answer endpoint. 2500 was cut too close for 6 questions and caused truncated,
    unparseable output (the token-budget fix that tightened everything else went too far here)."""
    llm = get_llm(provider=provider, temperature=0.6, max_tokens=4000)

    avoid_block = ""
    if exclude_questions:
        avoid_list = "\n".join(f"- {q}" for q in exclude_questions)
        avoid_block = f"\nDo NOT repeat or closely rephrase any of these already-asked questions:\n{avoid_list}\n"

    level_desc = "\n".join(f"- {lvl}: {instr}" for lvl, instr in LEVEL_INSTRUCTIONS.items())

    template = """You are an expert technical interviewer. Below is a JOB DESCRIPTION only -
you have NO candidate resume, NO personal background, nothing specific to any individual.
Generate interview questions and answers purely from general domain expertise for this role,
the same way you'd answer if someone pasted just this JD into a general-purpose AI assistant
and asked for interview prep.

JOB DESCRIPTION:
{jd_text}

""" + TERMINOLOGY_RULE + """

Generate exactly {num_questions} likely interview questions for this role, covering a mix of
technical and role-relevant conceptual questions grounded in what the JD actually asks for.
{avoid_block}
For EACH question, write FOUR separate answers - one per seniority level below. Each answer
must be genuinely different in depth and framing, not the same content reworded, and each kept
to 2-4 sentences (this generates 4 answers per question, so brevity matters - cut connective
filler, keep every sentence packed with a real point):
{level_desc}

Answers should read like strong, generic best-practice interview answers - the kind a
well-prepared candidate at that level would give. Do NOT invent a fake personal story, company
name, or "I did X at my last job" claim - keep answers framed around approach, reasoning, and
domain knowledge rather than fabricated personal history.

For EACH question, output in this EXACT format (use "===" as a separator between questions):

Question: <the interview question>
Junior: <junior-level answer, 2-4 sentences>
Mid-Level: <mid-level answer, 2-4 sentences>
Senior: <senior-level answer, 3-4 sentences, tradeoffs/depth>
Architect: <architect-level answer, 3-4 sentences, system-level framing>
===

Begin now:"""
    prompt = ChatPromptTemplate.from_template(template)
    messages = prompt.format_messages(
        jd_text=jd_text, num_questions=num_questions,
        avoid_block=avoid_block, level_desc=level_desc,
    )
    result, truncated = invoke_and_check_truncation(llm, messages)

    items = []
    for block in result.split("==="):
        block = block.strip()
        if not block:
            continue
        question = ""
        answers = {"Junior": "", "Mid-Level": "", "Senior": "", "Architect": ""}
        current_key = None
        for line in block.splitlines():
            stripped = line.strip()
            low = stripped.lower()
            if low.startswith("question:"):
                question = stripped.split(":", 1)[1].strip()
                current_key = None
            elif low.startswith("junior:"):
                answers["Junior"] = stripped.split(":", 1)[1].strip()
                current_key = "Junior"
            elif low.startswith("mid-level:") or low.startswith("mid level:"):
                answers["Mid-Level"] = stripped.split(":", 1)[1].strip()
                current_key = "Mid-Level"
            elif low.startswith("senior:"):
                answers["Senior"] = stripped.split(":", 1)[1].strip()
                current_key = "Senior"
            elif low.startswith("architect:"):
                answers["Architect"] = stripped.split(":", 1)[1].strip()
                current_key = "Architect"
            elif current_key and stripped:
                answers[current_key] += " " + stripped
        # Require ALL FOUR levels to be present, not just "at least one" - a block cut short by
        # hitting max_tokens mid-generation (the last question in the response, usually) would
        # otherwise show up as a card with three levels reading "No answer generated," which
        # looks like a bug rather than what it actually is: an incomplete generation. Better to
        # quietly drop it and return fewer complete questions than a broken-looking one.
        if question and all(answers.values()):
            items.append({"question": question, "answers": answers})
    return items, truncated
