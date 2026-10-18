# GreenLight Research

Researcher describes a research idea → intake chat sharpens it → a multi-agent harness (Lead Researcher + parallel
Scouts + Critic) searches arXiv / OpenAlex / Hugging Face / Tavily / the citation graph → every paper gets a
deterministic credibility score → quote-verified novelty matrix → Proponent vs Skeptic debate → Speaker (Nemotron Ultra)
rules green / amber / red, guardrailed in code → cited report with a citation check → ongoing research chat.

Hackathon: NVIDIA × Nebius (open models only). Sponsors to show: Nemotron on Nebius Token Factory, Tavily, Qwen/HF.

- Full feature/architecture docs and the benchmarks behind each design decision: `README.md`.

## Commands

```bash
make setup   # cd backend && uv sync ; cd web && npm install
make dev     # API :8100 (uvicorn --reload) + Vite UI :5180 (proxies /api)
make test    # offline tests, scripted model (no keys, no network)
make check   # tsc + vite build + oxlint + backend import check + tests — run before committing
```
Keys in `.env` (see `.env.example`): one LLM key (`NEBIUS_API_KEY` wins over `OPENROUTER_API_KEY`) + `TAVILY_API_KEY`.
Strongly recommended: `OPENALEX_API_KEY` (keyless OpenAlex shares a tiny per-IP budget), `S2_API_KEY`.

## Architecture

- `harness/` is the agent runtime: `Agent` (loop, parallel tools, budgets, loop detection, guards, review/reflection,
  forced finish), `Context` (3-tier compression; keeps tool_call/tool pairing valid), `@tool`, `swarm()`.
  All agents use it; don't add a second loop.
- `budget.py` + `trace.py`: budgets ride a contextvar and are charged by `trace.log` (llm → USD + call, tool → call).
  `trace.source()` is for external API calls (not charged). Agent scope sets parent → the UI's agent graph.
- `llm.py`/`providers.py`: provider plug-in; roles fast=Nano, reason=Super, judge=Ultra, embed=Qwen3-8B.
  `llm.FAKE` / `llm.EMBED_FAKE` are the offline test seams.
- `papers.py` merges records from all sources into stable ids `P#` per project; `corpus.py` is hybrid BM25 + dense RRF.
- `sources/http.py` is the only HTTP seam for scholarly APIs (per-host pacing, 429 cooldown, cache). Use it.

## Invariants — do not break

1. Redact (`privacy.redact`) before storage, LLM calls or any search query.
2. Overlap claims and audit flags must carry a quote verified by `verify.quote_ok`; unverified never counts.
3. Credibility is `credibility.score()` — deterministic. Don't let an LLM set it.
4. Verdict guardrails in `agents/verdict.py` run after the Speaker; only ever make the light more severe.
5. Paper identity: `openalex.same_title` is strict on purpose (LoRA vs LoRTA). Don't loosen it.
6. Tools never raise; agents never crash the run; tool calls in one turn always get a result each.
7. Nothing is faked: no seeded data.

## Conventions

Python 3.12, async, pydantic models for every LLM JSON output (`llm.chat_json`). No agent frameworks. Short module
docstrings, sparse comments. Frontend: React 19 + Tailwind 4 + three.js, hash routes `#/p/<id>/<tab>`; Markdown is
rendered by our safe renderer in `ui.tsx` (no HTML injection). Never commit `.env` or `backend/data/glr.db*`.
