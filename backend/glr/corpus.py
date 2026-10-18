"""Per-project paper corpus: chunking, Qwen3 embeddings and hybrid retrieval (BM25 + dense, reciprocal rank fusion).

Same retrieval recipe that scored best in Greenlight's legal RAG eval (weighted RRF of BM25 and Qwen3-Embedding-8B),
applied to abstracts and full texts the agents chose to read. Vectors are Matryoshka-truncated to 1024 dims and
stored as float16 next to each chunk. If embeddings are unavailable, retrieval degrades to BM25 instead of failing.
"""

import math
import re
from collections import Counter

import numpy as np

from . import db, llm, trace

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


async def search(pid: str, query: str, k: int = 8, paper_ids: list[str] | None = None,
                 kinds: list[str] | None = None) -> list[dict]:
    chunks = db.chunks(pid)
    if paper_ids:
        wanted = {p.upper() for p in paper_ids}
        chunks = [c for c in chunks if c["paper_id"] in wanted]
    if kinds:
        chunks = [c for c in chunks if c["kind"] in kinds]
    if not chunks:
        return []
    key = f"{pid}:{','.join(sorted(paper_ids or []))}:{','.join(kinds or [])}"
    cached = _bm25_cache.get(key)
    if not cached or cached[0] != len(chunks):
        cached = (len(chunks), BM25([c["text"] for c in chunks]))
        _bm25_cache[key] = cached
    bm = cached[1].scores(query)
    ranks = {}
    order = np.argsort(-bm)
    for r, i in enumerate(order[:60]):
        if bm[i] > 0:
            ranks.setdefault(int(i), 0.0)
            ranks[int(i)] += 0.6 / (60 + r)          # BM25 weight
    have_vec = [i for i, c in enumerate(chunks) if c["vec"] is not None]
    if have_vec:
        try:
            qv = _norm(np.asarray((await llm.embed([query], query=True, title="Embed query"))[0], dtype=np.float32))
            mat = np.stack([chunks[i]["vec"][:DIMS] for i in have_vec])
            if mat.shape[1] == qv.shape[0]:
                sims = mat @ qv
                for r, j in enumerate(np.argsort(-sims)[:60]):
                    i = have_vec[int(j)]
                    ranks.setdefault(i, 0.0)
                    ranks[i] += 1.0 / (60 + r)        # dense weight
        except Exception as e:
            trace.error("Dense retrieval failed; using BM25 only", str(e)[:300])
    best = sorted(ranks.items(), key=lambda kv: -kv[1])[:k]
    out = []
    for i, s in best:
        c = chunks[i]
        out.append({"chunk_id": c["id"], "paper_id": c["paper_id"], "kind": c["kind"], "score": round(s, 4),
                    "text": c["text"][:1800]})
    return out
