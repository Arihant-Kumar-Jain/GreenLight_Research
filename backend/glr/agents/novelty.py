"""Novelty matrix: does prior work already do each component of the idea? Quote-verified, then scored in code.

For each of the closest papers (in parallel), Nemotron Super maps every idea component to none / partial / full
overlap and must quote the paper. Quotes are verified against the paper text; a "partial" or "full" without a
verified quote is downgraded to "unverified" and does not count (market-claims rule from Greenlight, applied to
papers). The novelty score and "already done by" list are computed deterministically from verified cells.
"""

import asyncio
from typing import Literal

from pydantic import BaseModel, Field

from .. import corpus, db, llm, trace
from ..verify import paper_text, quote_ok
from .planner import Plan


class Cell(BaseModel):
    component: str = Field(description="C# id")
    overlap: Literal["none", "partial", "full"]
    quote: str = Field("", description="Verbatim fragment from the paper text proving the overlap (empty for none)")
    note: str = Field("", description="One short sentence: what the paper does for this component")


class PaperMap(BaseModel):
    cells: list[Cell]
    relation: Literal["same idea", "very close", "related", "background"]
    difference: str = Field(description="The most important way the idea differs from this paper, one sentence")


SYSTEM = """You compare a research idea, split into components, against ONE prior paper. For each component decide:
  full    - the paper clearly does this component (same technique in an equivalent setting)
  partial - the paper does something similar (related technique, different setting, or only part of it)
  none    - the paper does not do it
Quote the paper verbatim for every partial/full (copy a fragment of 8-30 words exactly from the given text).
"same idea" means the paper does all core components together. Be precise and fair in both directions."""

WEIGHT = {"full": 1.0, "partial": 0.5, "none": 0.0, "unverified": 0.0}


class Strict(BaseModel):
    verdict: Literal["full", "partial", "none"]
    why: str = Field(description="At most 20 words")


STRICT_SYSTEM = """You are an area chair double-checking a claimed FULL overlap between one component of a research idea
and a prior paper. First decide what the component is about:
- a MECHANISM (architecture, routing, loss, training procedure): the paper fully covers it if it uses the same
  mechanism, in ANY domain or modality. Do not downgrade for a different dataset or modality.
- a SETTING (specific data, benchmarks, domain, evaluation): the paper fully covers it only if it uses an equivalent
  setting; same mechanism in another setting is "partial".
Downgrade only when the passages clearly show the paper does something different. If unsure, keep "full".
Judge only from the quote and passages."""


async def _strict(plan_summary: str, comp: str, paper_title: str, quote: str, context: str) -> Strict | None:
    try:
        return await llm.chat_json("fast", STRICT_SYSTEM, f"Idea: {plan_summary}\nComponent: {comp}\n\nPaper: "
                                   f"{paper_title}\nQuote: \"{quote}\"\nPassages:\n{context[:5000]}", Strict,
                                   title="Strict check of a 'full' overlap", max_tokens=300, temperature=0.0)
    except Exception:
        return None


async def map_paper(pid: str, plan: Plan, paper_id: str) -> dict | None:
    p = db.paper(pid, paper_id)
    if not p:
        return None
    passages = []
    for c in plan.components:
        passages += await corpus.search(pid, c.text, k=2, paper_ids=[paper_id])
    seen, parts = set(), [f"Title: {p.get('title')}\nAbstract: {p.get('abstract')}"]
    for h in passages:
        if h["chunk_id"] not in seen and h["kind"] != "abstract":
            seen.add(h["chunk_id"])
            parts.append(h["text"])
    comps = "\n".join(f"{c.id}{' (core)' if c.core else ''}: {c.text}" for c in plan.components)
    try:
        m = await llm.chat_json("reason", SYSTEM, f"Idea: {plan.summary}\nComponents:\n{comps}\n\nPaper {paper_id}:\n"
                                + "\n\n".join(parts)[:16000], PaperMap, title=f"Novelty map vs {paper_id}",
                                max_tokens=2500, temperature=0.0)
    except Exception as e:
        trace.error(f"Novelty mapping failed for {paper_id}", str(e)[:300])
        return None
    full = paper_text(pid, paper_id)
    comp_text = {c.id: c.text for c in plan.components}
    cells = {}
    for cell in m.cells:
        d = cell.model_dump()
        if d["overlap"] != "none":
            d["verified"] = quote_ok(d["quote"], full)
            if not d["verified"]:
                d["claimed"] = d["overlap"]
                d["overlap"] = "unverified"
        cells[d["component"]] = d
    # second, stricter judge on every verified "full": same mechanism in another setting is only "partial"
    fulls = [d for d in cells.values() if d["overlap"] == "full"]
    checks = await asyncio.gather(*(_strict(plan.summary, comp_text.get(d["component"], ""), p.get("title", ""),
                                            d["quote"], "\n\n".join(parts)) for d in fulls))
    for d, chk in zip(fulls, checks):
        if chk and chk.verdict == "none":  # contradiction with a verified quote: treat as partial, never erase it
            chk.verdict = "partial"
        if chk and chk.verdict != "full":
            d["strict"] = {"verdict": chk.verdict, "why": chk.why}
            d["overlap"] = "partial" if chk.verdict == "partial" else "none"
    return {"paper_id": paper_id, "relation": m.relation, "difference": m.difference,
            "cells": [cells.get(c.id, {"component": c.id, "overlap": "none", "quote": "", "note": ""})
                      for c in plan.components]}


async def analyse(pid: str, plan: Plan, paper_ids: list[str]) -> dict:
    with trace.scope(agent="Novelty Mapper"):
        sem = asyncio.Semaphore(4)

        async def one(i):
            async with sem:
                return await map_paper(pid, plan, i)
        rows = [r for r in await asyncio.gather(*(one(i) for i in paper_ids)) if r]
        cred = {p["id"]: (p.get("credibility") or {}).get("score") for p in db.papers(pid)}
        comps = []
        for c in plan.components:
            cover = []
            for r in rows:
                cell = next(x for x in r["cells"] if x["component"] == c.id)
                if cell["overlap"] in ("full", "partial"):
                    cover.append({"paper_id": r["paper_id"], "overlap": cell["overlap"]})
            best = "full" if any(x["overlap"] == "full" for x in cover) else ("partial" if cover else "none")
            comps.append({"id": c.id, "text": c.text, "core": c.core, "best": best,
                          "covered_by": sorted(cover, key=lambda x: x["overlap"] != "full")})
        weights = [2.0 if c["core"] else 1.0 for c in comps]
        covered = sum(w * WEIGHT[c["best"]] for w, c in zip(weights, comps))
        score = round(100 * (1 - covered / sum(weights))) if comps else None
        core_ids = [c["id"] for c in comps if c["core"]] or [c["id"] for c in comps]
        done_by = []
        for r in rows:
            full = {x["component"] for x in r["cells"] if x["overlap"] == "full"}
            if core_ids and all(cid in full for cid in core_ids):
                done_by.append({"paper_id": r["paper_id"], "credibility": cred.get(r["paper_id"])})
        unverified = sum(x["overlap"] == "unverified" for r in rows for x in r["cells"])
        strict = sum(bool(x.get("strict")) for r in rows for x in r["cells"])
        trace.log("guard", f"Novelty score {score}/100; {len(done_by)} paper(s) cover all core components",
                  f"{unverified} overlap claim(s) downgraded: quote not found in the paper; {strict} 'full' claim(s) "
                  "downgraded by the strict second judge (same mechanism, different setting)")
        return {"components": comps, "papers": rows, "score": score, "already_done_by": done_by,
                "unverified_claims": unverified, "strict_downgrades": strict}
