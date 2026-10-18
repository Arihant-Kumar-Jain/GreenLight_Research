"""Hugging Face Papers: community + adoption signals for ML papers (upvotes, linked models/datasets/Spaces, code repo).

Adoption is a reproducibility signal for the credibility score: 480 public models built on a method is evidence the
results hold up outside the paper. Also a search source for recent ML papers. Free; HF_TOKEN raises rate limits.
"""

import time

from .. import trace
from ..config import settings
from . import http

API = "https://huggingface.co/api"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.hf_token}"} if settings.hf_token else {}


async def paper(arxiv_id: str) -> dict | None:
    d = await http.get(f"{API}/papers/{arxiv_id}", headers=_headers(), label="HF paper", cache_s=86400)
    if not d or not isinstance(d, dict) or "id" not in d:
        return None
    return {"upvotes": d.get("upvotes") or 0, "models": d.get("numTotalModels") or 0,
            "datasets": d.get("numTotalDatasets") or 0, "spaces": d.get("numTotalSpaces") or 0,
            "github": d.get("githubRepo"), "github_stars": d.get("githubStars"),
            "ai_summary": d.get("ai_summary"), "url": f"https://huggingface.co/papers/{arxiv_id}"}


async def search(query: str, max_results: int = 8) -> list[dict]:
    t0 = time.perf_counter()
    d = await http.get(f"{API}/papers/search", params={"q": query}, headers=_headers(), label="HF papers search")
    out = []
    for item in (d or [])[:max_results]:
        p = item.get("paper") or {}
        if not p.get("id"):
            continue
        out.append({"title": (p.get("title") or "").replace("\n", " ").strip(),
                    "abstract": (p.get("summary") or "").replace("\n", " ").strip(),
                    "authors": [{"name": a.get("name")} for a in p.get("authors") or []],
                    "published": (p.get("publishedAt") or "")[:10],
                    "year": int(p["publishedAt"][:4]) if (p.get("publishedAt") or "")[:4].isdigit() else None,
                    "arxiv_id": p["id"], "url": f"https://arxiv.org/abs/{p['id']}",
                    "pdf_url": f"https://arxiv.org/pdf/{p['id']}",
                    "hf": {"upvotes": p.get("upvotes") or 0, "url": f"https://huggingface.co/papers/{p['id']}"},
                    "sources": ["huggingface"]})
    trace.source(f"Hugging Face papers search: {query}", "\n".join(f"• {p['title']}" for p in out[:8]),
                 provider="Hugging Face", latency_ms=int((time.perf_counter() - t0) * 1000))
    return out
