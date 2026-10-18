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
 Relevance Ranker (cross-encoder: every paper vs the idea) → Reader (full texts of the closest papers)
    ▼
 Credibility Scorer (OpenAlex + HF + S2 → deterministic 0-100) ∥ Auditor (red flags, quote-verified)
    ▼
 Novelty Mapper: components × closest papers, every overlap must quote the paper (verified) → strict 2nd judge on
                 every "full" (same mechanism, other setting = partial) → novelty score
    ▼
 Research Chamber: Proponent ∥ Skeptic (openings, rebuttals, evidence ids, struck/weak args) → Speaker (Ultra)
    ▼
 Guardrails (code): credible paper doing all core components → RED · core component done → ≥AMBER · thin search → ≥AMBER
    ▼
 Report Writer → Citation Checker (each [P#] sentence judged against the cited paper's passages) → Export .md
    ▼
 Relationship Graph (citations from reference lists, embedding similarity, clusters)
    ▼
 Research Chat (Super + full toolbox + 5-layer memory + citation self-correction) — ask, challenge, pivot, search more
```

## Sponsor tech and models

| Role | Model / service | Used for |
|---|---|---|
| `fast` | **NVIDIA Nemotron 3 Nano** | scouts' helpers, Critic, Auditor, citation checks, context compression, query expansion, memory extraction, fallback reranker |
| `reason` | **NVIDIA Nemotron 3 Super** | intake, planner, Lead Researcher, Scouts, novelty mapping, Chamber speakers, report, research chat |
| `judge` | **NVIDIA Nemotron 3 Ultra** | the Speaker's green / amber / red ruling |
| `embed` | **Qwen3-Embedding-8B** (Matryoshka 1024-d) | dense retrieval, HyDE, paper similarity graph, episodic chat memory |
| rerank | **NVIDIA NeMo Retriever reranking NIM** · vLLM (Qwen3-Reranker-8B) · local bge-reranker-v2-m3 / MiniLM · Nemotron Nano | cross-encoder reranking, relevance triage, evidence gate |
| inference | **Nebius Token Factory** (OpenRouter as stand-in, same models) | every LLM + embedding call; provider chosen by key (`providers.py`) |
| web | **Tavily** search + extract | live web scouting, full-text reading; credit budget + cache |
| scholarly | arXiv · OpenAlex · Hugging Face Papers · Semantic Scholar | paper search, citation graph, bibliometrics, adoption signals |
| GPU (optional) | RTX PRO 6000 (CUDA) | heavy local reranker / self-hosted vLLM reranker |

Model roles resolve from the provider's live catalog unless pinned with `GLR_MODEL_*`; `GET /api/health` shows what
was picked.

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
| **Chat memory** | pinned project state · long-term facts (Nano-extracted, de-duplicated) · token-budget rolling summary · episodic recall of similar earlier exchanges (Qwen3 embeddings) · in-turn compression |
| **Self-correction** | chat + report sentences are citation-checked against the cited papers; chat answers with unsupported sentences are revised once and re-checked |
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

## Retrieval pipeline

`corpus.retrieve()`: **query expansion** (Nemotron Nano: 2 paraphrases + a HyDE passage, with a 6 s deadline) →
**BM25 + Qwen3-Embedding-8B** recall for every variant, fused by weighted **RRF** → **cross-encoder rerank** of the top 40
→ **calibrated evidence gate** (`sufficient_evidence: false` when the top score is below the threshold measured for
that reranker) → **MMR** diversity → **±1 neighbour context**. Full-text chunks carry a contextual title header.
Every search result is also **relevance-triaged** against the research idea by the cross-encoder.

Reranker chain (`rerank.py`, first available wins): **NVIDIA NeMo Retriever NIM** (`NVIDIA_API_KEY` or self-hosted)
→ any **vLLM `/rerank`** endpoint (e.g. Qwen3-Reranker-8B on our RTX PRO 6000) → **local cross-encoder**
(bge-reranker-v2-m3 on CUDA, MiniLM-L-12 on Mac) → **Nemotron Nano** listwise grading.

## Research chat memory (5 layers) + self-correction

1. **Pinned project state**: brief, verdict, novelty, closest papers, shared notebook, always in the system prompt.
2. **Long-term facts**: after every exchange Nemotron Nano extracts durable facts (decisions, idea changes,
   preferences, findings with [P#], open questions); de-duplicated, max 40, pinned, shown in the Chat sidebar.
3. **Rolling summary**: when the verbatim history exceeds 5k tokens, older turns are folded by Nano (last 6 kept).
   The intake chat folds the same way (4k-token budget).
4. **Episodic recall**: every exchange is embedded with Qwen3; the most similar earlier exchanges are recalled
   verbatim for a new message, even after they were folded away.
5. **In-turn compression**: the harness elides/folds tool results inside a long agent turn.

After answering, citations are normalised to `[P#]` and every cited sentence is checked against the cited papers'
passages. If any is unsupported, the agent revises the answer once and the revision is re-checked (kept only if not
worse); anything still unsupported is marked ⚠️ in the answer.

## Relationship graph

3D force-directed graph of the ~60 most relevant papers plus the idea (`graph.py`, `three/PaperGraph.tsx`).
- **cites** edges from reference lists: Semantic Scholar batch (with key) → OpenAlex `referenced_works` → the paper's
  own bibliography parsed from its arXiv HTML page (matched by arXiv id or exact 5+-word title). Each edge keeps the
  reference line as proof. Particles flow from citing to cited paper.
- **similar** edges: nearest neighbours of Qwen3 abstract embeddings (adaptive 88th-percentile threshold).
- **idea** edges: the Lead Researcher's relation (same idea / very close / related).
- **clusters**: weighted label propagation, labelled by distinctive title words (no LLM).
- Click a paper → who it cites, who cites it, what it resembles, each with an **Explain** button (Nemotron Nano, cached).

## Verdict guardrails (code, after the Speaker)

- A paper with credibility ≥ 35 and a **verified full overlap on every core component** → forced **RED** ("already done").
  Low-credibility or retracted "same idea" papers can't force red; they push to at least amber.
- Any core component fully covered by credible verified work → at least **AMBER**.
- Thin evidence (< 10 papers or low review confidence) → at least **AMBER**: no green on a search that could have missed prior work.
- The Speaker's original call is kept and shown next to the guardrail reason.

## Benchmarks (all measured, none estimated)

**Live end-to-end runs**, same idea ("per-token sparse mixture of LoRA experts for multi-task instruction tuning"):

| | OpenRouter (Nemotron) | **Nebius Token Factory** (Nemotron) |
|---|---|---|
| Wall time / cost | 9.3 min / $0.0995 | **6.2 min / $0.195** |
| Median LLM call latency | – | **0.95 s** |
| Agents / LLM calls / tool calls | 20 / 217 / 71 | 19 / 168 / 38 |
| Cost by model | – | Super $0.180 (62 calls), Ultra $0.008 (1), Nano $0.005 (37), Qwen3 embed $0.001 (68) |
| Research rounds / scouts | 2 / 6 (Critic rejected round 1) | 1 / 3 (Critic approved) |
| Papers collected / scored / audited | 180 / 80 / 8 | 97 / 80 / 5 (all 97 relevance-ranked) |
| Context compressions | 17.3k → 8.6k, 25.7k → 10.8k tokens | 16.2k → 9.4k, 25.8k → 10.1k tokens |
| Reranker calls / errors | – (added later) | 90 / 0 |
| Novelty | 0/100 (P7 covered every core component) | 50/100 (strict judge downgraded 19 "full" → "partial"; 4 unverified quotes dropped) |
| Verdict | **AMBER**, guardrails agreed | **GREEN**, no guardrail fired |
| Report citation check | 1 supported / 2 partial / 0 unsupported (before the [P#] fix) | 3 / 9 / 3 of 15 claims |
| Relationship graph | 60 papers, 36 citation links, 89 similarity, 5 clusters | 60 papers, **71 citation links**, 84 similarity, 7 clusters |

Honest reading: Nebius is faster (6.2 vs 9.3 min, sub-second calls) and costs more per run (its Super price is higher).
The two runs disagree on the verdict. The Nebius run searched less (one round: the Critic approved it) and the new
strict novelty judge treats "same mechanism, different setting" (LLaVA-MoLE is vision-language) as only partial
overlap, which lifted novelty to 50. Closest work (MoLoRA, MixLoRA, LLaVA-MoLE) does per-token LoRA-expert routing
with load balancing, so AMBER is the more defensible call; verdict stability across runs is an open issue (ideas:
force two research rounds, a guardrail on "very close" papers with high relevance, majority vote over 3 Speakers).

**Retrieval eval** (`make eval P=<id>`; 40 synthetic paraphrased questions written from the project's own passages,
gold = exact source chunk, 180-paper corpus; partial run, the "hard" no-shared-vocabulary set was not run yet):

| Pipeline | Recall@5 | MRR@10 | Latency |
|---|---|---|---|
| BM25 | 0.950 | 0.874 | 5 ms |
| Dense (Qwen3-Embedding-8B) | 0.900 | 0.806 | 759 ms |
| Hybrid RRF | 0.950 | 0.877 | 6 ms |
| Hybrid + expansion | 0.900 | 0.830 | 1.6 s |
| Hybrid + rerank (MiniLM-L-12) | 0.900 | 0.857 | 1.9 s |
| Evidence gate (MiniLM-L-12), answerable vs 12 off-topic | **AUROC 1.0** | | |

Honest reading: on paraphrased questions keyword search is already near the ceiling, so expansion and reranking
don't add recall here; their value is the evidence gate (perfect separation of answerable vs off-topic questions)
and vocabulary-mismatch queries, which the "hard" set measures (not run yet).

**Reranker latency** (40 real passages, M-series Mac): MiniLM-L-12 1.5 s · bge-reranker-base 4.6 s ·
bge-reranker-v2-m3 13–17 s (MPS) / 16–23 s (CPU) → v2-m3 is the default only on CUDA.

**Other measurements from live runs**

| What | Result |
|---|---|
| Nebius Token Factory smoke test | models resolved: `NVIDIA-Nemotron-3-Nano-30B-A3B`, `nemotron-3-super-120b-a12b`, `Nemotron-3-Ultra-550b-a55b`, `Qwen3-Embedding-8B`; structured JSON 0.7–0.9 s per role; tool call OK ($0.00014) |
| Credibility, "Attention Is All You Need" | 78/100 strong (77,978 citations, 300 HF models) |
| Credibility, LLaVA-MoLE before/after bibliometrics fix | 10/100 ("0 citations", data never fetched) → 32/100 (8 citations, author h-index 33) |
| Paper identity check | fuzzy title match merged "LoRA" with "LoRTA" → now strict; OpenAlex maps LoRA's DOI to an unrelated paper → refused |
| OpenAlex reference-list coverage (recent arXiv papers) | 5 / 49 → why the graph parses arXiv bibliographies (53 / 60) |
| Keyless Semantic Scholar | 429 rate-limited → used only with `S2_API_KEY` or as a cooled-down fallback |
| Context compression (live) | scouts 17.3k → 8.6k tokens, Lead 25.7k → 10.8k (tier-1 elision) |
| Chat long-term memory (live, 1 turn) | stored 1 decision + 1 preference + 2 findings with [P#] + 1 open question; vectors never sent to the UI |
| Chat answer before citation normalisation | wrote "(P66)" → 0 claims checked → fixed: normalised to [P66], all checkable |
| Local reranker first load | ~160 s incl. 2.3 GB model download (bge-reranker-v2-m3), then cached |

**Offline tests**: 29 passing (`make test`), incl. Sachit's auth / spend-cap guards: harness (parallel tools, loop detection, review gate, budget-forced
finish, tier-1/2 compression with tool-call pairing checked on every request, child budgets, chat memory layers),
credibility, quote verification, citation normalisation, guardrails, strict title identity, graph citation matching
+ clustering, MMR, reranker fallback, gate calibration.

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
make setup                # uv sync --extra local (torch + sentence-transformers) + npm install
make dev                  # API :8100 + UI :5180
make test                 # offline tests (scripted model: harness, compression, budgets, scoring, guardrails, auth)
make eval P=<project_id>  # retrieval eval + evidence-gate calibration (results on the Proof page, #/proof)
make check                # tsc + vite build + oxlint + import check + tests
```

Sign-in: set `GOOGLE_CLIENT_ID` for Google sign-in (projects are private per user); without it, localhost runs as a
built-in local user. **Deploy**: one container (`Dockerfile`) + Caddy on a Nebius VM, see [`deploy/nebius.md`](deploy/nebius.md).

UI: landing (three.js idea-in-a-galaxy hero) → intake chat with quick replies and a live brief → workspace tabs:
**Verdict** · **Agents (live)** (agent graph + trace) · **Paper galaxy** (3D, orbit = closeness, colour = credibility)
· **Relationship graph** (3D force graph: citation links with the reference line as proof, embedding similarity,
auto-clusters, "explain how these two relate")
· **Papers** (credibility breakdowns, relevance, audits, links) · **Novelty matrix** (verified quotes, strict-judge
downgrades) · **Chamber** (3D chamber + transcript) · **Report** (citation check, **Export .md**) · **Chat** (memory
panel, self-correction) · **Notebook**. Header: traffic light, **Stop** / **Re-run**. **Proof** page (`#/proof`):
retrieval eval table + gate calibration.

## Configuration (`.env`, see `.env.example`)

| Var | Purpose |
|---|---|
| `NEBIUS_API_KEY` / `OPENROUTER_API_KEY` | LLM + embeddings (Nebius wins when both are set); `GLR_LLM_PROVIDER` forces one |
| `TAVILY_API_KEY`, `GLR_TAVILY_BUDGET` | live web; stop at this many credits |
| `OPENALEX_API_KEY`, `OPENALEX_MAILTO` | OpenAlex own daily budget (keyless is a small shared per-IP budget) |
| `S2_API_KEY` | Semantic Scholar: influential citations, fallback bibliometrics, batch reference lists |
| `HF_TOKEN` | higher Hugging Face rate limits |
| `NVIDIA_API_KEY`, `GLR_NIM_RERANK_URL`, `GLR_NIM_RERANK_MODEL` | NeMo Retriever reranking NIM (hosted or self-hosted) |
| `GLR_RERANK_URL`, `GLR_RERANK_MODEL`, `GLR_RERANK_KEY` | any `/rerank` server (e.g. vLLM + Qwen3-Reranker-8B) |
| `GLR_RERANKER`, `GLR_RERANK_LOCAL_MODEL` | force a reranker backend / local model |
| `GLR_QUERY_EXPANSION`, `GLR_EXPANSION_DEADLINE` | multi-query + HyDE on/off, deadline in seconds |
| `GLR_MAX_USD_PER_RUN`, `GLR_RESEARCH_ROUNDS`, `GLR_MAX_SCOUTS`, `GLR_CONTEXT_BUDGET`, `GLR_PAPERS_TO_READ` | harness budgets |
| `GLR_THINKING`, `GLR_MODEL_FAST/REASON/JUDGE/EMBED` | Nemotron reasoning traces; pin model ids |

## API

| Endpoint | |
|---|---|
| `GET /api/health` | keys, provider, models, reranker chain, Tavily credits |
| `POST /api/projects` · `POST/GET /api/projects/{id}/intake` | start + continue the intake chat |
| `POST /api/projects/{id}/start` · `/stop` · `/rerun` · `DELETE /api/projects/{id}` | run control |
| `GET /api/projects/{id}` · `/trace?after=` · `/papers/{pid}` · `POST /papers/{pid}/score` | workspace data, live trace, paper detail, on-demand credibility |
| `GET /api/projects/{id}/graph` · `POST /graph/explain` | relationship graph, explain one link |
| `POST/GET /api/projects/{id}/chat` | research chat (+ long-term memory items) |
| `GET /api/evals` · `POST /api/evals/retrieval/{id}` | Proof page results, run the retrieval eval |

## Known limitations

- No sign-in or per-user data yet (single local user): don't expose it publicly. GreenLight's Google auth can be ported.
- SQLite only; hosting needs Postgres/pgvector (as in GreenLight) and the Nebius Serverless deploy is not done.
- The retrieval eval was only partly run (paraphrased set); the "hard" vocabulary-mismatch set and gate calibration
  need `make eval` once. Until then the evidence gate is off.
- NVIDIA NIM and vLLM reranker backends are implemented but untested without keys/GPU here.
- Verdicts are not yet stable across runs: the same idea got AMBER (OpenRouter run) and GREEN (Nebius run); see Benchmarks.
- A pipeline run takes ~9 min; the dev server's `--reload` kills a running analysis when backend files change.

## Demo checklist (15 min before judging)

1. `.env`: `NEBIUS_API_KEY` (sponsor: must show **Nebius Token Factory**), `TAVILY_API_KEY`; ideally `OPENALEX_API_KEY`,
   `NVIDIA_API_KEY` (NeMo Retriever reranker), `S2_API_KEY`.
2. `make dev` in a terminal → `curl localhost:8100/api/health`: `llm_provider` = Nebius Token Factory, models =
   Nemotron Nano/Super/Ultra + Qwen3-Embedding-8B, `rerankers.chain` starts with `nim` (or `local`).
3. Start one fresh run (~9 min) and keep it open: Agents (live) graph while it runs, then Verdict → Relationship graph
   → Novelty matrix → Chamber → Chat. **Stop** cancels a run; **Re-run** starts over.
4. Run `make eval P=<project_id>` once: it writes `data/eval/calibration.json`, which switches on the
   `sufficient_evidence` gate (until then the gate is off). Report tab → **Export .md** downloads the cited report.
5. Not built: see Known limitations.

## Layout

```
backend/glr/
  harness/        agent.py (runtime loop, swarm) · context.py (3-tier compression) · tools.py (@tool, finish tools)
  agents/         intake · planner · research (Lead, Scouts, Critic) · toolbox (+ relevance triage) · auditor · novelty
                  (+ strict judge) · chamber · verdict · writer · chat (5-layer memory, self-correction)
  sources/        arxiv · openalex · hf · s2 · http (per-host pacing, 429 cooldown, cache)
  llm.py providers.py   Nemotron roles on Nebius / OpenRouter (from GreenLight)
  papers.py credibility.py corpus.py verify.py   registry + enrichment · score · retrieval pipeline · quote/claim checks
  rerank.py       NIM / vLLM endpoint / local cross-encoder / Nemotron reranker chain, calibrated thresholds
  graph.py        relationship graph (citations, similarity, clusters, explain)
  evals.py        retrieval eval + evidence-gate calibration (scripts/eval_retrieval.py)
  budget.py trace.py db.py privacy.py web.py pipeline.py api.py
backend/tests/    offline tests with a scripted model
web/src/          React 19 + Tailwind 4 + three.js (three/: Constellation, PaperGalaxy, PaperGraph, ChamberScene, glass, core)
                  views/: Agents · Papers · Graph · Novelty · Chamber · Report · Chat; ProofPage, Intake, Home
```

Prior art we learned from: [researchAgent](https://github.com/Sachitbansal/researchAgent) (single-agent RAG over arXiv:
hand-written loop, tool-pairing rules, abstention gate, arXiv rate-limit lessons) and GreenLight (providers, Chamber,
guardrails, privacy, Tavily budget).
