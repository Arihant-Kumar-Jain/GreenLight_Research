"""OpenAlex: the bibliometric backbone of the credibility score (free, no key; polite pool with OPENALEX_MAILTO).

Gives citation counts, field-normalised impact (FWCI, citation percentile), retraction flags, author h-index and
venue statistics. Every lookup by id is checked against the expected title, because OpenAlex sometimes maps an
arXiv DOI to a different work (seen: LoRA's DOI resolving to an unrelated 2025 paper).
"""

import difflib
import re
import time

from .. import trace
from ..config import settings
from . import http

API = "https://api.openalex.org"
WORK_FIELDS = ("id,doi,title,publication_year,publication_date,cited_by_count,fwci,citation_normalized_percentile,"
               "is_retracted,type,primary_location,locations,authorships,abstract_inverted_index,counts_by_year,ids,"
               "referenced_works_count,primary_topic")


def _params(extra: dict) -> dict:
    p = dict(extra)
    if settings.openalex_mailto:
        p["mailto"] = settings.openalex_mailto
    if settings.openalex_api_key:  # keyless calls share a small per-IP daily budget
        p["api_key"] = settings.openalex_api_key
    return p


def norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def same_title(a: str | None, b: str | None) -> bool:
    """Same paper title, tolerating punctuation/typo noise but not a different word ("LoRA" vs "LoRTA … Tensor …"
    scores 0.9 on character similarity, so similarity alone is not enough)."""
    a, b = norm_title(a), norm_title(b)
    if not (a and b):
        return False
    if a == b:
        return True
    diff = set(a.split()) ^ set(b.split())
    return len(diff) <= 1 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.95


def abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = sorted((i, w) for w, idxs in inv.items() for i in idxs)
    return " ".join(w for _, w in pos)


def _record(w: dict) -> dict:
    from .arxiv import arxiv_id
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    aid = None
    for l in [loc] + (w.get("locations") or []):
        u = (l or {}).get("landing_page_url") or ""
        if "arxiv.org" in u:
            aid = arxiv_id(u)
            break
    doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
    if not aid and doi and "arxiv" in doi.lower():
        aid = arxiv_id(doi)
    pct = w.get("citation_normalized_percentile") or {}
    return {
        "title": w.get("title") or "",
        "abstract": abstract(w.get("abstract_inverted_index")),
        "year": w.get("publication_year"),
        "published": w.get("publication_date"),
        "doi": doi,
        "arxiv_id": aid,
        "openalex_id": (w.get("id") or "").rsplit("/", 1)[-1] or None,
        "url": loc.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else w.get("id")),
        "pdf_url": loc.get("pdf_url"),
        "authors": [{"name": (a.get("author") or {}).get("display_name"),
                     "openalex_id": ((a.get("author") or {}).get("id") or "").rsplit("/", 1)[-1] or None,
                     "position": a.get("author_position"),
                     "institutions": [i.get("display_name") for i in a.get("institutions") or []][:2]}
                    for a in (w.get("authorships") or [])[:25]],
        "venue": {"name": src.get("display_name"), "type": src.get("type"),
                  "openalex_id": (src.get("id") or "").rsplit("/", 1)[-1] or None} if src else None,
        "work_type": w.get("type"),
        "citations": w.get("cited_by_count") or 0,
        "counts_by_year": {c["year"]: c["cited_by_count"] for c in w.get("counts_by_year") or []},
        "fwci": w.get("fwci"),
        "citation_percentile": pct.get("value"),
        "top_1_percent": pct.get("is_in_top_1_percent"),
        "top_10_percent": pct.get("is_in_top_10_percent"),
        "is_retracted": bool(w.get("is_retracted")),
        "references": w.get("referenced_works_count"),
        "field": ((w.get("primary_topic") or {}).get("field") or {}).get("display_name"),
        "sources": ["openalex"],
    }


async def search(query: str, max_results: int = 8, from_year: int | None = None) -> list[dict]:
    t0 = time.perf_counter()
    params = {"search": query, "per_page": max_results, "select": WORK_FIELDS}
    if from_year:
        params["filter"] = f"from_publication_date:{from_year}-01-01"
    d = await http.get(f"{API}/works", params=_params(params), label="OpenAlex search")
    out = [_record(w) for w in (d or {}).get("results", []) if w.get("title")]
    trace.source(f"OpenAlex search: {query}", "\n".join(f"• {p['title']} ({p['year']}, {p['citations']} cites)"
                                                        for p in out[:8]),
                 provider="OpenAlex", latency_ms=int((time.perf_counter() - t0) * 1000))
    return out


async def resolve(title: str, doi: str | None = None, arxiv_id: str | None = None,
                  openalex_id: str | None = None) -> dict | None:
    """Find the OpenAlex record for a paper, verifying the title so a wrong id mapping is never accepted."""
    candidates = [openalex_id] if openalex_id else []
    if doi:
        candidates.append(f"doi:{doi}")
    if arxiv_id:
        candidates.append(f"doi:10.48550/arxiv.{arxiv_id}")
    for c in candidates:
        try:
            w = await http.get(f"{API}/works/{c}", params=_params({"select": WORK_FIELDS}), label="OpenAlex lookup")
        except http.SourceUnavailable:
            w = None
        if w and same_title(w.get("title"), title):
            return _record(w)
    if not title:
        return None
    d = await http.get(f"{API}/works", params=_params({"filter": f"title.search:{norm_title(title)[:200]}",
                                                        "per_page": 5, "select": WORK_FIELDS,
                                                        "sort": "cited_by_count:desc"}),
                       label="OpenAlex title lookup")
    for w in (d or {}).get("results", []):
        if same_title(w.get("title"), title):
            return _record(w)
    return None


async def authors(ids: list[str]) -> dict[str, dict]:
    """OpenAlex author id -> {h_index, works, citations, name}. Batched 50 per call."""
    ids = [i for i in dict.fromkeys(ids) if i]
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        part = ids[i:i + 50]
        d = await http.get(f"{API}/authors", params=_params({"filter": "openalex:" + "|".join(part), "per_page": 50,
                                                             "select": "id,display_name,summary_stats,works_count,cited_by_count"}),
                           label="OpenAlex authors")
        for a in (d or {}).get("results", []):
            s = a.get("summary_stats") or {}
            out[a["id"].rsplit("/", 1)[-1]] = {"name": a.get("display_name"), "h_index": s.get("h_index"),
                                               "i10_index": s.get("i10_index"), "works": a.get("works_count"),
                                               "citations": a.get("cited_by_count")}
    return out


async def sources(ids: list[str]) -> dict[str, dict]:
    ids = [i for i in dict.fromkeys(ids) if i]
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        part = ids[i:i + 50]
        d = await http.get(f"{API}/sources", params=_params({"filter": "openalex:" + "|".join(part), "per_page": 50,
                                                             "select": "id,display_name,type,summary_stats"}),
                           label="OpenAlex venues")
        for s in (d or {}).get("results", []):
            st = s.get("summary_stats") or {}
            out[s["id"].rsplit("/", 1)[-1]] = {"name": s.get("display_name"), "type": s.get("type"),
                                               "h_index": st.get("h_index"),
                                               "mean_citedness": st.get("2yr_mean_citedness")}
    return out


async def related(work_id: str, direction: str = "citing", query: str | None = None, max_results: int = 8) -> list[dict]:
    """Citation-graph hop. citing = newer papers that cite this work (forward snowballing: "was it done since?");
    references = what this work builds on (backward snowballing)."""
    t0 = time.perf_counter()
    f = f"cites:{work_id}" if direction == "citing" else f"cited_by:{work_id}"
    params = {"filter": f, "per_page": max_results, "select": WORK_FIELDS,
              "sort": "relevance_score:desc" if query else "cited_by_count:desc"}
    if query:
        params["search"] = query
    d = await http.get(f"{API}/works", params=_params(params), label="OpenAlex citation graph")
    out = [_record(w) for w in (d or {}).get("results", []) if w.get("title")]
    trace.source(f"OpenAlex {direction} {work_id}" + (f" matching '{query}'" if query else ""),
                 "\n".join(f"• {p['title']} ({p['year']})" for p in out[:8]), provider="OpenAlex",
                 latency_ms=int((time.perf_counter() - t0) * 1000))
    return out
