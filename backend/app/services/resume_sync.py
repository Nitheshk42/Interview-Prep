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
from concurrent.futures import ThreadPoolExecutor
from langchain_core.prompts import ChatPromptTemplate
from app.services.llm_provider import get_llm, invoke_and_check_truncation

# How many tools' rich per-client detail gets requested in a single LLM call (see
# generate_tool_breakdown's two-pass design below). Small enough that even a long resume's context
# plus this many tools' worth of 2-3-sentence-per-client output stays comfortably under Groq's
# hard 12,000-tokens-PER-REQUEST ceiling, regardless of how many tools the resume has in total.
DETAIL_BATCH_SIZE = 4


TOOL_LIST_TEMPLATE = """You are helping a candidate identify every distinct tool, technology,
language, platform, framework, or methodology actually mentioned in their resume (e.g. Java,
Kafka, AWS, Kubernetes, Agile/Scrum, Jenkins, React, SQL Server, Hadoop - whatever genuinely
appears). This is a first pass to build the complete LIST only - per-client detail comes in a
later step, so keep this fast and just cover EVERY tool, however many there are.

RESUME:
{resume_text}

For EACH tool, work out:
- EXPERIENCE: total time used, estimated from the date ranges of the client/project entries where
  it appears (e.g. "3 years 2 months" or "2+ years" if ranges are approximate). If a tool appears
  across multiple non-contiguous roles, add the periods together rather than just citing the most
  recent one.
- LEVEL: one of Beginner / Intermediate / Advanced / Expert, judged from how central the tool was
  to the role, how long it was used, and how deeply it's described (not just whether it's
  mentioned once in a skills list).

Do NOT invent a tool that isn't actually in the resume. Do NOT skip a tool just because it only
appears once - list it with whatever real duration that one appearance supports. Order the list
with the tools used most extensively (longest total experience) first. Do not write anything about
which clients used which tool - that's a separate step, skip it entirely here.

Respond with each tool as a block in EXACTLY this format, separated by ===, nothing else, no
extra commentary:

TOOL: <tool name>
EXPERIENCE: <total time>
LEVEL: <Beginner|Intermediate|Advanced|Expert>
===

Begin now:"""


TOOL_DETAIL_TEMPLATE = """You are helping a candidate "sync" with their own resume before a
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

Write per-client detail for ONLY these specific tools, and nothing else - do not write about any
other tool even if it appears in the resume, it's covered in a separate batch: {tool_names}

For EACH of those tools, for EVERY client/company/project (in the format the resume uses) where it
was actually used, most recent first, write a REAL, SPEAKABLE answer - 2 to 3 full sentences, not
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

Do NOT invent a client, metric, or system that doesn't appear anywhere in the resume. For INFERRED
entries, reasoning from the role's real surrounding context is expected and encouraged - that's
the whole point - but stay grounded in what's actually there.

Respond with each of the requested tools as a block in EXACTLY this format, separated by ===,
nothing else, no extra commentary. Repeat the CLIENT/INFERRED/DETAIL trio once per client:

TOOL: <tool name - must be one of the ones listed above>
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
    since the same tool is rarely used identically across different client engagements.

    TWO-PASS DESIGN - this used to be one giant LLM call asking for every tool AND every client's
    full narrative at once. That worked for a short resume, but Groq's free tier also enforces a
    hard 12,000-TOKENS-PER-REQUEST ceiling (prompt + output combined, separate from the 100K/day
    budget), and a resume with a dozen-plus tools each needing several rich per-client sentences
    can easily need more OUTPUT than that ceiling allows - the response then gets cut off
    mid-list, and whatever tools hadn't been written yet just never appear (seen in production: a
    resume with far more than 3 tools only showed 3, with a truncation warning).

    Splitting into two passes fixes this regardless of resume size:
    1. A cheap first call lists EVERY tool with just its total experience/level - no per-client
       narrative yet, so this is a small enough request to always finish completely no matter how
       many tools exist.
    2. The rich per-client detail is then generated in small batches (DETAIL_BATCH_SIZE tools per
       call, run concurrently) - each batch's output is small enough to stay well under the
       per-request ceiling even though the full resume text is resent each time, so no batch
       truncates either. A sync now takes a bit longer overall (several calls instead of one) and
       uses somewhat more total tokens - a deliberate trade for "never silently drops tools"."""
    tool_list, truncated = _generate_tool_list(resume_text, provider)
    if not tool_list:
        return [], truncated

    batches = [tool_list[i:i + DETAIL_BATCH_SIZE] for i in range(0, len(tool_list), DETAIL_BATCH_SIZE)]

    def _run_batch(batch):
        names = [t["tool"] for t in batch]
        return _generate_tool_details(resume_text, names, provider)

    details_by_name = {}
    with ThreadPoolExecutor(max_workers=min(4, len(batches))) as executor:
        for batch_details, batch_truncated in executor.map(_run_batch, batches):
            truncated = truncated or batch_truncated
            details_by_name.update(batch_details)

    tools = []
    for t in tool_list:
        detail_entry = details_by_name.get(t["tool"].strip().lower())
        usages = detail_entry["usages"] if detail_entry else []
        tools.append({
            "tool": t["tool"],
            "experience": t["experience"],
            "level": t["level"],
            "usages": usages,
            # Kept for anything still reading the old flat "clients" shape.
            "clients": [u["client"] for u in usages],
        })
    return tools, truncated


def _generate_tool_list(resume_text: str, provider: str):
    """Pass 1 - see generate_tool_breakdown's docstring. Returns (list[{tool, experience, level}],
    truncated: bool). Cheap enough (no per-client narrative) that this should essentially never
    truncate, but still checked - a truncated tool LIST would mean tools are missing before pass 2
    even starts, which is worth surfacing to the user same as any other truncation."""
    llm = get_llm(provider=provider, temperature=0.2, max_tokens=1500)
    prompt = ChatPromptTemplate.from_template(TOOL_LIST_TEMPLATE)
    messages = prompt.format_messages(resume_text=resume_text)
    result, truncated = invoke_and_check_truncation(llm, messages)

    tools = []
    for block in result.split("==="):
        tool_match = re.search(r"TOOL:\s*(.+)", block, re.IGNORECASE)
        exp_match = re.search(r"EXPERIENCE:\s*(.+)", block, re.IGNORECASE)
        level_match = re.search(r"LEVEL:\s*(.+)", block, re.IGNORECASE)
        if not (tool_match and exp_match and level_match):
            continue
        tool = tool_match.group(1).strip()
        if not tool or tool.lower() in ("tool", "none", "n/a"):
            continue
        tools.append({
            "tool": tool,
            "experience": exp_match.group(1).strip(),
            "level": level_match.group(1).strip(),
        })

    if not tools:
        # Nothing parsed at all - this is exactly the failure mode that shows the user "Couldn't
        # extract a tool breakdown," and until now there was no way to tell WHY from Render's logs
        # (the LLM call itself succeeded - no exception - it's the parser that came up empty). This
        # prints the model's actual raw response so the real cause (wrong format, refusal, empty
        # completion, etc.) is visible in the logs the next time this happens, instead of just a
        # generic "couldn't extract" with no signal.
        print(f"[resume_sync] Pass-1 tool list parse failed (provider={provider}). Raw model output was:\n{result[:3000]}")

    return tools, truncated


def _generate_tool_details(resume_text: str, tool_names: list[str], provider: str):
    """Pass 2, one batch - see generate_tool_breakdown's docstring. Returns
    ({tool_name_lowercase: {"usages": [...]}, ...}, truncated: bool) for just this batch of tools."""
    llm = get_llm(provider=provider, temperature=0.2, max_tokens=2200)
    prompt = ChatPromptTemplate.from_template(TOOL_DETAIL_TEMPLATE)
    messages = prompt.format_messages(resume_text=resume_text, tool_names=", ".join(tool_names))
    result, truncated = invoke_and_check_truncation(llm, messages)

    details = {}
    for block in result.split("==="):
        tool_match = re.search(r"TOOL:\s*(.+)", block, re.IGNORECASE)
        if not tool_match:
            continue
        tool = tool_match.group(1).strip()
        if not tool:
            continue

        # Each CLIENT: line starts a new entry; INFERRED: is optional; everything under DETAIL:
        # (including wrapped lines) belongs to that client, up until the next CLIENT: line or end
        # of block. Case-insensitive throughout - see generate_tool_breakdown's docstring on why.
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

        details[tool.lower()] = {"usages": usages}

    if not details:
        # Same visibility gap as _generate_tool_list above - a batch coming back with zero parsed
        # tools currently just means those tools silently show "no client detail" in the UI, with
        # nothing in the logs explaining why. This makes that batch's actual raw output visible.
        print(f"[resume_sync] Pass-2 detail batch parse failed for tools={tool_names} (provider={provider}). Raw model output was:\n{result[:3000]}")

    return details, truncated


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
