"""Paper registry for a project: merge records from every source into one paper (P#), enrich, score, read.

  ingest   - dedup across arXiv / OpenAlex / Hugging Face / web by arXiv id, DOI or near-identical title, merge fields,
             index the abstract into the corpus
  enrich   - OpenAlex bibliometrics (title-verified), author h-indexes, venue stats, Hugging Face adoption,
             optional Semantic Scholar → deterministic credibility score (credibility.py)
  read     - full text (Tavily Extract, else arXiv HTML, else PDF) chunked into the corpus for deep retrieval
"""

import asyncio
import io
import re

import httpx

from . import corpus, credibility, db, trace, web
from .config import settings
from .sources import hf, openalex, s2
from .sources.arxiv import arxiv_id
from .sources.openalex import norm_title, same_title

MERGE_KEEP = ("title", "abstract", "year", "published", "doi", "arxiv_id", "url", "pdf_url", "venue", "journal_ref",
              "openalex_id", "work_type", "field", "categories")


def key_of(rec: dict) -> str:
    if rec.get("arxiv_id"):
        return f"arxiv:{rec['arxiv_id']}"
    if rec.get("doi"):
        return f"doi:{rec['doi'].lower()}"
    return "title:" + norm_title(rec.get("title"))[:90]


def _merge(cur: dict, rec: dict, found_by: str | None) -> dict:
    for k in MERGE_KEEP:
        if not cur.get(k) and rec.get(k):
            cur[k] = rec[k]
    if len(rec.get("abstract") or "") > len(cur.get("abstract") or ""):
        cur["abstract"] = rec["abstract"]
    if rec.get("authors") and (not cur.get("authors") or (rec["authors"][0].get("openalex_id")
                                                          and not cur["authors"][0].get("openalex_id"))):
        cur["authors"] = rec["authors"]
    for k in ("citations", "fwci", "citation_percentile", "top_1_percent", "top_10_percent", "is_retracted",
              "counts_by_year", "references"):
        if rec.get(k) is not None:
            cur[k] = rec[k]
    if rec.get("hf"):
        cur["hf"] = {**(cur.get("hf") or {}), **rec["hf"]}
    cur["sources"] = sorted(set(cur.get("sources", [])) | set(rec.get("sources", [])))
    if found_by:
        cur["found_by"] = sorted(set(cur.get("found_by", [])) | {found_by})
    return cur


def _find_existing(pid: str, rec: dict) -> dict | None:
    hit = db.paper_by_key(pid, key_of(rec))
    if hit:
        return hit
    for p in db.papers(pid):
        if (rec.get("arxiv_id") and p.get("arxiv_id") == rec["arxiv_id"]) or \
           (rec.get("doi") and (p.get("doi") or "").lower() == rec["doi"].lower()) or same_title(p.get("title"), rec.get("title")):
            return p
    return None


async def ingest(pid: str, records: list[dict], found_by: str | None = None) -> list[dict]:
    """Add/merge records. Returns compact rows {id, title, year, new} for the agent."""
    out, to_embed = [], []
    for rec in records:
        if not (rec.get("title") or "").strip():
            continue
        cur = _find_existing(pid, rec)
        if cur:
            merged = _merge(cur, rec, found_by)
            db.update_paper(pid, cur["id"], **merged)
            out.append({"id": cur["id"], "title": merged["title"], "year": merged.get("year"), "new": False})
            continue
        data = _merge({"found_by": [], "sources": []}, rec, found_by)
        paper_id, _ = db.add_paper(pid, key_of(rec), data)
        to_embed.append((paper_id, "abstract", data.get("abstract") or "", f"{data['title']}. "))
        out.append({"id": paper_id, "title": data["title"], "year": data.get("year"), "new": True})
    if to_embed:
        await corpus.add_many(pid, to_embed)
    return out


# ---------------------------------------------------------------- enrichment + credibility

async def enrich(pid: str, paper_ids: list[str] | None = None, *, concurrency: int = 6) -> list[dict]:
    papers = [p for p in db.papers(pid) if (paper_ids is None or p["id"] in paper_ids)]
    sem = asyncio.Semaphore(concurrency)

    async def one(p: dict) -> None:
        async with sem:
            if not p.get("biblio_checked"):  # an id alone (e.g. from a citation hop) is not bibliometrics
                p["biblio_checked"] = True
                try:
                    rec = await openalex.resolve(p["title"], p.get("doi"), p.get("arxiv_id"), p.get("openalex_id"))
                    if rec:
                        _merge(p, rec, None)
                        p["authors"] = rec["authors"] or p.get("authors", [])
                        p["openalex_id"] = rec["openalex_id"]
                        p["venue"] = rec.get("venue") or p.get("venue")
                        p["work_type"] = rec.get("work_type")
                except Exception as e:
                    trace.error(f"OpenAlex lookup failed for {p['id']}", str(e)[:300])
            aid = p.get("arxiv_id") or (arxiv_id(p["doi"]) if "arxiv" in (p.get("doi") or "").lower() else None)
            if aid and not (p.get("hf") or {}).get("checked"):
                try:
                    info = await hf.paper(aid)
                    p["hf"] = {**(p.get("hf") or {}), **(info or {}), "checked": True}
                except Exception:
                    pass
            if not p.get("s2") and (settings.s2_api_key or p.get("citations") is None):
                p["s2"] = await s2.paper(p.get("arxiv_id"), p.get("doi"), fallback=not p.get("openalex_id")) or {}
                s = p["s2"]
                if s and p.get("citations") is None and same_title(s.get("title"), p.get("title")):
                    # OpenAlex couldn't verify this paper: take bibliometrics from Semantic Scholar instead
                    p["citations"] = s.get("citations")
                    p["biblio_source"] = "Semantic Scholar"
                    if s.get("authors") and any(a.get("h_index") is not None for a in s["authors"]):
                        p["authors"] = s["authors"]
                    if s.get("venue") and "arxiv" not in s["venue"].lower():
                        p["venue"] = {"name": s["venue"], "type": (s.get("venue_type") or "venue").lower()}
            db.update_paper(pid, p["id"], **p)

    await asyncio.gather(*(one(p) for p in papers))
    # author + venue stats in two batched calls for the whole set
    papers = [p for p in db.papers(pid) if (paper_ids is None or p["id"] in paper_ids)]
    a_ids = [a.get("openalex_id") for p in papers for a in p.get("authors", [])[:12] if a.get("openalex_id")]
    v_ids = [(p.get("venue") or {}).get("openalex_id") for p in papers if (p.get("venue") or {}).get("openalex_id")]
    try:
        a_stats, v_stats = await asyncio.gather(openalex.authors(a_ids), openalex.sources(v_ids))
    except Exception as e:
        trace.error("OpenAlex author/venue stats failed", str(e)[:300])
        a_stats, v_stats = {}, {}
    out = []
    for p in papers:
        for a in p.get("authors", []):
            if a.get("openalex_id") in a_stats:
                a.update({k: v for k, v in a_stats[a["openalex_id"]].items() if k != "name"})
        vid = (p.get("venue") or {}).get("openalex_id")
        if vid in v_stats:
            p["venue"].update(v_stats[vid])
        p["credibility"] = credibility.score(p)
        db.update_paper(pid, p["id"], **p)
        out.append(p)
    trace.info(f"Credibility scored for {len(out)} paper(s)",
               "\n".join(f"{p['id']} {p['credibility']['score']}/100 ({p['credibility']['tier']}) — {p['title'][:80]}"
                         for p in sorted(out, key=lambda p: -p['credibility']['score'])[:20]))
    return out


def rescore(pid: str, paper_id: str) -> dict:
    p = db.paper(pid, paper_id)
    p["credibility"] = credibility.score(p)
    return db.update_paper(pid, paper_id, credibility=p["credibility"])


# ---------------------------------------------------------------- full text

async def _pdf_text(url: str) -> str:
    from pypdf import PdfReader
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as h:
        r = await h.get(url, headers={"User-Agent": "GreenLightResearch/0.1"})
        r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    return "\n\n".join((pg.extract_text() or "") for pg in reader.pages[:30])


async def read(pid: str, paper_id: str) -> dict:
    """Fetch and index a paper's full text. Returns {chars, chunks, via} or an error dict."""
    p = db.paper(pid, paper_id)
    if not p:
        return {"error": "unknown_paper", "detail": f"No paper {paper_id}"}
    if p.get("fulltext"):
        return {"paper_id": paper_id, "already_read": True, **p["fulltext"]}
    aid = p.get("arxiv_id")
    candidates = []
    if aid:
        candidates.append(("arxiv-html", f"https://arxiv.org/html/{aid}"))
    if p.get("url") and "arxiv.org" not in (p.get("url") or ""):
        candidates.append(("landing", p["url"]))
    text, via = "", None
    if settings.tavily_api_key and candidates:
        try:
            got = await web.extract([u for _, u in candidates])
            for name, u in candidates:
                if len(got.get(u, "")) > 3000:
                    text, via = got[u], f"Tavily Extract ({name})"
                    break
        except Exception as e:
            trace.error("Tavily extract failed", str(e)[:300])
    if not text and (aid or p.get("pdf_url")):
        try:
            text = await _pdf_text(p.get("pdf_url") or f"https://arxiv.org/pdf/{aid}")
            via = "PDF (pypdf)"
        except Exception as e:
            trace.error(f"PDF read failed for {paper_id}", str(e)[:300])
    if len(text) < 1500:
        return {"error": "no_fulltext", "detail": "Full text not reachable; work from the abstract."}
    text = re.sub(r"\n{3,}", "\n\n", text)[:120000]
    n = await corpus.add_text(pid, paper_id, "fulltext", text, prefix=f"[{p['title'][:120]}] ")  # contextual header
    info = {"chars": len(text), "chunks": n, "via": via}
    db.update_paper(pid, paper_id, fulltext=info)
    trace.source(f"Read full text of {paper_id} via {via}", f"{len(text):,} chars → {n} chunks", provider=via)
    return {"paper_id": paper_id, **info}


def card(p: dict, abstract_chars: int = 600) -> dict:
    """Compact view of a paper for agent context."""
    c = p.get("credibility") or {}
    return {"id": p["id"], "title": p.get("title"), "year": p.get("year"),
            "authors": ", ".join(a.get("name") or "" for a in p.get("authors", [])[:4])
                       + (" et al." if len(p.get("authors", [])) > 4 else ""),
            "venue": (p.get("venue") or {}).get("name"), "citations": p.get("citations"),
            "credibility": c.get("score"), "credibility_tier": c.get("tier"),
            "retracted": p.get("is_retracted") or None, "url": p.get("url"),
            "abstract": (p.get("abstract") or "")[:abstract_chars]}
