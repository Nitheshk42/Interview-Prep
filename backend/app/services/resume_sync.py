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
vendor screening call or interview - they need to be able to state, without hesitation, how much
experience they have with each tool and where they used it.

RESUME:
{resume_text}

Go through this resume and identify EVERY distinct tool, technology, language, platform,
framework, or methodology actually mentioned (e.g. Java, Kafka, AWS, Kubernetes, Agile/Scrum,
Jenkins, React, SQL Server - whatever genuinely appears). For EACH one, work out:

- EXPERIENCE: total time used, estimated from the date ranges of the client/project entries
  where it appears (e.g. "3 years 2 months" or "2+ years" if ranges are approximate). If a tool
  appears across multiple non-contiguous roles, add the periods together rather than just citing
  the most recent one.
- CLIENTS: every client/company/project name (in the format the resume uses) where this tool
  was actually used, comma-separated, most recent first.
- LEVEL: one of Beginner / Intermediate / Advanced / Expert, judged from how central the tool was
  to the role, how long it was used, and how deeply it's described (not just whether it's
  mentioned once in a skills list).

Do NOT invent a tool that isn't actually in the resume. Do NOT skip a tool just because it only
appears once - list it with whatever real duration/client that one appearance supports. Order
the list with the tools used most extensively (longest total experience) first.

Respond with ONE LINE PER TOOL in EXACTLY this pipe-delimited format, nothing else, no headers,
no numbering:

TOOL :: EXPERIENCE :: LEVEL :: CLIENTS

Begin now:"""


def generate_tool_breakdown(resume_text: str, provider: str = "groq"):
    """Returns (tools: list[dict], truncated: bool). Each tool dict has tool/experience/level/clients."""
    llm = get_llm(provider=provider, temperature=0.2, max_tokens=2200)
    prompt = ChatPromptTemplate.from_template(TOOL_BREAKDOWN_TEMPLATE)
    messages = prompt.format_messages(resume_text=resume_text)
    result, truncated = invoke_and_check_truncation(llm, messages)
    tools = _parse_tool_breakdown(result)
    return tools, truncated


def _parse_tool_breakdown(raw: str):
    tools = []
    for line in raw.strip().splitlines():
        line = line.strip().lstrip("-").strip()
        if not line or "::" not in line:
            continue
        parts = [p.strip() for p in line.split("::")]
        if len(parts) != 4:
            continue
        tool, experience, level, clients_raw = parts
        if tool.lower() in ("tool", "none"):
            continue
        clients = [c.strip() for c in clients_raw.split(",") if c.strip()]
        tools.append({"tool": tool, "experience": experience, "level": level, "clients": clients})
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
    llm = get_llm(provider=provider, temperature=0.4, max_tokens=3200)
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
