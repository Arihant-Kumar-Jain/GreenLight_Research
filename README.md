# GreenLight Research

**Has your research idea already been done?** Describe it. A swarm of open-model agents reads the literature, scores
every paper's credibility, maps your idea against the closest work component by component, debates it in a
parliamentary-style Chamber, and rules **green / amber / red**, with citations and paper links. Then keep talking to
it: the research chat remembers everything and keeps searching.

Built for the NVIDIA × Nebius hackathon (Apps & Agentic AI). Sibling of [GreenLight](../GreenLight) (startup ideas);
this one is for research ideas. Open models only: **NVIDIA Nemotron 3 Nano / Super / Ultra** and **Qwen3-Embedding-8B**
on **Nebius Token Factory** (OpenRouter as a stand-in), **Tavily** for the live web, plus arXiv, OpenAlex, Hugging Face
Papers and Semantic Scholar.

```
                       ┌──────────── Intake chat (to-and-fro, Nemotron Super) ────────────┐
 researcher ─ redact ─▶│ rough idea → testable brief: question, method, contributions       │
                       └───────────────────────────────┬──────────────────────────────────┘
                                                       ▼
 Planner ── idea → 2-5 testable components + 3-5 search angles
    ▼
 Lead Researcher (Super, harness agent) ──dispatch_scouts──▶ Scout 1 ∥ Scout 2 ∥ Scout 3 …   (own loop + context each)
    │   ▲ compressed scout reports only                       arXiv · OpenAlex · HF Papers · Tavily · citation graph
    │   └── Critic (Nano) rejects thin coverage → round 2 (targeted scouts)          full-text reading · shared notebook
    ▼
 Reader (full texts of the closest papers) → Credibility Scorer (OpenAlex + HF + S2 → deterministic 0-100)
    ▼                                        → Auditor (red flags, quote-verified)
 Novelty Mapper: components × closest papers, every overlap must quote the paper (verified) → novelty score
    ▼
 Research Chamber: Proponent ∥ Skeptic (openings, rebuttals, evidence ids, struck/weak args) → Speaker (Ultra)
    ▼
 Guardrails (code): credible paper doing all core components → RED · core component done → ≥AMBER · thin search → ≥AMBER
    ▼
 Report Writer → Citation Checker (each [P#] sentence judged against the cited paper's passages)
    ▼
 Research Chat (Super + full toolbox + 3-layer memory) — ask, challenge, pivot, search more
```

## What makes it agentic (the harness)

No agent framework. `backend/glr/harness/` is a hand-written runtime every agent runs on:

| | |
|---|---|
| **Tools from signatures** | `@tool` turns a typed Python function into an OpenAI tool schema; args validated by pydantic; tools never raise (errors go back to the model) |
| **Parallel tool calls** | all tool calls in one model turn run concurrently (`asyncio.gather`) |
| **Sub-agent swarms** | `swarm()` runs agents concurrently with a limit; one failing never sinks the others; the Lead spawns scouts *through a tool* |
| **Budgets** | USD / LLM calls / tool calls / wall clock, shared parent→child: a swarm can never outspend its run (`GLR_MAX_USD_PER_RUN`) |
| **Loop detection** | identical `(tool, args)` returns a synthetic "already done" instead of re-running |
| **Guards** | `before_tool` veto hook; finish only via a typed terminal tool; `review` hook = reflection gate (the Critic) |
| **Forced finish** | at the step cap or budget limit only the finish tool is offered; last resort: JSON extraction from the transcript |
| **Context engine** | tier 1 elides old tool results to per-tool digests (pairing intact), tier 2 folds whole turn groups into a Nano-written working memory, tier 3 pins task + memory + shared notebook in the system prompt. Every compression is traced with before/after tokens |
| **Cross-agent compression** | the Lead sees only scouts' structured reports, never their raw search results |
| **Shared blackboard** | `note` writes findings to a project notebook pinned into every agent's prompt |
| **Trace** | every LLM call (provider, model, tokens, latency, cost), tool call, API call, spawn, compression and guardrail → live agent graph in the UI |

## Credibility score (0–100, deterministic)

`backend/glr/credibility.py` — never an LLM opinion; every component shows its evidence in the UI.

| Component | Weight | From |
|---|---|---|
| Impact | 35% | OpenAlex citation percentile + FWCI (field-normalised), citations/year, S2 influential citations |
| Authors | 25% | h-index of the strongest author (+ median author) |
| Venue | 15% | peer-reviewed venue h-index; preprints score low (not reviewed) |
| Adoption | 15% | released code, Hugging Face models / datasets / Spaces built on it, HF upvotes |
| Integrity | 10% | Auditor red flags (weak baselines, tiny samples, over-claiming…) **only if the quote is verified in the paper** |

Retracted → 0. Papers < 18 months old get their impact weight moved to authors/venue (confidence "low") instead of
being punished for missing citations. Identity is verified: OpenAlex records are accepted only if the title matches
(OpenAlex maps LoRA's DOI to an unrelated paper; we refuse it and fall back to Semantic Scholar).

## Invariants (the pitch)

1. **Redact before anything leaves the machine** (`privacy.py`, ported from GreenLight): ideas, chat messages and every
   search query.
2. **Claims about papers need the paper's own words.** Novelty overlaps and audit flags must quote the paper; quotes are
   verified against its text; unverified → not counted. Report sentences are citation-checked; unsupported ones are marked.
3. **Verdict colour is guardrailed, not purely LLM** (`agents/verdict.py`).
4. **Credibility is computed, not generated.**
5. **Nothing is faked.** No seeded data; every number in the UI comes from a run.

## Run it

```bash
cp .env.example .env      # OPENROUTER_API_KEY or NEBIUS_API_KEY, TAVILY_API_KEY (+ optional OPENALEX_API_KEY, S2_API_KEY)
make setup                # uv sync + npm install
make dev                  # API :8100 + UI :5180
make test                 # 15 offline tests (scripted model: harness, compression, budgets, scoring, guardrails)
make check                # tsc + vite build + oxlint + import check + tests
```

UI: landing (three.js idea-in-a-galaxy hero) → intake chat with quick replies and a live brief → workspace tabs:
**Verdict** · **Agents (live)** (agent graph + trace) · **Paper galaxy** (3D, orbit = closeness, colour = credibility)
· **Papers** (credibility breakdowns, audits, links) · **Novelty matrix** (verified quotes) · **Chamber** (3D chamber +
transcript) · **Report** (citation check) · **Chat** · **Notebook**.

## Layout

```
backend/glr/
  harness/        agent.py (runtime loop, swarm) · context.py (3-tier compression) · tools.py (@tool, finish tools)
  agents/         intake · planner · research (Lead, Scouts, Critic) · toolbox · auditor · novelty · chamber · verdict · writer · chat
  sources/        arxiv · openalex · hf · s2 · http (per-host pacing, 429 cooldown, cache)
  llm.py providers.py   Nemotron roles on Nebius / OpenRouter (from GreenLight)
  papers.py credibility.py corpus.py verify.py   registry + enrichment · score · hybrid BM25+Qwen3 RAG · quote/claim checks
  budget.py trace.py db.py privacy.py web.py pipeline.py api.py
backend/tests/    offline tests with a scripted model
web/src/          React 19 + Tailwind 4 + three.js (three/: Constellation, PaperGalaxy, ChamberScene, glass, core)
```

Prior art we learned from: [researchAgent](https://github.com/Sachitbansal/researchAgent) (single-agent RAG over arXiv:
hand-written loop, tool-pairing rules, abstention gate, arXiv rate-limit lessons) and GreenLight (providers, Chamber,
guardrails, privacy, Tavily budget).
