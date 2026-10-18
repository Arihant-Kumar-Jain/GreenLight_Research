# GreenLight Research: handoff (2026-10-18, night)

Context transfer for the next session (human or Claude). Read this first, then `CLAUDE.md`, `README.md`, `docs/CHANGES.md`.

## 1. What this is

Healthcare research assistant plus a novelty verdict: intake chat → multi-agent deep research (planner, lead, parallel
scouts, critic, reader, credibility auditor, novelty mapper, Proponent/Skeptic/Speaker panel) → green / amber / red
verdict → cited report → research chat. Scope boundary for the landing page: `docs/GreenLight_Research_Idea_Scope.pdf`.
Hackathon: NVIDIA × Nebius Build Week, Berlin (open models; sponsors: Nemotron on Nebius Token Factory, Tavily, Qwen, NVIDIA NIM).

- Repo: https://github.com/Arihant-Kumar-Jain/GreenLight_Research (public), branch `main`. Everything is merged; no
  open branches or PRs (`feat/auth-deploy-landing` is fully merged).
- **Team split:** Arihant owns the backend (`backend/glr/**`). Sachit owns UI (`web/**`), deploy (`Dockerfile`,
  `docker-compose.yml`, `deploy/**`) and auth. Don't change backend logic from the UI side; report issues to Arihant.
- Local machine quirk: ROS sits on `PYTHONPATH` and breaks pytest. Always run `env -u PYTHONPATH make check`.

## 2. Live deployment

| | |
|---|---|
| URL | **https://glr.softkernel.dev** (live). `https://greenlightresearch.tech` has certs too, but get.tech's nameservers were still out of sync at last check, so it resolves only intermittently. |
| VM | Nebius Compute `ivory-parrot-instance-2` (id `computeinstance-e04bktm8gpd0g5mxg5`), project `default-project-eu-west2`, `cpu-d3` 4 vCPU / 16 GiB, Ubuntu 24.04, **static IP 213.239.172.224**, about $0.15/h. **Stop or delete it after the hackathon.** |
| SSH | `ssh -i ~/.ssh/nebius sachit@213.239.172.224` (key made this session, no passphrase) |
| App dir | `~/GreenLight_Research` (git checkout of main). `.env` there is chmod 600; never print it. |
| Deploy | `ssh -i ~/.ssh/nebius sachit@213.239.172.224 '~/update.sh'` (git pull + `docker compose --profile prod up -d --build` + prune). Kills runs in progress. |
| Stack | `docker compose --profile prod`: `app` (uvicorn, one worker on purpose since runs are in-process asyncio tasks, SQLite at volume `greenlight_research_glr_data:/data`, port 127.0.0.1:8100) + `caddy` (80/443, Let's Encrypt). |
| Deployed | `0fd97c2` |

**VM `.env` keys (names only):** NEBIUS_API_KEY, TAVILY_API_KEY, GOOGLE_CLIENT_ID, NVIDIA_API_KEY,
GLR_NIM_RERANK_HOSTED_URL, GLR_NIM_RERANK_MODEL, GLR_TAVILY_BUDGET, GLR_MAX_USD_PER_RUN, GLR_RESEARCH_ROUNDS,
GLR_MAX_SCOUTS, GLR_CONTEXT_BUDGET, GLR_PAPERS_TO_READ, GLR_PUBLIC_BASE_URL=https://greenlightresearch.tech,
GLR_CORS_ORIGINS, GLR_DOMAIN=greenlightresearch.tech, GLR_ALT_DOMAIN=glr.softkernel.dev, GLR_MAX_USD_PER_DAY=5,
GLR_MAX_RUNS_PER_DAY=20. No OpenRouter key, so all LLM calls go to Token Factory. GLR_ALLOWED_EMAILS is empty, so any
Google account can sign in, with spend limited by the daily caps.

**DNS**
- `glr.softkernel.dev`: Cloudflare, A `glr` → 213.239.172.224, still **proxied (orange)**. It works: Caddy got the
  cert through the proxy.
- `greenlightresearch.tech`: get.tech (OrderBox, NS `cont603385.*.orderbox-dns.com`), A `@` and `www` →
  213.239.172.224. If it's still flaky, re-save the records at get.tech.
- To change domains: update GLR_DOMAIN / GLR_ALT_DOMAIN / GLR_PUBLIC_BASE_URL / GLR_CORS_ORIGINS in the VM `.env`, then
  `sudo docker compose --profile prod up -d --force-recreate`.

**Google OAuth** (client "GreenLightWebApp"): JS origins are http://localhost, :5180, :8100,
https://greenlightresearch.tech, https://glr.softkernel.dev. Add `https://www.greenlightresearch.tech` if wanted.

**Gotchas hit this session**
- A host checkout with a strict umask produced an unreadable image → fixed in the Dockerfile (`chmod -R a+rX /app`).
- The app answers HEAD with 405. Uptime checks should GET `/api/health`.
- On a laptop, Chrome caches failed DNS lookups: `chrome://net-internals/#dns` → Clear host cache.
- NVIDIA retired `llama-3.2-nv-rerankqa-1b-v2`, `llama-nemotron-rerank-1b-v2` and `nemoretriever-500m-rerank-v2`
  (410 Gone). Only `nvidia/llama-nemotron-rerank-vl-1b-v2` works; it's set via the env overrides above.
  **Arihant: update the default in `backend/glr/config.py`.** The NVIDIA key (expires 2027-04-18) was pasted in chat;
  revoke it after the hackathon.

## 3. Built this session (all on main; details in docs/CHANGES.md)

- **Auth:** Google sign-in (`backend/glr/auth.py`, `web/src/auth.tsx`). Modes google / dev (loopback only) / off.
  Per-user projects (others get 404). Optional `GLR_ALLOWED_EMAILS`. Daily caps `GLR_MAX_USD_PER_DAY` and
  `GLR_MAX_RUNS_PER_DAY`. Tests in `backend/tests/test_guards.py`.
- **Deploy:** Dockerfile, docker-compose (Caddy, `GLR_ALT_DOMAIN`), `deploy/Caddyfile`, `deploy/backup.sh` (SQLite
  → Nebius Object Storage, not yet scheduled), `deploy/nebius.md`.
- **UI revamp:** light "ink on paper" theme (`index.css` tokens; Newsreader + Atkinson Hyperlegible Next). Landing page
  at `#/` (`Landing.tsx`, copy strictly from the scope PDF) with the scroll-driven 3D specimen `three/Specimen.tsx`
  (helix → sources sphere → cited page → trust histogram → citation network → traffic light). App home at `#/app`.
  Workspace 3D scenes converted to light. Landing nav: Sign in with Google; "Start researching" opens a sign-in dialog
  when signed out.
- **Intake:** all follow-up questions stay until each one is answered (pick or type), sent together. "Other" focuses
  the text field. Inline Start card (narrow screens had no Start button).
- **Metrics:** `web/src/research.ts`. Research numbers (papers, relevant, read, scored, passages, searches, findings)
  instead of LLM calls, tokens and $ in the Agents view, the Overview and chat. Relevance tiers are relative to the
  best paper (the NIM scale is low). Low-confidence credibility shows as `~26/100` in grey.
- **Fixes:** Markdown renderer infinite loop on **bold** (froze the Report tab; present since v0.1). Verdict text
  rewrites internal evidence codes (F#/G#/N#) for reading.

## 4. Evaluation of a real run (live, project "Federated Sepsis Prediction", id `cec12a0b9871`)

Topic: federated learning, Transformer + FedProx, 6-hour Sepsis-3 prediction, eICU-CRD → MIMIC-IV held-out hospital.
Result: **AMBER**, 3/3 Speaker votes, confidence 0.68, 162 papers, 80 scored, novelty score 0/100 (every component
covered somewhere, no single paper covers all core ones).

**Good**
- The intake questions were sharp (architecture, FL algorithm, outcome definition, datasets, baselines). The brief was
  well formed.
- Retrieval found the right closest work (P12: federated temporal transformer, 6 h, MIMIC-IV/eICU, AUC 0.956;
  P32 leakage-aware FL sepsis). The reranker order was correct.
- The verdict was specific and actionable: a clean ablation design, a μ grid, P12 as the bar, the right primary endpoint.
- Novelty cells for P12 carry verified quotes; FedProx vs FoMAML was correctly marked partial.

**Problems (mostly backend → Arihant)**
1. **Citation checker too strict / blind:** 0 supported, 12 partial, 4 unsupported out of 16. It can't see full-text
   passages (it flagged FoMAML "not in passages" although the novelty step verified that exact quote), it judges
   metadata claims ("credibility 26/100") and absence claims ("no study isolates FedProx") as unsupported, and one
   "why" didn't match its claim (sentence splitting).
2. **Novelty mapper generous:** C4 "external validation on a held-out hospital" was marked full from a quote that only
   says "evaluated on MIMIC-IV and eICU".
3. **Auditor trigger-happy:** 5/5 audited papers flagged. P32 "no_baselines" contradicts its own quote (it lists
   three baselines); P12 "possible_leakage" was based on a section title. The quote check proves the quote exists, not
   that the flag follows.
4. **Reranker scale:** NIM vl probabilities are low (the best paper scored 0.42, clear matches 0.1-0.2). Run the Proof
   eval to write `data/eval/calibration.json` (none yet, so the evidence gate is off), and check that the triage
   thresholds aren't fixed at the old scale.
5. Intake offered a flawed option ("MIMIC-III + MIMIC-IV for training": same hospital, overlapping patients).
6. Landing lists PubMed / Europe PMC / medRxiv / ClinicalTrials / Cochrane / WHO-FDA-EMA (from the scope), but the
   scouts don't search them yet. Decide: build them or mark them "coming".

## 5. Open TODO (UI side, by priority)

- Verify on the live site that the Report tab now loads for `cec12a0b9871` (the fix is deployed; not re-checked after
  deploy because the browser tab was frozen).
- The verdict screen and the 3D views (galaxy, graph, chamber) weren't visually re-checked after the light conversion
  with this real project.
- The intake user bubble repeats full questions (wordy). Show "Q → answer" compactly (keep sending the full text).
- The last intake message ("Let me confirm the brief…") dangles; the inline Start card now follows it.
- Mobile was never tested on a device (the browser couldn't resize). Nav hides the wordmark below `sm`.
- Unanswered decisions: should the Proof page (`GET /api/evals`) be public? Landing source wording (see 4.6).
- README still describes the old dark landing; one Vite warning (PaperGraph static and dynamic import).
- `deploy/backup.sh` isn't on a cron yet (needs an Object Storage bucket and access key).

## 6. How to work

- Local: `make dev` → UI :5180, API :8100 (`.env` has GOOGLE_CLIENT_ID, so local is in google mode; empty it for dev
  mode).
- To test UI flows without Google: copy `backend/glr` plus a minimal `.env` (no GOOGLE_CLIENT_ID) into the scratchpad
  and run uvicorn on 8102 plus `GLR_API=http://localhost:8102 npx vite --port 5181`. Delete the copy after (it holds keys).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Add an entry to `docs/CHANGES.md` for
  meaningful changes. Run `env -u PYTHONPATH make check` before pushing.
