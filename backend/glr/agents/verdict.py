"""Verdict guardrails: the colour is the Speaker's call, bounded by rules computed from verified evidence.

  - A credible paper (credibility >= 35) with verified FULL overlap on every core component → forced RED
    ("already done"). Low-credibility or retracted "same idea" papers can't force red; they cap at amber.
  - Any core component fully covered by credible verified prior work → capped at AMBER.
  - Thin evidence (few papers found, or the review's confidence is low) → capped at AMBER: never a green on a
    search that could have missed the prior work.
  - A split Speaker panel (3 independent rulings) can't produce GREEN: green needs a unanimous panel.
  - The Lead Researcher's own coverage map says every core component is already covered and it found "same idea" /
    "very close" papers → at least AMBER. (A Nebius run went GREEN because the novelty matrix's strict judge
    downgraded every overlap while the review itself said the core was covered.)
"""

from .. import db, trace

ORDER = {"green": 0, "amber": 1, "red": 2}
CREDIBLE = 35


def apply(pid: str, ruling: dict, novelty: dict, lead: dict) -> dict:
    light = ruling["light"]
    guards = []
    papers = {p["id"]: p for p in db.papers(pid)}

    def cred(i: str) -> int:
        return ((papers.get(i) or {}).get("credibility") or {}).get("score") or 0

    def at_least(level: str, why: str) -> None:
        """Move the light to `level` if it is currently less severe (a green can never survive a failed rule)."""
        nonlocal light
        if ORDER[level] > ORDER[light]:
            guards.append({"to": level, "from": light, "why": why})
            light = level

    done = novelty.get("already_done_by", [])
    strong = [d for d in done if cred(d["paper_id"]) >= CREDIBLE and not papers.get(d["paper_id"], {}).get("is_retracted")]
    if strong:
        ids = ", ".join(d["paper_id"] for d in strong)
        at_least("red", f"Already done: {ids} covers every core component (verified quotes, credibility ≥ {CREDIBLE}).")
    elif done:
        at_least("amber", f"{', '.join(d['paper_id'] for d in done)} appears to cover the core idea but has low "
                        "credibility; treat as a serious risk until checked.")
    for c in novelty.get("components", []):
        if c["core"] and c["best"] == "full" and any(cred(x["paper_id"]) >= CREDIBLE for x in c["covered_by"]
                                                     if x["overlap"] == "full"):
            at_least("amber", f"Core component {c['id']} ('{c['text'][:80]}') is already done by credible prior work.")
            break
    votes = ruling.get("votes") or []
    if light == "green" and votes and votes.count("green") < len(votes):
        at_least("amber", f"The Speaker panel was split ({', '.join(votes)}): a green needs a unanimous panel.")
    core = [c["id"] for c in novelty.get("components", []) if c.get("core")] or \
        [c["id"] for c in novelty.get("components", [])]
    cov = {c["component"]: c["status"] for c in lead.get("coverage", [])}
    close = [c["id"] for c in lead.get("closest", []) if c.get("relation") in ("same idea", "very close")]
    if core and close and all(cov.get(i) == "covered" for i in core):
        at_least("amber", f"The literature review found every core component already covered; closest work: "
                          f"{', '.join(close[:4])}. Novelty would rest on the combination or setting only.")
    n = len(papers)
    if n < 10 or lead.get("confidence") == "low":
        at_least("amber", f"Evidence is thin ({n} papers, review confidence {lead.get('confidence')}): "
                        "a green needs a search that could not have missed the prior work.")
    out = {**ruling, "light": light, "speaker_light": ruling["light"], "speaker_headline": ruling["headline"],
           "guardrails": guards}
    if guards:
        out["headline"] = guards[-1]["why"] if light != ruling["light"] else ruling["headline"]
        trace.log("guard", f"Guardrail: {ruling['light'].upper()} → {light.upper()}", "\n".join(g["why"] for g in guards))
    return out
