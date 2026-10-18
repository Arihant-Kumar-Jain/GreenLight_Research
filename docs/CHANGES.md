# Team change log

Shared context for the team (and their Claude Code sessions: `CLAUDE.md` imports this file). Newest first.
For each change: what, why, new env vars, how to test, open TODOs.

---

## 2026-10-18 (merge) — Sachit (with Claude): feat/auth-deploy-landing merged with Arihant's retrieval/chat work

- New upstream routes now need the owner like every other project route: `POST /api/projects/{id}/stop`,
  `POST /api/evals/retrieval/{id}` (also behind the daily USD cap). `GET /api/projects/{id}/chat` keeps the memory
  panel and owner check. `GET /api/evals` stays public (Proof page).
- App home (`#/app`) top bar shows the **Proof** link and the active reranker; `#/proof` route kept next to the landing.
- `uv.lock` regenerated from the merged `pyproject.toml` (google-auth + the `local` reranker extra).
- **Test.** `make check` (29 tests).

---

## 2026-10-18 (night) — Sachit (with Claude): light theme, landing page, 3D specimen

**What.**
- **Light theme across the app** ("ink on paper"): tokens in `index.css` (paper `#f6f8f7`, pine ink `#0e2a21`, green
  `#0b7a47`, amber, red, teal for links/data). Colour only carries meaning: green = verified/trusted/open,
  amber = partly done, red = done/retracted. Fonts: Newsreader (headlines), Atkinson Hyperlegible Next (UI/body),
  JetBrains Mono for IDs/scores only. The all-caps tracked labels and the film grain are gone.
- **Landing page** at `#/` (`Landing.tsx`). The app home moved to `#/app` (`Home.tsx`, rebuilt as a clean start page
  with healthcare examples and a project list). The copy follows `docs/GreenLight_Research_Idea_Scope.pdf` only.
  Nav: section links + **Sign in with Google** (Open app + avatar when signed in). **Start researching** opens the
  Google sign-in popup when signed out, then goes to the app.
- **3D specimen** (`three/Specimen.tsx`), after GreenLight's Journey: one fixed particle cloud that morphs as you
  scroll, drawn as ink dots on paper. Shapes: DNA helix (question) → source sphere with scout orbits (discovery) → a
  page with cited lines in green (ask the papers) → trust-score histogram with a red retracted bar (credibility) →
  clustered citation network (graph) → traffic light (verdict). One draw call, no bloom, reduced motion respected.
  It fades out behind the reference sections.
- **Workspace 3D on light**: `three/core.ts` renders opaque on the white surface; bloom/lens only on request (bloom
  washes colours out on white). Paper galaxy, relationship graph and Chamber use lit, light-palette materials with
  normal blending; out-of-focus nodes/edges fade toward the paper. The glass core tints at the rim instead of glowing.
  `Constellation.tsx` (old dark hero) was removed.

**Test.** `make check`. Landing checked in the browser at every stage, plus the sign-in popup. Intake and the live
agents view were checked on a real run. Paper galaxy, relationship graph and Chamber were converted but **not yet
checked on a finished project** (open one and look).

**Heads-up for the backend.** The landing page lists the scope's healthcare sources (PubMed, Europe PMC, medRxiv/bioRxiv,
ClinicalTrials.gov, Cochrane, WHO/FDA/EMA). The scouts don't search those yet (arXiv, OpenAlex, HF Papers, Tavily).

---

## 2026-10-18 (evening) — Sachit (with Claude): Google sign-in, spend caps, Nebius deploy files

**What.**
- **Sign in with Google** (`backend/glr/auth.py`, `web/src/auth.tsx`), ported from GreenLight. Google Identity Services
  gives the browser an ID token. The backend verifies it against `GOOGLE_CLIENT_ID` (no client secret) and sets an
  HttpOnly `glr_session` cookie. Only the token's SHA-256 is stored (`sessions` table). Modes: `google` (client ID set),
  `dev` (no client ID on localhost → built-in `local` user, loopback requests only), `off` (no client ID on a public
  host → sign-in refused).
- **Projects are private to their owner.** New `projects.user_id`. Older databases are migrated with every project
  given to `local`. Every `/api/projects/{id}/…` route needs the owner. Other users get 404.
- **Daily spend caps** for a public deploy: `GLR_MAX_USD_PER_DAY` (LLM spend across all users, from the trace) and
  `GLR_MAX_RUNS_PER_DAY`. They answer 429. `GLR_MAX_USD_PER_RUN` only capped one run.
- **Deploy**: `Dockerfile` (multi-stage, one uvicorn worker, non-root, DB at `/data`), `docker-compose.yml` (app,
  plus Caddy with automatic HTTPS under `--profile prod`), `deploy/Caddyfile`, `deploy/backup.sh` (SQLite online backup
  to Nebius Object Storage), `deploy/nebius.md` (Token Factory + Compute VM + Container Registry + Object Storage).
  Why a VM and not a Serverless AI endpoint: in-process asyncio runs and SQLite need one long-lived process on a real
  disk. An endpoint's disk is wiped on stop, and its managed URL can't take a custom domain.

- **Invite-only option**: `GLR_ALLOWED_EMAILS` (emails or `@domain`). Empty = any verified Google account.
- **Heads-up, existing local projects**: the migration gives them to the `local` user, and nobody is `local` once
  `GOOGLE_CLIENT_ID` is set. To keep them, sign in once with Google, then run:
  `sqlite3 backend/data/glr.db "UPDATE projects SET user_id=(SELECT id FROM users WHERE email='you@gmail.com') WHERE user_id='local'"`

**Env vars**: `GOOGLE_CLIENT_ID`, `GLR_ALLOWED_EMAILS`, `GLR_AUTH` (`dev` forces the local user), `GLR_MAX_USD_PER_DAY`,
`GLR_MAX_RUNS_PER_DAY`, `GLR_DOMAIN` (Caddy), `GLR_IMAGE` (compose). New dependency: `google-auth`.

**Test.** `make test` (24, incl. sessions, ownership 404s, logout, allowlist, dev mode only from loopback, both caps).
Local: without `GOOGLE_CLIENT_ID` the nav shows "Local dev". With it, add `http://localhost` and
`http://localhost:5180` to the OAuth client's JavaScript origins, then sign in from the nav.
Container (checked: UI, API, DB on the volume, non-root): `docker compose up --build app` → http://localhost:8100. Inside
Docker requests are not loopback, so the dev user is off. Set `GOOGLE_CLIENT_ID` to sign in.

**TODO.** The Token Factory catalog (Ultra + Qwen3 embeddings) is not yet verified with a Nebius key. Sharing a
project read-only (for judges) isn't possible yet.

---

## 2026-10-18 (afternoon) — Arihant (with Claude): chat memory + self-correction, retrieval stack, stop button

- **Research chat memory, 5 layers** (`agents/chat.py`): pinned project state; long-term facts extracted by Nano after
  every exchange (decisions, idea changes, preferences, findings with [P#]; de-duplicated, max 40, shown in the Chat
  sidebar); rolling summary when verbatim history exceeds 5k tokens (keeps last 6 messages); episodic recall of the
  most similar earlier exchanges by Qwen3 embedding (vectors stay server-side); harness in-turn compression.
- **Self-correction**: chat citations are normalised to [P#], checked against the cited papers; if any sentence is
  unsupported the agent revises once and the revision is re-checked (kept only if not worse).
- Live: a decision ("FLAN + MMLU on Llama-3-8B") and 4 findings were stored after one turn.
- Retrieval: reranker chain, expansion, gate, MMR (see README "Retrieval pipeline" / "Benchmarks"). Stop button.
- Tests: 22 offline.

---

## 2026-10-18 (later) — Arihant (with Claude): paper relationship graph

**What.** New workspace tab **Relationship graph** (`backend/glr/graph.py`, `web/src/three/PaperGraph.tsx`,
`views/GraphView.tsx`): a 3D force-directed graph of the ~60 most relevant papers plus the idea.
- **cites** edges come from reference lists: Semantic Scholar batch (only with `S2_API_KEY`), then OpenAlex
  `referenced_works`, then the paper's own bibliography parsed from its arXiv HTML page (matched by arXiv id or an exact
  title of 5+ words). Every edge keeps the reference line as evidence. Why the fallbacks: in the live project OpenAlex
  had reference lists for only 5 of 49 recent preprints and keyless S2 answered 429; the arXiv bibliographies gave
  53/60 papers' references → 36 citation links.
- **similar** edges: nearest neighbours of the Qwen3 abstract embeddings, threshold = 88th percentile of pairwise cosine.
- **idea** edges: the Lead Researcher's relation (same idea / very close / related).
- **Clusters**: weighted label propagation over cites + similar, labelled by distinctive title words (no LLM).
- **Explain**: `POST /api/projects/{id}/graph/explain` asks Nemotron Nano how two papers relate (cached).
- UI: particles flow citing → cited, colour by cluster or credibility, edge-type toggles, click a cluster to focus it,
  click a paper to list who it cites / who cites it / what it resembles, each with evidence and an Explain button.
- The graph is built at the end of each run (non-fatal) and cached; `GET .../graph?refresh=1` rebuilds it.
- Fixed while testing: 3D clicks relied on hover state from the render loop, so taps on touch screens never selected
  anything (now hit-tested on click, also in Paper galaxy); duplicate trace events under StrictMode; `<div>` inside `<p>`.

**Test.** `make test` (17, incl. citation matching + clustering). Live: open a finished project → Relationship graph.

**TODO.** No reranker yet (see README "Retrieval"); arXiv HTML exists only for papers from ~Dec 2023 on, older papers
need S2/OpenAlex references.

---

## 2026-10-18 — Arihant (with Claude): GreenLight Research v0.1, from scratch

**What.** New project next to GreenLight, for research ideas instead of startup ideas. Reuses GreenLight's stack
(Nemotron roles via `providers.py`/`llm.py`, Tavily module with credit budget, `privacy.py`, the Chamber debate +
guardrail pattern, traffic light, glass shader, Chamber three.js scene) and lessons from
[researchAgent](https://github.com/Sachitbansal/researchAgent) (hand-written loop, tool pairing rules, arXiv pacing).
No GreenLight code was changed (only its git-ignored `.claude/launch.json` got two preview entries for this project).

- **Harness** (`backend/glr/harness/`): `Agent` runtime with parallel tool calls, budgets (USD/calls/time, parent →
  child), loop detection, guard + review hooks, forced finish; `Context` 3-tier compression; `@tool` schemas from
  signatures; `swarm()`.
- **Agents**: intake chat → planner → Lead Researcher dispatching Scout swarms (rounds gated by a Critic) → reader →
  credibility scorer + Auditor → Novelty Mapper (quote-verified) → Chamber (Proponent/Skeptic/Speaker) → guardrails →
  report writer + citation checker → research chat (to-and-fro, 3-layer memory).
- **Sources**: arXiv, OpenAlex (+ citation graph hops), Hugging Face Papers (adoption: models/datasets/Spaces), Semantic
  Scholar (optional / fallback), Tavily search + extract (full texts).
- **Credibility** (`credibility.py`): deterministic 0-100 from impact / authors / venue / adoption / integrity.
- **UI**: React 19 + Tailwind 4 + three.js: landing hero (liquid-glass idea orb in a spiral galaxy of papers, scout
  comets, bloom + lens), intake chat with quick replies and live brief, workspace with live agent graph + trace,
  3D Paper Galaxy, papers with credibility breakdowns, novelty matrix, 3D Chamber, report with citation check, chat.

**Env vars**: `NEBIUS_API_KEY` / `OPENROUTER_API_KEY`, `TAVILY_API_KEY`, `GLR_TAVILY_BUDGET`, `OPENALEX_API_KEY`,
`OPENALEX_MAILTO`, `S2_API_KEY`, `HF_TOKEN`, `GLR_MAX_USD_PER_RUN`, `GLR_RESEARCH_ROUNDS`, `GLR_MAX_SCOUTS`,
`GLR_CONTEXT_BUDGET`, `GLR_PAPERS_TO_READ`, `GLR_THINKING`, `GLR_MODEL_*`, `GLR_LLM_PROVIDER`, `GLR_DB_PATH`.

**Tested.**
- `make test`: 15 offline tests (scripted model): parallel tools, loop detection, review/reflection, budget-forced
  finish, tier-1 + tier-2 compression with tool-call pairing checked on every request, child budgets, credibility
  ordering, retracted = 0, new papers not punished, verified flags lower integrity, quote verification, citation
  extraction, guardrails (forced red, thin evidence → amber), strict title identity.
- Live sources: arXiv, OpenAlex, HF Papers work keyless; "Attention Is All You Need" scores 78/100 (strong).
  Found + fixed: fuzzy title match merged "LoRA" with "LoRTA" (now strict); OpenAlex has LoRA mis-merged into another
  work, so it is refused and S2 is the fallback (keyless S2 answers 429 → score marked low-confidence lower bound).
- **Live end-to-end run** via the UI (OpenRouter + Tavily), idea "per-token sparse mixture of LoRA experts for
  multi-task instruction tuning": intake 2 turns → plan (4 components, 5 angles) → Lead + 6 scouts over 2 rounds (the
  Critic rejected round 1) → 180 papers, 80 scored, 8 audited → novelty 0/100 (P7 LLaVA-MoLE covers all core
  components but on vision-language) → Speaker AMBER, guardrails agreed → report. **9.3 min, $0.0995, 20 agents,
  217 LLM calls, 71 tool calls, real context compressions (17.3k → 8.6k tokens).** Research chat answered a follow-up
  with 6 tool calls in 12 s for $0.004.
- Fixed after that run: report cited bare `P7` (now normalised to `[P7]`, so the citation checker sees every claim);
  a paper whose OpenAlex id came from a citation hop skipped bibliometrics (showed "0 citations", 10/100 → now 32/100
  with real data); unknown citations are scored as unknown, not zero; scouts are told to write to the notebook.

**Open TODOs.**
- No auth yet (single local user). Port GreenLight's Google sign-in + per-user ownership before any public deploy.
- SQLite only; Postgres/pgvector as in GreenLight for hosting.
- Proof/eval page: a set of known "already done" and "open" ideas to measure verdict accuracy (none faked meanwhile).
- Pipeline can't be cancelled mid-run; `--reload` dev server kills running analyses when backend files change.
- Novelty mapper is generous: a verified quote proves the paper says it, not that the setting matches (C4 "evaluates
  on FLAN/MMLU" was marked full for a vision-language paper). Consider a second, stricter judge on "full" cells.
- Chat answers are not citation-checked yet (the report is); one chat answer contradicted the review on P122's loss.
- The preview tool can't start the API (sandbox can't read `backend/.venv`); run `make dev` in a terminal.
