"""Planner: turns the research brief into testable novelty components and parallel search angles for the scouts."""

from pydantic import BaseModel, Field

from .. import llm, trace
from .intake import brief_text


class Component(BaseModel):
    id: str = Field(description="C1, C2, ...")
    text: str = Field(description="One specific, testable element of the idea, e.g. 'LoRA adapters routed per token by "
                                  "a learned gate'")
    core: bool = Field(True, description="True if the idea's novelty depends on it")


class Angle(BaseModel):
    title: str = Field(description="Short name of this search angle")
    instructions: str = Field(description="What the scout should find and how (sources, synonyms, citation hops)")
    seed_queries: list[str] = Field(description="3-5 concrete search queries incl. synonyms / older names")


class Plan(BaseModel):
    summary: str = Field(description="The idea in one sentence, as the research will test it")
    components: list[Component] = Field(description="2-5 components; the novelty test checks each against prior work")
    angles: list[Angle] = Field(description="3-5 complementary search angles")
    known_work_to_locate: list[str] = Field(default_factory=list, description="Named papers/methods to find first")


SYSTEM = """You are the planning lead of a deep literature review. Given a research brief, produce:
1. components: break the idea into 2-5 specific, testable elements. The idea is "already done" only if prior work
   covers its core components together, so phrase each precisely (technique + setting + condition).
2. angles: 3-5 complementary search angles for parallel scout agents, e.g. (a) the exact combination,
   (b) the core technique and its variants/older names, (c) the application setting/benchmarks, (d) the closest known
   work and what cites it since, (e) adjacent fields that may have done it under another name. Each angle gets
   concrete seed queries (short keyword queries work best on arXiv).
3. known_work_to_locate: papers or methods the researcher named, so scouts find them first."""


async def plan(brief: dict) -> Plan:
    with trace.scope(agent="Planner"):
        p = await llm.chat_json("reason", SYSTEM, brief_text(brief), Plan, title="Plan the research", max_tokens=4000)
        for i, c in enumerate(p.components, start=1):
            c.id = f"C{i}"
        trace.info(f"Plan: {len(p.components)} components, {len(p.angles)} search angles",
                   "\n".join([f"{c.id}{'*' if c.core else ''} {c.text}" for c in p.components]
                             + [f"→ {a.title}: {', '.join(a.seed_queries)}" for a in p.angles]))
        return p
