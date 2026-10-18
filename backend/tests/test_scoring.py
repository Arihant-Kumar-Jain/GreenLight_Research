"""Credibility score, quote verification and verdict guardrails (deterministic parts)."""

from glr import credibility, db
from glr.agents import verdict
from glr.verify import claims, quote_ok

STRONG = {"title": "LoRA", "published": "2021-06-17", "citations": 12000, "citation_percentile": 0.999, "fwci": 40,
          "openalex_id": "W1", "authors": [{"name": "A", "h_index": 60}, {"name": "B", "h_index": 30}],
          "venue": {"name": "ICLR", "type": "conference", "h_index": 300},
          "hf": {"github": "x", "models": 480, "datasets": 24, "spaces": 235, "upvotes": 67}}
WEAK = {"title": "Weak", "published": "2022-01-01", "citations": 2, "openalex_id": "W2",
        "authors": [{"name": "C", "h_index": 2}], "venue": {"name": "arXiv", "type": "repository"}}


def test_strong_beats_weak():
    s, w = credibility.score(STRONG), credibility.score(WEAK)
    assert s["score"] > 75 > 40 > w["score"]
    assert s["confidence"] == "high"


def test_retracted_is_zero():
    r = credibility.score({**STRONG, "is_retracted": True})
    assert r["score"] == 0 and r["tier"] == "retracted"


def test_new_paper_not_punished_for_citations():
    import datetime
    new = {**WEAK, "published": datetime.date.today().isoformat(), "authors": [{"name": "D", "h_index": 70}]}
    r = credibility.score(new)
    assert r["confidence"] == "low" and any("too new" in n for n in r["notes"])


def test_verified_flags_lower_integrity():
    flagged = {**STRONG, "audit": {"flags": [{"type": "no_baselines", "verified": True},
                                             {"type": "other", "verified": False}]}}
    assert credibility.score(flagged)["score"] < credibility.score(STRONG)["score"]


def test_quote_ok():
    text = "We propose Low-Rank Adaptation, or LoRA, which freezes the pre-trained model weights and injects trainable"
    assert quote_ok("which freezes the pre-trained model weights and injects", text)
    assert quote_ok("which freezes the pretrained model weights and injects", text)  # near-verbatim
    assert not quote_ok("which fine-tunes all model weights with a learned router", text)


def test_claims_extraction():
    cl = claims("LoRA reduces parameters by 10,000x [P1]. Nothing cited here. Adapters add latency [P2, P3].")
    assert [c["refs"] for c in cl] == [["P1"], ["P2", "P3"]]


def test_guardrail_forces_red_and_thin_evidence_amber():
    pid = db.create_project("idea")
    for i in range(12):
        db.add_paper(pid, f"k{i}", {"title": f"t{i}", "credibility": {"score": 60}})
    ruling = {"light": "green", "headline": "Go", "reasons": []}
    nov = {"already_done_by": [{"paper_id": "P1"}], "components": []}
    v = verdict.apply(pid, ruling, nov, {"confidence": "high"})
    assert v["light"] == "red" and v["speaker_light"] == "green" and v["guardrails"]
    pid2 = db.create_project("idea2")
    db.add_paper(pid2, "k", {"title": "t", "credibility": {"score": 60}})
    v2 = verdict.apply(pid2, ruling, {"already_done_by": [], "components": []}, {"confidence": "high"})
    assert v2["light"] == "amber"


def test_same_title_is_strict():
    from glr.sources.openalex import same_title
    assert same_title("LoRA: Low-Rank Adaptation of Large Language Models",
                      "LoRA: low rank adaptation of large language models.")
    assert not same_title("LoRA: Low-Rank Adaptation of Large Language Models",
                          "LoRTA: Low Rank Tensor Adaptation of Large Language Models")


def test_bracket_citations():
    from glr.agents.writer import bracket_citations
    out = bracket_citations("P7 does X (P12, P3). Already [P1]. P99 unknown.", {"P1", "P3", "P7", "P12"})
    assert out == "[P7] does X [P12, P3]. Already [P1]. P99 unknown."


def test_unknown_citations_are_not_zero():
    r = credibility.score({**WEAK, "citations": None, "openalex_id": None})
    assert r["components"][0]["score"] == 25 and r["confidence"] == "low"


def test_graph_cites_and_clusters():
    import numpy as np
    from glr import graph
    nodes = [
        {"id": "P1", "title": "Mixture of LoRA Experts for Multi Task Tuning", "arxiv_id": "2401.00001",
         "refs": [{"arxiv": "2106.09685", "text": ""}], "refs_via": "arXiv bibliography"},
        {"id": "P2", "title": "LoRA: Low-Rank Adaptation of Large Language Models", "arxiv_id": "2106.09685", "refs": []},
        {"id": "P3", "title": "Sparse experts", "refs": [{"text": "X et al. Mixture of LoRA Experts for Multi Task Tuning. 2024"}]},
    ]
    edges = graph._cite_edges(nodes)
    assert {(e["source"], e["target"]) for e in edges} == {("P1", "P2"), ("P3", "P1")}
    assign, clusters = graph._clusters(nodes, edges)
    assert len(set(assign.values())) == 1 and clusters[0]["size"] == 3


def test_calibration_and_auroc():
    from glr.evals import _auroc, _calibrate
    pos, neg = [0.9, 0.8, 0.7, 0.4], [0.1, 0.2, 0.5]
    c = _calibrate(pos, neg)
    assert c["auroc"] == _auroc(pos, neg) and 0.8 < c["auroc"] <= 1
    assert c["threshold"] == 0.7 and c["balanced_accuracy"] >= 0.8


def test_mmr_prefers_diverse():
    import numpy as np
    from glr.corpus import _mmr
    a, b = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    vecs = [a, a.copy(), b, b.copy()]  # 0/1 duplicates; 2 is different and nearly as relevant; 3 is weak
    assert _mmr([0, 1, 2, 3], [1.0, 0.99, 0.95, 0.1], vecs, 2) == [0, 2]


async def test_rerank_falls_back(monkeypatch):
    from glr import rerank

    async def boom(q, d):
        raise RuntimeError("down")

    async def ok(q, d):
        return [float(len(x)) for x in d]
    monkeypatch.setitem(rerank.BACKENDS, "nim", boom)
    monkeypatch.setitem(rerank.BACKENDS, "llm", ok)
    monkeypatch.setattr(rerank, "chain", lambda: ["nim", "llm"])
    scores, kind = await rerank.rerank("q", ["a", "bbb"])
    assert kind == "llm" and scores == [1.0, 3.0]


def test_normalise():
    from glr.rerank import normalise
    assert normalise([10, 0], "llm") == [1.0, 0.0]
    assert 0.99 < normalise([5.0], "nim")[0] < 1 and normalise([0.3], "local") == [0.3]


def test_guardrail_review_coverage_blocks_green():
    pid = db.create_project("idea3")
    for i in range(12):
        db.add_paper(pid, f"k{i}", {"title": f"t{i}", "credibility": {"score": 60}})
    nov = {"already_done_by": [], "components": [{"id": "C1", "core": True, "best": "partial", "covered_by": []},
                                                  {"id": "C2", "core": True, "best": "partial", "covered_by": []}]}
    lead = {"confidence": "high", "closest": [{"id": "P1", "relation": "very close"}],
            "coverage": [{"component": "C1", "status": "covered"}, {"component": "C2", "status": "covered"}]}
    v = verdict.apply(pid, {"light": "green", "headline": "Go", "reasons": []}, nov, lead)
    assert v["light"] == "amber" and "every core component" in v["headline"]
    lead["coverage"][1]["status"] = "open"
    assert verdict.apply(pid, {"light": "green", "headline": "Go", "reasons": []}, nov, lead)["light"] == "green"


def test_split_speaker_panel_blocks_green():
    pid = db.create_project("idea4")
    for i in range(12):
        db.add_paper(pid, f"k{i}", {"title": f"t{i}", "credibility": {"score": 60}})
    ruling = {"light": "green", "headline": "Go", "reasons": [], "votes": ["green", "green", "amber"]}
    v = verdict.apply(pid, ruling, {"already_done_by": [], "components": []}, {"confidence": "high"})
    assert v["light"] == "amber" and "split" in v["headline"]
    ruling["votes"] = ["green"] * 3
    assert verdict.apply(pid, ruling, {"already_done_by": [], "components": []}, {"confidence": "high"})["light"] == "green"


def test_table_rows_are_not_claims():
    assert claims("| [P1] Paper | 2024 | 50 | ✓ done |\nReal claim about methods here [P2].") == \
        [{"text": "Real claim about methods here [P2].", "refs": ["P2"]}]
