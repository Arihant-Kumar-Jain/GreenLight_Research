"""The Research Chamber: a for/against debate on "This House would pursue <idea>", ruled by a Speaker.

  Proponent (for)  - the idea is novel enough and worth the researcher's next months
  Skeptic (against)- it has been done, is incremental, or rests on shaky prior results
Openings run in parallel, then rebuttals (answer the Point of Information, rebut, concede one point). Every argument
must cite ids from a shared evidence pack (papers with their credibility, novelty cells, notebook findings).
Arguments without valid evidence are struck; arguments resting only on low-credibility papers are flagged weak.
The Speaker (Nemotron Ultra) names the clashes and rules green / amber / red; verdict.py then applies guardrails.
"""

import asyncio
import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .. import db, llm, trace

LOW_CRED = 38


def evidence_pack(pid: str, lead: dict, novelty: dict) -> dict[str, dict]:
    pack: dict[str, dict] = {}
    papers = {p["id"]: p for p in db.papers(pid)}
    rel = {c["id"]: c for c in lead.get("closest", [])}
    ids = list(dict.fromkeys([c["id"] for c in lead.get("closest", [])] +
                             [r["paper_id"] for r in novelty.get("papers", [])]))[:14]
    for i in ids:
        p = papers.get(i)
        if not p:
            continue
        c = p.get("credibility") or {}
        r = rel.get(i, {})
        nov = next((x for x in novelty.get("papers", []) if x["paper_id"] == i), {})
        pack[i] = {"label": p["title"], "url": p.get("url"), "credibility": c.get("score"),
                   "text": f"{p['title']} ({p.get('year')}). Credibility {c.get('score', '?')}/100 ({c.get('tier', '?')}"
                           f"{', RETRACTED' if p.get('is_retracted') else ''}). Relation: {nov.get('relation') or r.get('relation', '?')}. "
                           f"{r.get('why', '')} Difference from the idea: {nov.get('difference', 'n/a')}. "
                           f"Abstract: {(p.get('abstract') or '')[:400]}"}
    for c in novelty.get("components", []):
        pack[f"N{c['id'][1:]}"] = {"label": f"Novelty of {c['id']}",
                                   "text": f"Component {c['id']}{' (core)' if c['core'] else ''} '{c['text']}': best verified "
                                           f"overlap = {c['best']}; covered by "
                                           f"{', '.join(x['paper_id'] + ' (' + x['overlap'] + ')' for x in c['covered_by']) or 'nothing found'}."}
    pack["NS"] = {"label": "Novelty score", "text": f"Novelty score {novelty.get('score')}/100. Papers covering all core "
                  f"components: {', '.join(d['paper_id'] for d in novelty.get('already_done_by', [])) or 'none'}."}
    for i, n in enumerate(db.notes(pid, "finding")[-12:], start=1):
        pack[f"F{i}"] = {"label": n["text"][:80], "text": f"{n['text']} [{', '.join(n['refs'])}]"}
    for i, g in enumerate(lead.get("gaps", [])[:6], start=1):
        pack[f"G{i}"] = {"label": f"Gap: {g[:70]}", "text": f"Open gap per the literature review: {g}"}
    return pack


def _pack_text(pack: dict) -> str:
    return "\n".join(f"[{k}] {v['text']}" for k, v in pack.items())


class Argument(BaseModel):
    claim: str
    reasoning: str = Field(description="2-3 sentences")
    evidence: list[str] = Field(description="Evidence ids, e.g. ['P3', 'N1']")


class Opening(BaseModel):
    framing: str
    arguments: list[Argument] = Field(description="Your three strongest arguments")
    point_of_information: str = Field(description="One pointed question for the other side")


class Reply(BaseModel):
    target: str
    response: str
    evidence: list[str] = Field(default_factory=list)


class Rebuttal(BaseModel):
    poi_answer: str
    responses: list[Reply]
    concession: str = Field(description="One point you honestly concede")
    closing: str


class Clash(BaseModel):
    issue: str
    winner: Literal["proponent", "skeptic", "draw"]
    why: str


class Scores(BaseModel):
    novelty: float = Field(5, description="1 = done before, 10 = clearly new")
    significance: float = Field(5, description="How much the field would care if it works")
    soundness: float = Field(5, description="How well-founded the approach is, given the evidence")
    feasibility: float = Field(5, description="How doable with typical academic resources")


class Ruling(BaseModel):
    scores: Scores = Field(default_factory=Scores, description="Review-style scores, 1-10 each")
    clashes: list[Clash] = Field(default_factory=list, description="2-4 decisive clashes")
    deciding_factor: str = ""
    light: Literal["green", "amber", "red"]
    headline: str = Field("", description="One-line verdict for the researcher")
    confidence: float = Field(0.5, description="0-1")
    reasons: list[str] = Field(default_factory=list, description="3-5 reasons citing evidence ids")
    differentiation: list[str] = Field(default_factory=list,
                                       description="How to make the idea clearly novel vs the closest work")
    next_steps: list[str] = Field(default_factory=list, description="Concrete next research steps / experiments")

    @model_validator(mode="before")
    @classmethod
    def _aliases(cls, d):
        """Nemotron Ultra sometimes names the colour 'verdict'/'ruling'/'color' or nests it; accept those."""
        if isinstance(d, dict) and d.get("light") not in ("green", "amber", "red"):
            for k in ("verdict", "ruling", "color", "colour", "decision", "rating"):
                v = str(d.get(k) or "").lower()
                hit = next((c for c in ("red", "amber", "green") if c in v), None)
                if hit:
                    d = {**d, "light": hit}
                    break
            if not d.get("headline"):
                d["headline"] = str(d.get("summary") or d.get("verdict") or "")[:300]
        return d


SIDES = {
    "proponent": ("Proponent", "FOR the motion: the researcher should pursue this idea. You are an ambitious PI who "
                               "spots genuine openings in the literature. Make the strongest honest case"),
    "skeptic": ("Skeptic", "AGAINST the motion: this has been done, is incremental, or rests on shaky results. You are "
                           "a tough area chair who has rejected many 'novel' papers that re-did prior work"),
}
RULES = """Rules of the Chamber: argue ONLY from the evidence pack and cite its ids for every argument. Never invent
papers, results or numbers; an argument without valid evidence is struck. Weigh credibility: a retracted or
low-credibility paper is weak evidence."""

SPEAKER = """You are the Speaker of the Research Chamber and the final judge of whether this research idea is worth
pursuing as novel work. Weigh arguments by evidence quality (struck arguments carry nothing; low-credibility support
is weak). Name the 2-4 decisive clashes, the deciding factor, then rule:
  green = clearly novel: core components are open, the closest work leaves a real gap, worth pursuing now.
  amber = partially done or crowded: worth pursuing only with sharper differentiation, or evidence is thin.
  red   = already done (credible prior work covers the core idea), or not worth pursuing as stated.
A researcher who gets a false green wastes months. Give concrete differentiation and next steps.
Also score it like a peer reviewer, 1-10 each: novelty, significance, soundness, feasibility."""


LENS_NAMES = ("overall", "strict novelty", "significance")
LENSES = ("",
          "\nYour lens: STRICT NOVELTY. Ask only whether the core contribution already exists in credible prior work.",
          "\nYour lens: SIGNIFICANCE AND FEASIBILITY. Ask whether pursuing it would produce a result the field values, "
          "given what exists.")
FORMAT_RULE = ("\nOutput rule: the field `light` MUST be exactly one of \"green\", \"amber\", \"red\". "
               "Use exactly the schema's field names.")


def _check(args: list[dict], pack: dict) -> None:
    for a in args:
        a["evidence"] = [e.strip("[] ").upper() if e.strip("[] ").upper() in pack else e.strip("[] ")
                         for e in a.get("evidence", [])]
        a["evidence"] = [e for e in a["evidence"] if e in pack]
        a["struck"] = not a["evidence"]
        creds = [pack[e].get("credibility") for e in a["evidence"] if pack[e].get("credibility") is not None]
        a["weak"] = bool(creds) and max(creds) < LOW_CRED and all(e.startswith("P") for e in a["evidence"])


def _transcript(d: dict) -> str:
    out = []
    for side in SIDES:
        name = SIDES[side][0]
        o = d[side].get("opening")
        if o:
            out.append(f"== {name} opening ==\n{o['framing']}")
            for i, a in enumerate(o["arguments"], 1):
                tag = " [STRUCK]" if a["struck"] else (" [WEAK EVIDENCE]" if a.get("weak") else "")
                out.append(f"{name} {i}{tag}: {a['claim']} — {a['reasoning']} ({', '.join(a['evidence'])})")
            out.append(f"{name} POI: {o['point_of_information']}")
    for side in SIDES:
        name = SIDES[side][0]
        r = d[side].get("rebuttal")
        if r:
            out.append(f"== {name} rebuttal ==\nPOI answer: {r['poi_answer']}")
            out += [f"On '{x['target']}': {x['response']} ({', '.join(x['evidence'])})" for x in r["responses"]]
            out.append(f"{name} concedes: {r['concession']}\n{name} closing: {r['closing']}")
    return "\n".join(out)


async def hold(pid: str, motion: str, pack: dict, on_update=None) -> dict:
    pack_txt = _pack_text(pack)
    d = {"motion": motion, "status": "opening", "proponent": {}, "skeptic": {},
         "evidence": {k: {"label": v["label"], "url": v.get("url"), "credibility": v.get("credibility")}
                      for k, v in pack.items()}}

    async def opening(side):
        name, stance = SIDES[side]
        with trace.scope(agent=name):
            o = await llm.chat_json("reason", f"You are the {name} in the Research Chamber, arguing {stance}.\n{RULES}",
                                    f"Motion: {motion}\n\nEvidence pack:\n{pack_txt}", Opening,
                                    title=f"{name}: opening speech", max_tokens=3000)
            x = o.model_dump()
            _check(x["arguments"], pack)
            return x

    async def rebuttal(side, own, other):
        name, stance = SIDES[side]
        with trace.scope(agent=name):
            r = await llm.chat_json("reason", f"You are the {name} in the Research Chamber, arguing {stance}. Rebuttal "
                                              f"round.\n{RULES}\nConcede one point honestly.",
                                    f"Motion: {motion}\n\nEvidence pack:\n{pack_txt}\n\nYour opening:\n"
                                    f"{json.dumps(own, ensure_ascii=False)}\n\nOther side's opening:\n"
                                    f"{json.dumps(other, ensure_ascii=False)}\n\nPOI put to you: {other['point_of_information']}",
                                    Rebuttal, title=f"{name}: rebuttal", max_tokens=3000)
            x = r.model_dump()
            for y in x["responses"]:
                y["evidence"] = [e.strip("[] ").upper() for e in y.get("evidence", []) if e.strip("[] ").upper() in pack]
            return x

    with trace.scope(agent="Chamber"):
        trace.info("The Research Chamber is in session", f"{motion}\nEvidence pack: {len(pack)} items")
    pro, sk = await asyncio.gather(opening("proponent"), opening("skeptic"))
    d["proponent"]["opening"], d["skeptic"]["opening"] = pro, sk
    d["status"] = "rebuttal"
    if on_update:
        on_update(d)
    pr, sr = await asyncio.gather(rebuttal("proponent", pro, sk), rebuttal("skeptic", sk, pro))
    d["proponent"]["rebuttal"], d["skeptic"]["rebuttal"] = pr, sr
    d["struck"] = sum(a["struck"] for s in SIDES for a in d[s]["opening"]["arguments"])
    d["weak"] = sum(a.get("weak", False) for s in SIDES for a in d[s]["opening"]["arguments"])
    d["status"] = "adjudication"
    if on_update:
        on_update(d)
    user = f"Motion: {motion}\n\nEvidence pack:\n{pack_txt}\n\nDebate transcript:\n{_transcript(d)}"

    async def one(i: int):
        with trace.scope(agent=f"Speaker {i + 1}"):
            # diversity from the judging lens, not from sampling: at higher temperature Ultra drops the schema
            return await llm.chat_json("judge", SPEAKER + LENSES[i] + FORMAT_RULE, user, Ruling,
                                       title=f"Speaker {i + 1}/3 ({LENS_NAMES[i]}): adjudicate and rule",
                                       max_tokens=6000, temperature=0.0)
    results = await asyncio.gather(*(one(i) for i in range(3)), return_exceptions=True)
    for i, x in enumerate(results):
        if isinstance(x, BaseException):
            with trace.scope(agent=f"Speaker {i + 1}"):
                trace.error(f"Speaker {i + 1} gave no valid ruling; panel continues without it", str(x)[:300])
    rulings = [x.model_dump() for x in results if not isinstance(x, BaseException)]
    if not rulings:
        raise RuntimeError("All Speakers failed")
    votes = [x["light"] for x in rulings]
    order = {"green": 0, "amber": 1, "red": 2}
    # majority; with three different votes take the middle one (amber)
    majority = max(set(votes), key=lambda c: (votes.count(c), -abs(order[c] - 1)))
    r = next(x for x in rulings if x["light"] == majority)
    r["votes"] = votes
    # review-style scores: mean over the panel (each Speaker scores independently)
    r["scores"] = {k: round(sum(min(10.0, max(1.0, float((x.get("scores") or {}).get(k, 5)))) for x in rulings)
                            / len(rulings), 1)
                   for k in ("novelty", "significance", "soundness", "feasibility")}
    r["confidence"] = round(r.get("confidence", 0.5) * votes.count(majority) / len(votes), 3)
    with trace.scope(agent="Speaker"):
        trace.info(f"Speaker panel {votes.count(majority)}/{len(votes)} {majority.upper()} (votes: {', '.join(votes)}): "
                   f"{r['headline']}", r["deciding_factor"])
    d["ruling"] = r
    d["status"] = "done"
    return d
