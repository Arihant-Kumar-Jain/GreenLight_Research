"""Research chat: a to-and-fro conversation with an agent that knows the whole project and can keep researching.

Each researcher message runs one harness Agent (Nemotron Super) with the full research toolbox plus credibility
tools. Memory has three layers:
  - pinned project state: brief, verdict, novelty, closest papers and the shared notebook (always in the prompt)
  - conversation: recent turns verbatim; older turns folded by Nemotron Nano into a running summary
  - in-turn context: the harness compresses tool results when the turn gets long
New papers found in chat are scored for credibility before the agent answers about them.
"""

import re
from typing import Annotated

from pydantic import Field

from .. import db, llm, papers, privacy, trace, verify
from ..budget import Budget
from ..config import settings
from ..harness import Agent, tool
from . import toolbox
from .intake import brief_text, load_memory, save_memory

WINDOW_MAX = 16
WINDOW_KEEP = 8

SYSTEM = """You are GreenLight Research's research assistant, in an ongoing conversation with a researcher about their
idea. You have the full project state (pinned below) and research tools: scholarly + web search, citation graph,
full-text reading, the project's paper corpus, credibility scoring and the shared notebook.

How to answer:
- Ground every factual claim about the literature in papers, cited inline as [P#] (ids from the project or tool
  results only; never invent papers, numbers or authors). If the corpus lacks it, search for it.
- When you rely on a paper, consider its credibility (score/100, tier, red flags) and say so when it is weak.
- If the researcher changes the idea, say what that changes for novelty, and search the new angle.
- Be direct and concise, like a senior collaborator. Use Markdown. Admit uncertainty.
- Record important new findings with `note`."""


def _project_state(pid: str) -> str:
    p = db.project(pid) or {}
    parts = [f"## Project: {p.get('title') or 'untitled'}", brief_text(p.get("brief") or {})]
    v = p.get("verdict")
    if v:
        parts.append(f"Verdict: {v['light'].upper()} — {v['headline']}\nNext steps: {'; '.join(v.get('next_steps', [])[:4])}")
    nov = p.get("novelty")
    if nov:
        parts.append(f"Novelty score {nov.get('score')}/100. Components: " + "; ".join(
            f"{c['id']} {c['text'][:60]} → {c['best']}" for c in nov.get("components", [])))
    ps = sorted(db.papers(pid), key=lambda x: -((x.get("credibility") or {}).get("score") or 0))
    closest = {c["id"] for c in (((p.get("stats") or {}).get("review") or {}).get("closest") or [])}
    top = [x for x in ps if x["id"] in closest][:10] + [x for x in ps if x["id"] not in closest][:10]
    if top:
        parts.append(f"Key papers ({len(ps)} in corpus):\n" + "\n".join(
            f"- {x['id']} {x['title'][:90]} ({x.get('year')}, cred {(x.get('credibility') or {}).get('score', '?')})"
            for x in top))
    nb = toolbox.notebook_text(pid, 20)
    if nb:
        parts.append(nb)
    return "\n\n".join(parts)


async def _fold(pid: str, msgs: list[dict]) -> dict:
    summary = load_memory(pid, "chat")
    cut = len(msgs) - WINDOW_KEEP
    if len(msgs) <= WINDOW_MAX or cut <= summary["upto"]:
        return summary
    older = "\n".join(f"{m['role']}: {m['content'][:1500]}" for m in msgs[summary["upto"]:cut])
    res = await llm.chat("fast", [
        {"role": "system", "content": "Summarise these turns of a research conversation as compact facts: questions "
                                      "asked, answers with their [P#] citations, decisions, changes to the idea, open "
                                      "threads. Keep every paper id. No commentary."},
        {"role": "user", "content": f"Earlier summary:\n{summary['text'] or '(none)'}\n\nTurns:\n{older}"}],
        title="Fold older chat turns into memory", max_tokens=1200)
    summary = {"upto": cut, "text": res.text.strip()}
    save_memory(pid, "chat", summary)
    trace.log("compress", f"Chat memory: folded {cut} older message(s) into a summary",
              summary["text"][:1500])
    return summary


async def reply(pid: str, text: str) -> dict:
    """Answer one researcher message. Returns {content, papers, steps, tool_calls}."""
    clean = privacy.redact(text)
    db.add_message(pid, "chat", "user", clean.text, {"redactions": clean.summary()} if clean.count else None)
    budget = Budget(usd=max(0.05, settings.max_usd_per_run / 3), llm_calls=40, tool_calls=40, seconds=420)
    with trace.scope(project_id=pid, agent="Research Chat", budget=budget):
        msgs = db.messages(pid, "chat")
        summary = await _fold(pid, msgs)
        recent = msgs[summary["upto"]:]
        convo = "\n\n".join(f"{'Researcher' if m['role'] == 'user' else 'You'}: {m['content']}" for m in recent[:-1])

        @tool("Score credibility (0-100) of papers that don't have a score yet: citations, author h-index, venue, "
              "adoption, red flags. Returns the breakdown.",
              digest=lambda r: "scored " + ", ".join(f"{x['id']}={x['score']}" for x in (r or {}).get("scores", []))
              if isinstance(r, dict) else str(r)[:100])
        async def score_credibility(ids: Annotated[list[str], Field(description="P# ids, max 10")]) -> dict:
            ids = [i.upper() for i in ids[:10] if db.paper(pid, i)]
            todo = [i for i in ids if not (db.paper(pid, i) or {}).get("credibility")]
            if todo:
                await papers.enrich(pid, todo)
            out = []
            for i in ids:
                c = (db.paper(pid, i) or {}).get("credibility") or {}
                out.append({"id": i, "score": c.get("score"), "tier": c.get("tier"), "confidence": c.get("confidence"),
                            "why": {x["name"]: x["detail"] for x in c.get("components", [])}, "notes": c.get("notes")})
            return {"scores": out}

        agent = Agent("Research Chat", SYSTEM, toolbox.research_tools(pid, "Research Chat") + [score_credibility],
                      role="reason", max_steps=8, budget=budget, context_tokens=settings.context_budget_tokens,
                      pinned=lambda: _project_state(pid), max_tokens=4000, temperature=0.3)
        task = ((f"Summary of the earlier conversation:\n{summary['text']}\n\n" if summary["text"] else "")
                + (f"Recent conversation:\n{convo}\n\n" if convo else "")
                + f"Researcher's new message:\n{clean.text}")
        res = await agent.run(task)
    answer = res.text or "I couldn't produce an answer within the budget. Try a narrower question."
    known = {p["id"] for p in db.papers(pid)}
    cited = list(dict.fromkeys(i for i in re.findall(r"\bP\d+\b", answer)))
    bad = [i for i in cited if i not in known]
    if bad:
        answer += f"\n\n> ⚠️ Unknown paper id(s) {', '.join(bad)} in this answer: treat those claims as unsupported."
    check = None
    if any(i in known for i in cited):  # same groundedness check as the report, on every cited sentence
        with trace.scope(project_id=pid, agent="Citation Checker"):
            check = await verify.check_claims(pid, answer, max_claims=12)
        flagged = {c["text"] for c in check["claims"] if c["label"] == "unsupported"}
        for sent in flagged:
            answer = answer.replace(sent, f"{sent} ⚠️*[not supported by the cited paper]*")
    data = {"papers": [i for i in cited if i in known], "steps": res.steps, "tool_calls": res.tool_calls,
            "citations": {k: check[k] for k in ("supported", "partial", "unsupported")} if check else None,
            "stopped_because": res.stopped_because, "budget": budget.snapshot(), "context": res.context}
    db.add_message(pid, "chat", "assistant", answer, data)
    return {"content": answer, **data}
