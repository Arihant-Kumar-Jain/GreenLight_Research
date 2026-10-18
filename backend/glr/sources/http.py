"""One HTTP seam for scholarly APIs: per-host pacing, 429 cooldowns, retries and a response cache.

arXiv rate-limits per IP and answers 429 to *every* query once tripped,
so requests to a host share one clock, a 429 opens a cooldown that later calls respect (instead of hammering),
and identical requests are served from the cache.
"""

import asyncio
import hashlib
import json
import time

import httpx

from .. import db, trace

UA = "GreenLightResearch/0.1 (deep research assistant; hackathon project)"
PACE_S = {"export.arxiv.org": 3.1, "api.semanticscholar.org": 1.1, "api.openalex.org": 0.12, "huggingface.co": 0.2, "arxiv.org": 1.0}
COOLDOWN_S = 300

_last: dict[str, float] = {}
_cool_until: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}
_client: httpx.AsyncClient | None = None


class SourceUnavailable(RuntimeError):
    pass


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": UA})
    return _client


async def get(url: str, *, params: dict | None = None, headers: dict | None = None, label: str,
              as_text: bool = False, cache_s: float | None = 7 * 86400, retries: int = 2):
    """GET with pacing + cache. Returns parsed JSON (or text). Raises SourceUnavailable on cooldown/failure."""
    host = httpx.URL(url).host
    key = "http:" + hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    if cache_s and (hit := db.cache_get(key, cache_s)) is not None:
        return hit
    if time.time() < _cool_until.get(host, 0):
        raise SourceUnavailable(f"{host} is rate-limiting us; cooling down for {int(_cool_until[host] - time.time())}s")
    lock = _locks.setdefault(host, asyncio.Lock())
    err = None
    for attempt in range(retries + 1):
        async with lock:  # one clock per host
            wait = PACE_S.get(host, 0.1) - (time.time() - _last.get(host, 0))
            if wait > 0:
                await asyncio.sleep(wait)
            t0 = time.perf_counter()
            try:
                r = await client().get(url, params=params, headers=headers or {})
            except httpx.HTTPError as e:
                err = e
                _last[host] = time.time()
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            finally:
                _last[host] = time.time()
        ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code == 429:
            retry_after = r.headers.get("retry-after")
            _cool_until[host] = time.time() + (float(retry_after) if retry_after and retry_after.isdigit() else COOLDOWN_S)
            trace.source(f"{label}: rate-limited (429), cooling down", host, provider=host, latency_ms=ms)
            raise SourceUnavailable(f"{host} answered 429 (rate limit)")
        if r.status_code == 404:
            return None
        if r.status_code >= 500:
            err = RuntimeError(f"{host} {r.status_code}")
            await asyncio.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise SourceUnavailable(f"{host} {r.status_code}: {r.text[:200]}")
        out = r.text if as_text else r.json()
        if cache_s:
            db.cache_put(key, out)
        return out
    raise SourceUnavailable(f"{label} failed: {err}")
