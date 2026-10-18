"""Deep research: a Lead Researcher orchestrating a swarm of Scout sub-agents, with a Critic as reflection gate.

  Lead Researcher (Nemotron Super) - plans rounds, dispatches scouts via a tool, reads the closest papers itself,
                                     walks the citation graph, keeps the shared notebook, and finishes with a coverage
                                     map of every idea component.
  Scouts (one per angle, parallel)  - each runs its own tool loop and context window over arXiv, OpenAlex, Hugging
                                     Face, Tavily and the citation graph, then returns a compressed report. The lead
                                     only ever sees these reports, never raw search results (cross-agent compression).
  Critic (Nemotron Nano)            - reviews the lead's finish: components marked "open" without a targeted search,
                                     thin evidence, unverified "same idea" claims → rejected with concrete feedback,
                                     and the lead runs another round (bounded by GLR_RESEARCH_ROUNDS).
"""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .. import db, llm, trace
from ..budget import Budget
from ..config import settings
from ..harness import Agent, swarm, tool
from . import toolbox
from .intake import brief_text
from .planner import Plan


PERSPECTIVES = ("Same mechanism, other field or modality", "Reviewer: is this incremental?")


class PaperRelation(BaseModel):
    id: str = Field(description="P# id")
    relation: Literal["same idea", "very close", "related", "background"]
    why: str = Field(description="One sentence: what it does relative to the idea")


class ScoutReport(BaseModel):
    summary: str = Field(description="What this angle found, 3-5 sentences, citing P# ids")
    papers: list[PaperRelation] = Field(description="The most relevant papers found (max 8), closest first")
    findings: list[str] = Field(default_factory=list, description="Key facts, each citing P# ids")
    gaps: list[str] = Field(default_factory=list, description="What seems not done yet, as far as this angle shows")


class Coverage(BaseModel):
    component: str = Field(description="C# id")
    status: Literal["covered", "partially", "open"]
    papers: list[str] = Field(default_factory=list, description="P# ids that cover it")
    note: str = ""


class LeadReport(BaseModel):
    synthesis: str = Field(description="State of the art relevant to the idea, 1-3 paragraphs, citing P# ids")
    closest: list[PaperRelation] = Field(description="The 5-10 closest papers overall, closest first")
    coverage: list[Coverage] = Field(description="One entry per idea component")
    gaps: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


SCOUT_SYSTEM = """You are a Scout in a deep-research swarm. Your job: exhaustively search ONE angle of the literature
for a research idea and report back. You have arXiv, OpenAlex, Hugging Face Papers, the live web (Tavily), a
citation-graph tool, full-text reading and the shared corpus.

Method:
- Run several distinct searches: the seed queries, then synonyms, older names, and the setting phrased differently.
  Use more than one source, including search_web (Tavily live web) for very recent work the indexes miss. Short keyword queries work best on arXiv.
- When you find a very close paper, walk citation_graph(direction='citing') from it, optionally with a query, to see
  whether newer work already did the idea.
- read_fulltext only the 1-2 closest papers, with a precise focus.
- REQUIRED: record your 2-4 most important facts with `note` (kind finding or gap, with P# refs) as you find them;
  the whole team and the final report read the notebook.
- Judge relation honestly: "same idea" only if the paper does the idea's core components together.
- Do not invent papers or facts. Cite only P# ids you have seen in tool results.
Finish with your report when the angle is covered (usually 4-8 tool calls)."""

LEAD_SYSTEM = """You are the Lead Researcher of GreenLight Research's deep-research team. You must determine whether a
research idea has already been done, what the closest prior work is, and where the open gaps are.

You command a swarm of Scout agents: `dispatch_scouts` runs them in parallel (each with its own context and tools)
and returns their compressed reports. You can also search the collected corpus, read full texts of the decisive
papers, walk the citation graph and write to the shared notebook yourself.

Process:
1. Round 1: dispatch scouts on the planned angles (adapt the instructions; make them concrete).
2. Read the reports. For the closest papers, verify with paper_details / read_fulltext / search_corpus what they
   actually do, component by component. Walk citation_graph from the closest one to catch newer work.
3. If a component is still unclear, dispatch a targeted second round (fewer scouts, sharper instructions).
4. Finish with the coverage map: for each component, covered / partially / open, with the P# ids. "open" means you
   searched specifically and found nothing that does it.
Cite only P# ids from tool results. Never invent papers. Be skeptical: researchers lose months on a false "novel"."""

CRITIC_SYSTEM = """You review a lead researcher's literature-review result before it is accepted. Approve only if:
- every component marked "open" was searched specifically (look at the notebook and searches done),
- "covered"/"same idea" claims are backed by papers that were actually read or whose abstracts clearly say so,
- the closest-paper list is plausible and not tiny.
If not, reject with 1-3 concrete instructions (what to search, which paper to read, which citation hop to walk)."""


class CriticVerdict(BaseModel):
    approve: bool
    feedback: str = Field("", description="Concrete instructions if not approved")


def _scout_tools(pid: str, name: str):
    return toolbox.research_tools(pid, name)


async def run(pid: str, brief: dict, plan: Plan, budget: Budget) -> dict:
    components_txt = "\n".join(f"{c.id}{' (core)' if c.core else ''}: {c.text}" for c in plan.components)
    idea_txt = f"Research brief:\n{brief_text(brief)}\n\nIdea components:\n{components_txt}"
    rounds = {"n": 0}
    scout_n = {"n": 0}

    @tool("Dispatch Scout agents in parallel, one per task. Each searches its angle with its own tools and context and "
          "returns a compressed report. Use 3-4 scouts in round 1, 1-3 targeted scouts later.",
          digest=lambda r: f"{len((r or {}).get('reports', []))} scout report(s)" if isinstance(r, dict) else str(r)[:120])
    async def dispatch_scouts(tasks: Annotated[list[dict], Field(
            description="List of {angle: str, instructions: str, seed_queries: [str]}")]) -> dict:
        tasks = [t for t in tasks if isinstance(t, dict)][:settings.max_scouts]
        if not tasks:
            return {"error": "no_tasks", "detail": "Pass at least one {angle, instructions, seed_queries}."}
        rounds["n"] += 1
        if rounds["n"] == 1:  # perspective angles are mandatory in round 1 (the Lead tends to drop them)
            persp = [a for a in plan.angles if a.title in PERSPECTIVES]
            have = {str(t.get("angle", "")).lower() for t in tasks}
            missing = [a for a in persp if not any(a.title.lower()[:20] in h for h in have)]
            if missing:
                tasks = tasks[:max(1, settings.max_scouts - len(missing))] + [
                    {"angle": a.title, "instructions": a.instructions, "seed_queries": a.seed_queries} for a in missing]
                trace.log("guard", f"Added {len(missing)} mandatory perspective scout(s) to round 1",
                          ", ".join(a.title for a in missing))
        jobs = []
        for t in tasks:
            scout_n["n"] += 1
            name = f"Scout {scout_n['n']} · {str(t.get('angle', 'angle'))[:40]}"
            agent = Agent(name, SCOUT_SYSTEM, _scout_tools(pid, name), role="reason", output=ScoutReport,
                          finish_description="Submit your scout report.", max_steps=9,
                          budget=budget.child(usd=max(0.02, (budget.usd - budget.spent_usd) / (len(tasks) + 2))),
                          context_tokens=min(16000, settings.context_budget_tokens), keep_recent=3,
                          pinned=lambda: toolbox.notebook_text(pid, 15), max_tokens=4000)
            task = (f"{idea_txt}\n\nYOUR ANGLE: {t.get('angle')}\nInstructions: {t.get('instructions', '')}\n"
                    f"Seed queries: {', '.join(t.get('seed_queries') or [])}")
            jobs.append((agent, task))
        trace.log("spawn", f"Round {rounds['n']}: dispatching {len(jobs)} scouts in parallel",
                  "\n".join(a.name for a, _ in jobs))
        results = await swarm(jobs, limit=settings.max_scouts)
        reports = []
        for (agent, _), r in zip(jobs, results):
            if isinstance(r, BaseException):
                reports.append({"scout": agent.name, "error": str(r)[:300]})
            elif r.output:
                reports.append({"scout": agent.name, **r.output})
            else:
                reports.append({"scout": agent.name, "summary": r.text[:1500] or "no report", "papers": []})
        return {"round": rounds["n"], "reports": reports,
                "papers_in_corpus": len(db.papers(pid))}

    lead_tools = [dispatch_scouts] + toolbox.research_tools(
        pid, "Lead Researcher", include={"search_corpus", "paper_details", "read_fulltext", "citation_graph", "note",
                                         "search_openalex", "search_arxiv"})

    async def review(out: dict) -> str | None:
        n_papers = len(db.papers(pid))
        problems = []
        if rounds["n"] < min(2, settings.max_research_rounds):
            problems.append("Round 1 is never final: dispatch a targeted second round. Walk citation_graph(direction="
                            "'citing') from the closest papers, and search each component you marked covered or open "
                            "with new synonyms, to catch the closest prior work you may have missed.")
        if n_papers < 8:
            problems.append(f"Only {n_papers} papers collected: search wider (synonyms, other sources).")
        if len(out.get("closest") or []) < 3:
            problems.append("The closest-paper list is too short.")
        known = {p["id"] for p in db.papers(pid)}
        bad = [c["id"] for c in out.get("closest") or [] if c["id"].upper() not in known]
        if bad:
            problems.append(f"Unknown paper ids in closest: {', '.join(bad)}. Cite only ids from tool results.")
        if problems:
            return " ".join(problems)
        with trace.scope(agent="Critic"):
            v = await llm.chat_json("fast", CRITIC_SYSTEM,
                                    f"{idea_txt}\n\nNotebook:\n{toolbox.notebook_text(pid, 40)}\n\n"
                                    f"Lead's result:\n{json.dumps(out, ensure_ascii=False)[:9000]}",
                                    CriticVerdict, title="Critic: review literature coverage", max_tokens=1200,
                                    temperature=0.0)
            trace.log("guard", "Critic approved the review" if v.approve else "Critic rejected: another round",
                      v.feedback)
            return None if v.approve else v.feedback

    lead = Agent("Lead Researcher", LEAD_SYSTEM, lead_tools, role="reason", output=LeadReport,
                 finish_description="Submit the final literature review with the coverage map.",
                 max_steps=10 + 4 * settings.max_research_rounds, budget=budget,
                 context_tokens=settings.context_budget_tokens, keep_recent=4,
                 pinned=lambda: toolbox.notebook_text(pid, 30), review=review,
                 max_reviews=max(0, settings.max_research_rounds + 1), max_tokens=6000)
    angles = "\n".join(f"- {a.title}: {a.instructions} (seed queries: {', '.join(a.seed_queries)})" for a in plan.angles)
    task = (f"{idea_txt}\n\nPlanned search angles:\n{angles}\n\nRound 1 MUST include the two perspective angles "
            f"('Same mechanism, other field or modality' and 'Reviewer: is this incremental?').\n\n"
            f"Known work to locate first: {', '.join(plan.known_work_to_locate) or 'none'}")
    res = await lead.run(task)
    out = res.output or {"synthesis": res.text, "closest": [], "coverage": [], "gaps": [], "confidence": "low"}
    known = {p["id"] for p in db.papers(pid)}
    out["closest"] = [c for c in out.get("closest", []) if c["id"].upper() in known]
    for c in out["closest"]:
        c["id"] = c["id"].upper()
    out["rounds"] = rounds["n"]
    out["scouts"] = scout_n["n"]
    out["lead"] = {"steps": res.steps, "stopped_because": res.stopped_because, "context": res.context}
    return out
