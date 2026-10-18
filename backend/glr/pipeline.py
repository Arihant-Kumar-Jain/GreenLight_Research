"""Orchestrator for one deep-research run:

  plan → research (Lead + scout swarm + Critic rounds) → deep read (closest papers' full texts, parallel)
       → credibility (OpenAlex + HF + S2 enrichment, deterministic score) ∥ audit (Auditor red flags)
       → novelty matrix (quote-verified) → Research Chamber debate → Speaker ruling → guardrails
       → report (+ citation groundedness check) → done; the research chat stays open on the project.

One Budget caps the whole run (GLR_MAX_USD_PER_RUN); stage progress is written to the project row as it happens.
"""

import asyncio
import traceback

from . import db, graph, papers, trace
from .budget import Budget
from .config import settings
from .agents import auditor, chamber, novelty, planner, research, toolbox, verdict, writer
from .privacy import scrub_secrets

_running: dict[str, asyncio.Task] = {}


def start(pid: str) -> None:
    if pid in _running and not _running[pid].done():
        return
    db.update_project(pid, status="queued", stage="plan", error=None)
    _running[pid] = asyncio.create_task(run(pid))


def is_running(pid: str) -> bool:
    return pid in _running and not _running[pid].done()


async def run(pid: str) -> None:
    p = db.project(pid)
    if not p:
        return
    brief = p.get("brief") or {"title": p.get("title") or "", "research_question": p["idea_text"]}
    budget = Budget(usd=settings.max_usd_per_run, llm_calls=600, tool_calls=500, seconds=2400)
    with trace.scope(project_id=pid, agent="Orchestrator", budget=budget):
        try:
            db.update_project(pid, status="running", stage="plan")
            trace.info("Deep research started", f"Budget: ${budget.usd:.2f}, {settings.max_research_rounds} round(s), "
                                                f"up to {settings.max_scouts} parallel scouts")
            plan = await planner.plan(brief)
            db.update_project(pid, plan=plan.model_dump(), stage="research")

            review = await research.run(pid, brief, plan, budget)
            db.update_project(pid, stats={"review": review}, stage="credibility")

            closest = [c["id"] for c in review.get("closest", [])]
            # cross-encoder triage of everything collected (papers found before triage existed, or via other paths)
            with trace.scope(agent="Relevance Ranker"):
                untriaged = [x["id"] for x in db.papers(pid) if x.get("relevance") is None]
                for i in range(0, len(untriaged), 40):
                    await toolbox.triage(pid, untriaged[i:i + 40])
            by_rel = [x["id"] for x in sorted(db.papers(pid), key=lambda x: -(x.get("relevance") or 0))]
            deep = closest[:settings.papers_to_read]
            # Deep read: the decisive papers' full texts, so audits and novelty quotes check against more than abstracts
            with trace.scope(agent="Reader"):
                sem = asyncio.Semaphore(3)

                async def read(i):
                    async with sem:
                        try:
                            return await papers.read(pid, i)
                        except Exception as e:
                            return {"error": str(e)}
                await asyncio.gather(*(read(i) for i in deep[:5]))

            with trace.scope(agent="Credibility Scorer"):
                all_ids = [x["id"] for x in db.papers(pid)]
                ranked = list(dict.fromkeys(closest + by_rel + all_ids))
                await papers.enrich(pid, ranked[:80])
            await auditor.audit(pid, deep)

            db.update_project(pid, stage="novelty")
            # novelty-map the lead's closest work plus anything the cross-encoder rates very relevant that it missed
            missed = [i for i in by_rel[:12] if i not in closest and (db.paper(pid, i) or {}).get("relevance", 0) >= 0.8]
            mapped = list(dict.fromkeys(deep + [c["id"] for c in review.get("closest", [])
                                                if c["relation"] in ("same idea", "very close")] + missed[:3]))[:12]
            nov = await novelty.analyse(pid, plan, mapped)
            db.update_project(pid, novelty=nov, stage="chamber")

            pack = chamber.evidence_pack(pid, review, nov)
            motion = f"This House would pursue: {brief.get('title') or plan.summary}. {plan.summary}"
            debate = await chamber.hold(pid, motion, pack, on_update=lambda d: db.update_project(pid, debate=d))
            v = verdict.apply(pid, debate["ruling"], nov, review)
            db.update_project(pid, debate=debate, verdict=v, stage="report")

            report = await writer.write(pid, brief, review, nov, v)
            try:  # the relationship graph is a view; it must never fail the run
                db.cache_put(f"graph:{pid}:{len(db.papers(pid))}", await graph.build(pid))
            except Exception as e:
                trace.error("Paper graph failed", str(e)[:300])
            totals = db.trace_totals(pid)
            db.update_project(pid, report=report, status="done", stage="done",
                              stats={"review": review, "budget": budget.snapshot(), "totals": totals})
            trace.info(f"Done: {v['light'].upper()} — {v['headline']}",
                       f"{totals['llm_calls']} LLM calls, {totals['tool_calls']} tool calls, {totals['agents']} agents, "
                       f"${totals['cost_usd']:.4f}")
        except Exception as e:
            msg = scrub_secrets(f"{type(e).__name__}: {e}")
            trace.error("Research run failed", scrub_secrets(traceback.format_exc())[-3000:])
            if db.project(pid):
                db.update_project(pid, status="error", error=msg[:800])
