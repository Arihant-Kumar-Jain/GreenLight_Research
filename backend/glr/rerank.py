"""Reranking: a cross-encoder reads (query, passage) together and scores relevance far better than vector similarity.

Backends, tried in this order (first available wins; GLR_RERANKER forces one):
  nim       NVIDIA NeMo Retriever reranking NIM (llama-nemotron rerank), hosted API catalog with NVIDIA_API_KEY or a
            self-hosted NIM at GLR_NIM_RERANK_URL. Body {model, query:{text}, passages:[{text}]} → rankings[{index, logit}]
  endpoint  any /rerank server in the Jina/Cohere format (vLLM serves Qwen3-Reranker-8B or bge-reranker this way, e.g.
            on our own RTX PRO 6000): GLR_RERANK_URL (+ GLR_RERANK_MODEL, GLR_RERANK_KEY)
  local     sentence-transformers CrossEncoder (`--extra local`). Device-aware default, chosen by measurement: on CUDA
            BAAI/bge-reranker-v2-m3 (568M, multilingual SOTA); on Apple MPS / CPU cross-encoder/ms-marco-MiniLM-L-12-v2,
            because bge-v2-m3 took 13-17 s per 40 real passages on an M-series Mac vs 1.5 s for MiniLM-L-12.
            "local:<model>" picks a specific model (the eval compares them).
  llm       Nemotron Nano grades passages 0-10 in one listwise call (always available; slowest, noisiest)
Scores are on each backend's own scale (logits vs probabilities vs grades), so the "enough evidence" cutoff is
calibrated per backend by the retrieval eval (data/eval/calibration.json) and never shared across backends.
"""

import asyncio
import json
import time
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from . import llm, trace
from .config import DATA_DIR, settings

CALIBRATION = DATA_DIR / "eval" / "calibration.json"
_local_models: dict[str, object] = {}
_local_lock = asyncio.Lock()
HEAVY_LOCAL = "BAAI/bge-reranker-v2-m3"
LIGHT_LOCAL = "cross-encoder/ms-marco-MiniLM-L-12-v2"
_failed: dict[str, float] = {}   # backend -> time it failed (skip it for a while)


def _ok(kind: str) -> bool:
    return time.time() - _failed.get(kind, 0) > 300


def available() -> list[str]:
    out = []
    if settings.nvidia_api_key or settings.nim_rerank_url:
        out.append("nim")
    if settings.rerank_url:
        out.append("endpoint")
    if _has_local():
        out.append("local")
    out.append("llm")
    return out


@lru_cache(maxsize=1)
def _has_local() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def chain() -> list[str]:
    forced = settings.reranker.lower()
    if forced == "none":
        return []
    av = [k for k in available() if _ok(k)]
    if forced and forced in available():
        return [forced] + [k for k in av if k != forced]
    return av


# ---------------------------------------------------------------- backends

async def _nim(query: str, docs: list[str]) -> list[float]:
    url = settings.nim_rerank_url or settings.nim_rerank_hosted_url
    headers = {"Authorization": f"Bearer {settings.nvidia_api_key}"} if settings.nvidia_api_key else {}
    from .sources.http import client
    r = await client().post(url, headers=headers, json={
        "model": settings.nim_rerank_model, "query": {"text": query[:2000]},
        "passages": [{"text": d[:4000]} for d in docs], "truncate": "END"})
    r.raise_for_status()
    scores = [0.0] * len(docs)
    for item in r.json().get("rankings", []):
        scores[item["index"]] = float(item["logit"])
    return scores


async def _endpoint(query: str, docs: list[str]) -> list[float]:
    from .sources.http import client
    headers = {"Authorization": f"Bearer {settings.rerank_key}"} if settings.rerank_key else {}
    r = await client().post(settings.rerank_url, headers=headers, json={
        "model": settings.rerank_model, "query": query[:2000], "documents": [d[:4000] for d in docs],
        "top_n": len(docs)})
    r.raise_for_status()
    scores = [0.0] * len(docs)
    for item in r.json().get("results", []):
        scores[item["index"]] = float(item.get("relevance_score", item.get("score", 0.0)))
    return scores


def _device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def default_local_model() -> str:
    if settings.rerank_local_model:
        return settings.rerank_local_model
    try:
        import torch
        return HEAVY_LOCAL if torch.cuda.is_available() else LIGHT_LOCAL
    except Exception:
        return LIGHT_LOCAL


async def _local(query: str, docs: list[str], model_name: str | None = None) -> list[float]:
    name = model_name or default_local_model()
    async with _local_lock:  # one forward pass at a time (GPU memory, and MPS dislikes concurrency)
        if name not in _local_models:
            def load():
                from sentence_transformers import CrossEncoder
                return CrossEncoder(name, max_length=512, device=_device())
            t0 = time.perf_counter()
            _local_models[name] = await asyncio.to_thread(load)
            trace.info(f"Loaded local reranker {name} on {_device()}", f"{time.perf_counter() - t0:.1f}s")
        model = _local_models[name]
        scores = await asyncio.to_thread(lambda: model.predict([(query, d[:2500]) for d in docs], batch_size=16,
                                                               show_progress_bar=False))
    return [float(s) for s in scores]


class Grade(BaseModel):
    i: int
    score: int = Field(ge=0, le=10)


class Grades(BaseModel):
    grades: list[Grade]


LLM_SYSTEM = """Grade how well each passage answers or directly supports the query, 0-10:
10 = directly answers it; 6-8 = clearly relevant evidence; 3-5 = same topic, not the answer; 0-2 = unrelated.
Grade every passage. Be strict and consistent."""


async def _llm(query: str, docs: list[str]) -> list[float]:
    scores = [0.0] * len(docs)
    for s in range(0, len(docs), 20):
        part = docs[s:s + 20]
        user = f"Query: {query}\n\n" + "\n\n".join(f"[{s + i}] {d[:900]}" for i, d in enumerate(part))
        out = await llm.chat_json("fast", LLM_SYSTEM, user, Grades, title=f"Rerank {len(part)} passages (Nemotron)",
                                  max_tokens=1200, temperature=0.0)
        for g in out.grades:
            if 0 <= g.i < len(docs):
                scores[g.i] = float(g.score)
    return scores


BACKENDS = {"nim": _nim, "endpoint": _endpoint, "local": _local, "llm": _llm}


# ---------------------------------------------------------------- public API

def _resolve(kind: str) -> tuple[str, str]:
    """'local' → ('local', 'local:<default model>'); 'local:<m>' → ('local', 'local:<m>'); others unchanged."""
    if kind == "local":
        return "local", f"local:{default_local_model()}"
    if kind.startswith("local:"):
        return "local", kind
    return kind, kind


async def rerank(query: str, docs: list[str], *, prefer: str | None = None) -> tuple[list[float], str]:
    """Scores for each doc (higher = more relevant) and the backend that produced them ("none" if all failed).
    Local backends report "local:<model>", so gates and evals never mix two models' score scales."""
    if not docs:
        return [], "none"
    order = chain()
    if prefer and (prefer in BACKENDS or prefer.startswith("local:")):
        order = [prefer] + [k for k in order if k != prefer]
    for kind in order:
        base, label = _resolve(kind)
        t0 = time.perf_counter()
        try:
            if base == "local":
                scores = await _local(query, docs, label.split(":", 1)[1])
            else:
                scores = await BACKENDS[base](query, docs)
        except Exception as e:
            _failed[base] = time.time()
            trace.error(f"Reranker '{label}' failed, falling back", str(e)[:300])
            continue
        trace.log("rerank", f"Rerank {len(docs)} passages ({label})", query[:300],
                  latency_ms=int((time.perf_counter() - t0) * 1000))
        return scores, label
    return [0.0] * len(docs), "none"


def normalise(scores: list[float], kind: str) -> list[float]:
    """Map a backend's scores to 0..1 for display and triage (not for gating: gates use calibrated raw scores)."""
    import math
    if kind == "llm":
        return [max(0.0, min(1.0, x / 10)) for x in scores]
    if kind == "nim" or any(x < 0 or x > 1 for x in scores):  # logits
        return [1 / (1 + math.exp(-x)) for x in scores]
    return [max(0.0, min(1.0, x)) for x in scores]


def calibration() -> dict:
    try:
        return json.loads(Path(CALIBRATION).read_text())
    except Exception:
        return {}


def threshold(kind: str) -> float | None:
    """The 'enough evidence' cutoff measured for this backend, or None if it was never calibrated (then: no gate)."""
    return (calibration().get(kind) or {}).get("threshold")
