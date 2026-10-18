"""Per-project paper corpus: chunking, Qwen3 embeddings and a multi-stage retrieval pipeline.

  retrieve(query)
    1. expand    Nemotron Nano writes 2 paraphrased queries + a HyDE passage (a hypothetical answer, embedded as a
                 document) — cached per query
    2. recall    BM25 and Qwen3-Embedding-8B dense search for every query variant, fused by weighted reciprocal rank
                 fusion into a candidate pool (40)
    3. rerank    cross-encoder over the pool only (rerank.py: NVIDIA NIM / vLLM endpoint / local bge-reranker / Nano)
    4. gate      "enough evidence?" = top rerank score ≥ the threshold calibrated for that reranker by the eval
    5. MMR       maximal marginal relevance over the reranked list, so k results are not k near-duplicates
    6. context   ±1 neighbouring chunk attached to full-text hits (recovers sentences cut at chunk borders)
Chunks carry a contextual header (paper title) before embedding. Vectors are Matryoshka-truncated to 1024 dims,
float16. Every stage degrades instead of failing: no embeddings → BM25, no reranker → fused order, no calibration →
no gate. Each stage can be switched off, which is how the retrieval eval measures what each one buys.
"""

import asyncio
import hashlib
import math
import re
import time
from collections import Counter

import numpy as np
from pydantic import BaseModel, Field

from . import db, llm, rerank, trace
from .config import settings

DIMS = 1024
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]+")
STOP = set("the a an of and or in on to for with by is are was were be been this that these those we our it its as "
           "at from which can not has have had than their they using use used based via into also such more".split())
REF_HEAD = re.compile(r"(?im)^\s*#*\s*(references|bibliography|acknowledg(e)?ments?)\s*$")

_bm25_cache: dict[str, tuple[int, "BM25"]] = {}


def words(text: str) -> list[str]:
    return [w for w in TOKEN_RE.findall(text.lower()) if w not in STOP]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.tf = [Counter(words(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1
        df: Counter = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> np.ndarray:
        q = words(query)
        out = np.zeros(len(self.tf))
        for i, tf in enumerate(self.tf):
            s = 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            out[i] = s
        return out


def split(text: str, size: int = 1400, overlap: int = 200) -> list[str]:
    """Paragraph-aware chunks; the bibliography is dropped (every reference looks relevant to every query)."""
    m = REF_HEAD.search(text)
    if m and m.start() > len(text) * 0.4:
        text = text[:m.start()]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 40]
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = cur[-overlap:] + "\n" + p
        else:
            cur = f"{cur}\n{p}" if cur else p
        while len(cur) > size * 1.6:
            out.append(cur[:size])
            cur = cur[size - overlap:]
    if cur:
        out.append(cur)
    return out


def _norm(v: np.ndarray) -> np.ndarray:
    v = v[:DIMS]
    n = np.linalg.norm(v)
    return v / n if n else v


async def add_text(pid: str, paper_id: str, kind: str, text: str, *, prefix: str = "") -> int:
    """Chunk + embed one paper text into the corpus. Returns the number of chunks added."""
    return await add_many(pid, [(paper_id, kind, text, prefix)])


async def add_many(pid: str, items: list[tuple[str, str, str, str]]) -> int:
    """Chunk + embed several (paper_id, kind, text, prefix) items with one batched embedding call."""
    rows = []
    for paper_id, kind, text, prefix in items:
        existing = db.chunk_ids_for(pid, paper_id)
        pieces = [text] if kind == "abstract" else split(text)
        start = len(existing)
        for i, piece in enumerate(pieces):
            cid = f"{paper_id}#abs" if kind == "abstract" else f"{paper_id}#{kind[0]}{start + i}"
            if cid in existing:
                continue
            rows.append((cid, paper_id, kind, f"{prefix}{piece}".strip()))
    if not rows:
        return 0
    vecs: list = [None] * len(rows)
    try:
        emb = await llm.embed([r[3][:6000] for r in rows],
                              title=f"Embed {len(rows)} chunk(s) of {len({r[1] for r in rows})} paper(s)")
        vecs = [_norm(np.asarray(e, dtype=np.float32)) for e in emb]
    except Exception as e:
        trace.error("Embedding failed; chunks stay keyword-searchable", str(e)[:300])
    db.add_chunks(pid, [(r[0], r[1], r[2], r[3], v) for r, v in zip(rows, vecs)])
    return len(rows)


class Expansion(BaseModel):
    rewrites: list[str] = Field(description="2 alternative phrasings using different terminology / synonyms")
    hyde: str = Field(description="A 3-4 sentence passage, as it would appear in a paper, that answers the query")


EXPAND_SYSTEM = """You help search a corpus of scientific papers. For the query, write (1) two alternative search
queries that use different terminology a paper might use (synonyms, older names, the technical term), and (2) a short
hypothetical passage from a paper that would answer it (plausible wording; it is only used for matching)."""


async def expand(query: str) -> Expansion | None:
    key = "expand:" + hashlib.sha256(query.encode()).hexdigest()
    if (hit := db.cache_get(key)) is not None:
        return Expansion.model_validate(hit)
    try:
        e = await llm.chat_json("fast", EXPAND_SYSTEM, query, Expansion, title="Query expansion (multi-query + HyDE)",
                                max_tokens=700, temperature=0.3)
    except Exception as ex:
        trace.error("Query expansion failed; using the original query only", str(ex)[:200])
        return None
    e.rewrites = e.rewrites[:2]
    db.cache_put(key, e.model_dump())
    return e


def _bm25_for(pid: str, chunks: list[dict], tag: str) -> "BM25":
    key = f"{pid}:{tag}"
    cached = _bm25_cache.get(key)
    if not cached or cached[0] != len(chunks):
        cached = (len(chunks), BM25([c["text"] for c in chunks]))
        _bm25_cache[key] = cached
    return cached[1]


_qcache: dict[tuple[str, bool], list[float]] = {}


async def _embed_cached(texts: list[str], query: bool) -> list[list[float]]:
    todo = [t for t in texts if (t, query) not in _qcache]
    if todo:
        for t, v in zip(todo, await llm.embed(todo, query=query, title=f"Embed {len(todo)} query text(s)")):
            _qcache[(t, query)] = v
    if len(_qcache) > 5000:
        _qcache.clear()
    return [_qcache[(t, query)] for t in texts if (t, query) in _qcache]


def _mmr(cands: list[int], rel: list[float], vecs: list, k: int, lam: float = 0.75) -> list[int]:
    """Greedy maximal marginal relevance over candidate positions (rel normalised to 0..1)."""
    if len(cands) <= k or any(vecs[i] is None for i in cands):
        return cands[:k]
    lo, hi = min(rel), max(rel)
    norm = [(r - lo) / (hi - lo) if hi > lo else 1.0 for r in rel]
    chosen: list[int] = []
    left = list(range(len(cands)))
    while left and len(chosen) < k:
        def gain(j):
            if not chosen:
                return norm[j]
            sim = max(float(vecs[cands[j]] @ vecs[cands[c]]) for c in chosen)
            return lam * norm[j] - (1 - lam) * sim
        best = max(left, key=gain)
        chosen.append(best)
        left.remove(best)
    return [cands[j] for j in chosen]


async def retrieve(pid: str, query: str, k: int = 8, paper_ids: list[str] | None = None, kinds: list[str] | None = None,
                   *, expand_query: bool | None = None, use_dense: bool = True, use_bm25: bool = True,
                   use_rerank: bool = True, use_mmr: bool = True, neighbours: bool = True, pool: int = 40,
                   reranker: str | None = None) -> dict:
    """Multi-stage retrieval. Returns {hits, sufficient, reranker, top_score, threshold, queries, n_candidates, ms}."""
    t0 = time.perf_counter()
    chunks = db.chunks(pid)
    by_id = {c["id"]: c for c in chunks}
    if paper_ids:
        wanted = {p.upper() for p in paper_ids}
        chunks = [c for c in chunks if c["paper_id"] in wanted]
    if kinds:
        chunks = [c for c in chunks if c["kind"] in kinds]
    out = {"hits": [], "sufficient": None, "reranker": "none", "top_score": None, "threshold": None,
           "queries": [query], "n_candidates": 0}
    if not chunks:
        out["sufficient"] = False
        return out

    # 1. expand
    do_expand = settings.query_expansion if expand_query is None else expand_query
    exp = None
    if do_expand:  # speculative: wait at most the deadline; a late expansion still lands in the cache for next time
        task = asyncio.ensure_future(expand(query))
        try:
            exp = await asyncio.wait_for(asyncio.shield(task), timeout=settings.expansion_deadline_s)
        except asyncio.TimeoutError:
            out["expansion"] = "deadline missed"
    variants = [(query, 1.0)] + [(q, 0.5) for q in (exp.rewrites if exp else [])]
    out["queries"] = [q for q, _ in variants]

    # 2. recall: weighted RRF over BM25 + dense for every variant (+ HyDE as a document-side vector)
    fused: dict[int, float] = {}

    def add(order, weight):
        for r, i in enumerate(order[:80]):
            fused[int(i)] = fused.get(int(i), 0.0) + weight / (60 + r)
    if use_bm25:
        bm = _bm25_for(pid, chunks, f"{','.join(sorted(paper_ids or []))}:{','.join(kinds or [])}")
        for q, w in variants:
            sc = bm.scores(q)
            add([i for i in np.argsort(-sc) if sc[i] > 0], 0.6 * w)
    have = [i for i, c in enumerate(chunks) if c["vec"] is not None]
    if use_dense and have:
        try:
            qv = await _embed_cached([q for q, _ in variants], True)
            hv = await _embed_cached([exp.hyde], False) if exp and exp.hyde else []
            mat = np.stack([chunks[i]["vec"][:DIMS] for i in have])
            for vec, w in [(v, w) for v, (_, w) in zip(qv, variants)] + [(v, 0.8) for v in hv]:
                v = _norm(np.asarray(vec, dtype=np.float32))
                if mat.shape[1] == v.shape[0]:
                    add([have[int(j)] for j in np.argsort(-(mat @ v))], 1.0 * w)
        except Exception as e:
            trace.error("Dense retrieval failed; using BM25 only", str(e)[:300])
    cands = [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])][:pool]
    out["n_candidates"] = len(cands)
    if not cands:
        out["sufficient"] = False
        return out

    # 3. rerank the pool only (never the whole corpus)
    rel = [fused[i] for i in cands]
    if use_rerank:
        scores, kind = await rerank.rerank(query, [chunks[i]["text"] for i in cands], prefer=reranker)
        if kind != "none":
            order = sorted(range(len(cands)), key=lambda j: -scores[j])
            cands, rel = [cands[j] for j in order], [scores[j] for j in order]
            out["reranker"] = kind
            out["top_score"] = round(rel[0], 4)
            # 4. gate, with the threshold measured for this backend
            thr = rerank.threshold(kind)
            out["threshold"] = thr
            out["sufficient"] = None if thr is None else rel[0] >= thr

    # 5. diversity
    vecs = [c["vec"][:DIMS] if c["vec"] is not None else None for c in chunks]
    vecs = [(_norm(v) if v is not None else None) for v in vecs]
    pos = {i: j for j, i in enumerate(cands)}
    picked = _mmr(cands[:max(k * 3, 15)], rel[:max(k * 3, 15)], vecs, k) if use_mmr else cands[:k]

    # 6. neighbour context for full-text chunks
    for i in picked:
        c = chunks[i]
        hit = {"chunk_id": c["id"], "paper_id": c["paper_id"], "kind": c["kind"],
               "score": round(rel[pos[i]], 4), "text": c["text"][:1800]}
        m = re.match(r"(P\d+)#f(\d+)$", c["id"])
        if neighbours and m:
            n = int(m.group(2))
            before, after = by_id.get(f"{m.group(1)}#f{n - 1}"), by_id.get(f"{m.group(1)}#f{n + 1}")
            if before:
                hit["before"] = before["text"][-350:]
            if after:
                hit["after"] = after["text"][:350]
        out["hits"].append(hit)
    out["ms"] = int((time.perf_counter() - t0) * 1000)
    return out


async def search(pid: str, query: str, k: int = 8, paper_ids: list[str] | None = None,
                 kinds: list[str] | None = None, **kw) -> list[dict]:
    """Hits only (see retrieve). Internal callers skip query expansion (one extra LLM call) unless they ask for it."""
    kw.setdefault("expand_query", False)
    return (await retrieve(pid, query, k, paper_ids, kinds, **kw))["hits"]
