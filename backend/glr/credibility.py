"""Paper credibility score (0-100): deterministic, explainable, never an LLM's opinion.

Built from bibliometrics a researcher can check themselves:
  impact      35%  citation percentile / FWCI (field-normalised, OpenAlex), citations per year, S2 influential cites
  authors     25%  author reputation: h-index of the strongest author (and the median author)
  venue       15%  peer-reviewed venue strength (venue h-index); preprint servers score low (not reviewed)
  adoption    15%  reproducibility in the wild: released code, Hugging Face models/datasets/Spaces built on it
  integrity   10%  red flags found by the Auditor agent, each one backed by a verified quote from the paper
Hard rules: a retracted paper scores 0. Papers younger than ~18 months cannot have earned citations yet, so their
impact weight moves to authors/venue and the confidence is marked low rather than punishing them.
"""

import math
from datetime import date

WEIGHTS = {"impact": 0.35, "authors": 0.25, "venue": 0.15, "adoption": 0.15, "integrity": 0.10}


def _log(x: float | None, top: float) -> float:
    if not x or x <= 0:
        return 0.0
    return min(1.0, math.log1p(x) / math.log1p(top))


def _age_years(p: dict) -> float:
    try:
        d = date.fromisoformat((p.get("published") or "")[:10])
    except ValueError:
        d = date(int(p["year"]), 7, 1) if p.get("year") else None
    if not d:
        return 2.0
    return max(0.1, (date.today() - d).days / 365.25)


def score(p: dict) -> dict:
    age = _age_years(p)
    comps: dict[str, tuple[float, str]] = {}
    notes: list[str] = []

    # ---- impact (unknown citations are unknown, not zero)
    known = p.get("citations") is not None
    cites = p.get("citations") or 0
    cpy = cites / max(age, 1.0)
    signals = []
    if p.get("citation_percentile") is not None:
        signals.append(float(p["citation_percentile"]))
    if p.get("fwci") is not None:
        signals.append(_log(p["fwci"], 20))
    signals.append(_log(cpy, 150))
    infl = (p.get("s2") or {}).get("influential_citations")
    if infl:
        signals.append(_log(infl, 300))
    impact = sum(signals) / len(signals) if known else 0.25
    detail = f"{cites:,} citations ({cpy:.1f}/yr)" if known else "citation count unknown (not found in OpenAlex / Semantic Scholar)"
    if p.get("fwci") is not None:
        detail += f", FWCI {p['fwci']:.2f}"
    if p.get("citation_percentile") is not None:
        detail += f", {round(100 * float(p['citation_percentile']))}th percentile in field"
    if infl:
        detail += f", {infl} influential (Semantic Scholar)"
    comps["impact"] = (impact, detail)

    # ---- authors
    hs = sorted([a["h_index"] for a in p.get("authors", []) if a.get("h_index") is not None], reverse=True)
    if hs:
        med = hs[len(hs) // 2]
        auth = 0.7 * _log(hs[0], 100) + 0.3 * _log(med, 60)
        top = max((a for a in p["authors"] if a.get("h_index") is not None), key=lambda a: a["h_index"])
        comps["authors"] = (auth, f"strongest author {top.get('name')} (h-index {hs[0]}), median h {med}, "
                                  f"{len(p.get('authors', []))} author(s)")
    else:
        comps["authors"] = (0.2, "author records not found")

    # ---- venue
    v = p.get("venue") or {}
    vtype = (v.get("type") or "").lower()
    preprint = vtype == "repository" or (p.get("work_type") == "preprint" and not p.get("journal_ref"))
    if preprint:
        comps["venue"] = (0.3, f"preprint on {v.get('name') or 'arXiv'}: not peer-reviewed"
                               + (f" (journal ref: {p['journal_ref']})" if p.get("journal_ref") else ""))
    elif v.get("name"):
        vs = max(0.45, _log(v.get("h_index"), 400))
        comps["venue"] = (vs, f"{v['name']} ({vtype or 'venue'}"
                              + (f", h-index {v['h_index']}" if v.get("h_index") else "") + ")")
    else:
        comps["venue"] = (0.3, "venue unknown")

    # ---- adoption / reproducibility
    hf = p.get("hf") or {}
    adopt = 0.0
    bits = []
    if hf.get("github") or p.get("code_url"):
        adopt += 0.35
        bits.append("code released")
    if hf.get("models"):
        adopt += 0.4 * _log(hf["models"], 300)
        bits.append(f"{hf['models']} HF models")
    if hf.get("datasets") or hf.get("spaces"):
        adopt += 0.15 * _log((hf.get("datasets") or 0) + (hf.get("spaces") or 0), 200)
        bits.append(f"{hf.get('datasets') or 0} datasets, {hf.get('spaces') or 0} Spaces")
    if hf.get("upvotes"):
        adopt += 0.1 * _log(hf["upvotes"], 200)
        bits.append(f"{hf['upvotes']} HF upvotes")
    comps["adoption"] = (min(1.0, adopt), ", ".join(bits) or "no public code or downstream models found")

    # ---- integrity
    flags = [f for f in (p.get("audit") or {}).get("flags", []) if f.get("verified")]
    comps["integrity"] = (max(0.0, 1.0 - 0.34 * len(flags)),
                          f"{len(flags)} verified red flag(s)" if flags else "no verified red flags")

    weights = dict(WEIGHTS)
    too_new = age < 1.5 and cites < 50
    if too_new:  # citations can't exist yet: judge on authors + venue + adoption instead
        notes.append(f"Published {age:.1f} years ago: too new for citation counts to mean much; "
                     "impact weight moved to authors and venue.")
        moved = weights["impact"] * 0.8
        weights["impact"] -= moved
        weights["authors"] += moved * 0.6
        weights["venue"] += moved * 0.2
        weights["adoption"] += moved * 0.2

    total = sum(weights[k] * comps[k][0] for k in comps)
    value = round(100 * total)
    hard = None
    if p.get("is_retracted"):
        value, hard = 0, "RETRACTED: this paper has been retracted. Do not rely on its results."
        notes.insert(0, hard)

    has_biblio = known
    confidence = "low" if (too_new or not has_biblio) else ("high" if age >= 2 and hs else "medium")
    if not has_biblio:
        notes.append("Not verifiable in OpenAlex or Semantic Scholar: bibliometrics unavailable, score is a lower bound.")
    elif p.get("biblio_source"):
        notes.append(f"Bibliometrics from {p['biblio_source']} (OpenAlex had no record matching this title).")
    tier = ("retracted" if hard else "strong" if value >= 72 else "solid" if value >= 55
            else "mixed" if value >= 38 else "weak")
    return {
        "score": value, "tier": tier, "confidence": confidence, "retracted": bool(hard),
        "components": [{"name": k, "score": round(100 * comps[k][0]), "weight": round(weights[k], 3),
                        "detail": comps[k][1]} for k in ("impact", "authors", "venue", "adoption", "integrity")],
        "flags": flags, "notes": notes,
    }
