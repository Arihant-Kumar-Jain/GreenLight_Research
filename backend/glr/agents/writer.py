"""Report writer: the deep-research report, with every claim cited [P#] and then citation-checked.

Nemotron Super writes from the verified material only (lead synthesis, novelty matrix, audits, ruling, notebook).
verify.check_claims then judges each cited sentence against the cited papers' passages; unsupported sentences are
marked in the report rather than silently kept.
"""

import json
import re

from pydantic import BaseModel, Field

from .. import db, llm, trace, verify
from .intake import brief_text


class Report(BaseModel):
    title: str
    tldr: str = Field(description="2-3 sentences: has it been done, how novel, should they pursue it")
    markdown: str = Field(description="The full report in Markdown with inline [P#] citations")


SYSTEM = """You write the final deep-research report for a researcher. Use ONLY the material given. Cite papers inline
ALWAYS in square brackets, [P3] or [P3, P7], right after the claim they support (never bare P3 or (P3)). Never cite an id that is not in the paper list. Mention
credibility where it matters ("P4 (credibility 31/100, preprint, no code) reports…"). Do not repeat the verdict box;
explain it. Sections (Markdown ## headings):
## Has this been done?   direct answer, the closest work and exactly how the idea differs
## State of the art       what exists, grouped by approach
## Novelty by component   one bullet per component: covered / partial / open, with papers
## How credible is the closest work?   citations, authors, venue, red flags from the audits
## Open gaps & opportunities
## Recommended next steps   experiments, baselines, datasets, positioning vs the closest papers
Be concrete and honest about uncertainty. No legal or career advice."""


def bracket_citations(md: str, known: set[str]) -> str:
    """Models often write "P7" or "(P7, P12)" instead of "[P7]"; normalise so every citation is checkable."""
    md = re.sub(r"\((P\d+(?:\s*[,;]\s*P\d+)*)\)", r"[\1]", md)
    parts = re.split(r"(\[[^\]]*\])", md)  # leave existing [...] alone
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"\bP\d+\b", lambda m: f"[{m.group(0)}]" if m.group(0) in known else m.group(0), parts[i])
    return re.sub(r"\](\s*)\[(?=P\d)", ", ", "".join(parts)).replace("], [", ", ")


def _material(pid: str, brief: dict, lead: dict, novelty: dict, verdict: dict) -> str:
    ps = sorted(db.papers(pid), key=lambda p: -((p.get("credibility") or {}).get("score") or 0))
    rel = {c["id"] for c in lead.get("closest", [])} | {r["paper_id"] for r in novelty.get("papers", [])}
    lines = []
    for p in sorted(ps, key=lambda p: p["id"] not in rel)[:30]:
        c = p.get("credibility") or {}
        a = p.get("audit") or {}
        lines.append(f"[{p['id']}] {p['title']} ({p.get('year')}; {(p.get('venue') or {}).get('name') or 'n/a'}; "
                     f"{p.get('citations') or 0} citations; credibility {c.get('score', '?')}/100 {c.get('tier', '')}"
                     f"{'; RETRACTED' if p.get('is_retracted') else ''})"
                     + (f"\n   shows: {a.get('shows')}" if a.get("shows") else "")
                     + "".join(f"\n   result: {r['claim']}" for r in a.get("key_results", []) if r.get("verified"))
                     + "".join(f"\n   red flag ({f['type']}): {f['why']}" for f in a.get("flags", []) if f.get("verified"))
                     + f"\n   abstract: {(p.get('abstract') or '')[:500]}")
    notes = "\n".join(f"- {n['text']} [{', '.join(n['refs'])}]" for n in db.notes(pid)[-25:])
    return (f"BRIEF\n{brief_text(brief)}\n\nVERDICT (already decided)\n{verdict['light'].upper()}: {verdict['headline']}\n"
            f"Reasons: {json.dumps(verdict.get('reasons'), ensure_ascii=False)}\n"
            f"Differentiation: {json.dumps(verdict.get('differentiation'), ensure_ascii=False)}\n"
            f"Next steps: {json.dumps(verdict.get('next_steps'), ensure_ascii=False)}\n"
            f"Guardrails: {json.dumps(verdict.get('guardrails'), ensure_ascii=False)}\n\n"
            f"LITERATURE REVIEW\n{lead.get('synthesis')}\nGaps: {lead.get('gaps')}\n\n"
            f"NOVELTY MATRIX (verified quotes only; score {novelty.get('score')}/100)\n"
            + "\n".join(f"{c['id']}{' core' if c['core'] else ''} '{c['text']}': {c['best']} "
                        f"by {', '.join(x['paper_id'] + ':' + x['overlap'] for x in c['covered_by']) or 'none'}"
                        for c in novelty.get("components", []))
            + "\nPer-paper differences:\n" + "\n".join(f"{r['paper_id']} ({r['relation']}): {r['difference']}"
                                                       for r in novelty.get("papers", []))
            + f"\n\nNOTEBOOK\n{notes}\n\nPAPERS\n" + "\n".join(lines))


async def write(pid: str, brief: dict, lead: dict, novelty: dict, verdict: dict) -> dict:
    with trace.scope(agent="Report Writer"):
        r = await llm.chat_json("reason", SYSTEM, _material(pid, brief, lead, novelty, verdict)[:60000], Report,
                                title="Write the research report", max_tokens=7000, temperature=0.3)
        out = r.model_dump()
        known = {p["id"] for p in db.papers(pid)}
        out["markdown"] = bracket_citations(out["markdown"], known)
        out["tldr"] = bracket_citations(out["tldr"], known)
    with trace.scope(agent="Citation Checker"):
        check = await verify.check_claims(pid, out["markdown"])
    flagged = {c["text"] for c in check["claims"] if c["label"] == "unsupported"}
    md = out["markdown"]
    for s in flagged:
        md = md.replace(s, f"{s} ⚠️*[citation not supported by the cited paper]*")
    out["markdown"] = md
    out["citations"] = check
    return out
