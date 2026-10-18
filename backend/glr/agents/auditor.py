"""Auditor: reads the decisive papers like a skeptical reviewer and flags reasons to distrust their results.

Every red flag and key result must quote the paper; quotes are verified against the paper's own text and only
verified flags lower the credibility score (integrity component). Runs in parallel over the closest papers.
"""

import asyncio
from typing import Literal

from pydantic import BaseModel, Field

from .. import corpus, db, llm, papers, trace
from ..verify import paper_text, quote_ok


class Flag(BaseModel):
    type: Literal["no_baselines", "weak_evaluation", "small_sample", "overclaiming", "no_code_for_strong_claim",
                  "possible_leakage", "inconsistent_numbers", "other"]
    quote: str = Field(description="Verbatim sentence fragment from the paper text that shows the problem")
    why: str = Field(description="One sentence")


class KeyResult(BaseModel):
    claim: str = Field(description="A main result, one sentence, with numbers if given")
    quote: str = Field(description="Verbatim fragment from the paper supporting it")


class Audit(BaseModel):
    shows: str = Field(description="What the paper actually shows, one sentence")
    key_results: list[KeyResult] = Field(default_factory=list, description="At most 3")
    flags: list[Flag] = Field(default_factory=list, description="At most 3 real problems; empty if none")


SYSTEM = """You are a rigorous peer reviewer auditing a paper's credibility from its text. Extract its main results
and flag ONLY real problems visible in the text (missing or weak baselines, tiny samples, single benchmark with broad
claims, numbers that don't add up, strong claims without released code/data, leakage risks). Do not flag things just
because the excerpt is short. Every quote must be copied verbatim from the given text."""


async def audit_one(pid: str, paper_id: str) -> dict | None:
    p = db.paper(pid, paper_id)
    if not p:
        return None
    hits = await corpus.search(pid, "experiments results baselines evaluation benchmark limitations", k=5,
                               paper_ids=[paper_id])
    text = f"Title: {p.get('title')}\nAbstract: {p.get('abstract')}\n\n" + "\n\n".join(h["text"] for h in hits
                                                                                         if h["kind"] != "abstract")
    try:
        a = await llm.chat_json("fast", SYSTEM, text[:14000], Audit, title=f"Audit {paper_id}", max_tokens=1800)
    except Exception as e:
        trace.error(f"Audit failed for {paper_id}", str(e)[:300])
        return None
    full = paper_text(pid, paper_id)
    out = a.model_dump()
    for f in out["flags"]:
        f["verified"] = quote_ok(f["quote"], full)
    for r in out["key_results"]:
        r["verified"] = quote_ok(r["quote"], full)
    out["dropped"] = sum(not f["verified"] for f in out["flags"])
    p["audit"] = out
    db.update_paper(pid, paper_id, audit=out)
    papers.rescore(pid, paper_id)
    return out


async def audit(pid: str, paper_ids: list[str]) -> dict:
    with trace.scope(agent="Auditor"):
        sem = asyncio.Semaphore(4)

        async def one(i):
            async with sem:
                return i, await audit_one(pid, i)
        res = dict(await asyncio.gather(*(one(i) for i in paper_ids)))
        flags = sum(len([f for f in (a or {}).get("flags", []) if f["verified"]]) for a in res.values())
        dropped = sum((a or {}).get("dropped", 0) for a in res.values())
        trace.log("guard", f"Audited {len(res)} paper(s): {flags} verified red flag(s), {dropped} unverified dropped")
        return {k: v for k, v in res.items() if v}
