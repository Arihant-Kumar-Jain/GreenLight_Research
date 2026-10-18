"""Knowledge graph of research entities: which papers use which methods, datasets, tasks and metrics.

Nemotron Nano reads each relevant paper (title, abstract and, when read, its best full-text passages) and lists the
entities it uses or proposes, plus up to three headline results. Grounding rule (same as everywhere else): an entity is
kept only if its name appears in that paper's own text; results only if the number appears too. Names are merged by a
normalised key. From the bipartite paper-entity graph we derive the most used methods/datasets, and a method × dataset
matrix whose empty cells are candidate gaps ("no collected paper evaluates method M on dataset D").
"""

import asyncio
import re
from collections import Counter, defaultdict

from pydantic import BaseModel, Field

from . import db, llm, trace
from .verify import paper_text

TYPES = ("method", "dataset", "task", "metric")


class Result(BaseModel):
    method: str = ""
    dataset: str = ""
    metric: str = ""
    value: str = Field("", description="The number as written, e.g. '71.3' or '+2.1'")


class Entities(BaseModel):
    methods: list[str] = Field(default_factory=list, description="Methods/models/techniques proposed or compared (≤8)")
    datasets: list[str] = Field(default_factory=list, description="Datasets/benchmarks used (≤8)")
    tasks: list[str] = Field(default_factory=list, description="Tasks addressed (≤5)")
    metrics: list[str] = Field(default_factory=list, description="Evaluation metrics (≤5)")
    results: list[Result] = Field(default_factory=list, description="Up to 3 headline results with numbers")


SYSTEM = """Extract the research entities of ONE paper from its text. Use the names exactly as written in the text
(short canonical names, e.g. "LoRA", "MMLU", "accuracy"). Only entities the text mentions; no guessing.
Datasets: ONLY specific named datasets/benchmarks (e.g. MMLU, GSM8K, FLAN, ScienceQA) — never descriptions like
"five benchmarks" or "existing benchmark". Methods: named methods/models (e.g. LoRA, MoLE, Switch Transformer).
Results only when a number is stated."""

VERSION = 2
VAGUE = re.compile(r"(?i)^(the |an? |our |existing |several |multiple |various |\d+ |one |two |three |four |five |six |seven |eight |nine |ten )|benchmarks$|datasets$|tasks$")


def key(name: str) -> str:
    """Merge key: drop parenthesised acronyms and punctuation ("Mixture-of-Experts (MoE)" == "mixture of experts")."""
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"\([^)]*\)", "", name).lower()) or re.sub(r"[^a-z0-9]+", "", name.lower())


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower())


async def _extract_one(pid: str, p: dict) -> dict | None:
    if (p.get("entities") or {}).get("v") == VERSION:
        return p["entities"]
    full = paper_text(pid, p["id"])
    text = f"Title: {p.get('title')}\nAbstract: {p.get('abstract') or ''}\n\n{full[len(p.get('title') or '') + len(p.get('abstract') or ''):][:6000]}"
    try:
        e = await llm.chat_json("fast", SYSTEM, text[:9000], Entities, title=f"Extract entities from {p['id']}",
                                max_tokens=900, temperature=0.0)
    except Exception as ex:
        trace.error(f"Entity extraction failed for {p['id']}", str(ex)[:200])
        return None
    hay = _norm(full)
    out, dropped = {}, 0
    for t, names in (("method", e.methods), ("dataset", e.datasets), ("task", e.tasks), ("metric", e.metrics)):
        kept = []
        for n in names[:8]:
            n = n.strip()
            specific = not (t == "dataset" and (VAGUE.search(n) or (n.islower() and " " in n)))
            if specific and len(n) >= 2 and _norm(n).strip() and _norm(n).strip() in hay:  # grounded + specific
                kept.append(n)
            else:
                dropped += 1
        out[t] = list(dict.fromkeys(kept))
    out["results"] = [r.model_dump() for r in e.results[:3] if r.value and r.value.strip().lstrip("+") in full]
    out["dropped"] = dropped
    out["v"] = VERSION
    db.update_paper(pid, p["id"], entities=out)
    return out


def _relevant(pid: str, limit: int) -> list[dict]:
    p = db.project(pid) or {}
    closest = [c["id"] for c in (((p.get("stats") or {}).get("review") or {}).get("closest") or [])]
    ps = {x["id"]: x for x in db.papers(pid)}
    ranked = sorted(ps.values(), key=lambda x: -(x.get("relevance") or 0))
    order = list(dict.fromkeys(closest + [x["id"] for x in ranked]))
    return [ps[i] for i in order[:limit] if i in ps]


async def build(pid: str, limit: int = 30) -> dict:
    with trace.scope(project_id=pid, agent="Knowledge Graph"):
        papers = _relevant(pid, limit)
        sem = asyncio.Semaphore(8)

        async def one(p):
            async with sem:
                return p["id"], await _extract_one(pid, p)
        got = {i: e for i, e in await asyncio.gather(*(one(p) for p in papers)) if e}
        names: dict[tuple[str, str], Counter] = defaultdict(Counter)   # (type, key) -> display-name counts
        users: dict[tuple[str, str], set[str]] = defaultdict(set)      # (type, key) -> paper ids
        for pid_, e in got.items():
            for t in TYPES:
                for n in e.get(t, []):
                    names[(t, key(n))][n] += 1
                    users[(t, key(n))].add(pid_)
        ents = [{"id": f"{t}:{k}", "type": t, "name": names[(t, k)].most_common(1)[0][0],
                 "papers": sorted(users[(t, k)], key=lambda x: int(x[1:])), "count": len(users[(t, k)])}
                for (t, k) in names]
        ents.sort(key=lambda x: (-x["count"], x["name"].lower()))
        # gaps only between entities that recur (used by ≥2 papers), otherwise every one-off name is a "gap"
        top_m = [x for x in ents if x["type"] == "method" and x["count"] >= 2][:8]
        top_d = [x for x in ents if x["type"] == "dataset" and x["count"] >= 2][:8]
        matrix = [{"method": m["name"], "cells": {d["name"]: sorted(set(m["papers"]) & set(d["papers"])) for d in top_d}}
                  for m in top_m]
        gaps = [{"method": r["method"], "dataset": d} for r in matrix for d, ps in r["cells"].items() if not ps]
        results = [{"paper": i, **r} for i, e in got.items() for r in e.get("results", [])]
        dropped = sum(e.get("dropped", 0) for e in got.values())
        trace.info(f"Knowledge graph: {len(ents)} entities from {len(got)} papers "
                   f"({sum(x['type'] == 'method' for x in ents)} methods, {sum(x['type'] == 'dataset' for x in ents)} "
                   f"datasets), {len(gaps)} method×dataset gaps; {dropped} ungrounded entity names dropped")
        return {"entities": ents, "matrix": matrix, "datasets": [d["name"] for d in top_d], "gaps": gaps,
                "results": results, "papers": len(got), "dropped": dropped}
