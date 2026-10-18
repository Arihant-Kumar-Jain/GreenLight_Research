"""Run the retrieval eval on a project:
    uv run python scripts/eval_retrieval.py <project_id> [--rebuild] [--rerankers local,llm] [--styles paraphrase,hard]"""

import argparse
import asyncio
import json

from glr import evals

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--rebuild", action="store_true", help="regenerate the question sets")
ap.add_argument("--rerankers", default="", help="comma list, default: every available backend")
ap.add_argument("--styles", default="paraphrase,hard")
a = ap.parse_args()
res = asyncio.run(evals.run(a.project, [k for k in a.rerankers.split(",") if k] or None, a.rebuild,
                            tuple(s for s in a.styles.split(",") if s)))
for style, s in res["sets"].items():
    print(f"\n== {style}: {s['n_pos']} answerable + {s['n_neg']} off-topic ==")
    for r in s["rows"]:
        print(f"{r['config']:<30} {str(r['reranker'] or ''):<6} R@1 {r['recall@1']:.3f}  R@5 {r['recall@5']:.3f}  "
              f"R@10 {r['recall@10']:.3f}  MRR {r['mrr@10']:.3f}  nDCG {r['ndcg@10']:.3f}  paper@5 {r['paper_hit@5']:.3f}  "
              f"{r['latency_ms']} ms" + (f"  gate {json.dumps(r['gate'])}" if "gate" in r else ""))
