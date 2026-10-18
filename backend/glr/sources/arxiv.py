"""arXiv search (Atom API) → normalised paper records. Free, no key; paced to arXiv's 3 s rule by http.py."""

import re
import time
import xml.etree.ElementTree as ET

from .. import trace
from . import http

NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
API = "https://export.arxiv.org/api/query"
STOP = {"a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with", "using", "via", "by", "is", "are", "how"}


def arxiv_id(s: str | None) -> str | None:
    """Bare arXiv id (no version) from an id, abs/pdf URL or DOI."""
    if not s:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", s) or re.search(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})", s)
    return m.group(1) if m else None


def _query(q: str, mode: str) -> str:
    if re.search(r"\b(ti|abs|au|all|cat):", q):
        return q
    words = [w for w in re.findall(r"[A-Za-z0-9\-]+", q) if w.lower() not in STOP][:8]
    if mode == "and":
        return " AND ".join(f"all:{w}" for w in words)
    return " OR ".join(f"all:{w}" for w in words)


def _parse(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", NS):
        aid = arxiv_id(e.findtext("a:id", "", NS))
        if not aid:
            continue
        pdf = next((link.get("href") for link in e.findall("a:link", NS) if link.get("title") == "pdf"), None)
        published = e.findtext("a:published", "", NS)
        out.append({
            "title": re.sub(r"\s+", " ", e.findtext("a:title", "", NS)).strip(),
            "abstract": re.sub(r"\s+", " ", e.findtext("a:summary", "", NS)).strip(),
            "authors": [{"name": a.findtext("a:name", "", NS)} for a in e.findall("a:author", NS)],
            "year": int(published[:4]) if published[:4].isdigit() else None,
            "published": published[:10],
            "arxiv_id": aid,
            "doi": e.findtext("arxiv:doi", None, NS),
            "url": f"https://arxiv.org/abs/{aid}",
            "pdf_url": pdf or f"https://arxiv.org/pdf/{aid}",
            "categories": [c.get("term") for c in e.findall("a:category", NS)],
            "journal_ref": e.findtext("arxiv:journal_ref", None, NS),
            "sources": ["arxiv"],
        })
    return out


async def search(query: str, max_results: int = 8) -> list[dict]:
    t0 = time.perf_counter()
    results: list[dict] = []
    for mode in ("and", "or"):  # precise first; widen only if the AND query is too narrow
        xml = await http.get(API, params={"search_query": _query(query, mode), "start": 0, "max_results": max_results,
                                          "sortBy": "relevance"}, as_text=True, label="arXiv search")
        results = _parse(xml or "<feed xmlns='http://www.w3.org/2005/Atom'/>")
        if len(results) >= min(3, max_results):
            break
    trace.source(f"arXiv search: {query}", "\n".join(f"• {p['title']} ({p['arxiv_id']})" for p in results[:8]),
                 provider="arXiv", latency_ms=int((time.perf_counter() - t0) * 1000))
    return results


async def by_ids(ids: list[str]) -> list[dict]:
    ids = [i for i in dict.fromkeys(arxiv_id(i) for i in ids) if i]
    if not ids:
        return []
    xml = await http.get(API, params={"id_list": ",".join(ids), "max_results": len(ids)}, as_text=True,
                         label="arXiv lookup")
    return _parse(xml or "<feed xmlns='http://www.w3.org/2005/Atom'/>")
