"""Verification: nothing an agent says about a paper is shown as fact unless the paper's own text backs it.

  quote_ok        - a claimed quote must appear in the paper text (exact after normalisation, or a near-verbatim
                    window). Used for novelty overlaps and Auditor red flags. Unverified → not counted.
  check_claims    - groundedness of the report: every sentence citing [P#] is judged against the cited papers'
                    retrieved passages by Nemotron Nano (supported / partial / unsupported). Unsupported claims are
                    marked in the report, never silently kept.
"""

import asyncio
import difflib
import re
from typing import Literal

from pydantic import BaseModel, Field

from . import corpus, db, llm, trace

CITE_RE = re.compile(r"\[(P\d+(?:\s*[,;]\s*P\d+)*)\]")


def _n(s: str) -> str:
    s = s.lower().replace("ﬁ", "fi").replace("ﬂ", "fl")
    s = re.sub(r"-\s*\n\s*", "", s)
    return re.sub(r"[^a-z0-9%.]+", " ", s).strip()


def quote_ok(quote: str, text: str) -> bool:
    q, t = _n(quote), _n(text)
    if len(q) < 12:
        return False
    if q in t:
        return True
    qw, tw = q.split(), t.split()
    n = len(qw)
    if n < 4 or len(tw) < n:
        return False
    first = {qw[0], qw[1]}
    for i in range(len(tw) - n + 1):
        if tw[i] not in first and tw[min(i + 1, len(tw) - 1)] not in first:
            continue
        window = " ".join(tw[i:i + n + 3])
        if difflib.SequenceMatcher(None, q, window[:len(q) + 12]).ratio() >= 0.88:
            return True
    return False


def paper_text(pid: str, paper_id: str) -> str:
    rows = db.q("SELECT text FROM chunks WHERE project_id=? AND paper_id=? ORDER BY id", (pid, paper_id.upper()))
    p = db.paper(pid, paper_id) or {}
    return (p.get("title") or "") + "\n" + (p.get("abstract") or "") + "\n" + "\n".join(r["text"] for r in rows)


# ---------------------------------------------------------------- report groundedness

class Judgement(BaseModel):
    n: int
    label: Literal["supported", "partial", "unsupported"]
    why: str = Field("", description="At most 15 words")


class Judgements(BaseModel):
    items: list[Judgement]


JUDGE_SYSTEM = """You check citations in a research report. For each numbered claim you get the claim and passages
from the papers it cites. Label it:
  supported   - the passages state or directly imply the claim
  partial     - the passages support part of it, or it overstates them (stronger, broader, different numbers)
  unsupported - the passages do not support it, or contradict it
Judge only against the passages, not your own knowledge. Be strict about numbers and comparisons."""


def claims(markdown: str) -> list[dict]:
    out = []
    for para in markdown.split("\n"):
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", para):
            refs = []
            for m in CITE_RE.finditer(sent):
                refs += [r.strip() for r in re.split(r"[,;]", m.group(1))]
            if refs and len(sent) > 25:
                out.append({"text": sent.strip(), "refs": list(dict.fromkeys(refs))})
    return out


async def check_claims(pid: str, markdown: str, max_claims: int = 40) -> dict:
    cl = claims(markdown)[:max_claims]
    if not cl:
        return {"claims": [], "supported": 0, "partial": 0, "unsupported": 0, "ratio": None}
    known = {p["id"] for p in db.papers(pid)}

    async def evidence(c: dict) -> str:
        parts = []
        for r in c["refs"][:3]:
            if r not in known:
                parts.append(f"[{r}] (no such paper in the corpus)")
                continue
            hits = await corpus.search(pid, c["text"], k=3, paper_ids=[r])
            parts.append("\n".join(f"[{r}] {h['text'][:700]}" for h in hits) or f"[{r}] (no text)")
        return "\n".join(parts)

    ev = await asyncio.gather(*(evidence(c) for c in cl))
    results: dict[int, Judgement] = {}
    batch = 8
    for i in range(0, len(cl), batch):
        part = list(range(i, min(i + batch, len(cl))))
        user = "\n\n".join(f"Claim {j}: {cl[j]['text']}\nPassages:\n{ev[j]}" for j in part)
        try:
            out = await llm.chat_json("fast", JUDGE_SYSTEM, user, Judgements,
                                      title=f"Citation check · claims {part[0] + 1}-{part[-1] + 1}", max_tokens=2500)
            for jd in out.items:
                if jd.n in part:
                    results[jd.n] = jd
        except Exception as e:
            trace.error("Citation check batch failed", str(e)[:300])
    rows = []
    for j, c in enumerate(cl):
        jd = results.get(j)
        bad = [r for r in c["refs"] if r not in known]
        label = "unsupported" if bad else (jd.label if jd else "unchecked")
        rows.append({**c, "label": label, "why": ("cites unknown paper " + ", ".join(bad)) if bad else (jd.why if jd else "")})
    counts = {k: sum(r["label"] == k for r in rows) for k in ("supported", "partial", "unsupported", "unchecked")}
    checked = len(rows) - counts["unchecked"]
    ratio = round((counts["supported"] + 0.5 * counts["partial"]) / checked, 3) if checked else None
    trace.log("guard", f"Citation check: {counts['supported']} supported, {counts['partial']} partial, "
                       f"{counts['unsupported']} unsupported of {len(rows)} claims",
              "\n".join(f"✗ {r['text'][:160]} — {r['why']}" for r in rows if r["label"] == "unsupported")[:3000])
    return {"claims": rows, **counts, "ratio": ratio}
