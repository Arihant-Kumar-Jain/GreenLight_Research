"""Research chat: a to-and-fro conversation with an agent that knows the whole project and can keep researching.

Each researcher message runs one harness Agent (Nemotron Super) with the full research toolbox plus credibility
tools. Memory has five layers, from always-present to on-demand:
  1. pinned project state  - brief, verdict, novelty, closest papers, shared notebook (always in the system prompt)
  2. long-term facts       - after every exchange Nano extracts durable facts (decisions, idea changes, preferences,
                             findings with P# ids); merged, de-duplicated, pinned forever
  3. rolling summary       - when the verbatim history exceeds a token budget, older turns are folded by Nano
  4. episodic recall       - every exchange is embedded (Qwen3); the most relevant earlier exchanges are recalled
                             verbatim for the new message, including ones already folded away
  5. in-turn compression   - the harness elides/folds tool results inside a long turn
After answering, every cited sentence is checked against the cited papers; if any is unsupported the agent revises
its answer once (self-correction) and the revision is checked again.
"""

import re
from typing import Annotated

from pydantic import Field

from typing import Literal

import numpy as np
from pydantic import BaseModel

from .. import corpus, db, llm, papers, privacy, trace, verify
from ..budget import Budget
from ..harness.context import tokens
from ..config import settings
from ..harness import Agent, tool
from . import toolbox
from .intake import brief_text, load_memory, save_memory

HISTORY_TOKENS = 5000   # verbatim history budget before folding
KEEP_RECENT = 6         # messages always kept verbatim
MAX_FACTS = 40

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
    """Layer 3: fold older turns once the verbatim history is over the token budget."""
    summary = load_memory(pid, "chat")
    recent = msgs[summary["upto"]:]
    size = sum(tokens(m["content"]) for m in recent)
    cut = len(msgs) - KEEP_RECENT
    if size <= HISTORY_TOKENS or cut <= summary["upto"]:
        return summary
    older = "\n".join(f"{m['role']}: {m['content'][:1500]}" for m in msgs[summary["upto"]:cut])
    res = await llm.chat("fast", [
        {"role": "system", "content": "Summarise these turns of a research conversation as compact facts: questions "
                                      "asked, answers with their [P#] citations, decisions, changes to the idea, open "
                                      "threads. Keep every paper id. No commentary."},
        {"role": "user", "content": f"Earlier summary:\n{summary['text'] or '(none)'}\n\nTurns:\n{older}"}],
        title="Fold older chat turns into memory", max_tokens=1200)
    new = {"upto": cut, "text": res.text.strip()}
    save_memory(pid, "chat", new)
    trace.log("compress", f"Chat memory: folded {cut - summary['upto']} message(s), {size:,} → "
                          f"{tokens(new['text']) + sum(tokens(m['content']) for m in msgs[cut:]):,} tokens",
              new["text"][:1500], tokens_in=size, tokens_out=tokens(new["text"]))
    return new


class Fact(BaseModel):
    kind: Literal["decision", "idea_change", "preference", "finding", "open_question"]
    text: str


class Facts(BaseModel):
    facts: list[Fact]


async def _remember(pid: str, question: str, answer: str) -> None:
    """Layer 2: extract durable facts from the latest exchange into long-term memory."""
    mem = load_memory(pid, "facts")
    items = mem.get("items") or []
    try:
        out = await llm.chat_json("fast", "Extract 0-4 DURABLE facts worth remembering for the rest of this research "
                                  "conversation: the researcher's decisions, changes to their idea, stated preferences "
                                  "or constraints, key findings (keep [P#] ids), open questions. Skip small talk and "
                                  "anything already known.",
                                  f"Already known:\n" + "\n".join(f"- {i['text']}" for i in items[-MAX_FACTS:])
                                  + f"\n\nResearcher: {question[:2000]}\n\nAssistant: {answer[:3000]}",
                                  Facts, title="Long-term memory: extract facts", max_tokens=600)
    except Exception as e:
        trace.error("Fact extraction failed", str(e)[:200])
        return
    seen = {re.sub(r"\W+", " ", i["text"].lower()).strip() for i in items}
    added = [f.model_dump() for f in out.facts if re.sub(r"\W+", " ", f.text.lower()).strip() not in seen]
    if added:
        save_memory(pid, "facts", {"upto": 0, "text": "", "items": (items + added)[-MAX_FACTS:]})
        trace.log("compress", f"Long-term memory: +{len(added)} fact(s)", "\n".join(f"{a['kind']}: {a['text']}" for a in added))


def _facts_text(pid: str) -> str:
    items = load_memory(pid, "facts").get("items") or []
    if not items:
        return ""
    return "## Long-term memory of this conversation\n" + "\n".join(f"- ({i['kind']}) {i['text']}" for i in items)


async def _recall(pid: str, query: str, exclude_ids: set[int], k: int = 3) -> list[dict]:
    """Layer 4: earlier exchanges most similar to the new message (episodic memory), even if folded away."""
    past = [m for m in db.messages(pid, "chat") if m["role"] == "assistant" and m["id"] not in exclude_ids
            and (m.get("data") or {}).get("vec")]
    if not past:
        return []
    try:
        qv = np.asarray((await llm.embed([query], query=True, title="Embed message for episodic recall"))[0][:1024])
    except Exception:
        return []
    qv = qv / (np.linalg.norm(qv) or 1)
    scored = []
    for m in past:
        v = np.asarray(m["data"]["vec"], dtype=np.float32)
        scored.append((float(v @ qv) / (np.linalg.norm(v) or 1), m))
    scored.sort(key=lambda x: -x[0])
    return [{"sim": round(s, 3), "q": m["data"].get("question", ""), "a": m["content"][:900]} for s, m in scored[:k]
            if s > 0.3]


async def _embed_exchange(question: str, answer: str) -> list[float] | None:
    try:
        v = (await llm.embed([f"Q: {question[:1000]}\nA: {answer[:2000]}"], title="Embed exchange (episodic memory)"))[0]
        return [round(float(x), 5) for x in v[:1024]]
    except Exception:
        return None


REVISE = """You wrote the answer below. A citation check found sentences that the cited papers do not support.
Rewrite the answer: fix each flagged sentence (correct it from the evidence, cite the right paper, soften it, or remove
it). Keep everything else, keep [P#] citation format, no meta-commentary about the revision."""


async def _self_correct(pid: str, answer: str, check: dict) -> tuple[str, dict | None]:
    bad = [c for c in check["claims"] if c["label"] == "unsupported"]
    if not bad:
        return answer, None
    evidence = []
    for c in bad[:5]:
        hits = await corpus.search(pid, c["text"], k=2, paper_ids=c["refs"][:3])
        evidence.append(f"Flagged: {c['text']}\nWhy: {c['why']}\nEvidence:\n" + "\n".join(h["text"][:600] for h in hits))
    with trace.scope(agent="Self-correction"):
        res = await llm.chat("reason", [{"role": "system", "content": REVISE},
                                        {"role": "user", "content": f"Answer:\n{answer}\n\n" + "\n\n".join(evidence)}],
                             title=f"Revise {len(bad)} unsupported sentence(s)", max_tokens=3000, temperature=0.2)
        revised = res.text.strip() or answer
        with trace.scope(agent="Citation Checker"):
            recheck = await verify.check_claims(pid, revised, max_claims=12)
        trace.log("guard", f"Self-correction: unsupported {check['unsupported']} → {recheck['unsupported']}")
    return revised, recheck


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
        recalled = await _recall(pid, clean.text, {m["id"] for m in recent})
        if recalled:
            trace.log("compress", f"Episodic recall: {len(recalled)} earlier exchange(s)",
                      "\n".join(f"({r['sim']}) {r['q'][:120]}" for r in recalled))

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

        @tool("Query the project's knowledge graph of entities extracted from the papers (grounded in their text): "
              "most used methods/datasets/tasks/metrics, which papers use an entity, reported results, and "
              "method×dataset gaps (combinations no collected paper evaluates).",
              digest=lambda r: f"knowledge graph: {len((r or {}).get('entities', []))} entities" if isinstance(r, dict) else str(r)[:100])
        async def knowledge_graph(entity_type: Annotated[str | None, Field(description="method|dataset|task|metric")] = None,
                                  name: Annotated[str | None, Field(description="entity name to look up")] = None) -> dict:
            from .. import kg as kgm
            g = db.cache_get(f"kg:{pid}:{len(db.papers(pid))}") or await kgm.build(pid)
            db.cache_put(f"kg:{pid}:{len(db.papers(pid))}", g)
            ents = [e for e in g["entities"] if (not entity_type or e["type"] == entity_type)
                    and (not name or kgm.key(name) in e["id"])]
            return {"entities": ents[:25], "gaps": g["gaps"][:15] if not name else [],
                    "results": [r for r in g["results"] if not name or kgm.key(name) in kgm.key(
                        f"{r['method']} {r['dataset']} {r['metric']}")][:15]}

        agent = Agent("Research Chat", SYSTEM, toolbox.research_tools(pid, "Research Chat") + [score_credibility, knowledge_graph],
                      role="reason", max_steps=8, budget=budget, context_tokens=settings.context_budget_tokens,
                      pinned=lambda: "\n\n".join(x for x in (_project_state(pid), _facts_text(pid)) if x),
                      max_tokens=4000, temperature=0.3)
        task = ((f"Summary of the earlier conversation:\n{summary['text']}\n\n" if summary["text"] else "")
                + ("Relevant earlier exchanges (recalled from memory):\n" + "\n\n".join(
                    f"Researcher asked: {r['q']}\nYou answered: {r['a']}" for r in recalled) + "\n\n" if recalled else "")
                + (f"Recent conversation:\n{convo}\n\n" if convo else "")
                + f"Researcher's new message:\n{clean.text}")
        res = await agent.run(task)
    answer = res.text or "I couldn't produce an answer within the budget. Try a narrower question."
    known = {p["id"] for p in db.papers(pid)}
    from .writer import bracket_citations
    answer = bracket_citations(answer, known)  # "(P66)" / "P66" → "[P66]" so every citation is checkable + clickable
    cited = list(dict.fromkeys(i for i in re.findall(r"\bP\d+\b", answer)))
    bad = [i for i in cited if i not in known]
    if bad:
        answer += f"\n\n> ⚠️ Unknown paper id(s) {', '.join(bad)} in this answer: treat those claims as unsupported."
    check = None
    if any(i in known for i in cited):  # same groundedness check as the report, on every cited sentence
        with trace.scope(project_id=pid, agent="Citation Checker"):
            check = await verify.check_claims(pid, answer, max_claims=12)
        before = check["unsupported"]
        if before:
            revised, recheck = await _self_correct(pid, answer, check)
            if recheck is not None and recheck["unsupported"] <= before:
                answer, check = revised, {**recheck, "revised_from": before}
        flagged = {c["text"] for c in check["claims"] if c["label"] == "unsupported"}
        for sent in flagged:
            answer = answer.replace(sent, f"{sent} ⚠️*[not supported by the cited paper]*")
    data = {"papers": [i for i in cited if i in known], "steps": res.steps, "tool_calls": res.tool_calls,
            "citations": {k: check.get(k) for k in ("supported", "partial", "unsupported", "revised_from")} if check else None,
            "recalled": len(recalled), "question": clean.text[:1000],
            "stopped_because": res.stopped_because, "budget": budget.snapshot(), "context": res.context}
    data["vec"] = await _embed_exchange(clean.text, answer)
    db.add_message(pid, "chat", "assistant", answer, data)
    await _remember(pid, clean.text, answer)
    data.pop("vec", None)
    return {"content": answer, **data}
