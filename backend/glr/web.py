"""Real-time web access via Tavily (search, extract), with a cache for re-runs.

Scouts use it for what scholarly indexes miss: blog posts, benchmark leaderboards, GitHub repos, workshop papers,
very recent preprints, and reading full paper pages (arXiv HTML) when an agent needs more than the abstract.

Credits are scarce, so: results are cached (repeat queries and page reads cost 0), searches default to basic depth (1 credit),
each trace line shows its estimated credit cost, and calls stop at GLR_TAVILY_BUDGET using Tavily's /usage endpoint.
"""

import hashlib
import json
import math
import re
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from tavily import AsyncTavilyClient

from . import db, privacy, trace
from .config import settings

PROVIDER = "Tavily"
_client: AsyncTavilyClient | None = None
_client_key = ""


def tavily() -> AsyncTavilyClient:
    global _client, _client_key
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is not set. Add it to GreenLight_Research/.env")
    if _client is None or _client_key != settings.tavily_api_key:
        _client = AsyncTavilyClient(api_key=settings.tavily_api_key)
        _client_key = settings.tavily_api_key
    return _client


class TavilyBudgetError(RuntimeError):
    pass


_usage: dict = {"at": 0.0, "used": None, "limit": None}
LEDGER_KEY = "tavily:credits_spent"  # our own running estimate, kept in the database


def ledger() -> float:
    return float(db.cache_get(LEDGER_KEY) or 0)


async def usage(refresh: bool = False) -> dict:
    """Credits used: the larger of Tavily's /usage figure and our own ledger. /usage is rate-limited and lags (it
    showed 0 after real calls), so the ledger is what actually enforces the budget."""
    if refresh or time.time() - _usage["at"] > 300:
        try:
            async with httpx.AsyncClient(timeout=10) as h:
                r = await h.get("https://api.tavily.com/usage",
                                headers={"Authorization": f"Bearer {settings.tavily_api_key}"})
                r.raise_for_status()
            acct = r.json().get("account") or {}
            _usage.update(at=time.time(), used=acct.get("plan_usage"), limit=acct.get("plan_limit"))
        except Exception:
            _usage["at"] = time.time()  # rate-limited or offline: keep the estimate, try again later
    spent = ledger()
    return {"used": max(_usage["used"] or 0, spent), "reported": _usage["used"], "ledger": spent,
            "limit": _usage["limit"], "budget": settings.tavily_budget or None}


async def _spend(credits: float) -> None:
    """Refuse a call that would cross the budget; otherwise add its estimated cost to the ledger."""
    u = await usage()
    cap = min(x for x in (u["budget"], u["limit"], math.inf) if x)
    if u["used"] + credits > cap:
        raise TavilyBudgetError(f"Tavily credit budget reached ({u['used']:.0f}/{cap:.0f}). "
                                "Raise GLR_TAVILY_BUDGET or top up the plan.")
    db.cache_put(LEDGER_KEY, ledger() + credits)


def _credits(n: float) -> str:
    return f"{n:g} credit" + ("" if n == 1 else "s")


def _key(kind: str, payload: dict) -> str:
    return kind + ":" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def is_local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    own = urlparse(settings.public_base_url).hostname or ""
    return host in {"localhost", "127.0.0.1", "0.0.0.0", own} or host.endswith(".localhost")


async def search(query: str, *, topic: str = "general", max_results: int = 6, time_range: str | None = None,
                 include_domains: list[str] | None = None, depth: str | None = None, fresh: bool = False,
                 max_age_s: float | None = None) -> list[dict]:
    """fresh=True skips the cache; max_age_s reuses a cached result only if it is younger than that."""
    depth = depth or settings.tavily_search_depth
    clean = privacy.redact(query)
    if clean.count:  # never send personal data or secrets to a web search
        trace.info(f"Privacy: removed {clean.count} item(s) from a search query before calling Tavily",
                   ", ".join(x["label"] for x in clean.summary()))
        query = clean.text
    payload = {"q": query, "topic": topic, "n": max_results, "tr": time_range, "dom": include_domains, "d": depth}
    key = _key("search", payload)
    if (settings.cache_web or max_age_s) and not fresh and (hit := db.cache_get(key, max_age_s)) is not None:
        trace.source(f"Tavily search (cached, 0 credits): {query}", f"{len(hit)} results", provider=PROVIDER, latency_ms=0)
        return hit
    cost = 2 if depth == "advanced" else 1
    await _spend(cost)
    t0 = time.perf_counter()
    kwargs = dict(search_depth=depth, topic=topic, max_results=max_results)
    if time_range:
        kwargs["time_range"] = time_range
    if include_domains:
        kwargs["include_domains"] = include_domains
    resp = await tavily().search(query, **kwargs)
    results = [{"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", ""),
                "score": r.get("score"), "published_date": r.get("published_date")}
               for r in resp.get("results", [])]
    ms = int((time.perf_counter() - t0) * 1000)
    trace.source(f"Tavily search ({_credits(cost)}): {query}", "\n".join(f"• {r['title']} — {r['url']}" for r in results[:6]),
               provider=PROVIDER, latency_ms=ms)
    db.cache_put(key, results)
    return results


async def _fetch_direct(url: str) -> str:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as h:
        r = await h.get(url, headers={"User-Agent": "GreenLightResearch/0.1"})
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\n{2,}", "\n", soup.get_text("\n", strip=True))


async def extract(urls: list[str], *, fresh: bool = False, depth: str = "basic") -> dict[str, str]:
    """URL -> page text (markdown). Missing keys mean the page could not be read."""
    urls = [u for u in dict.fromkeys(urls) if u]
    out: dict[str, str] = {}
    remote = []
    for u in urls:
        if is_local(u):
            try:
                t0 = time.perf_counter()
                out[u] = await _fetch_direct(u)
                trace.source(f"Fetch (direct): {u}", f"{len(out[u])} chars", provider="direct",
                           latency_ms=int((time.perf_counter() - t0) * 1000))
            except Exception as e:
                trace.error(f"Fetch failed: {u}", str(e))
            continue
        key = _key("extract", {"u": u, "d": depth})
        if settings.cache_web and not fresh and (hit := db.cache_get(key)) is not None:
            out[u] = hit
        else:
            remote.append(u)
    if remote:
        per5 = 2 if depth == "advanced" else 1
        await _spend(math.ceil(len(remote) / 5) * per5)  # upper bound; failed URLs are free
        t0 = time.perf_counter()
        try:
            resp = await tavily().extract(remote, extract_depth=depth, format="markdown")
        except Exception as e:
            trace.error("Tavily extract failed", str(e))
            resp = {}
        for r in resp.get("results", []):
            u = r.get("url")
            content = r.get("raw_content") or ""
            if u and content:
                out[u] = content
                db.cache_put(_key("extract", {"u": u, "d": depth}), content)
        failed = [f.get("url") for f in resp.get("failed_results", [])]
        ok = sum(1 for u in remote if u in out)
        trace.source(f"Tavily extract ({_credits(math.ceil(ok / 5) * per5)}): {len(remote)} page(s)",
                   "\n".join([f"✓ {u}" for u in remote if u in out] + [f"✗ {u}" for u in failed]),
                   provider=PROVIDER, latency_ms=int((time.perf_counter() - t0) * 1000))
    elif urls:
        trace.source(f"Tavily extract (cached, 0 credits): {len(urls)} page(s)", "\n".join(urls), provider=PROVIDER, latency_ms=0)
    return out


def domain(url: str | None) -> str:
    host = urlparse(url or "").hostname or ""
    return host[4:] if host.startswith("www.") else host
