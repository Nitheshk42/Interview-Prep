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
  with this there?" Each one must cover, using specifics pulled straight from that client's
  bullet points/context in the resume:
    1. What was actually built or the problem solved (the concrete deliverable, not "worked on
       data pipelines").
    2. The specific sub-components/ecosystem pieces used if the resume shows them (e.g. for
       Hadoop: HDFS, Hive, YARN, MapReduce, Sqoop - whichever the resume actually names; for AWS:
       which specific services).
    3. Scale, data volume, team size, or frequency if the resume states or implies any of it.
  Never write the same description twice for two different clients even if the resume's phrasing
  for them is similar - find the real distinguishing detail (different data source, different
  scale, different part of the pipeline, different team's need). If the resume genuinely gives no
  detail beyond listing the tool for that client, say so plainly (e.g. "The resume lists Hadoop
  under this role's skills but doesn't detail specific usage - be ready to speak to it from
  memory or lean on a client where the resume does have detail") rather than fabricating specifics
  that aren't there.

Do NOT invent a tool that isn't actually in the resume. Do NOT invent ecosystem components,
scale, or specifics the resume doesn't support - ground everything in what's actually written,
and be honest in the DETAIL when it isn't there. Do NOT skip a tool just because it only appears
once - list it with whatever real duration/client that one appearance supports. Order the list
with the tools used most extensively (longest total experience) first.

Respond with each tool as a block in EXACTLY this format, separated by ===, nothing else, no
extra commentary. Repeat the CLIENT/DETAIL pair once per client that tool was used at:

TOOL: <tool name>
EXPERIENCE: <total time>
LEVEL: <Beginner|Intermediate|Advanced|Expert>
CLIENT: <Client A>
DETAIL: <2-3 full, speakable sentences - what was built, ecosystem pieces used, scale if known>
CLIENT: <Client B>
DETAIL: <2-3 full, speakable sentences - what was built, ecosystem pieces used, scale if known>
===

Begin now:"""


def generate_tool_breakdown(resume_text: str, provider: str = "groq"):
    """Returns (tools: list[dict], truncated: bool). Each tool dict has tool/experience/level and
    usages: list[{client, detail}] - the per-client breakdown of how that tool was actually used,
    since the same tool is rarely used identically across different client engagements."""
    # Raised (2200 -> 3200 -> 7000 -> 9000). Each client entry is now 2-3 full sentences instead
    # of one fragment - a resume with 15-20+ tools across several clients each needs real headroom
    # for that. Completeness over token frugality during testing: still a small fraction of the
    # 100K/day budget, and a partial/truncated tool list defeats the entire point of the feature.
    llm = get_llm(provider=provider, temperature=0.2, max_tokens=9000)
    prompt = ChatPromptTemplate.from_template(TOOL_BREAKDOWN_TEMPLATE)
    messages = prompt.format_messages(resume_text=resume_text)
    result, truncated = invoke_and_check_truncation(llm, messages)
    tools = _parse_tool_breakdown(result)
    return tools, truncated


def _parse_tool_breakdown(raw: str):
    """Each tool block now has repeated CLIENT:/DETAIL: line pairs (DETAIL can span multiple
    lines - it's 2-3 full sentences, not a one-liner) instead of the old single semicolon-joined
    USAGE: line, since real sentences can contain semicolons/colons themselves and would have
    broken that format."""
    tools = []
    for block in raw.split("==="):
        tool_match = re.search(r"TOOL:\s*(.+)", block)
        exp_match = re.search(r"EXPERIENCE:\s*(.+)", block)
        level_match = re.search(r"LEVEL:\s*(.+)", block)
        if not (tool_match and exp_match and level_match):
            continue
        tool = tool_match.group(1).strip()
        if not tool or tool.lower() in ("tool", "none", "n/a"):
            continue

        # Each CLIENT: line starts a new entry; everything under its DETAIL: (including extra
        # wrapped lines) belongs to that client, up until the next CLIENT: line or end of block.
        usages = []
        for client_match, detail_text in re.findall(
            r"CLIENT:\s*(.+?)\s*\nDETAIL:\s*(.+?)(?=\n\s*CLIENT:|\Z)", block, re.DOTALL
        ):
            client = client_match.strip()
            detail = " ".join(detail_text.split())  # collapse wrapped newlines/whitespace
            if client:
                usages.append({"client": client, "detail": detail})

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


def generate_vendor_qa(resume_text: str, jd_text: str, provider: str = "groq", num_questions: int = 8):
    """Returns (items: list[dict], truncated: bool). Each item has category/question/answer."""
    # Raised (3200 -> 4500) - 8 full Q&A pairs per call; completeness over frugality during testing.
    llm = get_llm(provider=provider, temperature=0.4, max_tokens=4500)
    prompt = ChatPromptTemplate.from_template(VENDOR_QA_TEMPLATE)
    messages = prompt.format_messages(resume_text=resume_text, jd_text=jd_text, num_questions=num_questions)
    result, truncated = invoke_and_check_truncation(llm, messages)
    items = _parse_vendor_qa(result)
    return items, truncated


def _parse_vendor_qa(raw: str):
    items = []
    for block in raw.split("==="):
        cat_match = re.search(r"CATEGORY:\s*(.+)", block)
        q_match = re.search(r"QUESTION:\s*(.+?)(?=\nANSWER:|\Z)", block, re.DOTALL)
        a_match = re.search(r"ANSWER:\s*(.+)", block, re.DOTALL)
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
