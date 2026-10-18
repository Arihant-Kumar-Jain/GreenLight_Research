"""Retrieval eval: measures what every stage of the pipeline buys, per reranker, and calibrates the evidence gate.

Test set (synthetic, built from the project's own corpus and labelled as such):
  positives - Nemotron Nano writes one researcher question per sampled passage, paraphrased (it may not copy more
              than 3 consecutive words), so keyword overlap alone cannot pass; the source passage is the gold chunk
  negatives - research questions from unrelated fields, which the corpus cannot answer; the gate should reject them
Metrics: chunk-level recall@1/5/10, MRR@10, nDCG@10, paper-level hit@5, mean/p95 latency; for each reranker the
top-score separation of positives vs negatives (AUROC) and the threshold maximising balanced accuracy → saved to
data/eval/calibration.json, which corpus.retrieve uses as the "enough evidence" gate for that reranker.
Nothing here is invented: results only exist after a run, with the set and model ids saved next to them.
"""

import asyncio
import json
import math
import random
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from . import corpus, db, llm, rerank, trace
from .config import DATA_DIR

EVAL_DIR = DATA_DIR / "eval"
CONFIGS = {
    "BM25": dict(use_dense=False, use_rerank=False, use_mmr=False, expand_query=False),
    "Dense (Qwen3-8B)": dict(use_bm25=False, use_rerank=False, use_mmr=False, expand_query=False),
    "Hybrid RRF": dict(use_rerank=False, use_mmr=False, expand_query=False),
    "Hybrid + expansion": dict(use_rerank=False, use_mmr=False, expand_query=True),
    "Hybrid + rerank": dict(use_mmr=False, expand_query=False),
    "Hybrid + expansion + rerank": dict(use_mmr=False, expand_query=True),
    "Full (+ MMR)": dict(expand_query=True),
}
RERANKED = {"Hybrid + rerank", "Hybrid + expansion + rerank", "Full (+ MMR)"}


class Q(BaseModel):
    question: str


class Negs(BaseModel):
    questions: list[str] = Field(description="Research questions from unrelated fields")


Q_HARD = """Write ONE question that a researcher who has NOT seen this passage would ask, whose answer is in it.
Rules: describe the idea in your own everyday words — do NOT use the passage's technical terms, method names, acronyms
or distinctive words (at most one shared content word); no "this paper"; one sentence. This tests semantic search."""

Q_SYSTEM = """Write ONE specific question a researcher might ask that the passage answers. Rules: it must be answerable
from this passage; paraphrase — never copy more than 3 consecutive words from the passage; no "this paper"/"the
authors" references; one sentence."""


async def build_set(pid: str, n_pos: int = 40, n_neg: int = 12, seed: int = 7, style: str = "paraphrase") -> dict:
    rng = random.Random(seed)
    chunks = [c for c in db.chunks(pid) if len(c["text"]) > 300]
    rng.shuffle(chunks)
    per_paper: dict[str, int] = {}
    picked = []
    for c in sorted(chunks, key=lambda c: c["kind"] != "fulltext"):  # full-text passages first, then abstracts
        if per_paper.get(c["paper_id"], 0) < 2:
            per_paper[c["paper_id"]] = per_paper.get(c["paper_id"], 0) + 1
            picked.append(c)
        if len(picked) >= n_pos:
            break
    sem = asyncio.Semaphore(6)

    async def gen(c):
        async with sem:
            try:
                q = await llm.chat_json("fast", Q_HARD if style == "hard" else Q_SYSTEM, c["text"][:2500], Q,
                                        title=f"Eval: write a {style} question",
                                        max_tokens=200, temperature=0.4)
                return {"question": q.question, "gold": c["id"], "paper": c["paper_id"], "kind": c["kind"]}
            except Exception:
                return None
    pos = [x for x in await asyncio.gather(*(gen(c) for c in picked)) if x]
    titles = "; ".join(p["title"] for p in db.papers(pid)[:25])
    negs = await llm.chat_json("fast", "Write research questions from fields completely unrelated to the given paper "
                               "collection (e.g. biology, economics, astronomy, materials). Specific, one sentence each.",
                               f"Paper collection: {titles}\nWrite {n_neg} questions.", Negs,
                               title="Eval: off-topic questions", max_tokens=1200, temperature=0.7)
    data = {"project": pid, "created": datetime.now(timezone.utc).isoformat(), "synthetic": True, "style": style,
            "positives": pos, "negatives": negs.questions[:n_neg]}
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / f"retrieval_set_{pid}_{style}.json").write_text(json.dumps(data, indent=1))
    return data


def _auroc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def _calibrate(pos: list[float], neg: list[float]) -> dict:
    best = (0.0, None)
    for t in sorted(set(pos + neg)):
        tpr = sum(p >= t for p in pos) / len(pos)
        tnr = sum(n < t for n in neg) / len(neg)
        bal = (tpr + tnr) / 2
        if bal > best[0]:
            best = (bal, t)
    t = best[1]
    return {"threshold": t, "balanced_accuracy": round(best[0], 3), "auroc": _auroc(pos, neg),
            "pass_rate_answerable": round(sum(p >= t for p in pos) / len(pos), 3) if t is not None else None,
            "reject_rate_offtopic": round(sum(n < t for n in neg) / len(neg), 3) if t is not None else None}


async def run(pid: str, rerankers: list[str] | None = None, rebuild: bool = False,
              styles: tuple[str, ...] = ("paraphrase", "hard")) -> dict:
    """Run every style's set; the 'hard' set (vocabulary mismatch) also calibrates the gate when present."""
    from .config import settings
    out = {}
    deadline = settings.expansion_deadline_s
    settings.expansion_deadline_s = 120.0  # measure what expansion buys, not whether it beat the agents' deadline
    try:
        for style in styles:
            out[style] = await _run_set(pid, rerankers, rebuild, style)
    finally:
        settings.expansion_deadline_s = deadline
    result = {"project": pid, "date": datetime.now(timezone.utc).isoformat(), "sets": out}
    (EVAL_DIR / "retrieval_results.json").write_text(json.dumps(result, indent=1))
    return result


async def _run_set(pid: str, rerankers: list[str] | None, rebuild: bool, style: str) -> dict:
    with trace.scope(project_id=pid, agent="Retrieval Eval"):
        path = EVAL_DIR / f"retrieval_set_{pid}_{style}.json"
        legacy = EVAL_DIR / f"retrieval_set_{pid}.json"
        if style == "paraphrase" and legacy.exists() and not path.exists():
            legacy.rename(path)
        data = json.loads(path.read_text()) if path.exists() and not rebuild else await build_set(pid, style=style)
        pos, neg = data["positives"], data["negatives"]
        kinds = rerankers or ([k for k in rerank.available() if k not in ("llm", "local")]
                              + ([f"local:{rerank.LIGHT_LOCAL}", f"local:{rerank.HEAVY_LOCAL}"]
                                 if "local" in rerank.available() else []) + ["llm"])
        trace.info(f"Retrieval eval: {len(pos)} answerable + {len(neg)} off-topic questions, rerankers {kinds}")
        rows = []
        calib_all = rerank.calibration()
        for name, cfg in CONFIGS.items():
            for kind in (kinds if name in RERANKED else [None]):
                if kind == f"local:{rerank.HEAVY_LOCAL}" and name != "Hybrid + rerank" and not _cuda():
                    continue  # 15 s per query on a laptop GPU; measured once, on the plain rerank config
                lat, rr, ndcg, hits, phit = [], [], [], {1: 0, 5: 0, 10: 0}, 0
                pos_scores, neg_scores = [], []
                # sequential (honest latency), except the slow LLM reranker which runs 6-way parallel
                par = 6 if kind == "llm" else 1
                sem = asyncio.Semaphore(par)

                async def one(question: str):
                    async with sem:
                        t0 = time.perf_counter()
                        r = await corpus.retrieve(pid, question, 10, neighbours=False, reranker=kind, **cfg)
                        return r, (time.perf_counter() - t0) * 1000
                for q, (r, ms) in zip(pos, await asyncio.gather(*(one(q["question"]) for q in pos))):
                    lat.append(ms)
                    ids = [h["chunk_id"] for h in r["hits"]]
                    rank = ids.index(q["gold"]) + 1 if q["gold"] in ids else None
                    for k in hits:
                        hits[k] += bool(rank and rank <= k)
                    rr.append(1 / rank if rank else 0)
                    ndcg.append(1 / math.log2(rank + 1) if rank else 0)
                    phit += q["paper"] in [h["paper_id"] for h in r["hits"][:5]]
                    if r["top_score"] is not None:
                        pos_scores.append(r["top_score"])
                if kind and name == "Hybrid + rerank":
                    for r, _ in await asyncio.gather(*(one(nq) for nq in neg)):
                        if r["top_score"] is not None:
                            neg_scores.append(r["top_score"])
                n = len(pos)
                row = {"config": name, "reranker": kind, "recall@1": round(hits[1] / n, 3), "recall@5": round(hits[5] / n, 3),
                       "recall@10": round(hits[10] / n, 3), "mrr@10": round(sum(rr) / n, 3), "ndcg@10": round(sum(ndcg) / n, 3),
                       "paper_hit@5": round(phit / n, 3), "latency_ms": round(sum(lat) / n),
                       "p95_ms": round(sorted(lat)[int(0.95 * (n - 1))]), "concurrency": par}
                if neg_scores and pos_scores:
                    cal = _calibrate(pos_scores, neg_scores)
                    row["gate"] = cal
                    calib_all[kind] = {**cal, "set": style, "measured_on": pid, "n_pos": len(pos_scores), "n_neg": len(neg_scores),
                                       "model": _model_of(kind), "date": datetime.now(timezone.utc).date().isoformat()}
                rows.append(row)
                trace.info(f"Eval [{style}] {name}{' / ' + kind if kind else ''}: R@5 {row['recall@5']}, MRR {row['mrr@10']}, "
                           f"{row['latency_ms']} ms" + (f", gate AUROC {row['gate']['auroc']}" if 'gate' in row else ""))
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        (EVAL_DIR / "calibration.json").write_text(json.dumps(calib_all, indent=1))
        roles = await llm.resolve_models()
        return {"style": style, "n_pos": len(pos), "n_neg": len(neg), "synthetic": True,
                "embed_model": roles.get("embed"), "expansion_model": roles.get("fast"),
                "rerankers": {k: _model_of(k) for k in kinds}, "rows": rows,
                "examples": [q["question"] for q in pos[:5]] + neg[:3]}


def _cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def _model_of(kind: str) -> str:
    from .config import settings
    if kind.startswith("local:"):
        return kind.split(":", 1)[1]
    return {"nim": settings.nim_rerank_model, "endpoint": settings.rerank_model, "local": rerank.default_local_model(),
            "llm": "Nemotron Nano (listwise grading)"}.get(kind, kind)


def results() -> dict:
    p = EVAL_DIR / "retrieval_results.json"
    return {"retrieval": json.loads(p.read_text()) if p.exists() else None, "calibration": rerank.calibration()}
