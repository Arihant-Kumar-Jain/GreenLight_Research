"""Paper relationship graph: how the papers around an idea relate to each other.

Edges, each with its evidence:
  cites    - A's reference list contains B. Sources in order: Semantic Scholar (with S2_API_KEY), OpenAlex
             referenced_works, then A's own bibliography parsed from its arXiv HTML page (matched by arXiv id or exact
             title). OpenAlex alone lists references for few recent preprints (5/49 in a real run), hence the fallbacks.
  similar  - nearest neighbours by Qwen3 embedding of the abstracts (threshold adapts to the corpus' cosine spread).
  idea     - the Lead Researcher's relation of a paper to the researcher's idea (same idea / very close / related).
Clusters: weighted label propagation over cites+similar, labelled by each cluster's most distinctive title words.
No LLM involved; `explain()` adds an on-demand Nemotron Nano explanation for one pair.
"""

import asyncio
import re
from collections import Counter

import numpy as np
from bs4 import BeautifulSoup

from . import db, llm, trace
from .config import settings
from .corpus import words
from .sources import http
from .sources.openalex import API as OA, _params, norm_title

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")


def _nodes(pid: str, limit: int) -> list[dict]:
    p = db.project(pid) or {}
    closest = [c["id"] for c in (((p.get("stats") or {}).get("review") or {}).get("closest") or [])]
    mapped = [r["paper_id"] for r in ((p.get("novelty") or {}).get("papers") or [])]
    papers = {x["id"]: x for x in db.papers(pid)}
    # then by cross-encoder relevance to the idea, credibility as tiebreak
    scored = sorted(papers.values(), key=lambda x: -((x.get("relevance") or 0) * 100
                                                     + ((x.get("credibility") or {}).get("score") or 0) * 0.2))
    order = list(dict.fromkeys(closest + mapped + [x["id"] for x in scored] + list(papers)))
    return [papers[i] for i in order[:limit] if i in papers]


# ---------------------------------------------------------------- reference lists

async def _refs_s2(nodes: list[dict]) -> dict[str, list[dict]]:
    ids = {f"arXiv:{n['arxiv_id']}": n["id"] for n in nodes if n.get("arxiv_id") and "refs" not in n}
    if not settings.s2_api_key or not ids:
        return {}
    try:
        r = await http.client().post("https://api.semanticscholar.org/graph/v1/paper/batch",
                                     params={"fields": "references.externalIds,references.title"},
                                     json={"ids": list(ids)}, headers={"x-api-key": settings.s2_api_key})
        r.raise_for_status()
    except Exception as e:
        trace.error("Semantic Scholar references failed", str(e)[:300])
        return {}
    out = {}
    for key, item in zip(ids, r.json()):
        if item:
            out[ids[key]] = [{"arxiv": (x.get("externalIds") or {}).get("ArXiv"), "text": x.get("title") or ""}
                             for x in item.get("references") or []]
    return out


async def _refs_openalex(nodes: list[dict]) -> dict[str, list[dict]]:
    by_oa = {n["openalex_id"]: n["id"] for n in nodes if n.get("openalex_id") and "refs" not in n}
    out: dict[str, list[dict]] = {}
    keys = list(by_oa)
    for i in range(0, len(keys), 50):
        try:
            d = await http.get(f"{OA}/works", params=_params({"filter": "openalex:" + "|".join(keys[i:i + 50]),
                                                              "select": "id,referenced_works", "per_page": 50}),
                               label="OpenAlex references")
        except http.SourceUnavailable:
            continue
        for w in (d or {}).get("results", []):
            refs = [x.rsplit("/", 1)[-1] for x in w.get("referenced_works") or []]
            if refs:
                out[by_oa[w["id"].rsplit("/", 1)[-1]]] = [{"openalex": r, "text": ""} for r in refs]
    return out


async def _refs_arxiv_html(n: dict) -> list[dict] | None:
    try:
        html = await http.get(f"https://arxiv.org/html/{n['arxiv_id']}", as_text=True, label="arXiv HTML bibliography",
                              cache_s=30 * 86400, retries=1)
    except http.SourceUnavailable:
        return None
    if not html:
        return None
    items = BeautifulSoup(html, "lxml").select("li.ltx_bibitem")
    out = []
    for it in items:
        t = re.sub(r"\s+", " ", it.get_text(" ", strip=True))[:400]
        m = ARXIV_ID_RE.search(t)
        out.append({"arxiv": m.group(1) if m else None, "text": t})
    return out or None


async def references(pid: str, nodes: list[dict]) -> None:
    """Fill `refs` (+ `refs_via`) on each node paper, once; stored on the paper so later graphs are free."""
    todo = [n for n in nodes if "refs" not in n]
    if not todo:
        return
    found: dict[str, tuple[str, list[dict]]] = {}
    for via, res in (("Semantic Scholar", await _refs_s2(todo)), ("OpenAlex", await _refs_openalex(todo))):
        for k, v in res.items():
            found.setdefault(k, (via, v))
    rest = [n for n in todo if n["id"] not in found and n.get("arxiv_id")]
    sem = asyncio.Semaphore(3)

    async def one(n):
        async with sem:
            return n["id"], await _refs_arxiv_html(n)
    for k, v in await asyncio.gather(*(one(n) for n in rest)):
        if v:
            found[k] = ("arXiv bibliography", v)
    for n in todo:
        via, refs = found.get(n["id"], (None, []))
        n["refs"], n["refs_via"] = refs, via
        db.update_paper(pid, n["id"], refs=refs, refs_via=via)
    trace.source(f"Reference lists for {len(todo)} paper(s)",
                 ", ".join(f"{v}: {sum(1 for x in found.values() if x[0] == v)}"
                           for v in ("Semantic Scholar", "OpenAlex", "arXiv bibliography")), provider="graph")


def _cite_edges(nodes: list[dict]) -> list[dict]:
    by_arxiv = {n["arxiv_id"]: n["id"] for n in nodes if n.get("arxiv_id")}
    by_oa = {n["openalex_id"]: n["id"] for n in nodes if n.get("openalex_id")}
    # exact titles of >= 5 words, longest first, so "mixture of lora experts" can't match inside a longer title
    titles = sorted([(norm_title(n["title"]), n["id"]) for n in nodes if len(norm_title(n["title"]).split()) >= 5],
                    key=lambda x: -len(x[0]))
    edges = {}
    for n in nodes:
        for r in n.get("refs") or []:
            target = by_arxiv.get(r.get("arxiv")) or by_oa.get(r.get("openalex"))
            if not target and r.get("text"):
                t = norm_title(r["text"])
                target = next((i for nt, i in titles if nt in t), None)
            if target and target != n["id"] and (n["id"], target) not in edges:
                edges[(n["id"], target)] = {"source": n["id"], "target": target, "type": "cites",
                                            "via": n.get("refs_via"), "evidence": (r.get("text") or "")[:240]}
    return list(edges.values())


# ---------------------------------------------------------------- similarity + clusters

def _sim_edges(pid: str, nodes: list[dict], k: int = 3) -> list[dict]:
    vecs = {c["paper_id"]: c["vec"] for c in db.chunks(pid) if c["id"].endswith("#abs") and c["vec"] is not None}
    ids = [n["id"] for n in nodes if n["id"] in vecs]
    if len(ids) < 3:
        return []
    m = np.stack([vecs[i] for i in ids])
    m = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
    sims = m @ m.T
    np.fill_diagonal(sims, -1)
    thr = float(np.percentile(sims[sims > -1], 88))  # adaptive: top ~12% of pairs count as "similar"
    edges = {}
    for a in range(len(ids)):
        for b in np.argsort(-sims[a])[:k]:
            if sims[a, b] >= thr:
                key = tuple(sorted((ids[a], ids[int(b)])))
                edges[key] = {"source": key[0], "target": key[1], "type": "similar", "weight": round(float(sims[a, b]), 3)}
    return list(edges.values())


def _clusters(nodes: list[dict], edges: list[dict]) -> tuple[dict[str, int], list[dict]]:
    adj: dict[str, Counter] = {n["id"]: Counter() for n in nodes}
    for e in edges:
        if e["type"] in ("cites", "similar"):
            w = e.get("weight", 0.6) if e["type"] == "similar" else 1.0
            adj[e["source"]][e["target"]] += w
            adj[e["target"]][e["source"]] += w
    label = {i: i for i in adj}
    order = sorted(adj)  # deterministic
    for _ in range(20):
        changed = False
        for i in order:
            if not adj[i]:
                continue
            score: Counter = Counter()
            for j, w in adj[i].items():
                score[label[j]] += w
            best = max(sorted(score), key=lambda lb: score[lb])
            if best != label[i]:
                label[i], changed = best, True
        if not changed:
            break
    groups = Counter(label.values())
    big = [lb for lb, c in groups.most_common() if c >= 2][:9]
    cid = {lb: k for k, lb in enumerate(big)}
    assign = {i: cid.get(label[i], -1) for i in adj}
    titles = {n["id"]: n["title"] for n in nodes}
    total = Counter(w for t in titles.values() for w in set(words(t)))
    out = []
    for lb, k in cid.items():
        members = [i for i in adj if assign[i] == k]
        c = Counter(w for i in members for w in set(words(titles[i])))
        top = sorted(c, key=lambda w: -(c[w] / (total[w] + 1)) * c[w])[:3]
        out.append({"id": k, "label": " · ".join(top) or f"cluster {k + 1}", "size": len(members)})
    return assign, out


async def build(pid: str, limit: int = 60) -> dict:
    with trace.scope(project_id=pid, agent="Graph Builder"):
        nodes = _nodes(pid, limit)
        await references(pid, nodes)
        cites = _cite_edges(nodes)
        sims = _sim_edges(pid, nodes)
        p = db.project(pid) or {}
        rel = {c["id"]: c for c in (((p.get("stats") or {}).get("review") or {}).get("closest") or [])}
        idea = [{"source": "IDEA", "target": i, "type": "idea", "relation": c["relation"], "evidence": c["why"]}
                for i, c in rel.items() if any(n["id"] == i for n in nodes)]
        assign, clusters = _clusters(nodes, cites + sims)
        out_nodes = [{"id": n["id"], "title": n["title"], "year": n.get("year"), "citations": n.get("citations"),
                      "credibility": (n.get("credibility") or {}).get("score"), "cluster": assign.get(n["id"], -1),
                      "relevance": n.get("relevance"),
                      "relation": rel.get(n["id"], {}).get("relation"), "refs_via": n.get("refs_via"),
                      "n_refs": len(n.get("refs") or [])} for n in nodes]
        trace.info(f"Paper graph: {len(out_nodes)} papers, {len(cites)} citation links, {len(sims)} similarity links, "
                   f"{len(clusters)} clusters", ", ".join(c["label"] for c in clusters))
        return {"nodes": out_nodes, "edges": cites + sims + idea, "clusters": clusters,
                "idea": {"title": p.get("title") or (p.get("brief") or {}).get("title") or "Your idea"},
                "stats": {"cites": len(cites), "similar": len(sims),
                          "refs_via": dict(Counter(n.get("refs_via") or "none" for n in nodes))}}


# ---------------------------------------------------------------- explain one relation

EXPLAIN = """Explain in 2-3 sentences how two research papers relate: does one build on, extend, compete with, or apply
the other; what they share; and the key difference. Use only the abstracts and facts given. Plain language."""


async def explain(pid: str, a: str, b: str, facts: str = "") -> str:
    key = f"explain:{pid}:{a}:{b}"
    if (hit := db.cache_get(key)) is not None:
        return hit
    pa, pb = db.paper(pid, a), db.paper(pid, b)
    if not pa or not pb:
        return "Unknown paper."
    with trace.scope(project_id=pid, agent="Graph Explainer"):
        res = await llm.chat("fast", [{"role": "system", "content": EXPLAIN}, {"role": "user", "content":
                             f"[{a}] {pa['title']} ({pa.get('year')}): {(pa.get('abstract') or '')[:1500]}\n\n"
                             f"[{b}] {pb['title']} ({pb.get('year')}): {(pb.get('abstract') or '')[:1500]}\n\n"
                             f"Known links: {facts or 'none'}"}],
                             title=f"Explain relation {a} ↔ {b}", max_tokens=400, temperature=0.2)
    db.cache_put(key, res.text.strip())
    return res.text.strip()
