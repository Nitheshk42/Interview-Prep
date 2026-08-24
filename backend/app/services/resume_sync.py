"""Resume Sync: two features that both exist so a candidate walks into a vendor screening call
or interview knowing their own resume cold.

1. Tool breakdown - scan the FULL resume text (not similarity-searched chunks, since this needs
   the whole picture) and produce, for every tool/technology actually mentioned, how much
   experience the candidate has with it and which client project(s) it was used on.

2. Vendor JD prep - simulate a real vendor/staffing screening call against a pasted JD: realistic
   vendor questions (tool depth, years, rate, availability, visa/work authorization, project
   scope, gaps, why open to move) each answered confidently and specifically from the resume, the
   way a vendor needs to hear it before they'll submit the candidate to a client.
"""
import re
from langchain_core.prompts import ChatPromptTemplate
from app.services.llm_provider import get_llm, invoke_and_check_truncation


TOOL_BREAKDOWN_TEMPLATE = """You are helping a candidate "sync" with their own resume before a
vendor screening call or interview. Picture the exact moment this is for: a vendor calls and asks
"do you have experience with Hadoop?" The candidate says "yes, 6 years." The vendor's very next
question is "where, and what did you actually do with it?" - and a candidate who can only name a
company, or worse, goes quiet, sounds like they're exaggerating even if they aren't. A candidate
who can say "at Verizon I used HDFS and Hive to build the ingestion layer for a 2TB/day clickstream
pipeline that fed our fraud-detection models, then at Best Buy I used it mainly for batch ETL
staging on top of Hive" sounds like someone who obviously did the work. That second version - real,
specific, speakable out loud on a call without notes - is what you're building here. One thin
sentence per client is not enough; it will not survive a follow-up question.

RESUME:
{resume_text}

Go through this resume and identify EVERY distinct tool, technology, language, platform,
framework, or methodology actually mentioned (e.g. Java, Kafka, AWS, Kubernetes, Agile/Scrum,
Jenkins, React, SQL Server, Hadoop - whatever genuinely appears). For EACH one, work out:

- EXPERIENCE: total time used, estimated from the date ranges of the client/project entries
  where it appears (e.g. "3 years 2 months" or "2+ years" if ranges are approximate). If a tool
  appears across multiple non-contiguous roles, add the periods together rather than just citing
  the most recent one.
- LEVEL: one of Beginner / Intermediate / Advanced / Expert, judged from how central the tool was
  to the role, how long it was used, and how deeply it's described (not just whether it's
  mentioned once in a skills list).
- Then, for EVERY client/company/project (in the format the resume uses) where this tool was
  actually used, most recent first, write a REAL, SPEAKABLE answer - 2 to 3 full sentences, not
  one fragment - that a candidate could say out loud verbatim if a vendor asked "what did you do
  with this there?" Each one must cover:
    1. What was actually built or the problem solved (the concrete deliverable, not "worked on
       data pipelines").
    2. The specific sub-components/ecosystem pieces used if identifiable (e.g. for Hadoop: HDFS,
       Hive, YARN, MapReduce, Sqoop; for AWS: which specific services).
    3. Scale, data volume, team size, or frequency if known or reasonably implied.

  TWO SOURCES OF TRUTH, use both, and be explicit about which one you used:
  a) EXPLICIT - the resume directly describes what this tool did in that role's bullet points.
     Use those specifics verbatim/near-verbatim. Mark this entry INFERRED: no.
  b) INFERRED - the resume only lists the tool in a skills line for that role, with no dedicated
     bullet describing it, BUT that role has OTHER bullet points describing the broader
     project/system, the client's industry, the team's responsibilities, or other tools used
     alongside it. In that much more common case, DO NOT give up and say "no detail" - reason
     from that surrounding context the way the candidate themselves would when reconstructing a
     memory: "I was building X system in the Y industry using these other tools, so realistically
     this tool's role in that same system was probably Z." Write the same 2-3 sentence speakable
     answer using that reasoning, grounded in what the role's other bullets actually say, not
     invented from nothing. Mark this entry INFERRED: yes, and end the DETAIL with one short
     clause flagging it as a reconstruction to verify, e.g. "...(this isn't spelled out
     explicitly for this client, so confirm it matches your actual memory before repeating it)."
  Only fall back to a plain "the resume doesn't give enough context to reconstruct this" when a
  client's role has genuinely NO other bullets/context to reason from at all (rare - a skills-only
  listing with zero role description anywhere for that entry). Mark that INFERRED: yes too.

  Never write the same description twice for two different clients even if the resume's phrasing
  for them is similar - find the real distinguishing detail (different data source, different
  scale, different part of the pipeline, different team's need, different industry).

Do NOT invent a tool that isn't actually in the resume. For EXPLICIT entries, do not invent
specifics beyond what's written. For INFERRED entries, reasoning from the role's real surrounding
context is expected and encouraged - that's the whole point - but never invent a company, metric,
or system that doesn't appear anywhere in the resume. Do NOT skip a tool just because it only
appears once - list it with whatever real duration/client that one appearance supports. Order the
list with the tools used most extensively (longest total experience) first.

Respond with each tool as a block in EXACTLY this format, separated by ===, nothing else, no
extra commentary. Repeat the CLIENT/INFERRED/DETAIL trio once per client that tool was used at:

TOOL: <tool name>
EXPERIENCE: <total time>
LEVEL: <Beginner|Intermediate|Advanced|Expert>
CLIENT: <Client A>
INFERRED: <yes|no>
DETAIL: <2-3 full, speakable sentences - what was built, ecosystem pieces used, scale if known>
CLIENT: <Client B>
INFERRED: <yes|no>
DETAIL: <2-3 full, speakable sentences - what was built, ecosystem pieces used, scale if known>
===

Begin now:"""


def generate_tool_breakdown(resume_text: str, provider: str = "groq"):
    """Returns (tools: list[dict], truncated: bool). Each tool dict has tool/experience/level and
    usages: list[{client, detail}] - the per-client breakdown of how that tool was actually used,
    since the same tool is rarely used identically across different client engagements."""
    # IMPORTANT - this is capped by a DIFFERENT limit than the 100K/day figure elsewhere in this
    # file: Groq's free/on_demand tier also enforces a hard 12,000 TOKENS PER REQUEST ceiling
    # (prompt + max_tokens combined), independent of the daily budget. This endpoint sends the
    # FULL resume text as input (this template + a real resume commonly runs ~7-8K tokens on its
    # own), so max_tokens has to leave real headroom under 12,000 rather than being pushed as high
    # as the daily budget alone would allow - a request that exceeds it fails outright with a 413,
    # not a graceful truncation. 9000 was too high (a real request hit 16,395 total and got
    # rejected); this is set conservatively enough that prompt + max_tokens stays under the cap
    # for realistically long resumes.
    llm = get_llm(provider=provider, temperature=0.2, max_tokens=4000)
    prompt = ChatPromptTemplate.from_template(TOOL_BREAKDOWN_TEMPLATE)
    messages = prompt.format_messages(resume_text=resume_text)
    result, truncated = invoke_and_check_truncation(llm, messages)
    tools = _parse_tool_breakdown(result)
    return tools, truncated


def _parse_tool_breakdown(raw: str):
    """Each tool block has repeated CLIENT:/INFERRED:/DETAIL: line trios (DETAIL can span
    multiple lines - it's 2-3 full sentences, not a one-liner). INFERRED distinguishes an answer
    the resume states directly from one reconstructed from the role's surrounding context - see
    TOOL_BREAKDOWN_TEMPLATE's "two sources of truth" instructions."""
    # Case-insensitive throughout: different LLM providers/models don't reliably reproduce the
    # exact "TOOL:"/"EXPERIENCE:" casing asked for in the prompt (one might write "Tool:" instead)
    # - a case-sensitive regex would then match nothing at all and silently return zero tools,
    # even though the model answered the question correctly. This was seen in production after
    # switching Answer engines: a perfectly good answer came back, but the strict-case parser
    # couldn't read it, so the endpoint reported "couldn't extract a tool breakdown" for a synced
    # resume that had actually been read and summarized just fine.
    tools = []
    for block in raw.split("==="):
        tool_match = re.search(r"TOOL:\s*(.+)", block, re.IGNORECASE)
        exp_match = re.search(r"EXPERIENCE:\s*(.+)", block, re.IGNORECASE)
        level_match = re.search(r"LEVEL:\s*(.+)", block, re.IGNORECASE)
        if not (tool_match and exp_match and level_match):
            continue
        tool = tool_match.group(1).strip()
        if not tool or tool.lower() in ("tool", "none", "n/a"):
            continue

        # Each CLIENT: line starts a new entry; INFERRED: is optional (older cached syncs won't
        # have it - defaults to False rather than breaking); everything under DETAIL: (including
        # wrapped lines) belongs to that client, up until the next CLIENT: line or end of block.
        usages = []
        for client_match, inferred_match, detail_text in re.findall(
            r"CLIENT:\s*(.+?)\s*\n(?:INFERRED:\s*(.+?)\s*\n)?DETAIL:\s*(.+?)(?=\n\s*CLIENT:|\Z)",
            block, re.DOTALL | re.IGNORECASE,
        ):
            client = client_match.strip()
            detail = " ".join(detail_text.split())  # collapse wrapped newlines/whitespace
            inferred = inferred_match.strip().lower().startswith("y") if inferred_match else False
            if client:
                usages.append({"client": client, "detail": detail, "inferred": inferred})

        tools.append({
            "tool": tool,
            "experience": exp_match.group(1).strip(),
            "level": level_match.group(1).strip(),
            "usages": usages,
            # Kept for anything still reading the old flat "clients" shape.
            "clients": [u["client"] for u in usages],
        })
    return tools


VENDOR_QA_TEMPLATE = """You are simulating a REAL vendor/staffing agency screening call - the kind
that happens before a vendor will submit a candidate to their end client for a role. Below is the
candidate's RESUME and the JOB DESCRIPTION the vendor is screening against.

RESUME:
{resume_text}

JOB DESCRIPTION:
{jd_text}

Generate {num_questions} realistic vendor screening questions for THIS specific JD, drawn from the
categories a real vendor actually asks before submission - mix categories naturally, don't do them
in a fixed order:
- Tool/technology depth ("How many years of hands-on X do you have, and where did you use it?")
- Project scope and ownership ("Walk me through your role on the most relevant project.")
- Availability and notice period
- Rate expectations / rate justification
- Work authorization / visa status (ask generically, e.g. "What's your current work authorization
  status?" - never assume or state a specific status since the resume may not say)
- Relocation/remote preference
- Gaps or transitions between roles, if any are visible in the resume
- Why looking to move / why this opportunity

For EACH question, write the ANSWER the way the CANDIDATE should actually say it out loud on the
call - you ARE the candidate, speaking naturally in first person, never an AI describing someone
else's background. Read it back to yourself before finalizing: if a sentence sounds like it came
from a resume summary or an AI narrating a third party ("The candidate has experience with...",
"They worked on..."), rewrite it the way a real person actually talks on a phone screen -
contractions, natural phrasing, not stiff or formal.

AUTHENTICITY RULE: Never open an answer with generic soft-skill filler ("I'm a dedicated
professional with strong communication skills") - a vendor has heard that a thousand times and it
proves nothing. Ground every answer in specifics: real client/project names, real tool names,
real durations, real numbers/scale wherever the resume has them.

RECRUITER LENS: A vendor is satisfied by ownership language ("I built," "I owned," "I ran") over
passive team-speak, a concrete situation-action-result shape, and direct answers with zero
hedging ("I have some experience with..." fails - "I used it for about a year and a half at
Verizon" passes). Never a fabricated claim the resume doesn't support. If the JD asks about
something the resume doesn't clearly show, the honest answer should acknowledge that plainly and
pivot to the closest real transferable experience - a vendor screening a gap dishonestly is worse
than a vendor screening an honest "I haven't used X directly, but I've done Y which is closely
related."

For availability/rate/visa/relocation questions where the resume has no data, write a generic but
professional placeholder answer the candidate can adjust (e.g. "I'm available with two weeks
notice" - clearly framed as adjustable, not fabricated as fact), still in natural spoken first
person, not a form-letter tone.

Respond with each Q&A block in EXACTLY this format, separated by ===, nothing else:

CATEGORY: <Tool Depth|Project Scope|Availability|Rate|Work Authorization|Relocation|Gaps|Motivation>
QUESTION: <the vendor's question>
ANSWER: <the candidate's confident, resume-grounded answer, 60-140 words>
===

Begin now:"""


GENERIC_VENDOR_QA_TEMPLATE = """You are simulating a REAL vendor/staffing agency screening call - the
kind that happens before a vendor will submit a candidate to ANY end client, before a specific JD is
even in the picture. Below is the candidate's RESUME.

RESUME:
{resume_text}

Generate {num_questions} realistic vendor screening questions a staffing vendor would ask about THIS
candidate based on their resume alone, drawn from the categories a real vendor actually asks before
submission - mix categories naturally, don't do them in a fixed order:
- Tool/technology depth ("How many years of hands-on X do you have, and where did you use it?") -
  pick the 2-3 tools/technologies that show up MOST prominently across the resume, since those are
  what a vendor is most likely to probe on any call regardless of which client role comes up.
- Project scope and ownership ("Walk me through your role on your most significant project.")
- Availability and notice period
- Rate expectations / rate justification
- Work authorization / visa status (ask generically, e.g. "What's your current work authorization
  status?" - never assume or state a specific status since the resume may not say)
- Relocation/remote preference
- Gaps or transitions between roles, if any are visible in the resume
- Why looking for a new opportunity right now

For EACH question, write the ANSWER the way the CANDIDATE should actually say it out loud on the
call - you ARE the candidate, speaking naturally in first person, never an AI describing someone
else's background. Read it back to yourself before finalizing: if a sentence sounds like it came
from a resume summary or an AI narrating a third party ("The candidate has experience with...",
"They worked on..."), rewrite it the way a real person actually talks on a phone screen -
contractions, natural phrasing, not stiff or formal.

AUTHENTICITY RULE: Never open an answer with generic soft-skill filler ("I'm a dedicated
professional with strong communication skills") - a vendor has heard that a thousand times and it
proves nothing. Ground every answer in specifics: real client/project names, real tool names,
real durations, real numbers/scale wherever the resume has them.

RECRUITER LENS: A vendor is satisfied by ownership language ("I built," "I owned," "I ran") over
passive team-speak, a concrete situation-action-result shape, and direct answers with zero
hedging ("I have some experience with..." fails - "I used it for about a year and a half at
Verizon" passes).

For availability/rate/visa/relocation questions where the resume has no data, write a generic but
professional placeholder answer the candidate can adjust (e.g. "I'm available with two weeks
notice" - clearly framed as adjustable, not fabricated as fact), still in natural spoken first
person, not a form-letter tone.

Respond with each Q&A block in EXACTLY this format, separated by ===, nothing else:

CATEGORY: <Tool Depth|Project Scope|Availability|Rate|Work Authorization|Relocation|Gaps|Motivation>
QUESTION: <the vendor's question>
ANSWER: <the candidate's confident, resume-grounded answer, 60-140 words>
===

Begin now:"""


def generate_vendor_qa(resume_text: str, jd_text: str = "", provider: str = "groq", num_questions: int = 8):
    """Returns (items: list[dict], truncated: bool). Each item has category/question/answer.

    jd_text is optional: with a JD pasted, questions/answers are tailored to that specific role
    (original behavior). Without one, this generates the same category set straight from the
    resume alone - the common case, since a real vendor screening call usually happens before any
    specific JD is even shared, and requiring a JD paste for every sync was unnecessary friction
    for the core "know your resume cold" use case."""
    # Same Groq 12,000-tokens-per-request ceiling applies here as generate_tool_breakdown above
    # (see that function's comment) - this call also sends the FULL resume text as input, plus
    # the JD on top, so max_tokens needs real headroom under 12,000 rather than being pushed to
    # the daily-budget ceiling alone. Pulled back from 4500 as a precaution before it fails the
    # same way on a long resume + long JD.
    llm = get_llm(provider=provider, temperature=0.4, max_tokens=3200)
    if jd_text and jd_text.strip():
        prompt = ChatPromptTemplate.from_template(VENDOR_QA_TEMPLATE)
        messages = prompt.format_messages(resume_text=resume_text, jd_text=jd_text, num_questions=num_questions)
    else:
        prompt = ChatPromptTemplate.from_template(GENERIC_VENDOR_QA_TEMPLATE)
        messages = prompt.format_messages(resume_text=resume_text, num_questions=num_questions)
    result, truncated = invoke_and_check_truncation(llm, messages)
    items = _parse_vendor_qa(result)
    return items, truncated


def _parse_vendor_qa(raw: str):
    # Case-insensitive for the same reason as _parse_tool_breakdown above - different Answer
    # engines don't reliably reproduce the exact requested casing.
    items = []
    for block in raw.split("==="):
        cat_match = re.search(r"CATEGORY:\s*(.+)", block, re.IGNORECASE)
        q_match = re.search(r"QUESTION:\s*(.+?)(?=\nANSWER:|\Z)", block, re.DOTALL | re.IGNORECASE)
        a_match = re.search(r"ANSWER:\s*(.+)", block, re.DOTALL | re.IGNORECASE)
        if not (cat_match and q_match and a_match):
            continue
        items.append({
            "category": cat_match.group(1).strip(),
            "question": q_match.group(1).strip(),
            "answer": a_match.group(1).strip(),
        })
    return items


def jd_fingerprint(jd_text: str) -> str:
    """Normalizes a JD to a stable hash for dedup: same JD pasted again (even with minor
    whitespace differences) should be recognized as the same JD, so the cached vendor Q&A can be
    reused instead of spending tokens generating the same thing twice."""
    import hashlib
    normalized = re.sub(r"\s+", " ", jd_text.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()
