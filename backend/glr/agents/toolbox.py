"""The research tools every agent can be given, bound to one project.

Search tools ingest what they find into the project's paper registry (dedup across sources) and return compact
cards with stable ids (P#) that all agents share. Every tool has a digest for context compression.
"""

import asyncio
from typing import Annotated, Literal

from pydantic import Field

from .. import corpus, db, papers, privacy, rerank, trace, web
from ..harness import Tool, tool
from ..sources import arxiv, hf, openalex


def _papers_digest(r) -> str:
    if not isinstance(r, dict):
        return str(r)[:160]
    items = r.get("papers") or []
    return f"{len(items)} paper(s): " + "; ".join(f"{p['id']} {str(p.get('title'))[:50]}" for p in items[:10])


def _passages_digest(r) -> str:
    if not isinstance(r, dict):
        return str(r)[:160]
    ps = r.get("passages") or []
    return f"{len(ps)} passage(s) from " + ", ".join(sorted({p['paper_id'] for p in ps}))


def _clean_query(q: str) -> str:
    red = privacy.redact(q)
    if red.count:
        trace.info(f"Privacy: removed {red.count} item(s) from a search query", ", ".join(x["label"] for x in red.summary()))
    return red.text


def focus_text(pid: str) -> str:
    """What the project is about, for relevance triage of search results."""
    b = (db.project(pid) or {}).get("brief") or {}
    return " ".join(x for x in (b.get("research_question"), b.get("method"), "; ".join(b.get("contributions") or [])) if x)[:1500]


async def triage(pid: str, ids: list[str]) -> dict[str, float]:
    """Cross-encoder relevance of papers (title + abstract) to the research idea; kept as the max seen per paper."""
    focus = focus_text(pid)
    ps = [db.paper(pid, i) for i in ids]
    ps = [p for p in ps if p]
    if not focus or not ps:
        return {}
    scores, kind = await rerank.rerank(focus, [f"{p['title']}. {(p.get('abstract') or '')[:1500]}" for p in ps])
    if kind == "none":
        return {}
    out = {}
    for p, s in zip(ps, rerank.normalise(scores, kind)):
        rel = round(max(s, p.get("relevance") or 0.0), 3)
        db.update_paper(pid, p["id"], relevance=rel, relevance_by=kind)
        out[p["id"]] = rel
    return out


def research_tools(pid: str, agent: str, *, include: set[str] | None = None) -> list[Tool]:
    async def _ingest(records: list[dict], source: str, abstract_chars: int = 280) -> dict:
        rows = await papers.ingest(pid, records, found_by=agent)
        rel = await triage(pid, [r["id"] for r in rows])
        cards = []
        for r in rows:
            p = db.paper(pid, r["id"]) or {}
            c = papers.card(p, abstract_chars)
            c["new"] = r["new"]
            if r["id"] in rel:
                c["relevance"] = rel[r["id"]]
            cards.append(c)
        cards.sort(key=lambda c: -(c.get("relevance") or 0))
        return {"source": source, "papers": cards,
                "hint": "Sorted by cross-encoder relevance to the research idea (0-1). Ids (P#) are shared by all "
                        "agents. Use paper_details or read_fulltext to go deeper."}

    @tool("Search arXiv (preprints, CS/ML/physics/math/q-bio). Short keyword queries work best, e.g. "
          "'low-rank adaptation mixture of experts'.", digest=_papers_digest)
    async def search_arxiv(query: Annotated[str, Field(description="3-8 keywords")],
                           max_results: Annotated[int, Field(ge=1, le=15)] = 8) -> dict:
        return await _ingest(await arxiv.search(_clean_query(query), max_results), "arXiv")

    @tool("Search OpenAlex (250M+ scholarly works across all fields, incl. journals and conferences; has citation "
          "counts). Use for peer-reviewed work and fields beyond arXiv.", digest=_papers_digest)
    async def search_openalex(query: Annotated[str, Field(description="natural-language or keyword query")],
                              max_results: Annotated[int, Field(ge=1, le=15)] = 8,
                              from_year: Annotated[int | None, Field(description="only papers from this year on")] = None
                              ) -> dict:
        return await _ingest(await openalex.search(_clean_query(query), max_results, from_year), "OpenAlex")

    @tool("Search Hugging Face Papers: recent ML papers the community is discussing (with upvotes).",
          digest=_papers_digest)
    async def search_hf_papers(query: Annotated[str, Field(description="keywords")]) -> dict:
        return await _ingest(await hf.search(_clean_query(query), 8), "Hugging Face")

    @tool("Search the live web with Tavily: blog posts, benchmark leaderboards, GitHub repos, workshop papers, very "
          "recent results not yet indexed. arXiv links found here are added to the paper registry automatically.",
          digest=lambda r: f"{len((r or {}).get('results', []))} web result(s)" if isinstance(r, dict) else str(r)[:120])
    async def search_web(query: Annotated[str, Field(description="web search query")],
                         max_results: Annotated[int, Field(ge=1, le=8)] = 5) -> dict:
        results = await web.search(_clean_query(query), max_results=max_results)
        ids = [arxiv.arxiv_id(r["url"]) for r in results if "arxiv.org" in r["url"]]
        added = []
        if ids:
            recs = await arxiv.by_ids([i for i in ids if i])
            added = (await _ingest(recs, "arXiv via web"))["papers"]
        return {"results": [{"title": r["title"], "url": r["url"], "snippet": r["content"][:400],
                             "date": r.get("published_date")} for r in results],
                "papers_added": [{"id": p["id"], "title": p["title"]} for p in added]}

    @tool("Citation-graph hop from a paper (OpenAlex). direction='citing' finds NEWER papers that cite it (best way to "
          "check whether an idea was done after a key paper); 'references' finds what it builds on. Optional query "
          "filters the hop.", digest=_papers_digest)
    async def citation_graph(paper_id: Annotated[str, Field(description="P# id")],
                             direction: Literal["citing", "references"] = "citing",
                             query: Annotated[str | None, Field(description="optional filter keywords")] = None) -> dict:
        p = db.paper(pid, paper_id)
        if not p:
            return {"error": "unknown_paper", "detail": paper_id}
        if not p.get("openalex_id"):
            rec = await openalex.resolve(p["title"], p.get("doi"), p.get("arxiv_id"))
            if not rec:
                return {"error": "not_in_openalex", "detail": "Can't walk citations for this paper."}
            db.update_paper(pid, p["id"], openalex_id=rec["openalex_id"])
            p["openalex_id"] = rec["openalex_id"]
        recs = await openalex.related(p["openalex_id"], direction, _clean_query(query) if query else None)
        return await _ingest(recs, f"{direction} {paper_id}")

    @tool("Get details of papers by id: full abstract, authors, venue, citations and credibility score if computed.",
          digest=lambda r: f"details of {', '.join(p['id'] for p in (r or {}).get('papers', []))}"
          if isinstance(r, dict) else str(r)[:120])
    async def paper_details(ids: Annotated[list[str], Field(description="P# ids, at most 8")]) -> dict:
        out = []
        for i in ids[:8]:
            p = db.paper(pid, i)
            if p:
                c = papers.card(p, 2500)
                if p.get("credibility"):
                    c["credibility_breakdown"] = {x["name"]: x["detail"] for x in p["credibility"]["components"]}
                out.append(c)
        return {"papers": out}

    @tool("Read a paper's full text (arXiv HTML / PDF via Tavily Extract) and index it for retrieval. Slow-ish; use "
          "on the few papers that matter most. Returns the passages most relevant to `focus`.",
          digest=_passages_digest)
    async def read_fulltext(paper_id: Annotated[str, Field(description="P# id")],
                            focus: Annotated[str, Field(description="what you are looking for in this paper")]) -> dict:
        info = await papers.read(pid, paper_id.upper())
        if "error" in info:
            info["passages"] = await corpus.search(pid, focus, k=2, paper_ids=[paper_id])
            return info
        return {**info, "passages": await corpus.search(pid, focus, k=4, paper_ids=[paper_id], expand_query=True)}

    @tool("Search everything already collected (abstracts + full texts read so far) with the full retrieval stack: "
          "query expansion (paraphrases + hypothetical answer), BM25 + dense recall, cross-encoder reranking, "
          "diversity. Returns `sufficient_evidence`: false means the corpus does not contain a good answer — then "
          "search the literature (or say so) instead of answering from weak passages. Use it before new searches.",
          digest=_passages_digest)
    async def search_corpus(query: Annotated[str, Field(description="what you need evidence for")],
                            k: Annotated[int, Field(ge=1, le=12)] = 6,
                            paper_ids: Annotated[list[str] | None, Field(description="restrict to these P# ids")] = None
                            ) -> dict:
        r = await corpus.retrieve(pid, query, k, paper_ids, expand_query=True)
        note = ("Top passage is below the calibrated relevance threshold: the corpus likely lacks this."
                if r["sufficient"] is False else None)
        return {"sufficient_evidence": r["sufficient"], "note": note, "reranker": r["reranker"],
                "passages": [{"paper_id": h["paper_id"], "chunk_id": h["chunk_id"], "kind": h["kind"],
                              "relevance": h["score"], "text": h["text"][:900],
                              **({"context_after": h["after"][:250]} if h.get("after") else {})} for h in r["hits"]]}

    @tool("Write a finding to the shared research notebook. Every agent (and the final report) sees the notebook, and "
          "it survives context compression. Cite paper ids in refs.",
          digest=lambda r: "noted")
    async def note(kind: Literal["finding", "gap", "question", "decision"],
                   text: Annotated[str, Field(description="one crisp sentence with the fact")],
                   refs: Annotated[list[str], Field(description="P# ids backing it")] = []) -> dict:
        valid = [r.upper() for r in refs if db.paper(pid, r)]
        db.add_note(pid, agent, kind, text, valid)
        return {"ok": True, "refs_kept": valid}

    tools = [search_arxiv, search_openalex, search_hf_papers, search_web, citation_graph, paper_details,
             read_fulltext, search_corpus, note]
    return [t for t in tools if include is None or t.name in include]


async def web_sweep(pid: str, queries: list[str], per_query: int = 6) -> dict:
    """Tavily web search on the plan's key queries, every run: recent preprints, blogs, GitHub repos and leaderboards
    that scholarly indexes lag behind. arXiv links found are added to the paper registry (and relevance-ranked)."""
    found, added = [], []
    with trace.scope(project_id=pid, agent="Web Scout (Tavily)"):
        for q in [q for q in dict.fromkeys(queries) if q][:4]:
            try:
                res = await web.search(_clean_query(q), max_results=per_query, time_range="year")
            except Exception as e:
                trace.error("Tavily search failed", str(e)[:200])
                continue
            for r in res:
                found.append({"query": q, "title": r["title"], "url": r["url"], "snippet": r["content"][:300],
                              "date": r.get("published_date")})
            ids = [arxiv.arxiv_id(r["url"]) for r in res if "arxiv.org" in r["url"]]
            if any(ids):
                recs = await arxiv.by_ids([i for i in ids if i])
                rows = await papers.ingest(pid, recs, found_by="Web Scout (Tavily)")
                added += [r["id"] for r in rows if r["new"]]
        if added:
            await triage(pid, added)
        trace.info(f"Tavily web sweep: {len(found)} web results, {len(added)} new arXiv paper(s)",
                   "\n".join(f"• {f['title']} — {f['url']}" for f in found[:12]))
    return {"results": found, "new_papers": added}


def notebook_text(pid: str, limit: int = 40) -> str:
    ns = db.notes(pid)
    if not ns:
        return ""
    lines = [f"- ({n['kind']}, {n['agent']}) {n['text']}" + (f" [{', '.join(n['refs'])}]" if n['refs'] else "")
             for n in ns[-limit:]]
    return "## Shared research notebook (all agents)\n" + "\n".join(lines)


async def gather_limited(coros, limit: int = 4):
    sem = asyncio.Semaphore(limit)

    async def one(c):
        async with sem:
            return await c
    return await asyncio.gather(*(one(c) for c in coros), return_exceptions=True)
