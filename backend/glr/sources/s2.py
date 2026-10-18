"""Semantic Scholar: influential-citation counts, and the bibliometric fallback when OpenAlex can't verify a paper
(e.g. OpenAlex has LoRA mis-merged into another work). With S2_API_KEY it is always used; without one it is tried
only as a fallback, because the keyless pool is shared and often answers 429 (http.py then cools down)."""

from ..config import settings
from . import http

API = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,year,citationCount,influentialCitationCount,venue,publicationVenue,authors.name,authors.hIndex"


async def paper(arxiv_id: str | None = None, doi: str | None = None, *, fallback: bool = False) -> dict | None:
    if not (arxiv_id or doi) or not (settings.s2_api_key or fallback):
        return None
    pid = f"arXiv:{arxiv_id}" if arxiv_id else f"DOI:{doi}"
    headers = {"x-api-key": settings.s2_api_key} if settings.s2_api_key else {}
    try:
        d = await http.get(f"{API}/paper/{pid}", params={"fields": FIELDS}, headers=headers,
                           label="Semantic Scholar", cache_s=86400, retries=0)
    except http.SourceUnavailable:
        return None
    if not d:
        return None
    pv = d.get("publicationVenue") or {}
    return {"title": d.get("title"), "citations": d.get("citationCount"),
            "influential_citations": d.get("influentialCitationCount"),
            "venue": d.get("venue") or pv.get("name"), "venue_type": pv.get("type"),
            "authors": [{"name": a.get("name"), "h_index": a.get("hIndex")} for a in d.get("authors") or []]}
