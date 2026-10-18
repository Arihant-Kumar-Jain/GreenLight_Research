"""Intake agent: a to-and-fro chat that sharpens a researcher's rough idea into a testable research brief.

Each turn Nemotron Super sees the conversation (older turns folded into a summary by Nano) plus its current draft and
returns a reply, up to four clarifying questions with quick-reply options, an updated structured brief and whether
it is specific enough to start the deep research. The brief's `contributions` are what novelty is tested against.
"""

import json

from pydantic import BaseModel, Field

from .. import db, llm, trace

HISTORY_TOKENS = 4000  # fold older intake turns once the verbatim chat exceeds this
WINDOW_KEEP = 8


class Question(BaseModel):
    question: str
    why: str = Field("", description="Why it matters for the research, at most 12 words")
    options: list[str] = Field(default_factory=list, description="2-4 likely answers as quick replies, or empty")


class Brief(BaseModel):
    title: str = Field("", description="Short working title of the research idea")
    research_question: str = Field("", description="The question the researcher wants to answer, one sentence")
    hypothesis: str = Field("", description="What they expect to show")
    method: str = Field("", description="Proposed approach / technique, concretely")
    contributions: list[str] = Field(default_factory=list,
                                     description="2-5 claimed novel contributions, each a specific, testable phrase")
    field: str = Field("", description="Research area, e.g. 'NLP / parameter-efficient fine-tuning'")
    datasets_benchmarks: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list, description="Methods they would compare against")
    known_related_work: list[str] = Field(default_factory=list, description="Papers/methods the researcher named")
    constraints: str = Field("", description="Compute, data, time or venue constraints if mentioned")
    keywords: list[str] = Field(default_factory=list, description="6-12 search keywords incl. synonyms")
    open_points: list[str] = Field(default_factory=list, description="Assumptions made and facts still unknown")


class Turn(BaseModel):
    reply: str = Field(description="Markdown shown to the researcher. Do not repeat the questions here.")
    questions: list[Question] = Field(default_factory=list, description="0-4 clarifying questions, most important first")
    ready: bool = Field(False, description="True when the brief is specific enough for literature + novelty research")
    missing: list[str] = Field(default_factory=list)
    brief: Brief


SYSTEM = """You are the intake scientist of GreenLight Research, a deep research assistant that tells researchers
whether their idea has already been done, how credible the closest prior work is, and whether it is worth pursuing.
Your job: through a short conversation, turn a rough idea into a precise research brief so the literature search and
the novelty test are excellent.

What the research needs (ask only about what is missing or vague):
1. The research question and hypothesis.  2. The concrete method (what is actually new in the technique).
3. The claimed contributions, phrased as specific testable statements (these are checked one by one against prior
   work, so vague ones like "better performance" are useless; push for "X applied to Y under Z").
4. Field, datasets/benchmarks and baselines.  5. Related work the researcher already knows (to avoid re-finding it).

How to behave:
- After every message rebuild the brief from the WHOLE conversation. Never drop facts the researcher gave.
- Ask 1-4 short, high-value questions at a time with a few words on why each matters; offer 2-4 likely answers as
  options when it helps. Never re-ask. Think like a sharp advisor: probe what makes the idea different.
- Generate good search keywords yourself, including synonyms and older names of the technique.
- When the brief is specific enough, set ready=true; the reply MUST then restate the idea in 2-3 crisp lines (question,
  method, key contributions) and invite them to start the deep research or keep refining.
- If they say "just start", set ready=true, fill gaps with labelled assumptions under open_points.
- Never claim anything about the literature yet — the research does that. No invented papers."""


def _transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        if m["role"] == "user":
            lines.append(f"Researcher: {m['content']}")
        else:
            qs = "".join(f"\n  {i + 1}. {q['question']}" for i, q in enumerate((m.get("data") or {}).get("questions") or []))
            lines.append(f"Intake: {m['content']}{qs}")
    return "\n\n".join(lines)


async def _fold(pid: str, messages: list[dict]) -> dict:
    from ..harness.context import tokens
    summary = load_memory(pid, "intake")
    cut = len(messages) - WINDOW_KEEP
    if sum(tokens(m["content"]) for m in messages[summary["upto"]:]) <= HISTORY_TOKENS or cut <= summary["upto"]:
        return summary
    res = await llm.chat("fast", [
        {"role": "system", "content": "Summarise this part of a research-idea interview as a compact list of facts "
                                      "(question, method, contributions, datasets, baselines, known work, decisions). "
                                      "Keep every concrete fact. No commentary."},
        {"role": "user", "content": f"Earlier summary:\n{summary['text'] or '(none)'}\n\n"
                                    f"New turns:\n{_transcript(messages[summary['upto']:cut])}"},
    ], title="Fold older intake turns into memory", max_tokens=1500)
    summary = {"upto": cut, "text": res.text.strip()}
    save_memory(pid, "intake", summary)
    return summary


def load_memory(pid: str, phase: str) -> dict:
    p = db.project(pid) or {}
    mem = json.loads(p["chat_memory"]) if p.get("chat_memory") else {}
    return mem.get(phase) or {"upto": 0, "text": ""}


def save_memory(pid: str, phase: str, summary: dict) -> None:
    p = db.project(pid) or {}
    mem = json.loads(p["chat_memory"]) if p.get("chat_memory") else {}
    mem[phase] = summary
    db.update_project(pid, chat_memory=json.dumps(mem, ensure_ascii=False))


async def turn(pid: str) -> Turn:
    """Run one intake turn over the project's intake conversation (its last message is the researcher's newest)."""
    with trace.scope(project_id=pid, agent="Intake"):
        messages = db.messages(pid, "intake")
        summary = await _fold(pid, messages)
        p = db.project(pid) or {}
        parts = []
        if summary["text"]:
            parts.append(f"Summary of earlier conversation:\n{summary['text']}")
        if p.get("brief"):
            parts.append(f"Your current brief:\n{json.dumps(p['brief'], ensure_ascii=False)}")
        parts.append(f"Conversation (latest last):\n{_transcript(messages[summary['upto']:])}")
        t = await llm.chat_json("reason", SYSTEM, "\n\n".join(parts), Turn, title="Intake turn", max_tokens=3500)
        db.update_project(pid, brief=t.brief.model_dump(), title=t.brief.title or p.get("title"))
        return t


def brief_text(brief: dict) -> str:
    b = Brief.model_validate(brief or {})
    rows = [("Title", b.title), ("Research question", b.research_question), ("Hypothesis", b.hypothesis),
            ("Method", b.method), ("Claimed contributions", "; ".join(b.contributions)), ("Field", b.field),
            ("Datasets/benchmarks", ", ".join(b.datasets_benchmarks)), ("Baselines", ", ".join(b.baselines)),
            ("Related work the researcher knows", ", ".join(b.known_related_work)), ("Constraints", b.constraints),
            ("Keywords", ", ".join(b.keywords)), ("Assumptions / open points", "; ".join(b.open_points))]
    return "\n".join(f"{k}: {v}" for k, v in rows if v)
